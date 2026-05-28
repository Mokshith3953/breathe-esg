# Data Model

## Overview

The model has to solve four problems simultaneously: multi-tenancy, source traceability, unit normalisation across incompatible source formats, and a review workflow with an immutable audit trail. Every design decision below is downstream of one of those four requirements.

---

## Entities

### Tenant
One row per client company. Every record in the system is scoped to a tenant. This is the root of the multi-tenancy design.

Why a hard tenant scoping rather than row-level security? Because emissions data is inherently company-confidential and auditor-sensitive. A misconfigured query that leaks one client's data to another is a material compliance failure. Hard foreign keys on every record make that leak impossible at the query level without a deliberate `tenant=None` escape.

### DataSource
A named origin within a tenant. A single tenant might have a Hamburg SAP instance and a Singapore SAP instance — these are separate DataSources of the same type, producing separate IngestionRuns. This matters because:
- Different plants may use different units (L vs GAL)
- Different sources have different data quality histories
- Analysts often need to review one site's data independently

```python
DataSource
  tenant         FK → Tenant
  source_type    enum: SAP | UTILITY | TRAVEL
  name           "Hamburg Plant SAP"
  config         JSONField  # site-specific config (plant codes, meter IDs)
```

### IngestionRun
One file upload = one IngestionRun. This is the atomic unit of ingestion. Storing it separately from the records it produced lets us:
- Reprocess a file without duplicating records
- Show upload history with parse statistics
- Detect re-upload of the same file via SHA-256 hash

The `file_hash` field is a SHA-256 of the raw file bytes. We warn (not block) on re-upload — the analyst may be intentionally correcting a previous upload.

```python
IngestionRun
  data_source      FK → DataSource
  uploaded_by      FK → User (null if seeded)
  uploaded_at      DateTimeField
  original_filename
  file_hash        SHA-256, 64 chars
  status           pending | processing | done | failed
  rows_parsed      int
  rows_errored     int
  error_log        JSONField: [{row, message}]
```

### RawRecord
One row from the source file, stored verbatim as a JSON blob. This is the non-negotiable source-of-truth requirement: auditors need to see what came in, unmodified, even if the normalised version was edited later.

The `OneToOneField` from ActivityRecord → RawRecord uses `on_delete=PROTECT`, which prevents anyone from deleting a raw record that has been normalised. This is intentional and irreversible by design.

```python
RawRecord
  run          FK → IngestionRun
  row_index    int  # 0-based row number in the source file
  raw_data     JSONField  # original parsed row, all values as strings
  parse_error  TextField  # empty if parsed cleanly
```

### ActivityRecord
The normalised, canonical emission-activity record. This is the unit analysts review and auditors sign off on.

**Why two quantity fields?**

```python
quantity_value / quantity_unit    # exactly as it came out of the source
normalized_value / normalized_unit  # converted to canonical unit
```

Consider an SAP row that says `4500 GAL`. The normalised form is `17033.35 liters`. Storing both means:
1. Analysts can spot conversion errors ("that doesn't look right for 4500 gallons")
2. The audit trail preserves what the original system said
3. If our conversion factor is wrong, we can recompute without re-uploading

**Scope and category**

```
Scope 1: fuel_combustion           (direct combustion — SAP goods issues of fuel materials)
Scope 2: electricity               (purchased electricity — utility data)
Scope 3: travel_air, travel_hotel, travel_ground  (business travel — Concur/Navan)
Scope 3: procurement               (purchased goods — SAP goods receipts)
```

Scope assignment is deterministic from source type + category:
- SAP movement types 201/261 on fuel materials → Scope 1
- SAP movement types 101/501 → Scope 3 (procurement)
- All utility data → Scope 2
- All travel data → Scope 3

**Period fields**

`period_start` / `period_end` rather than a single month/year field. This is necessary because:
- Utility billing periods straddle calendar months (e.g. Dec 23 – Jan 24)
- SAP posting dates are point-in-time, not periods; we set start=end=posting date
- Travel segments span multiple days; we store travel_start/travel_end

**Extra field**

`extra: JSONField` preserves source-specific fields that don't have a canonical column: SAP cost center, order number, Concur trip ID, utility tariff code. These are not indexed or filtered on, but they're available to analysts who need to trace a record back to its source system.

**Review workflow**

```
pending → approved (analyst signs off, goes to auditors)
pending → flagged  (needs investigation)
pending → rejected (excluded from reporting)
flagged → approved | rejected
```

Status is set at ingestion to `pending` (or `flagged` if anomalies were detected). Only an analyst can move to `approved`. Once `approved`, a record is locked for audit purposes — we don't prevent edits in the current prototype but the audit trail makes any change visible.

```python
ActivityRecord
  raw_record       OneToOneField → RawRecord (PROTECT)
  tenant           FK → Tenant
  scope            int: 1 | 2 | 3
  category         enum (6 values)
  period_start     DateField
  period_end       DateField
  quantity_value   Decimal(20,6)
  quantity_unit    CharField  # original unit
  normalized_value Decimal(20,6)
  normalized_unit  CharField  # canonical unit
  location         CharField  # plant / meter address / employee name
  vendor           CharField  # utility / airline / supplier
  description      TextField
  extra            JSONField  # source-specific preserved fields
  status           pending | approved | rejected | flagged
  review_note      TextField
  reviewed_by      FK → User (null)
  reviewed_at      DateTimeField (null)
  is_edited        BooleanField  # true if modified post-ingestion
```

### AuditEvent
Append-only log. Never updated, never deleted. One row per state change.

For edits (currently not fully exposed in the UI but modelled), `diff` contains `{field: {before: x, after: y}}`. This lets you reconstruct the full history of a record without a separate versioning table.

```python
AuditEvent
  record     FK → ActivityRecord
  event      ingested | approved | rejected | flagged | edited | note_added
  actor      FK → User (null for system events)
  timestamp  DateTimeField(auto_now_add=True)
  diff       JSONField  # {field: {before, after}} for edits
```

### Anomaly
Something the parser or normaliser found suspicious. Linked to both the IngestionRun (so you can see all issues from one upload) and optionally to the specific RawRecord and ActivityRecord.

Anomalies don't block ingestion — a row with an anomaly still produces an ActivityRecord, but its status is set to `flagged`. The analyst decides whether to approve, reject, or investigate.

```python
Anomaly
  run              FK → IngestionRun
  raw_record       FK → RawRecord (null)
  activity_record  FK → ActivityRecord (null)
  anomaly_type     missing_field | unknown_unit | zero_qty | outlier | duplicate | parse_error | unknown_code
  severity         low | medium | high
  message          TextField
  detail           JSONField  # structured data for the specific anomaly type
  resolved         BooleanField
```

---

## Multi-tenancy

Every `ActivityRecord`, `Anomaly`, and query is scoped through `Tenant`. The views layer calls `_get_tenant(request)` on every request and filters all querysets by the returned tenant. There is no global list or cross-tenant query in any view.

In the current prototype, all demo data belongs to `acme-corp` and the demo user implicitly maps to that tenant via a fallback to `Tenant.objects.first()`. In production this would be a proper `TenantMembership` table with roles (analyst, admin, auditor-read-only).

---

## What this model deliberately does not do

- **No emission factors or CO₂e calculations.** That's a separate concern (factor tables, GWP values, methodology choices like market-based vs location-based for Scope 2). The normalised quantity is the input to that layer; we don't mix it here.
- **No versioned record history beyond audit events.** Edits are flagged via `is_edited` and recorded in `AuditEvent.diff`. Full row-level versioning (django-simple-history style) would be the next step for a production system.
- **No file storage.** Raw file bytes are not retained after parsing. The `RawRecord` JSON representation is the persistence layer. Retaining files would require object storage and isn't necessary for the prototype.
