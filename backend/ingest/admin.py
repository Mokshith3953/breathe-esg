from django.contrib import admin
from .models import Tenant, DataSource, IngestionRun, RawRecord, ActivityRecord, AuditEvent, Anomaly

admin.site.register(Tenant)
admin.site.register(DataSource)

@admin.register(IngestionRun)
class IngestionRunAdmin(admin.ModelAdmin):
    list_display = ["id", "data_source", "uploaded_at", "status", "rows_parsed", "rows_errored"]
    list_filter = ["status", "data_source__source_type"]

@admin.register(ActivityRecord)
class ActivityRecordAdmin(admin.ModelAdmin):
    list_display = ["id", "category", "scope", "period_start", "normalized_value", "normalized_unit", "status"]
    list_filter = ["status", "scope", "category"]
    search_fields = ["location", "vendor", "description"]

@admin.register(Anomaly)
class AnomalyAdmin(admin.ModelAdmin):
    list_display = ["id", "anomaly_type", "severity", "message", "resolved", "created_at"]
    list_filter = ["anomaly_type", "severity", "resolved"]

admin.site.register(RawRecord)
admin.site.register(AuditEvent)
