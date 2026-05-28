"""
SAP MB51 flat-file parser.

We handle the pipe-delimited ALV export produced by SAP transaction MB51
(Material Document List). This is what sustainability teams typically get
from their SAP admin: a pipe-delimited TXT export from SE16/MB51 with
SAP technical field names as headers. German SAP installations use German
column names; we normalise both variants.

Format decisions:
- Delimiter: pipe (|). SAP can export tab or pipe; pipe is safer because
  material descriptions sometimes contain tabs.
- Encoding: try UTF-8 first, fall back to latin-1 (Windows SAP clients).
- Dates: SAP stores as YYYYMMDD internally; some exports render as DD.MM.YYYY
  depending on user locale. We handle both.
- Units: SAP internal codes (L, KG, TO, GAL, GL, M3, NM3, KWH, MWH).
  We map these to canonical units.
- Movement types: we only ingest fuel-relevant movements (201, 261, 551)
  and procurement receipts (101, 501). Other movements are skipped.
"""

import csv
import io
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Iterator

# SAP internal unit → (canonical_unit, multiplier_to_canonical)
UNIT_MAP = {
    "L": ("liters", Decimal("1")),
    "LTR": ("liters", Decimal("1")),
    "KL": ("liters", Decimal("1000")),        # kiloliter
    "GAL": ("liters", Decimal("3.78541")),    # US gallon
    "GL": ("liters", Decimal("3.78541")),     # SAP alias for US gallon
    "M3": ("liters", Decimal("1000")),        # cubic meter
    "NM3": ("m3_gas", Decimal("1")),          # normal m3 of gas (keep separate — needs calorific conversion)
    "KG": ("kg", Decimal("1")),
    "G": ("kg", Decimal("0.001")),
    "TO": ("kg", Decimal("1000")),            # metric tonne
    "T": ("kg", Decimal("1000")),
    "LB": ("kg", Decimal("0.453592")),
    "KWH": ("kwh", Decimal("1")),
    "MWH": ("kwh", Decimal("1000")),
    "GJ": ("kwh", Decimal("277.778")),
    "TJ": ("kwh", Decimal("277778")),
}

# Movement types that represent fuel/energy consumption → Scope 1
FUEL_MOVEMENTS = {"201", "261", "551", "201X", "261X"}
# Goods receipts for procurement → Scope 3
PROCUREMENT_MOVEMENTS = {"101", "501"}

# Plant code → human-readable location (extend per real client)
PLANT_LOOKUP = {
    "1001": "Hamburg Plant, Germany",
    "1002": "Rotterdam Terminal, Netherlands",
    "2001": "Houston Refinery, USA",
    "2002": "Singapore Operations, Singapore",
    "3001": "London Office, UK",
    "3002": "Mumbai Office, India",
}

# Material number prefix → category hint (crude heuristic; real impl uses
# material master data from a separate lookup table)
MATERIAL_CATEGORY_HINTS = {
    "DIESEL": "fuel_combustion",
    "PETROL": "fuel_combustion",
    "BENZIN": "fuel_combustion",    # German
    "HFO": "fuel_combustion",
    "LPG": "fuel_combustion",
    "NATGAS": "fuel_combustion",
    "NAT_GAS": "fuel_combustion",
    "ERDGAS": "fuel_combustion",    # German
    "KOHLE": "fuel_combustion",     # German coal
    "COAL": "fuel_combustion",
}

# Canonical German→English SAP column name mapping
COLUMN_ALIASES = {
    "MBLNR": "MBLNR",               # material document number
    "MATBEL": "MBLNR",
    "ZEILE": "ZEILE",                # line item
    "POZZ": "ZEILE",
    "BUDAT": "BUDAT",                # posting date
    "BUCHUNGSDATUM": "BUDAT",
    "BLDAT": "BLDAT",                # document date
    "BELEGDATUM": "BLDAT",
    "BWART": "BWART",                # movement type
    "BEWEGUNGSART": "BWART",
    "WERKS": "WERKS",                # plant
    "WERK": "WERKS",
    "LGORT": "LGORT",                # storage location
    "MATNR": "MATNR",                # material number
    "MATERIALNUMMER": "MATNR",
    "MAKTX": "MAKTX",                # material description
    "MATERIALKURZTEXT": "MAKTX",
    "MENGE": "MENGE",                # quantity
    "BUCHUNGSMENGE": "MENGE",
    "MEINS": "MEINS",                # base unit of measure
    "BASISMENGENEINHEIT": "MEINS",
    "DMBTR": "DMBTR",                # amount in local currency
    "BETRAG": "DMBTR",
    "WAERS": "WAERS",                # currency
    "WAEHRUNG": "WAERS",
    "KOSTL": "KOSTL",                # cost center
    "KOSTENSTELLE": "KOSTL",
    "AUFNR": "AUFNR",                # order number
    "LIFNR": "LIFNR",                # vendor number
}


def _parse_date(s: str):
    s = s.strip()
    for fmt in ("%Y%m%d", "%d.%m.%Y", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def _parse_decimal(s: str):
    # SAP sometimes uses comma as decimal separator (German locale)
    s = s.strip().replace(",", ".")
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def _normalise_headers(raw_headers: list[str]) -> dict[str, int]:
    """Return {canonical_name: column_index} mapping."""
    mapping = {}
    for i, h in enumerate(raw_headers):
        key = h.strip().upper()
        canonical = COLUMN_ALIASES.get(key)
        if canonical:
            mapping[canonical] = i
    return mapping


def _infer_category(matnr: str, maktx: str, bwart: str) -> str:
    text = f"{matnr} {maktx}".upper()
    for prefix, cat in MATERIAL_CATEGORY_HINTS.items():
        if prefix in text:
            return cat
    if bwart in PROCUREMENT_MOVEMENTS:
        return "procurement"
    return "fuel_combustion"  # safe default for goods-issue movements


def parse(file_bytes: bytes) -> Iterator[dict]:
    """
    Yield one dict per valid SAP row. Each dict has these keys:
      mblnr, budat, bwart, werks, matnr, maktx, menge, meins,
      dmbtr, waers, kostl, aufnr, lifnr, _row_index, _parse_error
    """
    # Try UTF-8, fall back to latin-1 (Windows SAP client exports)
    try:
        text = file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        text = file_bytes.decode("latin-1")

    # Strip BOM if present
    text = text.lstrip("﻿")

    reader = csv.reader(io.StringIO(text), delimiter="|")
    rows = list(reader)

    if not rows:
        return

    # Find the header row — it's the first row that contains a recognised SAP field
    header_idx = None
    col_map = {}
    for i, row in enumerate(rows):
        col_map = _normalise_headers(row)
        if "MBLNR" in col_map or "BWART" in col_map or "MENGE" in col_map:
            header_idx = i
            break

    if header_idx is None:
        yield {"_row_index": 0, "_parse_error": "Could not locate SAP header row"}
        return

    for row_i, row in enumerate(rows[header_idx + 1:], start=header_idx + 1):
        if not any(c.strip() for c in row):
            continue  # skip blank lines

        def get(col, default=""):
            idx = col_map.get(col)
            if idx is None or idx >= len(row):
                return default
            return row[idx].strip()

        bwart = get("BWART")
        if bwart not in FUEL_MOVEMENTS and bwart not in PROCUREMENT_MOVEMENTS:
            # Skip non-relevant movements (transfers, reversals, etc.)
            continue

        budat_str = get("BUDAT") or get("BLDAT")
        budat = _parse_date(budat_str)
        menge_str = get("MENGE")
        menge = _parse_decimal(menge_str)
        meins = get("MEINS").upper()
        matnr = get("MATNR")
        maktx = get("MAKTX")
        werks = get("WERKS")

        errors = []
        if budat is None:
            errors.append(f"unparseable date '{budat_str}'")
        if menge is None:
            errors.append(f"unparseable quantity '{menge_str}'")
        if meins not in UNIT_MAP:
            errors.append(f"unknown unit '{meins}'")

        location = PLANT_LOOKUP.get(werks, werks or "Unknown plant")
        category = _infer_category(matnr, maktx, bwart)

        yield {
            "_row_index": row_i,
            "_parse_error": "; ".join(errors),
            "mblnr": get("MBLNR"),
            "budat": budat,
            "bwart": bwart,
            "werks": werks,
            "location": location,
            "matnr": matnr,
            "maktx": maktx or matnr,
            "menge": menge,
            "meins": meins,
            "dmbtr": _parse_decimal(get("DMBTR")),
            "waers": get("WAERS"),
            "kostl": get("KOSTL"),
            "aufnr": get("AUFNR"),
            "lifnr": get("LIFNR"),
            "category": category,
        }
