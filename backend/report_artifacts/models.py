import uuid

from django.db import models


class ReportArtifact(models.Model):
    class ArtifactType(models.TextChoices):
        PAYLOAD = "payload", "Payload"
        EVIDENCE_MAP = "evidence_map", "Evidence map"
        COVERAGE = "coverage", "Coverage"
        MISSING_REQUIREMENTS = "missing_requirements", "Missing requirements"
        DISCLOSURE_PLAN = "disclosure_plan", "Disclosure plan"
        DRAFT_SECTION = "draft_section", "Draft section"
        CLAIMS_REGISTER = "claims_register", "Claims register"
        VALIDATION_RESULT = "validation_result", "Validation result"
        APPROVED_SECTION = "approved_section", "Approved section"
        FINAL_MARKDOWN = "final_markdown", "Final Markdown"
        FINAL_PDF = "final_pdf", "Final PDF"
        WARNING_SUMMARY = "warning_summary", "Warning summary"
        AUDIT_SUMMARY = "audit_summary", "Audit summary"
        LOG = "log", "Log"
        ERROR = "error", "Error"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    job = models.ForeignKey(
        "report_generation.ReportGenerationJob",
        on_delete=models.CASCADE,
        related_name="artifacts",
    )

    report_version = models.ForeignKey(
        "report_generation.ReportVersion",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="artifacts",
    )

    artifact_type = models.CharField(max_length=80, choices=ArtifactType.choices)

    bucket = models.CharField(max_length=100)
    object_key = models.CharField(max_length=500)

    content_type = models.CharField(max_length=100, blank=True)
    size_bytes = models.BigIntegerField(null=True, blank=True)
    checksum = models.CharField(max_length=128, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.artifact_type} - {self.object_key}"