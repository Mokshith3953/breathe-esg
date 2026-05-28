import hashlib
from datetime import datetime

from django.contrib.auth import authenticate, login, logout
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.authtoken.models import Token

from .models import (
    Tenant, DataSource, IngestionRun, RawRecord,
    ActivityRecord, AuditEvent, Anomaly,
)
from .serializers import (
    IngestionRunSerializer, ActivityRecordSerializer,
    ActivityRecordListSerializer, AnomalySerializer,
    DashboardStatsSerializer,
)
from .parsers import sap as sap_parser
from .parsers import utility as utility_parser
from .parsers import travel as travel_parser
from .normalize import normalise_sap, normalise_utility, normalise_travel
from .anomaly import detect_outliers, detect_duplicates


# ── Auth ──────────────────────────────────────────────────────────────────────

@api_view(["POST"])
@permission_classes([AllowAny])
def login_view(request):
    username = request.data.get("username", "")
    password = request.data.get("password", "")
    user = authenticate(request, username=username, password=password)
    if user is None:
        return Response({"detail": "Invalid credentials."}, status=status.HTTP_401_UNAUTHORIZED)
    token, _ = Token.objects.get_or_create(user=user)
    return Response({
        "token": token.key,
        "user": {
            "id": user.id,
            "username": user.username,
            "name": user.get_full_name() or user.username,
            "email": user.email,
        },
    })


@api_view(["POST"])
def logout_view(request):
    try:
        request.user.auth_token.delete()
    except Exception:
        pass
    return Response({"detail": "Logged out."})


@api_view(["GET"])
def me_view(request):
    user = request.user
    return Response({
        "id": user.id,
        "username": user.username,
        "name": user.get_full_name() or user.username,
        "email": user.email,
    })


# ── Dashboard ─────────────────────────────────────────────────────────────────

@api_view(["GET"])
def dashboard_stats(request):
    tenant = _get_tenant(request)
    qs = ActivityRecord.objects.filter(tenant=tenant)

    scope_breakdown = {}
    for scope, label in ActivityRecord.SCOPE_CHOICES:
        scope_breakdown[str(scope)] = {
            "label": label,
            "count": qs.filter(scope=scope).count(),
        }

    category_breakdown = {}
    for cat, label in ActivityRecord.CATEGORY_CHOICES:
        count = qs.filter(category=cat).count()
        if count:
            category_breakdown[cat] = {"label": label, "count": count}

    recent_runs = IngestionRun.objects.filter(
        data_source__tenant=tenant
    ).order_by("-uploaded_at")[:5]

    data = {
        "total_records": qs.count(),
        "pending": qs.filter(status="pending").count(),
        "approved": qs.filter(status="approved").count(),
        "rejected": qs.filter(status="rejected").count(),
        "flagged": qs.filter(status="flagged").count(),
        "anomaly_count": Anomaly.objects.filter(run__data_source__tenant=tenant, resolved=False).count(),
        "scope_breakdown": scope_breakdown,
        "category_breakdown": category_breakdown,
        "recent_runs": IngestionRunSerializer(recent_runs, many=True).data,
    }
    return Response(data)


# ── Ingestion ─────────────────────────────────────────────────────────────────

class IngestView(APIView):
    """Base class for file upload ingestion endpoints."""
    source_type = None
    parser_module = None
    normaliser = None

    def post(self, request):
        tenant = _get_tenant(request)
        f = request.FILES.get("file")
        if not f:
            return Response({"detail": "No file provided."}, status=status.HTTP_400_BAD_REQUEST)

        file_bytes = f.read()
        file_hash = hashlib.sha256(file_bytes).hexdigest()

        # Warn on duplicate upload (same hash seen before for this tenant)
        duplicate_run = IngestionRun.objects.filter(
            data_source__tenant=tenant,
            file_hash=file_hash,
        ).first()
        duplicate_warning = None
        if duplicate_run:
            duplicate_warning = (
                f"This file was already uploaded on "
                f"{duplicate_run.uploaded_at:%Y-%m-%d} (run #{duplicate_run.pk}). "
                "Proceeding anyway — check for duplicates in the review queue."
            )

        # Find or create the DataSource for this tenant+type
        ds, _ = DataSource.objects.get_or_create(
            tenant=tenant,
            source_type=self.source_type,
            defaults={"name": f"{tenant.name} {self.source_type}"},
        )

        run = IngestionRun.objects.create(
            data_source=ds,
            uploaded_by=request.user,
            original_filename=f.name,
            file_hash=file_hash,
            status=IngestionRun.STATUS_PROCESSING,
        )

        errors = []
        parsed_count = 0
        error_count = 0

        for parsed_row in self.parser_module.parse(file_bytes):
            row_idx = parsed_row.get("_row_index", 0)
            parse_error = parsed_row.get("_parse_error", "")

            raw = RawRecord.objects.create(
                run=run,
                row_index=row_idx,
                raw_data={k: str(v) if v is not None else None for k, v in parsed_row.items()
                          if not k.startswith("_")},
                parse_error=parse_error,
            )

            if parse_error and all(
                err_type in parse_error
                for err_type in ["missing/invalid period_start", "unparseable date"]
                if err_type in parse_error
            ):
                # Hard parse failure — still create raw record but skip activity record
                error_count += 1
                errors.append({"row": row_idx, "message": parse_error})
                Anomaly.objects.create(
                    run=run,
                    raw_record=raw,
                    anomaly_type=Anomaly.TYPE_PARSE_ERROR,
                    severity=Anomaly.SEV_HIGH,
                    message=parse_error,
                    detail={"row": row_idx},
                )
                continue

            kwargs, anomalies = self.normaliser(parsed_row, tenant.id, raw.id)
            ar = ActivityRecord.objects.create(**kwargs)

            # Create anomaly records from normalisation
            for a in anomalies:
                Anomaly.objects.create(
                    run=run,
                    raw_record=raw,
                    activity_record=ar,
                    **a,
                )
                if a["severity"] == "high":
                    error_count += 1

            # If any anomalies exist, flag the record
            if anomalies:
                ar.status = ActivityRecord.STATUS_FLAGGED
                ar.save(update_fields=["status"])

            # Initial audit event
            AuditEvent.objects.create(
                record=ar,
                event=AuditEvent.EVENT_INGESTED,
                actor=request.user,
            )

            parsed_count += 1

        # Post-normalisation statistical checks
        try:
            detect_outliers(run)
            detect_duplicates(run)
        except Exception:
            pass  # don't fail the whole upload if anomaly detection errors

        run.status = IngestionRun.STATUS_DONE
        run.rows_parsed = parsed_count
        run.rows_errored = error_count
        run.error_log = errors
        run.save()

        return Response({
            "run_id": run.pk,
            "rows_parsed": parsed_count,
            "rows_errored": error_count,
            "duplicate_warning": duplicate_warning,
        }, status=status.HTTP_201_CREATED)


class IngestSAPView(IngestView):
    source_type = DataSource.SOURCE_SAP
    parser_module = sap_parser
    normaliser = staticmethod(normalise_sap)


class IngestUtilityView(IngestView):
    source_type = DataSource.SOURCE_UTILITY
    parser_module = utility_parser
    normaliser = staticmethod(normalise_utility)


class IngestTravelView(IngestView):
    source_type = DataSource.SOURCE_TRAVEL
    parser_module = travel_parser
    normaliser = staticmethod(normalise_travel)


# ── Ingestion Runs ────────────────────────────────────────────────────────────

@api_view(["GET"])
def ingestion_runs(request):
    tenant = _get_tenant(request)
    source_type = request.query_params.get("source_type")
    qs = IngestionRun.objects.filter(data_source__tenant=tenant).order_by("-uploaded_at")
    if source_type:
        qs = qs.filter(data_source__source_type=source_type)
    serializer = IngestionRunSerializer(qs[:50], many=True)
    return Response(serializer.data)


# ── Activity Records ──────────────────────────────────────────────────────────

@api_view(["GET"])
def records_list(request):
    tenant = _get_tenant(request)
    qs = ActivityRecord.objects.filter(tenant=tenant).select_related("raw_record__run__data_source")

    # Filters
    status_filter = request.query_params.get("status")
    scope_filter = request.query_params.get("scope")
    category_filter = request.query_params.get("category")
    source_type_filter = request.query_params.get("source_type")
    date_from = request.query_params.get("date_from")
    date_to = request.query_params.get("date_to")

    if status_filter:
        qs = qs.filter(status=status_filter)
    if scope_filter:
        qs = qs.filter(scope=scope_filter)
    if category_filter:
        qs = qs.filter(category=category_filter)
    if source_type_filter:
        qs = qs.filter(raw_record__run__data_source__source_type=source_type_filter)
    if date_from:
        qs = qs.filter(period_start__gte=date_from)
    if date_to:
        qs = qs.filter(period_end__lte=date_to)

    # Pagination
    page = int(request.query_params.get("page", 1))
    page_size = int(request.query_params.get("page_size", 50))
    total = qs.count()
    start = (page - 1) * page_size
    end = start + page_size

    serializer = ActivityRecordListSerializer(qs[start:end], many=True)
    return Response({
        "count": total,
        "page": page,
        "page_size": page_size,
        "results": serializer.data,
    })


@api_view(["GET"])
def record_detail(request, pk):
    tenant = _get_tenant(request)
    try:
        ar = ActivityRecord.objects.prefetch_related(
            "audit_trail__actor", "anomalies"
        ).get(pk=pk, tenant=tenant)
    except ActivityRecord.DoesNotExist:
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
    return Response(ActivityRecordSerializer(ar).data)


@api_view(["POST"])
def record_approve(request, pk):
    return _set_status(request, pk, ActivityRecord.STATUS_APPROVED, AuditEvent.EVENT_APPROVED)


@api_view(["POST"])
def record_reject(request, pk):
    return _set_status(request, pk, ActivityRecord.STATUS_REJECTED, AuditEvent.EVENT_REJECTED)


@api_view(["POST"])
def record_flag(request, pk):
    return _set_status(request, pk, ActivityRecord.STATUS_FLAGGED, AuditEvent.EVENT_FLAGGED)


@api_view(["POST"])
def record_bulk_approve(request):
    ids = request.data.get("ids", [])
    tenant = _get_tenant(request)
    qs = ActivityRecord.objects.filter(pk__in=ids, tenant=tenant, status=ActivityRecord.STATUS_PENDING)
    count = 0
    for ar in qs:
        ar.status = ActivityRecord.STATUS_APPROVED
        ar.reviewed_by = request.user
        ar.reviewed_at = timezone.now()
        ar.save(update_fields=["status", "reviewed_by", "reviewed_at"])
        AuditEvent.objects.create(
            record=ar,
            event=AuditEvent.EVENT_APPROVED,
            actor=request.user,
        )
        count += 1
    return Response({"approved": count})


@api_view(["PATCH"])
def record_note(request, pk):
    tenant = _get_tenant(request)
    try:
        ar = ActivityRecord.objects.get(pk=pk, tenant=tenant)
    except ActivityRecord.DoesNotExist:
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
    note = request.data.get("review_note", "")
    ar.review_note = note
    ar.save(update_fields=["review_note", "updated_at"])
    AuditEvent.objects.create(
        record=ar,
        event=AuditEvent.EVENT_NOTE,
        actor=request.user,
        diff={"review_note": note},
    )
    return Response({"review_note": note})


# ── Anomalies ─────────────────────────────────────────────────────────────────

@api_view(["GET"])
def anomalies_list(request):
    tenant = _get_tenant(request)
    qs = Anomaly.objects.filter(run__data_source__tenant=tenant).order_by("-created_at")

    severity_filter = request.query_params.get("severity")
    resolved_filter = request.query_params.get("resolved")
    source_type_filter = request.query_params.get("source_type")

    if severity_filter:
        qs = qs.filter(severity=severity_filter)
    if resolved_filter is not None:
        qs = qs.filter(resolved=(resolved_filter.lower() == "true"))
    if source_type_filter:
        qs = qs.filter(run__data_source__source_type=source_type_filter)

    page = int(request.query_params.get("page", 1))
    page_size = int(request.query_params.get("page_size", 50))
    total = qs.count()
    start = (page - 1) * page_size

    serializer = AnomalySerializer(qs[start:start + page_size], many=True)
    return Response({"count": total, "results": serializer.data})


@api_view(["POST"])
def anomaly_resolve(request, pk):
    tenant = _get_tenant(request)
    try:
        anomaly = Anomaly.objects.get(pk=pk, run__data_source__tenant=tenant)
    except Anomaly.DoesNotExist:
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
    anomaly.resolved = True
    anomaly.save(update_fields=["resolved"])
    return Response({"resolved": True})


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_tenant(request) -> Tenant:
    """
    Return the tenant for the current user.
    In the prototype every user implicitly belongs to the first (and only)
    tenant. A production system would look up a TenantMembership row here.
    """
    return Tenant.objects.first()


def _set_status(request, pk, new_status, event_type):
    tenant = _get_tenant(request)
    try:
        ar = ActivityRecord.objects.get(pk=pk, tenant=tenant)
    except ActivityRecord.DoesNotExist:
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    old_status = ar.status
    ar.status = new_status
    ar.reviewed_by = request.user
    ar.reviewed_at = timezone.now()

    note = request.data.get("note", "")
    if note:
        ar.review_note = note

    ar.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_note", "updated_at"])

    AuditEvent.objects.create(
        record=ar,
        event=event_type,
        actor=request.user,
        diff={"status": {"before": old_status, "after": new_status}, "note": note},
    )

    return Response(ActivityRecordListSerializer(ar).data)
