from django.contrib import admin

from .models import IFRSAssetBundle, StyleAssetBundle


@admin.register(IFRSAssetBundle)
class IFRSAssetBundleAdmin(admin.ModelAdmin):
    list_display = ("name", "version", "status", "minio_prefix", "created_at")
    search_fields = ("name", "version", "minio_prefix")
    list_filter = ("status",)


@admin.register(StyleAssetBundle)
class StyleAssetBundleAdmin(admin.ModelAdmin):
    list_display = ("name", "version", "bank", "status", "minio_prefix", "created_at")
    search_fields = ("name", "version", "bank__code", "minio_prefix")
    list_filter = ("status", "bank")