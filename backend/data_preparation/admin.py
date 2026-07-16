from django.contrib import admin

from .models import (
    DataPreparationIssue,
    DataPreparationJob,
    DataUploadBatch,
    PreparedPayloadArtifact,
    UploadedDataFile,
)


class UploadedDataFileInline(admin.TabularInline):
    model = UploadedDataFile
    extra = 0
    readonly_fields = ("uploaded_at", "size_bytes", "checksum_sha256")


class DataPreparationJobInline(admin.TabularInline):
    model = DataPreparationJob
    extra = 0
    readonly_fields = ("created_at", "updated_at", "started_at", "completed_at")


@admin.register(DataUploadBatch)
class DataUploadBatchAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "status", "uploaded_by", "uploaded_files_count", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("id", "name", "original_filename")
    readonly_fields = ("id", "created_at", "updated_at")
    inlines = [UploadedDataFileInline, DataPreparationJobInline]


@admin.register(UploadedDataFile)
class UploadedDataFileAdmin(admin.ModelAdmin):
    list_display = ("original_filename", "batch", "file_type", "size_bytes", "uploaded_at")
    list_filter = ("file_type", "uploaded_at")
    search_fields = ("original_filename", "batch__id")
    readonly_fields = ("id", "uploaded_at")


@admin.register(DataPreparationJob)
class DataPreparationJobAdmin(admin.ModelAdmin):
    list_display = ("id", "batch", "status", "progress", "total_payloads_generated", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("id", "batch__id", "celery_task_id")
    readonly_fields = ("id", "created_at", "updated_at", "started_at", "completed_at")


@admin.register(PreparedPayloadArtifact)
class PreparedPayloadArtifactAdmin(admin.ModelAdmin):
    list_display = ("filename", "bank_id", "reporting_year", "payload_type", "section_name", "created_at")
    list_filter = ("payload_type", "reporting_year", "created_at")
    search_fields = ("filename", "bank_id", "section_name")
    readonly_fields = ("id", "created_at")


@admin.register(DataPreparationIssue)
class DataPreparationIssueAdmin(admin.ModelAdmin):
    list_display = ("severity", "code", "table_name", "field_name", "is_report_blocking", "created_at")
    list_filter = ("severity", "is_report_blocking", "is_internal_only", "created_at")
    search_fields = ("message", "code", "table_name", "field_name")
    readonly_fields = ("id", "created_at")