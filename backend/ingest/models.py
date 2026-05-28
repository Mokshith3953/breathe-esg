from django.db import models
from django.contrib.auth.models import User


class Tenant(models.Model):
    """
    One row per client company. Every record is scoped to a tenant so the
    same deployment can serve multiple enterprise clients without data bleed.
    """
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class DataSource(models.Model):
    """
    A named connection point for one category of data within a tenant.
    A single tenant might have two DataSources of type SAP (e.g. Hamburg
    plant and Singapore plant), each producing separate IngestionRuns.
    """
    SOURCE_SAP = "SAP"
    SOURCE_UTILITY = "UTILITY"
    SOURCE_TRAVEL = "TRAVEL"
    SOURCE_CHOICES = [
        (SOURCE_SAP, "SAP Fuel & Procurement"),
        (SOURCE_UTILITY, "Utility Electricity"),
        (SOURCE_TRAVEL, "Corporate Travel"),
    ]

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="sources")
    source_type = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    name = models.CharField(max_length=255)
    # Flexible bag for source-specific config (e.g. plant codes, meter IDs)
    config = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.tenant.slug} / {self.name}"


class IngestionRun(models.Model):
    """
    One upload event — a user drops a file and we create one IngestionRun.
    Stores the original filename, a SHA-256 hash (for duplicate detection),
    and the final parse counts. Immutable once completed; errors are logged
    in error_log as a JSON array of {row, message} objects.
    """
    STATUS_PENDING = "pending"
    STATUS_PROCESSING = "processing"
    STATUS_DONE = "done"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_PROCESSING, "Processing"),
        (STATUS_DONE, "Done"),
        (STATUS_FAILED, "Failed"),
    ]

    data_source = models.ForeignKey(DataSource, on_delete=models.CASCADE, related_name="runs")
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    original_filename = models.CharField(max_length=500)
    # SHA-256 of file bytes; used to warn on re-upload of identical file
    file_hash = models.CharField(max_length=64)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    rows_parsed = models.IntegerField(default=0)
    rows_errored = models.IntegerField(default=0)
    # JSON array: [{"row": 3, "message": "unknown unit 'FT3'"}]
    error_log = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"{self.data_source.name} @ {self.uploaded_at:%Y-%m-%d %H:%M}"


class RawRecord(models.Model):
    """
    One row from the source file, stored verbatim as JSON. This is the
    source-of-truth for what came in. ActivityRecord.raw_record points back
    here so an auditor can always see the unmodified original.
    """
    run = models.ForeignKey(IngestionRun, on_delete=models.CASCADE, related_name="raw_records")
    row_index = models.IntegerField()
    raw_data = models.JSONField()
    parse_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["run", "row_index"]

    def __str__(self):
        return f"Run {self.run_id} row {self.row_index}"


class ActivityRecord(models.Model):
    """
    The normalized, canonical representation of one emission-relevant event.
    This is what analysts review and what eventually goes to auditors.

    Quantity is preserved in two forms:
    - quantity_value / quantity_unit: exactly as it came out of the source
      (e.g. 4500 GAL, 12.3 TO)
    - normalized_value / normalized_unit: converted to the canonical unit
      for that category (liters for fuel, kWh for electricity, km for air
      travel, nights for hotel)

    Keeping both lets analysts spot conversion errors and means the audit
    trail always shows what the original source said.
    """
    SCOPE_1 = 1
    SCOPE_2 = 2
    SCOPE_3 = 3
    SCOPE_CHOICES = [
        (SCOPE_1, "Scope 1 – Direct combustion"),
        (SCOPE_2, "Scope 2 – Purchased electricity"),
        (SCOPE_3, "Scope 3 – Value chain"),
    ]

    CATEGORY_FUEL = "fuel_combustion"
    CATEGORY_ELECTRICITY = "electricity"
    CATEGORY_TRAVEL_AIR = "travel_air"
    CATEGORY_TRAVEL_HOTEL = "travel_hotel"
    CATEGORY_TRAVEL_GROUND = "travel_ground"
    CATEGORY_PROCUREMENT = "procurement"
    CATEGORY_CHOICES = [
        (CATEGORY_FUEL, "Fuel Combustion"),
        (CATEGORY_ELECTRICITY, "Purchased Electricity"),
        (CATEGORY_TRAVEL_AIR, "Business Travel – Air"),
        (CATEGORY_TRAVEL_HOTEL, "Business Travel – Hotel"),
        (CATEGORY_TRAVEL_GROUND, "Business Travel – Ground"),
        (CATEGORY_PROCUREMENT, "Purchased Goods & Services"),
    ]

    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"
    STATUS_FLAGGED = "flagged"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending Review"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
        (STATUS_FLAGGED, "Flagged"),
    ]

    # Traceability: never delete a RawRecord that an ActivityRecord points to
    raw_record = models.OneToOneField(
        RawRecord, on_delete=models.PROTECT, null=True, blank=True, related_name="activity"
    )
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="records")

    # GHG classification
    scope = models.IntegerField(choices=SCOPE_CHOICES)
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES)

    # Reporting period. Billing periods don't align with calendar months so
    # we store both ends rather than just a month/year.
    period_start = models.DateField()
    period_end = models.DateField()

    # Quantity — original and normalized
    quantity_value = models.DecimalField(max_digits=20, decimal_places=6)
    quantity_unit = models.CharField(max_length=20)
    normalized_value = models.DecimalField(max_digits=20, decimal_places=6)
    normalized_unit = models.CharField(max_length=20)

    # Context fields — interpreted differently per source type
    location = models.CharField(max_length=500, blank=True)   # plant / meter / office
    vendor = models.CharField(max_length=255, blank=True)     # utility / carrier / supplier
    description = models.TextField(blank=True)
    # Preserve source-specific fields that don't have a canonical column
    # (e.g. SAP cost center, Concur trip ID, utility tariff code)
    extra = models.JSONField(default=dict, blank=True)

    # Review workflow
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING)
    review_note = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="reviewed_records"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    # True if any field was changed after initial ingestion (triggers re-review)
    is_edited = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-period_start"]

    def __str__(self):
        return f"{self.get_category_display()} | {self.period_start} | {self.normalized_value} {self.normalized_unit}"


class AuditEvent(models.Model):
    """
    Append-only log. One row per state change on an ActivityRecord.
    Never updated, never deleted. For edits, diff contains the before/after
    values so you can reconstruct history without a separate history table.
    """
    EVENT_INGESTED = "ingested"
    EVENT_APPROVED = "approved"
    EVENT_REJECTED = "rejected"
    EVENT_FLAGGED = "flagged"
    EVENT_EDITED = "edited"
    EVENT_NOTE = "note_added"
    EVENT_CHOICES = [
        (EVENT_INGESTED, "Ingested"),
        (EVENT_APPROVED, "Approved"),
        (EVENT_REJECTED, "Rejected"),
        (EVENT_FLAGGED, "Flagged"),
        (EVENT_EDITED, "Edited"),
        (EVENT_NOTE, "Note Added"),
    ]

    record = models.ForeignKey(ActivityRecord, on_delete=models.CASCADE, related_name="audit_trail")
    event = models.CharField(max_length=20, choices=EVENT_CHOICES)
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    # For EVENT_EDITED: {"field": "quantity_value", "before": "4500", "after": "4600"}
    diff = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["timestamp"]

    def __str__(self):
        return f"{self.record_id} {self.event} @ {self.timestamp:%Y-%m-%d %H:%M}"


class Anomaly(models.Model):
    """
    Something the parser or normalizer found suspicious. Linked to the
    IngestionRun so analysts can see all issues from one upload together,
    and optionally to the specific RawRecord and ActivityRecord.

    Anomalies don't block ingestion — a row with an anomaly still produces
    an ActivityRecord with status=flagged. The analyst decides what to do.
    """
    TYPE_MISSING_FIELD = "missing_field"
    TYPE_UNKNOWN_UNIT = "unknown_unit"
    TYPE_ZERO_QTY = "zero_qty"
    TYPE_OUTLIER = "outlier"
    TYPE_DUPLICATE = "duplicate"
    TYPE_PARSE_ERROR = "parse_error"
    TYPE_UNKNOWN_CODE = "unknown_code"
    TYPE_CHOICES = [
        (TYPE_MISSING_FIELD, "Missing Required Field"),
        (TYPE_UNKNOWN_UNIT, "Unrecognized Unit"),
        (TYPE_ZERO_QTY, "Zero or Negative Quantity"),
        (TYPE_OUTLIER, "Statistical Outlier"),
        (TYPE_DUPLICATE, "Possible Duplicate"),
        (TYPE_PARSE_ERROR, "Parse Error"),
        (TYPE_UNKNOWN_CODE, "Unrecognized Code"),
    ]
    SEV_LOW = "low"
    SEV_MEDIUM = "medium"
    SEV_HIGH = "high"
    SEV_CHOICES = [
        (SEV_LOW, "Low"),
        (SEV_MEDIUM, "Medium"),
        (SEV_HIGH, "High"),
    ]

    run = models.ForeignKey(IngestionRun, on_delete=models.CASCADE, related_name="anomalies")
    raw_record = models.ForeignKey(RawRecord, on_delete=models.SET_NULL, null=True, blank=True, related_name="anomalies")
    activity_record = models.ForeignKey(ActivityRecord, on_delete=models.SET_NULL, null=True, blank=True, related_name="anomalies")
    anomaly_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    severity = models.CharField(max_length=10, choices=SEV_CHOICES)
    message = models.TextField()
    detail = models.JSONField(default=dict, blank=True)
    resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.anomaly_type} ({self.severity}) run {self.run_id}"
