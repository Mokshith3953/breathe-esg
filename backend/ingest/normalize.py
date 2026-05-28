"""
Converts parsed rows into ActivityRecord instances.

Each source type has its own normalizer function. All of them return
(activity_record_kwargs, anomaly_list). The caller creates the DB records.
"""

from datetime import date
from decimal import Decimal
from typing import Optional

from .parsers.sap import UNIT_MAP as SAP_UNIT_MAP
from .parsers.utility import UNIT_MAP as UTILITY_UNIT_MAP


def _scope_for_sap_category(category: str) -> int:
    return 1 if category == "fuel_combustion" else 3


def normalise_sap(parsed: dict, tenant_id: int, raw_record_id: int) -> tuple[dict, list[dict]]:
    """
    Map a parsed SAP row to ActivityRecord kwargs + list of anomaly dicts.
    Anomaly dict keys: anomaly_type, severity, message, detail
    """
    anomalies = []

    if parsed.get("_parse_error"):
        for err in parsed["_parse_error"].split("; "):
            if err:
                anomalies.append({
                    "anomaly_type": "parse_error",
                    "severity": "high",
                    "message": err,
                    "detail": {"raw": parsed},
                })

    menge: Optional[Decimal] = parsed.get("menge")
    meins: str = (parsed.get("meins") or "").upper()
    budat = parsed.get("budat")
    category = parsed.get("category", "fuel_combustion")

    if menge is not None and menge <= 0:
        anomalies.append({
            "anomaly_type": "zero_qty",
            "severity": "medium",
            "message": f"Quantity is {menge} {meins} — zero or negative",
            "detail": {"mblnr": parsed.get("mblnr"), "menge": str(menge)},
        })

    # Normalise unit
    unit_entry = SAP_UNIT_MAP.get(meins)
    if unit_entry:
        norm_unit, multiplier = unit_entry
        norm_value = (menge * multiplier).quantize(Decimal("0.000001")) if menge else Decimal("0")
    else:
        norm_unit = meins.lower() or "unknown"
        norm_value = menge or Decimal("0")
        if meins:
            anomalies.append({
                "anomaly_type": "unknown_unit",
                "severity": "medium",
                "message": f"SAP unit '{meins}' not in conversion table — stored as-is",
                "detail": {"meins": meins, "mblnr": parsed.get("mblnr")},
            })

    period_start = budat or date.today()
    period_end = budat or date.today()

    extra = {
        "mblnr": parsed.get("mblnr", ""),
        "bwart": parsed.get("bwart", ""),
        "werks": parsed.get("werks", ""),
        "kostl": parsed.get("kostl", ""),
        "aufnr": parsed.get("aufnr", ""),
        "lifnr": parsed.get("lifnr", ""),
        "dmbtr": str(parsed.get("dmbtr", "")),
        "waers": parsed.get("waers", ""),
    }

    kwargs = {
        "raw_record_id": raw_record_id,
        "tenant_id": tenant_id,
        "scope": _scope_for_sap_category(category),
        "category": category,
        "period_start": period_start,
        "period_end": period_end,
        "quantity_value": menge or Decimal("0"),
        "quantity_unit": meins,
        "normalized_value": norm_value,
        "normalized_unit": norm_unit,
        "location": parsed.get("location", ""),
        "vendor": parsed.get("lifnr", ""),
        "description": parsed.get("maktx", ""),
        "extra": extra,
        "status": "pending",
    }

    return kwargs, anomalies


def normalise_utility(parsed: dict, tenant_id: int, raw_record_id: int) -> tuple[dict, list[dict]]:
    anomalies = []

    if parsed.get("_parse_error"):
        for err in parsed["_parse_error"].split("; "):
            if err:
                anomalies.append({
                    "anomaly_type": "parse_error",
                    "severity": "high",
                    "message": err,
                    "detail": {"raw": {k: str(v) for k, v in parsed.items()}},
                })

    usage: Optional[Decimal] = parsed.get("usage_value")
    unit: str = (parsed.get("usage_unit") or "KWH").upper()

    if usage is not None and usage <= 0:
        anomalies.append({
            "anomaly_type": "zero_qty",
            "severity": "medium",
            "message": f"Usage is {usage} {unit} — zero or negative",
            "detail": {"account": parsed.get("account_number"), "usage": str(usage)},
        })

    unit_entry = UTILITY_UNIT_MAP.get(unit)
    if unit_entry:
        norm_unit, multiplier = unit_entry
        norm_value = (usage * multiplier).quantize(Decimal("0.000001")) if usage else Decimal("0")
    else:
        norm_unit = unit.lower()
        norm_value = usage or Decimal("0")
        anomalies.append({
            "anomaly_type": "unknown_unit",
            "severity": "medium",
            "message": f"Utility unit '{unit}' not recognised — stored as-is",
            "detail": {"unit": unit},
        })

    period_start = parsed.get("period_start") or date.today()
    period_end = parsed.get("period_end") or period_start

    extra = {
        "account_number": parsed.get("account_number", ""),
        "meter_number": parsed.get("meter_number", ""),
        "rate_schedule": parsed.get("rate_schedule", ""),
        "peak_demand_kw": str(parsed.get("peak_demand_kw", "")),
        "total_charges": str(parsed.get("total_charges", "")),
        "read_type": parsed.get("read_type", ""),
        "power_factor": str(parsed.get("power_factor", "")),
    }

    kwargs = {
        "raw_record_id": raw_record_id,
        "tenant_id": tenant_id,
        "scope": 2,
        "category": "electricity",
        "period_start": period_start,
        "period_end": period_end,
        "quantity_value": usage or Decimal("0"),
        "quantity_unit": unit,
        "normalized_value": norm_value,
        "normalized_unit": norm_unit,
        "location": parsed.get("service_address", ""),
        "vendor": "",  # utility name not always in the CSV
        "description": f"Meter {parsed.get('meter_number', '')} | {parsed.get('rate_schedule', '')}",
        "extra": extra,
        "status": "pending",
    }

    return kwargs, anomalies


def normalise_travel(parsed: dict, tenant_id: int, raw_record_id: int) -> tuple[dict, list[dict]]:
    anomalies = []

    if parsed.get("_parse_error"):
        for err in parsed["_parse_error"].split("; "):
            if err:
                anomalies.append({
                    "anomaly_type": "parse_error",
                    "severity": "high",
                    "message": err,
                    "detail": {"raw": {k: str(v) for k, v in parsed.items() if v is not None}},
                })

    category = parsed.get("category", "travel_air")
    distance_km: Optional[Decimal] = parsed.get("distance_km")
    nights: Optional[Decimal] = parsed.get("nights")
    travel_start = parsed.get("travel_start") or date.today()
    travel_end = parsed.get("travel_end") or travel_start

    # Determine canonical quantity
    if category == "travel_air":
        if distance_km is not None and distance_km > 0:
            qty_value = distance_km
            qty_unit = "km"
            norm_value = distance_km
            norm_unit = "km"
        else:
            # No distance — record with zero, flag it
            qty_value = Decimal("0")
            qty_unit = "km"
            norm_value = Decimal("0")
            norm_unit = "km"
            anomalies.append({
                "anomaly_type": "missing_field",
                "severity": "medium",
                "message": (
                    f"Air segment {parsed.get('origin', '?')}→{parsed.get('destination', '?')} "
                    "has no distance — needs great-circle calculation"
                ),
                "detail": {
                    "origin": parsed.get("origin", ""),
                    "destination": parsed.get("destination", ""),
                    "trip_id": parsed.get("trip_id", ""),
                },
            })
    elif category == "travel_hotel":
        if nights is not None and nights > 0:
            qty_value = nights
            qty_unit = "nights"
            norm_value = nights
            norm_unit = "nights"
        else:
            qty_value = Decimal("1")
            qty_unit = "nights"
            norm_value = Decimal("1")
            norm_unit = "nights"
            anomalies.append({
                "anomaly_type": "missing_field",
                "severity": "low",
                "message": "Hotel stay has no nights count — defaulting to 1",
                "detail": {"trip_id": parsed.get("trip_id", "")},
            })
    else:  # ground transport
        if distance_km is not None and distance_km > 0:
            qty_value = distance_km
            qty_unit = "km"
            norm_value = distance_km
            norm_unit = "km"
        else:
            # Ground transport without distance — use cost as proxy (flagged)
            qty_value = parsed.get("amount") or Decimal("0")
            qty_unit = parsed.get("currency") or "USD"
            norm_value = qty_value
            norm_unit = qty_unit
            anomalies.append({
                "anomaly_type": "missing_field",
                "severity": "low",
                "message": "Ground segment has no distance — cost recorded as proxy quantity",
                "detail": {"trip_id": parsed.get("trip_id", ""), "segment": parsed.get("segment_type", "")},
            })

    if qty_value <= 0:
        anomalies.append({
            "anomaly_type": "zero_qty",
            "severity": "low",
            "message": f"Travel segment quantity is {qty_value} — zero or negative",
            "detail": {"trip_id": parsed.get("trip_id", ""), "category": category},
        })

    extra = {
        "trip_id": parsed.get("trip_id", ""),
        "employee_id": parsed.get("employee_id", ""),
        "employee_name": parsed.get("employee_name", ""),
        "department": parsed.get("department", ""),
        "cost_center": parsed.get("cost_center", ""),
        "segment_type": parsed.get("segment_type", ""),
        "class_of_service": parsed.get("class_of_service", ""),
        "origin": parsed.get("origin", ""),
        "destination": parsed.get("destination", ""),
        "amount": str(parsed.get("amount", "")),
        "currency": parsed.get("currency", ""),
        "purpose": parsed.get("purpose", ""),
        "project_code": parsed.get("project_code", ""),
    }

    origin = parsed.get("origin", "")
    dest = parsed.get("destination", "")
    route_desc = f"{origin} → {dest}" if (origin or dest) else ""

    kwargs = {
        "raw_record_id": raw_record_id,
        "tenant_id": tenant_id,
        "scope": 3,
        "category": category,
        "period_start": travel_start,
        "period_end": travel_end,
        "quantity_value": qty_value,
        "quantity_unit": qty_unit,
        "normalized_value": norm_value,
        "normalized_unit": norm_unit,
        "location": parsed.get("employee_name", ""),
        "vendor": parsed.get("carrier", ""),
        "description": route_desc or parsed.get("carrier", ""),
        "extra": extra,
        "status": "pending",
    }

    return kwargs, anomalies
