# Decisions

Every ambiguity I resolved, what I chose, and why.

---

## SAP: Which export format?

**Options researched:** IDoc (XML-like segment format used for system-to-system EDI), BAPI (function call returning structured data), OData service (RESTful, used in S/4HANA), flat file ALV export via SE16/MB51 transaction.

**Chose:** Flat file (pipe-delimited) from MB51.

**Why:** The assignment says sustainability teams pull this data. In practice, sustainability coordinators are not SAP BASIS consultants. They run MB51 (Material Document List), click "Download", and get a pipe-delimited TXT file. That's the actual workflow.

IDoc is used for SAP-to-SAP integration and requires a receiving system configured as an IDoc partner. BAPIs require API access and a developer. OData is available in S/4HANA (post-2015) but not all clients have migrated. The flat file is what lands in someone's Downloads folder.

**What I ignored:** IDocs entirely. BAPI/OData — valid for a real integration but overkill for what a sustainability team actually hands over.

**What would break in production:** A client with S/4HANA and an integration team would prefer the OData approach because it's pull-on-demand and doesn't require a manual export step. We'd need to negotiate which transaction and export format their SAP admin uses.

---

## SAP: Which movement types?

**201** — Goods issue to cost center (fuel drawn from tank to a department)
**261** — Goods issue to production order (fuel consumed in production)
**551** — Scrapping/waste disposal
**101** — Goods receipt (procurement, for Scope 3)
**501** — Receipt without purchase order

I skip transfers (311, 312), returns (262), and reversals (anything with an X suffix like 201X) because they're not net consumption — they're movements between locations or corrections of previous postings. Including them would double-count.

**What I'd ask the PM:** Does the client use any non-standard movement types for fuel consumption? Some plants have custom Z-movements (e.g. Z201 for tracked vehicle fuel). Those would need adding to the filter list.

---

## SAP: German vs English column names

SAP exports in the language of the user's system locale. A German SAP installation will have "Buchungsdatum" instead of "BUDAT". I handle this with a bidirectional alias map. The canonical names are SAP's internal field names (BUDAT, WERKS, MENGE, etc.) since those are locale-independent.

**What I'd ask the PM:** What locale is the client's SAP system in? Do they have custom field names from enhancements (Z-fields)?

---

## Utility: Which ingestion mode?

**Options:** Green Button XML (ESPI standard, used by US utilities), portal CSV export, API (utilities like PG&E offer REST APIs), PDF bill parsing.

**Chose:** Portal CSV export.

**Why:**
- Green Button XML is well-standardised but facilities teams don't know what it is. They click "Download Usage Data" and get a CSV.
- Utility APIs (like PG&E's Share My Data) require account linking and OAuth — a multi-week IT process, not something a sustainability team does ad hoc.
- PDF parsing is fragile (layout changes break it) and unnecessary when portals offer CSV.

The portal CSV format is not perfectly standardised, but the column names are recognisable enough that a column alias map handles the common variants (PG&E, ConEd, Eversource, National Grid, etc. all use roughly the same fields with different names).

**What I ignored:** Green Button XML, utility APIs, PDF parsing.

**What would break in production:** A utility with a completely non-standard export format. I've seen utility portals that export kVAh instead of kWh, or that separate on-peak and off-peak usage into separate columns. The parser handles the common case; unusual formats would need a custom column alias entry.

---

## Utility: Billing periods

Utility billing periods don't align with calendar months. A meter read on Dec 19 to Jan 21 spans two months and two calendar years. I store `period_start` and `period_end` explicitly and do not try to split the usage across months. Downstream reporting (which month does this kWh belong to?) is a separate concern — you can pro-rate by days if needed, but that's an emissions calculation layer decision, not an ingestion layer decision.

---

## Travel: Concur vs Navan vs API

**Options:** Concur REST API (SAP Concur's v4 APIs), Navan API, CSV export from either.

**Chose:** CSV export, compatible with both Concur and Navan standard trip exports.

**Why:** Concur's API requires OAuth2 with company-level admin consent and partner registration. Navan's is similar. In practice, the travel manager or sustainability coordinator downloads a "Trip Summary" CSV quarterly. That's the actual workflow — I've read the Concur documentation and the API is genuinely complex to set up.

The CSV format is similar between Concur and Navan. I handle both via column aliasing.

**What I ignored:** API-based pull for either platform.

---

## Travel: Distance for air segments

Concur sometimes includes distance; sometimes it only has airport codes. I handle three cases:
1. Distance given in km → use it directly
2. Distance given in miles → convert (×1.60934)
3. No distance, airport codes present → record with zero distance and flag with an anomaly (`missing_field`, medium severity)

I do not silently impute distances using great-circle calculations because that's a methodology choice (do you use actual route distance or great-circle? do you add a radiative forcing uplift factor?). The flag tells the analyst "this air segment needs distance calculated" rather than silently inserting a number they didn't verify.

**What I'd ask the PM:** What's the preferred methodology for air distances where Concur didn't provide them? Great-circle (as per DEFRA/GHG Protocol guidance) or actual sector distance?

---

## Scope assignment

Scope is assigned deterministically at parse time, not stored as a user input field. The rules are:

- SAP goods issues of fuel materials (201, 261, 551) → Scope 1, category `fuel_combustion`
- SAP goods receipts (101, 501) → Scope 3, category `procurement`
- All utility electricity → Scope 2, category `electricity`
- Travel segments (AIR, RAIL, BUS, CAR, TAXI) → Scope 3, category `travel_air/hotel/ground`

The category→scope mapping is baked in because it follows GHG Protocol directly. The only ambiguity is company-owned vs. leased vehicles (Scope 1 vs. Scope 3) — I default car rental to Scope 3 because the sample data is Concur/Navan (implying third-party vehicles). Fleet data from SAP would be Scope 1.

**What I'd ask the PM:** Does the client own any of their ground transport fleet? That would need to be Scope 1 rather than Scope 3.

---

## Anomalies don't block ingestion

A row with a parse error or anomaly still produces an ActivityRecord with `status=flagged`. I considered two alternatives:
1. Hard reject rows with errors (don't create ActivityRecord)
2. Queue them separately for re-processing

I chose soft-flag because analysts need to see what came in even when it's imperfect. If a SAP row has an unknown unit, the analyst should see the quantity and decide whether it's a typo (should have been "L" not "LTR") or a real data quality problem. Silently dropping it would hide the problem.

---

## Multi-tenancy implementation

Current prototype uses a `Tenant` model with every record having a tenant FK. The view layer resolves the current user's tenant via `_get_tenant()`, which falls back to `Tenant.objects.first()` for the demo. 

In production this would be a `TenantMembership(user, tenant, role)` table. I chose not to build this in the prototype because it's pure CRUD that doesn't demonstrate anything interesting about the emissions data problem.

---

## SQLite in development, PostgreSQL in production

`dj_database_url` reads `DATABASE_URL` from the environment. If not set, falls back to SQLite. This means local development works without Docker, and Render deployment uses the provided PostgreSQL URL without code changes.

---

## What I'd ask the PM

1. Does the client have company-owned vehicles, or is all ground transport third-party (Scope 1 vs Scope 3)?
2. What SAP locale/language is the system in? Any custom Z-fields?
3. What methodology for air distances where Concur doesn't provide them?
4. Are there multiple legal entities within the client that need separate reporting? (Changes the multi-tenancy model)
5. What's the sign-off workflow? Does approval require two analysts, or is one sufficient?
6. What happens to rejected records — are they permanently excluded or can they be corrected and re-submitted?
