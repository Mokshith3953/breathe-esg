# Breathe ESG — Emissions Data Ingestion & Review

Django REST + React prototype that ingests emissions activity data from three source types, normalises it, and surfaces a review dashboard for analyst sign-off before audit.

## Live demo

> Add deployed URL here after Render deployment.
>
> Login: `analyst` / `demo1234`

## Local setup

### Backend

```bash
cd backend
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend dev server at `http://localhost:5173`, proxies `/api` to Django on `8000`.

## Sample data

Three files in `sample_data/` can be uploaded via the Ingest page or are pre-loaded by `seed_demo`:

| File | Source | Rows |
|------|--------|------|
| `sap_mb51_export.txt` | SAP MB51 pipe-delimited ALV export | 20 |
| `utility_portal_export.csv` | Utility portal CSV | 17 |
| `concur_travel_export.csv` | Concur travel export | 21 |

## Architecture

```
backend/
  esg/           Django project config (settings, urls, wsgi)
  ingest/        Single app for all ingestion + review logic
    models.py    Tenant, DataSource, IngestionRun, RawRecord,
                 ActivityRecord, AuditEvent, Anomaly
    parsers/     sap.py, utility.py, travel.py
    normalize.py Maps parsed rows → ActivityRecord kwargs
    anomaly.py   Statistical outlier + duplicate detection
    views.py     API endpoints
    urls.py      URL routing

frontend/
  src/
    api/         Axios client + TypeScript types
    components/  Layout, Badge, StatCard, FileUpload
    pages/       Dashboard, Ingest, Review, Anomalies
```

## Deployment (Render)

1. Push to GitHub
2. Create new Render service, point to this repo
3. Set `rootDir: backend`, build command: `bash build.sh`
4. Render will provision PostgreSQL via `render.yaml`

See `render.yaml` for full configuration.

## Documentation

- [MODEL.md](MODEL.md) — Data model design and rationale
- [DECISIONS.md](DECISIONS.md) — Every ambiguity resolved + what I'd ask the PM
- [TRADEOFFS.md](TRADEOFFS.md) — Three things deliberately not built
- [SOURCES.md](SOURCES.md) — Source format research notes
