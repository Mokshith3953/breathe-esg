"""
Post-normalisation anomaly detection.

Run after all ActivityRecords for an IngestionRun are created.
Flags statistical outliers within the same (tenant, category) group.
"""

from decimal import Decimal
from statistics import mean, stdev
from typing import Sequence

from .models import ActivityRecord, Anomaly, IngestionRun


OUTLIER_STDEV_THRESHOLD = 3.0


def detect_outliers(run: IngestionRun) -> None:
    """
    Within each (tenant, category) pair touched by this run, flag records
    whose normalized_value is more than OUTLIER_STDEV_THRESHOLD standard
    deviations above the mean of all existing records in that group.

    We only flag HIGH outliers (not low) because zero/negative quantities
    are already caught at parse time. Very large values are the concern here
    (e.g. a 10× spike that might be a unit entry error).
    """
    records = list(run.data_source.runs.prefetch_related("raw_records__activity").values_list(
        "raw_records__activity__id",
        "raw_records__activity__tenant_id",
        "raw_records__activity__category",
        "raw_records__activity__normalized_value",
        flat=False,
    ))

    # Get all activity records from this run
    run_activities = ActivityRecord.objects.filter(
        raw_record__run=run
    ).select_related("raw_record")

    if not run_activities:
        return

    # Group by category to compute stats
    categories = run_activities.values_list("category", flat=True).distinct()

    for category in categories:
        # Use all historical records for this tenant+category as the baseline
        tenant_id = run.data_source.tenant_id
        all_values = list(
            ActivityRecord.objects.filter(
                tenant_id=tenant_id,
                category=category,
                normalized_value__gt=0,
            ).values_list("normalized_value", flat=True)
        )

        if len(all_values) < 5:
            # Not enough data for statistical outlier detection
            continue

        floats = [float(v) for v in all_values]
        mu = mean(floats)
        sigma = stdev(floats)

        if sigma == 0:
            continue

        threshold = mu + OUTLIER_STDEV_THRESHOLD * sigma

        for ar in run_activities.filter(category=category):
            if float(ar.normalized_value) > threshold:
                Anomaly.objects.create(
                    run=run,
                    raw_record=ar.raw_record,
                    activity_record=ar,
                    anomaly_type=Anomaly.TYPE_OUTLIER,
                    severity=Anomaly.SEV_HIGH,
                    message=(
                        f"{ar.normalized_value} {ar.normalized_unit} is "
                        f"{float(ar.normalized_value) / mu:.1f}× the category mean "
                        f"({mu:.1f}) — possible unit entry error"
                    ),
                    detail={
                        "value": str(ar.normalized_value),
                        "unit": ar.normalized_unit,
                        "mean": round(mu, 2),
                        "stdev": round(sigma, 2),
                        "threshold": round(threshold, 2),
                    },
                )
                # Escalate status to flagged
                ar.status = ActivityRecord.STATUS_FLAGGED
                ar.save(update_fields=["status"])


def detect_duplicates(run: IngestionRun) -> None:
    """
    Flag records in this run that look like duplicates of already-existing
    records: same tenant, category, period_start, location, and
    normalized_value within 0.1%.
    """
    run_activities = ActivityRecord.objects.filter(raw_record__run=run)

    for ar in run_activities:
        tolerance = ar.normalized_value * Decimal("0.001")
        duplicates = ActivityRecord.objects.filter(
            tenant_id=ar.tenant_id,
            category=ar.category,
            period_start=ar.period_start,
            location=ar.location,
            normalized_value__gte=ar.normalized_value - tolerance,
            normalized_value__lte=ar.normalized_value + tolerance,
        ).exclude(pk=ar.pk)

        if duplicates.exists():
            dup = duplicates.first()
            Anomaly.objects.create(
                run=run,
                raw_record=ar.raw_record,
                activity_record=ar,
                anomaly_type=Anomaly.TYPE_DUPLICATE,
                severity=Anomaly.SEV_MEDIUM,
                message=(
                    f"Possible duplicate of record #{dup.pk} "
                    f"({dup.period_start}, {dup.normalized_value} {dup.normalized_unit})"
                ),
                detail={"existing_record_id": dup.pk},
            )
            if ar.status == ActivityRecord.STATUS_PENDING:
                ar.status = ActivityRecord.STATUS_FLAGGED
                ar.save(update_fields=["status"])
