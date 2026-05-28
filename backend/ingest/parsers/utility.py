"""
Utility electricity CSV parser.

We handle the portal CSV export format. This is the format most large
utilities expose when you click "Download Usage Data" from their customer
portal (PG&E, ConEd, Eversource, National Grid, etc.). The alternative
is Green Button XML (ESPI standard), which is more structured but requires
an XML parser and the format varies between utilities. Portal CSV is what
facilities teams actually use day-to-day.

Key challenges this parser handles:
- Billing periods that straddle month boundaries (e.g. 23-Mar to 19-Apr)
- Units that might be kWh or MWh depending on account tier
- Multiple meters per file (each has its own account/meter number)
- Missing demand columns on residential-class accounts
"""

import csv
import io
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Iterator

UNIT_MAP = {
    "KWH": ("kwh", Decimal("1")),
    "MWH": ("kwh", Decimal("1000")),
    "GJ": ("kwh", Decimal("277.778")),
    "THERM": ("kwh", Decimal("29.3001")),
}

COLUMN_ALIASES = {
    "ACCOUNT NUMBER": "account_number",
    "ACCOUNT_NUMBER": "account_number",
    "ACCOUNTNUMBER": "account_number",
    "ACCOUNT NO": "account_number",
    "SERVICE ADDRESS": "service_address",
    "SERVICE_ADDRESS": "service_address",
    "SERVICEADDRESS": "service_address",
    "LOCATION": "service_address",
    "METER NUMBER": "meter_number",
    "METER_NUMBER": "meter_number",
    "METERNUMBER": "meter_number",
    "METER NO": "meter_number",
    "BILLING PERIOD START": "period_start",
    "BILLING_PERIOD_START": "period_start",
    "START DATE": "period_start",
    "FROM DATE": "period_start",
    "READ DATE FROM": "period_start",
    "BILLING PERIOD END": "period_end",
    "BILLING_PERIOD_END": "period_end",
    "END DATE": "period_end",
    "THRU DATE": "period_end",
    "READ DATE TO": "period_end",
    "USAGE (KWH)": "usage_kwh",
    "USAGE(KWH)": "usage_kwh",
    "USAGE KWH": "usage_kwh",
    "KWH USED": "usage_kwh",
    "ELECTRIC USAGE (KWH)": "usage_kwh",
    "CONSUMPTION": "usage_kwh",
    "USAGE": "usage_kwh",
    "ENERGY USAGE": "usage_kwh",
    "USAGE (MWH)": "usage_mwh",
    "PEAK DEMAND (KW)": "peak_demand_kw",
    "PEAK_DEMAND_KW": "peak_demand_kw",
    "PEAK DEMAND": "peak_demand_kw",
    "DEMAND (KW)": "peak_demand_kw",
    "TOTAL CHARGES ($)": "total_charges",
    "TOTAL CHARGES": "total_charges",
    "AMOUNT DUE": "total_charges",
    "CHARGES": "total_charges",
    "RATE SCHEDULE": "rate_schedule",
    "RATE_SCHEDULE": "rate_schedule",
    "TARIFF": "rate_schedule",
    "RATE CODE": "rate_schedule",
    "METER READ TYPE": "read_type",
    "READ TYPE": "read_type",
    "POWER FACTOR (%)": "power_factor",
    "POWER FACTOR": "power_factor",
}


def _parse_date(s: str):
    s = s.strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%d/%m/%Y", "%d-%b-%Y", "%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def _parse_decimal(s: str):
    if not s:
        return None
    s = s.strip().replace(",", "").replace("$", "").replace("%", "")
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def _normalise_headers(raw_headers: list[str]) -> dict[str, int]:
    mapping = {}
    for i, h in enumerate(raw_headers):
        key = h.strip().upper()
        canonical = COLUMN_ALIASES.get(key)
        if canonical and canonical not in mapping:
            mapping[canonical] = i
    return mapping


def parse(file_bytes: bytes) -> Iterator[dict]:
    """
    Yield one dict per billing row with keys:
      account_number, service_address, meter_number,
      period_start, period_end,
      usage_value, usage_unit,
      peak_demand_kw, total_charges, rate_schedule,
      _row_index, _parse_error
    """
    try:
        text = file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = file_bytes.decode("latin-1")

    # Some portals wrap the file in metadata lines before the actual CSV
    # Find the first line that looks like a header
    lines = text.splitlines()
    start_idx = 0
    col_map = {}
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        # Try parsing as CSV and check for recognisable column names
        try:
            row = next(csv.reader([line]))
        except StopIteration:
            continue
        col_map = _normalise_headers(row)
        if "period_start" in col_map or "usage_kwh" in col_map or "account_number" in col_map:
            start_idx = i
            break

    data_lines = "\n".join(lines[start_idx:])
    reader = csv.DictReader(io.StringIO(data_lines))

    for row_i, raw_row in enumerate(reader, start=start_idx + 1):
        if not any(v.strip() for v in raw_row.values()):
            continue

        # Normalise keys
        row = {COLUMN_ALIASES.get(k.strip().upper(), k.strip().lower()): v for k, v in raw_row.items()}

        errors = []

        period_start = _parse_date(row.get("period_start", ""))
        period_end = _parse_date(row.get("period_end", ""))
        if not period_start:
            errors.append("missing/invalid period_start")
        if not period_end:
            errors.append("missing/invalid period_end")

        # Prefer kWh column; fall back to MWh column
        usage_raw = row.get("usage_kwh") or row.get("usage_mwh") or row.get("usage", "")
        usage = _parse_decimal(usage_raw)
        if usage is None:
            errors.append(f"unparseable usage '{usage_raw}'")

        # Determine original unit
        if row.get("usage_mwh") and not row.get("usage_kwh"):
            orig_unit = "MWH"
        else:
            orig_unit = "KWH"

        yield {
            "_row_index": row_i,
            "_parse_error": "; ".join(errors),
            "account_number": row.get("account_number", ""),
            "service_address": row.get("service_address", ""),
            "meter_number": row.get("meter_number", ""),
            "period_start": period_start,
            "period_end": period_end,
            "usage_value": usage,
            "usage_unit": orig_unit,
            "peak_demand_kw": _parse_decimal(row.get("peak_demand_kw", "")),
            "total_charges": _parse_decimal(row.get("total_charges", "")),
            "rate_schedule": row.get("rate_schedule", ""),
            "read_type": row.get("read_type", ""),
            "power_factor": _parse_decimal(row.get("power_factor", "")),
        }
