# Tradeoffs — Three Things I Deliberately Did Not Build

## 1. Emission factor tables and CO₂e calculation

**What it would be:** A table of emission factors (kg CO₂e per unit of activity) for each category — DEFRA factors for UK electricity, EPA factors for US fuel combustion, ICAO/DEFRA factors for air travel by class, etc. The normalised quantity would be multiplied by the appropriate factor to produce a CO₂e estimate on each record.

**Why I didn't build it:** Emission factor selection is a methodology choice, not a data ingestion choice, and it's contentious. Market-based vs location-based for Scope 2 electricity (they produce different numbers and clients often need both). Whether to apply a radiative forcing multiplier for air travel. Which year's DEFRA tables to use. These decisions belong to the emissions calculation layer, not the ingestion layer. Building a factor table now would either (a) hardcode methodology choices the client hasn't made, or (b) require a whole separate configuration UI for factor management.

The data model is correct — `normalized_value` and `normalized_unit` are the inputs to whatever emission factor calculation runs downstream. Adding the calculation layer is a well-defined next step with a clear interface.

---

## 2. Real-time / streaming ingestion

**What it would be:** A polling or webhook-based mechanism to pull data automatically from SAP OData services, utility APIs (Green Button / Share My Data), or the Concur/Navan REST APIs on a schedule, rather than requiring a manual file upload.

**Why I didn't build it:** Each integration would require client-side setup (OAuth credentials, API keys, SAP connectivity), which can't be prototyped without actual client credentials. More importantly, the assignment is 4 days and the hard part is the data model, normalisation, and review workflow — not the HTTP transport. The file upload mechanism is a placeholder that a polling job could replace without any model changes. The `IngestionRun` model already has the shape needed for a scheduled pull (just replace the `uploaded_by` FK with a `triggered_by` enum).

Building fake API clients would have produced demo code that looks impressive but can't be maintained or tested.

---

## 3. A proper user and permissions system

**What it would be:** Role-based access control with at least three roles: Analyst (can review and approve), Admin (can manage data sources and users), Auditor (read-only, can see approved records but not pending ones). TenantMembership table linking users to tenants with roles. The audit trail records which analyst approved which record, with their specific role at the time of approval.

**Why I didn't build it:** The current prototype has a single analyst user per tenant and the review workflow works correctly for that case. Adding roles requires a permissions framework (Django's built-in groups system or a custom RBAC layer), role-checking on every view, and UI for user management — that's a week of work that produces boilerplate code rather than insight about the emissions data problem.

What I did build: the auth layer is correct (token auth, every endpoint requires authentication, audit events record the actor). Adding roles is a matter of adding the `TenantMembership` table and replacing `IsAuthenticated` with custom permission classes. The shape is right; the RBAC detail is scope-appropriate to skip.
