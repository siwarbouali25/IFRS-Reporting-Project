from django.contrib import admin

from .models import (
    GenerationWarning,
    ReportGenerationJob,
    ReportSection,
    ReportVersion,
)


class GenerationWarningInline(admin.TabularInline):
    model = GenerationWarning
    extra = 0
    readonly_fields = ("created_at",)


@admin.register(ReportGenerationJob)
class ReportGenerationJobAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "bank",
        "reporting_year",
        "status",
        "current_stage",
        "progress_percent",
        "warning_count",
        "created_by",
        "created_at",
    )
    search_fields = ("id", "bank__code", "bank__name", "current_stage")
    list_filter = ("status", "bank", "reporting_year", "created_at")
    readonly_fields = (
        "id",
        "created_at",
        "started_at",
        "completed_at",
    )
    inlines = [GenerationWarningInline]


@admin.register(GenerationWarning)
class GenerationWarningAdmin(admin.ModelAdmin):
    list_display = ("job", "stage", "warning_type", "created_at")
    search_fields = ("job__id", "stage", "warning_type", "message")
    list_filter = ("stage", "warning_type", "created_at")


@admin.register(ReportVersion)
class ReportVersionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "bank",
        "reporting_year",
        "version_number",
        "status",
        "created_at",
    )
    search_fields = ("id", "bank__code", "bank__name")
    list_filter = ("status", "bank", "reporting_year")


@admin.register(ReportSection)
class ReportSectionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "report_version",
        "section_key",
        "status",
        "score",
        "revision_count",
        "created_at",
    )
    search_fields = ("id", "section_key", "report_version__bank__code")
    list_filter = ("status", "section_key", "created_at")