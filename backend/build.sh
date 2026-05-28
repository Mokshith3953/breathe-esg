#!/usr/bin/env bash
set -e

# 1. Install Python deps
pip install -r requirements-prod.txt

# 2. Build React frontend
cd ../frontend
npm install
npm run build

# 3. Copy React build into Django's static directory so WhiteNoise serves it
cd ../backend
mkdir -p static/frontend
cp -r ../frontend/dist/* static/frontend/

# 4. Django setup
python manage.py collectstatic --no-input
python manage.py migrate

# 5. Seed demo data (idempotent — skips if already seeded)
python manage.py seed_demo || true
