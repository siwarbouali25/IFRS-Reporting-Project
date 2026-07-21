import uuid

from django.conf import settings
from django.db import models


class RiskAnalysis(models.Model):
    """
    One risk-analysis result generated from an available PayloadManifest.

    Legacy fields are kept temporarily so existing database rows remain
    readable. New analyses are linked to `payload_manifest`; the prepared
    source files remain in the payload storage layer rather than being
    duplicated in PostgreSQL.
    """

    STATUS_PENDING = "pending"
    STATUS_READY = "ready"
    STATUS_FAILED = "failed"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_READY, "Ready"),
        (STATUS_FAILED, "Failed"),
    ]

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="risk_analyses",
    )

    payload_manifest = models.ForeignKey(
        "payloads.PayloadManifest",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="risk_analyses",
    )

    # Legacy snapshots retained for existing rows and easy audit exports.
    original_filename = models.CharField(
        max_length=255,
        blank=True,
    )
    bank_id = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
    )
    bank_name = models.CharField(
        max_length=255,
        blank=True,
    )
    reporting_year = models.IntegerField(
        null=True,
        blank=True,
        db_index=True,
    )

    # Legacy uploads may still contain raw JSON. New manifest-based
    # analyses leave this empty and keep the source data in MinIO/storage.
    raw_payload = models.JSONField(
        default=dict,
        blank=True,
    )

    processed = models.JSONField(
        null=True,
        blank=True,
    )

    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
    )
    validation_warnings = models.JSONField(
        default=list,
        blank=True,
    )
    error_message = models.TextField(
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )
    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=[
                    "payload_manifest",
                    "status",
                    "created_at",
                ],
                name="risk_manifest_status_idx",
            ),
        ]

    def __str__(self):
        entity = (
            self.bank_name
            or self.bank_id
            or "Unknown institution"
        )
        return (
            f"{entity} · "
            f"{self.reporting_year or '?'} · "
            f"{self.status}"
        )


class AssessmentResult(models.Model):
    """
    Evidence-linked narrative generated for one RiskAnalysis.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    analysis = models.ForeignKey(
        RiskAnalysis,
        on_delete=models.CASCADE,
        related_name="assessments",
    )
    assessment_text = models.TextField()
    recommendations = models.JSONField(
        default=list,
    )
    avoid = models.JSONField(
        default=list,
    )
    evidence = models.JSONField(
        default=list,
    )
    model_used = models.CharField(
        max_length=128,
        blank=True,
    )
    is_fallback = models.BooleanField(
        default=False,
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"Assessment for {self.analysis_id} · "
            f"{self.created_at:%Y-%m-%d %H:%M}"
        )
