from django.contrib import admin

from .models import AssessmentResult, RiskAnalysis


@admin.register(RiskAnalysis)
class RiskAnalysisAdmin(admin.ModelAdmin):
    list_display = ["id", "bank_id", "bank_name", "reporting_year", "status", "uploaded_by", "created_at"]
    list_filter = ["status"]
    search_fields = ["bank_id", "bank_name", "original_filename"]
    readonly_fields = ["id", "created_at", "updated_at"]


@admin.register(AssessmentResult)
class AssessmentResultAdmin(admin.ModelAdmin):
    list_display = ["id", "analysis", "model_used", "is_fallback", "created_at"]
    list_filter = ["is_fallback", "model_used"]
    readonly_fields = ["id", "created_at"]
