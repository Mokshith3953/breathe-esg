from django.contrib.auth.models import User
from rest_framework import serializers
from .models import (
    Tenant, DataSource, IngestionRun, RawRecord,
    ActivityRecord, AuditEvent, Anomaly,
)


class TenantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tenant
        fields = ["id", "name", "slug", "created_at"]


class DataSourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = DataSource
        fields = ["id", "tenant", "source_type", "name", "config", "created_at"]


class IngestionRunSerializer(serializers.ModelSerializer):
    data_source_name = serializers.CharField(source="data_source.name", read_only=True)
    source_type = serializers.CharField(source="data_source.source_type", read_only=True)
    uploaded_by_name = serializers.SerializerMethodField()

    class Meta:
        model = IngestionRun
        fields = [
            "id", "data_source", "data_source_name", "source_type",
            "uploaded_by", "uploaded_by_name", "uploaded_at",
            "original_filename", "file_hash",
            "status", "rows_parsed", "rows_errored", "error_log",
        ]

    def get_uploaded_by_name(self, obj):
        if obj.uploaded_by:
            return obj.uploaded_by.get_full_name() or obj.uploaded_by.username
        return None


class RawRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = RawRecord
        fields = ["id", "run", "row_index", "raw_data", "parse_error", "created_at"]


class AuditEventSerializer(serializers.ModelSerializer):
    actor_name = serializers.SerializerMethodField()

    class Meta:
        model = AuditEvent
        fields = ["id", "event", "actor", "actor_name", "timestamp", "diff"]

    def get_actor_name(self, obj):
        if obj.actor:
            return obj.actor.get_full_name() or obj.actor.username
        return "System"


class AnomalySerializer(serializers.ModelSerializer):
    class Meta:
        model = Anomaly
        fields = [
            "id", "run", "raw_record", "activity_record",
            "anomaly_type", "severity", "message", "detail",
            "resolved", "created_at",
        ]


class ActivityRecordSerializer(serializers.ModelSerializer):
    audit_trail = AuditEventSerializer(many=True, read_only=True)
    anomalies = AnomalySerializer(many=True, read_only=True)
    source_type = serializers.SerializerMethodField()
    reviewed_by_name = serializers.SerializerMethodField()

    class Meta:
        model = ActivityRecord
        fields = [
            "id", "tenant", "scope", "category",
            "period_start", "period_end",
            "quantity_value", "quantity_unit",
            "normalized_value", "normalized_unit",
            "location", "vendor", "description", "extra",
            "status", "review_note", "reviewed_by", "reviewed_by_name", "reviewed_at",
            "is_edited", "created_at", "updated_at",
            "source_type", "audit_trail", "anomalies",
        ]
        read_only_fields = [
            "id", "tenant", "scope", "category",
            "period_start", "period_end",
            "quantity_value", "quantity_unit",
            "normalized_value", "normalized_unit",
            "is_edited", "created_at", "updated_at",
            "source_type", "audit_trail", "anomalies",
            "reviewed_by", "reviewed_by_name", "reviewed_at",
        ]

    def get_source_type(self, obj):
        if obj.raw_record:
            return obj.raw_record.run.data_source.source_type
        return None

    def get_reviewed_by_name(self, obj):
        if obj.reviewed_by:
            return obj.reviewed_by.get_full_name() or obj.reviewed_by.username
        return None


class ActivityRecordListSerializer(serializers.ModelSerializer):
    """Lighter serializer for list views — no audit trail or anomaly nesting."""
    source_type = serializers.SerializerMethodField()
    anomaly_count = serializers.SerializerMethodField()

    class Meta:
        model = ActivityRecord
        fields = [
            "id", "scope", "category",
            "period_start", "period_end",
            "quantity_value", "quantity_unit",
            "normalized_value", "normalized_unit",
            "location", "vendor", "description",
            "status", "review_note",
            "is_edited", "created_at",
            "source_type", "anomaly_count",
        ]

    def get_source_type(self, obj):
        if obj.raw_record:
            return obj.raw_record.run.data_source.source_type
        return None

    def get_anomaly_count(self, obj):
        return obj.anomalies.count()


class DashboardStatsSerializer(serializers.Serializer):
    total_records = serializers.IntegerField()
    pending = serializers.IntegerField()
    approved = serializers.IntegerField()
    rejected = serializers.IntegerField()
    flagged = serializers.IntegerField()
    anomaly_count = serializers.IntegerField()
    scope_breakdown = serializers.DictField()
    category_breakdown = serializers.DictField()
    recent_runs = IngestionRunSerializer(many=True)
