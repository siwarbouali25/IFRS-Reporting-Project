import uuid

from django.conf import settings
from django.db import models


class RiskAnalysis(models.Model):
    """
    One row per uploaded reporting payload. `raw_payload` is exactly what the
    user uploaded (untouched, for audit/traceability). `processed` is the
    derived bundle — every chart series, KPI and the data-quality/peer/
    sensitivity augmentation — computed by services.process_payload() at
    upload time. Nothing about a specific bank or year is hardcoded; the
    processor reads whatever is in raw_payload.
    """

    STATUS_PENDING = "pending"
    STATUS_READY = "ready"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_READY, "Ready"),
        (STATUS_FAILED, "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    original_filename = models.CharField(max_length=255, blank=True)
    bank_id = models.CharField(max_length=64, blank=True, db_index=True)
    bank_name = models.CharField(max_length=255, blank=True)
    reporting_year = models.IntegerField(null=True, blank=True)

    raw_payload = models.JSONField()
    processed = models.JSONField(null=True, blank=True)

    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING)
    validation_warnings = models.JSONField(default=list, blank=True)
    error_message = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.bank_id or 'unknown'} · {self.reporting_year or '?'} · {self.status}"


class AssessmentResult(models.Model):
    """
    A generated LLM assessment for a given RiskAnalysis. Kept separate from
    RiskAnalysis so a user can regenerate the narrative (e.g. after a prompt
    tweak) without reprocessing the whole payload.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    analysis = models.ForeignKey(
        RiskAnalysis, on_delete=models.CASCADE, related_name="assessments"
    )
    assessment_text = models.TextField()
    recommendations = models.JSONField(default=list)
    avoid = models.JSONField(default=list)
    evidence = models.JSONField(default=list)
    model_used = models.CharField(max_length=64, blank=True)
    is_fallback = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
