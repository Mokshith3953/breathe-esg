"""
Corporate travel CSV parser — Concur/Navan expense export format.

We handle the standard Concur Travel & Expense CSV export. This is what
you get from Concur Reports > Standard Reports > Trip Summary or from
the Navan admin export. Both produce similar flat CSVs; the main
difference is column naming. We handle both.

Why CSV export rather than API:
- Concur's REST API requires OAuth2 with company-level setup and
  partner certification. No enterprise client hands those credentials
  to a sustainability team without an IT ticket.
- Navan's API is similar. In practice, the travel manager downloads
  a CSV once per quarter for the sustainability report.
- CSV export is the actual workflow.

Segment types and their Scope 3 sub-categories:
  AIR   → travel_air   (Scope 3, Category 6)
  HOTEL → travel_hotel (Scope 3, Category 6)
  CAR   → travel_ground (Scope 3, Category 6; if rental)
  RAIL  → travel_ground
  BUS   → travel_ground
  TAXI  → travel_ground

Distance:
  Concur sometimes includes distance (km or miles). When it doesn't,
  we record the origin/destination pair and flag for downstream
  great-circle calculation. We do NOT silently drop those rows.
"""

import csv
import io
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Iterator

SEGMENT_TYPE_MAP = {
    "AIR": "travel_air",
    "FLIGHT": "travel_air",
    "AIRPLANE": "travel_air",
    "HOTEL": "travel_hotel",
    "LODGING": "travel_hotel",
    "ACCOMMODATION": "travel_hotel",
    "CAR": "travel_ground",
    "RENTAL CAR": "travel_ground",
    "CAR RENTAL": "travel_ground",
    "TAXI": "travel_ground",
    "UBER": "travel_ground",
    "LYFT": "travel_ground",
    "RIDESHARE": "travel_ground",
    "RAIL": "travel_ground",
    "TRAIN": "travel_ground",
    "BUS": "travel_ground",
    "GROUND": "travel_ground",
    "LIMO": "travel_ground",
}

COLUMN_ALIASES = {
    "TRIP ID": "trip_id",
    "TRIPID": "trip_id",
    "REPORT ID": "trip_id",
    "EMPLOYEE ID": "employee_id",
    "EMPLOYEEID": "employee_id",
    "EMPLOYEE NAME": "employee_name",
    "EMPLOYEENAME": "employee_name",
    "TRAVELER": "employee_name",
    "TRAVELER NAME": "employee_name",
    "DEPARTMENT": "department",
    "DEPT": "department",
    "COST CENTER": "cost_center",
    "COSTCENTER": "cost_center",
    "COST_CENTER": "cost_center",
    "BOOKING DATE": "booking_date",
    "BOOKED DATE": "booking_date",
    "TRAVEL START DATE": "travel_start",
    "TRAVEL DATE": "travel_start",
    "DEPARTURE DATE": "travel_start",
    "CHECK-IN DATE": "travel_start",
    "START DATE": "travel_start",
    "TRAVEL END DATE": "travel_end",
    "RETURN DATE": "travel_end",
    "CHECK-OUT DATE": "travel_end",
    "END DATE": "travel_end",
    "SEGMENT TYPE": "segment_type",
    "SEGMENTTYPE": "segment_type",
    "TRAVEL TYPE": "segment_type",
    "TYPE": "segment_type",
    "CATEGORY": "segment_type",
    "ORIGIN": "origin",
    "FROM": "origin",
    "DEPARTURE": "origin",
    "ORIGIN CITY": "origin",
    "FROM CITY": "origin",
    "DESTINATION": "destination",
    "TO": "destination",
    "ARRIVAL": "destination",
    "DESTINATION CITY": "destination",
    "TO CITY": "destination",
    "CARRIER": "carrier",
    "AIRLINE": "carrier",
    "VENDOR": "carrier",
    "HOTEL NAME": "carrier",
    "CAR COMPANY": "carrier",
    "CLASS OF SERVICE": "class_of_service",
    "CABIN CLASS": "class_of_service",
    "FARE CLASS": "class_of_service",
    "TRAVEL CLASS": "class_of_service",
    "DISTANCE (KM)": "distance_km",
    "DISTANCE KM": "distance_km",
    "DISTANCE": "distance_km",
    "DISTANCE (MI)": "distance_mi",
    "DURATION (NIGHTS)": "nights",
    "NIGHTS": "nights",
    "NO. NIGHTS": "nights",
    "AMOUNT": "amount",
    "COST": "amount",
    "TICKET COST": "amount",
    "TOTAL COST": "amount",
    "FARE": "amount",
    "CURRENCY": "currency",
    "PURPOSE": "purpose",
    "TRIP PURPOSE": "purpose",
    "PROJECT CODE": "project_code",
}


def _parse_date(s: str):
    s = s.strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%d/%m/%Y", "%d-%b-%Y", "%d %b %Y", "%b %d %Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def _parse_decimal(s: str):
    if not s:
        return None
    s = s.strip().replace(",", "").replace("$", "").replace("€", "").replace("£", "")
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
    Yield one dict per travel segment row. Keys:
      trip_id, employee_id, employee_name, department, cost_center,
      booking_date, travel_start, travel_end,
      segment_type (raw), category (canonical),
      origin, destination, carrier, class_of_service,
      distance_km (may be None), nights (for hotels),
      amount, currency, purpose, project_code,
      _row_index, _parse_error
    """
    try:
        text = file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = file_bytes.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))

    for row_i, raw_row in enumerate(reader, start=2):  # 1-indexed, row 1 is header
        if not any(v.strip() for v in raw_row.values()):
            continue

        row = {COLUMN_ALIASES.get(k.strip().upper(), k.strip().lower()): (v or "").strip()
               for k, v in raw_row.items() if k is not None}

        errors = []

        travel_start = _parse_date(row.get("travel_start", ""))
        if not travel_start:
            errors.append("missing/invalid travel_start")

        travel_end = _parse_date(row.get("travel_end", "")) or travel_start

        raw_segment = row.get("segment_type", "").strip().upper()
        category = SEGMENT_TYPE_MAP.get(raw_segment)
        if not category:
            errors.append(f"unknown segment type '{raw_segment}'")
            category = "travel_air"  # default to keep the row

        # Distance handling
        distance_km = None
        dist_raw = row.get("distance_km", "")
        dist_mi_raw = row.get("distance_mi", "")
        if dist_raw:
            distance_km = _parse_decimal(dist_raw)
        elif dist_mi_raw:
            d_mi = _parse_decimal(dist_mi_raw)
            if d_mi is not None:
                distance_km = (d_mi * Decimal("1.60934")).quantize(Decimal("0.01"))

        # For air travel without distance, flag but keep row (distance will need
        # to be computed from airport codes downstream)
        if category == "travel_air" and distance_km is None:
            if not row.get("origin") or not row.get("destination"):
                errors.append("air segment missing distance and origin/destination")

        nights = _parse_decimal(row.get("nights", ""))

        yield {
            "_row_index": row_i,
            "_parse_error": "; ".join(errors),
            "trip_id": row.get("trip_id", ""),
            "employee_id": row.get("employee_id", ""),
            "employee_name": row.get("employee_name", ""),
            "department": row.get("department", ""),
            "cost_center": row.get("cost_center", ""),
            "booking_date": _parse_date(row.get("booking_date", "")),
            "travel_start": travel_start,
            "travel_end": travel_end,
            "segment_type": raw_segment,
            "category": category,
            "origin": row.get("origin", ""),
            "destination": row.get("destination", ""),
            "carrier": row.get("carrier", ""),
            "class_of_service": row.get("class_of_service", ""),
            "distance_km": distance_km,
            "nights": nights,
            "amount": _parse_decimal(row.get("amount", "")),
            "currency": row.get("currency", ""),
            "purpose": row.get("purpose", ""),
            "project_code": row.get("project_code", ""),
        }
