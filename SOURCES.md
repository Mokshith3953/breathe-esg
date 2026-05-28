# Sources — Research Notes

## 1. SAP Fuel & Procurement (MB51 flat-file export)

### What I researched

SAP transaction MB51 (Material Document List) is the standard way sustainability teams pull material movement data from SAP. I read:
- SAP Help documentation for MB51 and the underlying MKPF/MSEG tables
- SAP Community discussions about exporting material documents for environmental reporting
- The SAP field name dictionary for MSEG (material document segment): BWART (movement type), WERKS (plant), MATNR (material number), MENGE (quantity), MEINS (base unit of measure), KOSTL (cost center), BUDAT (posting date)
- A comparison of SAP export formats: IDoc vs BAPI vs OData vs ALV grid export

### What I learned

SAP stores quantities in "base units of measure" which are SAP internal codes: L (liter), KG (kilogram), TO (metric ton), GAL (US gallon), GL (SAP alias for gallon), M3 (cubic meter), NM3 (normal cubic meter of gas). These differ from ISO units in subtle ways (NM3 is at standard conditions of 0°C/1 atm, not just volume). German SAP instances use German field names in exports: "Buchungsdatum" for posting date, "Werk" for plant, "Bewegungsart" for movement type.

Movement type matters enormously for emissions accounting. 201 is a goods issue to a cost center (someone drew fuel from a tank for a department's vehicles or equipment). 261 is goods issue for a production order. 101 is goods receipt (procurement). You can't just total all movements — you'd double-count receipts and issues.

### What the sample data looks like and why

I created 20 rows with:
- Four plants: Hamburg (1001), Rotterdam (1002), Houston (2001), Singapore (2002), London (3001)
- Multiple material types: diesel (DIESEL_ROAD), heavy fuel oil (HFO_380), LPG, natural gas (NM3), coal, and procurement materials (STEEL_COIL, CHEM_SOLV)
- Mixed units: L (European plants), GAL (US plant), KG (for HFO and LPG), NM3 (for natural gas)
- German-style decimal comma notation (4500,000 not 4500.000) — this is what German SAP exports produce
- Both fuel movements (201, 261) and procurement receipts (101)
- One deliberate outlier: row 5000012364 has 99,000 L diesel — roughly 22× the typical row. This tests the statistical outlier detection.
- Currency mix: EUR, USD, SGD, GBP reflecting the four regions

The German decimal comma format is realistic and frequently breaks naive parsers. My parser normalises it (`"4500,000".replace(",", ".")`) before Decimal conversion.

### What would break in real deployment

1. **Unknown movement types**: Clients with custom Z-movement types (e.g. Z201 for a special fuel tracking process) would have their rows silently skipped. Mitigation: surface the list of skipped movement types in the ingestion report.

2. **Material master gap**: Our category inference (fuel vs procurement) is based on substring matching of material numbers and descriptions. A real deployment needs the material master (material → material group → emission category) from SAP, which is a separate extract.

3. **Plant code lookup**: We have 5 plant codes hardcoded. A real client might have 50+. The plant lookup table needs to come from SAP's T001W table.

4. **NM3 (normal cubic meters of gas)**: We flag this unit separately because converting gas volume to energy requires a calorific value specific to the gas type and source. We can't assume standard calorific value without the client confirming the gas composition.

---

## 2. Utility Electricity (portal CSV export)

### What I researched

I reviewed the download formats from several major utility portals:
- PG&E (California): Green Button CSV and "My Energy" CSV exports — uses account number, meter number, billing period, kWh
- ConEd (New York): "My Account" CSV — similar structure, uses "Meter Read Date" not "Billing Period"
- Eversource (New England): "Usage History" CSV — uses "Service Period" start/end
- National Grid (UK/US): similar to Eversource with "Read Date From/To"
- UK utilities (British Gas, EDF): different structure, some use half-hourly AMR data

I also read the Green Button Initiative documentation (ESPI standard, used by US utilities for machine-readable exports).

### What I learned

The most important finding: billing periods do not align with calendar months. A meter is read on whatever date the utility sends a reader (or receives an AMR transmission), not on the first of the month. A billing period might be Dec 19 – Jan 21 (33 days). Treating it as "December electricity" introduces a ~40% error on that month's figure.

Meter read types matter: "Actual Read" means someone physically read the meter. "Estimated Read" means the utility interpolated (common in winter when meters are in awkward locations). Estimated reads should be flagged for analyst review.

Power factor is rarely in sustainability reports but appears in utility data. We capture it in `extra` for completeness — it's useful for identifying sites with poor power quality.

Utilities in some markets (UK, Netherlands, Singapore) report in different units — some export demand in kVA rather than kW, or consumption in MWh for large industrial accounts. The unit normalisation handles MWh → kWh.

### What the sample data looks like and why

17 rows covering 5 meters across 4 sites:
- Hamburg (Germany), Rotterdam (Netherlands), Houston (USA), Singapore, London (UK)
- 3-4 billing periods per meter, none aligned to calendar month-ends
- Mixed rate schedules: HV-Industrial (Hamburg), MV-Commercial (Rotterdam), LGS-Large-Industrial (Houston), C3-Commercial-HT (Singapore), UT-Firm-Supply (London)
- One estimated read (Singapore Feb-Mar) — this creates an anomaly flag
- Amounts in USD (no currency conversion — that's a separate concern)
- Peak demand included for all meters (realistic for industrial accounts, not for small offices)

The billing period misalignment is intentional: Dec 19 – Jan 21, then Jan 22 – Feb 19, etc. This tests that the model correctly stores both dates rather than losing the period boundaries.

### What would break in real deployment

1. **Half-hourly AMR data**: Large industrial clients sometimes have 30-minute interval data (48 readings per day). Our parser expects one row = one billing period. An AMR file with 48×365 rows would need a pre-aggregation step.

2. **Multiple meters per account**: Some large sites have sub-metering (production, office, car park). Our model handles this (each meter_number is a separate billing row) but the dashboard doesn't currently group by site.

3. **Green Button XML**: If a client's portal only offers Green Button XML (no CSV), we'd need an XML parser. The data model supports it; only the parser would change.

4. **Utility bill PDFs**: Some smaller sites only have PDF bills. That would require OCR or a structured extraction step — significantly more complex.

---

## 3. Corporate Travel — Concur/Navan CSV Export

### What I researched

I read:
- Concur's documentation for standard travel expense reports and the "Trip Summary" export format
- Navan's export documentation (simpler than Concur, similar column structure)
- The GHG Protocol guidance for Scope 3 Category 6 (business travel) and the emission factor structure it implies
- DEFRA's business travel emission factors (per passenger-km by class, per hotel-night by region)
- ICAO's Carbon Emissions Calculator methodology (uses actual route data, not great-circle)

### What I learned

The two main challenges are: (1) different segment types need different emission factors and different quantity metrics, and (2) distance is often missing.

Concur's export has segment types: AIR, HOTEL, CAR, RAIL, BUS, TAXI. Each implies a different measurement:
- AIR: passenger-km (or passenger-mile) by class of service
- HOTEL: room-nights by region
- CAR/TAXI/BUS: km (or cost as proxy)
- RAIL: passenger-km

Concur sometimes includes distance for air segments (especially for managed travel programs); often it doesn't. The IATA airport codes (LHR, SIN, JFK) are always present for air segments. Distance can be computed from airport coordinates using the haversine formula, but that's a calculation the client should approve — some clients want actual flight path distance, others want great-circle.

Class of service (Economy, Business, First) matters because DEFRA's factors differ 3× between economy and business class. Concur uses carrier-specific codes (Y, C, F) which need mapping to Economy/Business/First.

### What the sample data looks like and why

21 rows covering 10 trips, 5 employees, across engineering/sales/finance/ops/HR departments:
- Mix of AIR (long-haul: LHR-SIN, LHR-IAH, BOM-HOU; short-haul: AMS-LHR), HOTEL, CAR, RAIL, TAXI
- International routes reflecting a realistic multinational client (Europe/US/Asia travel pattern)
- One air segment with no distance (TRP-2024-0145, LHR→Hamburg) — tests missing-distance flag
- Realistic class of service mix: mostly Economy with some Business for senior staff
- Multiple currencies (GBP, EUR, USD, SGD, PLN) — we store amount + currency, no FX conversion
- Costs included (flights, hotels, car rental) — useful for the analyst but not used in emission calculation
- RAIL segment (Eurostar LHR→CDG with 494km) — tests that rail is classified as travel_ground

The missing-distance row for TRP-2024-0145 is intentional. It tests that we flag it rather than silently skipping it or inventing a distance.

### What would break in real deployment

1. **Concur class-of-service codes**: Concur uses airline-specific fare class codes (Y, Q, W, C, J, F, etc.) rather than plain "Economy/Business/First". A real implementation needs a fare class → cabin class mapping table.

2. **Personal vs business travel**: Concur exports sometimes include personal-use days on business trips. Without a flag for personal days, we'd over-count hotel nights.

3. **Currency conversion**: Amounts are in booking currency (GBP, EUR, USD, SGD). For a financial rollup, you'd need FX rates at the transaction date. We store amount + currency; FX is a separate concern.

4. **Large travel programs**: A company with 10,000 employees travelling frequently might have 50,000+ rows per quarter. The current parser streams rows but the anomaly detection (in-memory statistics) would need reworking for that volume.
