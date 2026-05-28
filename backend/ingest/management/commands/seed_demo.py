"""
Creates demo tenant, user, and pre-ingests sample data files so the
dashboard is populated on first load.

Usage:
  python manage.py seed_demo
  python manage.py seed_demo --reset   # drops existing demo data first
"""

import os
import hashlib
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from rest_framework.authtoken.models import Token

from ingest.models import (
    Tenant, DataSource, IngestionRun, RawRecord,
    ActivityRecord, AuditEvent, Anomaly,
)


DEMO_EMAIL = "analyst@breatheesg.com"
DEMO_PASSWORD = "demo1234"

SAMPLE_DIR = Path(__file__).resolve().parents[4] / "sample_data"


class Command(BaseCommand):
    help = "Seed demo tenant, analyst user, and sample ingestion data."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete existing demo data first")

    def handle(self, *args, **options):
        if options["reset"]:
            # Must delete in dependency order because raw_record is PROTECT
            tenant = Tenant.objects.filter(slug="acme-corp").first()
            if tenant:
                AuditEvent.objects.filter(record__tenant=tenant).delete()
                Anomaly.objects.filter(run__data_source__tenant=tenant).delete()
                ActivityRecord.objects.filter(tenant=tenant).delete()
                RawRecord.objects.filter(run__data_source__tenant=tenant).delete()
                IngestionRun.objects.filter(data_source__tenant=tenant).delete()
                DataSource.objects.filter(tenant=tenant).delete()
                tenant.delete()
            User.objects.filter(username="analyst").delete()
            self.stdout.write("Cleared existing demo data.")

        # Tenant
        tenant, _ = Tenant.objects.get_or_create(
            slug="acme-corp",
            defaults={"name": "Acme Corporation"},
        )
        self.stdout.write(f"Tenant: {tenant}")

        # Analyst user
        user, created = User.objects.get_or_create(
            username="analyst",
            defaults={
                "email": DEMO_EMAIL,
                "first_name": "Demo",
                "last_name": "Analyst",
                "is_staff": False,
            },
        )
        if created:
            user.set_password(DEMO_PASSWORD)
            user.save()
        token, _ = Token.objects.get_or_create(user=user)
        self.stdout.write(f"User: {user.username} / {DEMO_PASSWORD}  (token: {token.key})")

        # Add user → tenant mapping via groups (simple: store in tenant config)
        # We use a simple lookup in views._get_tenant that falls back to first tenant
        # In production this would be a proper ManyToMany or profile model.

        # Ingest sample files
        for source_type, filename, parser_mod, normaliser in [
            (DataSource.SOURCE_SAP, "sap_mb51_export.txt", "sap", None),
            (DataSource.SOURCE_UTILITY, "utility_portal_export.csv", "utility", None),
            (DataSource.SOURCE_TRAVEL, "concur_travel_export.csv", "travel", None),
        ]:
            filepath = SAMPLE_DIR / filename
            if not filepath.exists():
                self.stdout.write(self.style.WARNING(f"  Skipping {filename} — not found at {filepath}"))
                continue

            file_bytes = filepath.read_bytes()
            file_hash = hashlib.sha256(file_bytes).hexdigest()

            if IngestionRun.objects.filter(file_hash=file_hash).exists():
                self.stdout.write(f"  Skipping {filename} — already ingested")
                continue

            ds, _ = DataSource.objects.get_or_create(
                tenant=tenant,
                source_type=source_type,
                defaults={"name": f"Acme {source_type}"},
            )

            run = IngestionRun.objects.create(
                data_source=ds,
                uploaded_by=user,
                original_filename=filename,
                file_hash=file_hash,
                status=IngestionRun.STATUS_PROCESSING,
            )

            # Dynamically import parser and normaliser
            import importlib
            parser = importlib.import_module(f"ingest.parsers.{parser_mod}")
            normalise_fn_map = {
                "sap": "normalise_sap",
                "utility": "normalise_utility",
                "travel": "normalise_travel",
            }
            from ingest import normalize as norm_module
            normalise_fn = getattr(norm_module, normalise_fn_map[parser_mod])

            parsed_count = 0
            error_count = 0

            for parsed_row in parser.parse(file_bytes):
                row_idx = parsed_row.get("_row_index", 0)
                parse_error = parsed_row.get("_parse_error", "")

                raw = RawRecord.objects.create(
                    run=run,
                    row_index=row_idx,
                    raw_data={k: str(v) if v is not None else None
                              for k, v in parsed_row.items() if not k.startswith("_")},
                    parse_error=parse_error,
                )

                kwargs, anomalies = normalise_fn(parsed_row, tenant.id, raw.id)
                ar = ActivityRecord.objects.create(**kwargs)

                for a in anomalies:
                    Anomaly.objects.create(run=run, raw_record=raw, activity_record=ar, **a)

                if anomalies:
                    ar.status = ActivityRecord.STATUS_FLAGGED
                    ar.save(update_fields=["status"])

                AuditEvent.objects.create(record=ar, event=AuditEvent.EVENT_INGESTED, actor=user)
                parsed_count += 1

            run.status = IngestionRun.STATUS_DONE
            run.rows_parsed = parsed_count
            run.rows_errored = error_count
            run.save()

            self.stdout.write(f"  Ingested {filename}: {parsed_count} records")

        self.stdout.write(self.style.SUCCESS("\nDemo seeding complete."))
        self.stdout.write(f"  Login: {DEMO_EMAIL} / {DEMO_PASSWORD}")
        self.stdout.write(f"  URL:   http://localhost:8000/")
