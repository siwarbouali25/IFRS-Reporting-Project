from django.contrib import admin

from .models import PayloadManifest


@admin.register(PayloadManifest)
class PayloadManifestAdmin(admin.ModelAdmin):
    list_display = (
        "bank",
        "reporting_year",
        "version",
        "status",
        "minio_prefix",
        "created_at",
    )
    search_fields = ("bank__code", "bank__name", "version", "minio_prefix")
    list_filter = ("status", "reporting_year", "bank")