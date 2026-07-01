from django.contrib import admin

from .models import ReportArtifact


@admin.register(ReportArtifact)
class ReportArtifactAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "job",
        "artifact_type",
        "bucket",
        "object_key",
        "content_type",
        "created_at",
    )
    search_fields = ("id", "job__id", "artifact_type", "bucket", "object_key")
    list_filter = ("artifact_type", "bucket", "created_at")