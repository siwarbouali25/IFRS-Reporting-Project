import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class ReportGenerationJob(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        COMPLETED_WITH_WARNINGS = "completed_with_warnings", "Completed with warnings"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    bank = models.ForeignKey("organizations.Bank", on_delete=models.CASCADE)
    reporting_year = models.IntegerField()

    payload_manifest = models.ForeignKey(
        "payloads.PayloadManifest",
        on_delete=models.PROTECT,
    )

    ifrs_asset_bundle = models.ForeignKey(
        "ifrs_assets.IFRSAssetBundle",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )

    style_asset_bundle = models.ForeignKey(
        "ifrs_assets.StyleAssetBundle",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    status = models.CharField(
        max_length=40,
        choices=Status.choices,
        default=Status.QUEUED,
    )

    current_stage = models.CharField(max_length=100, default="queued")
    progress_percent = models.IntegerField(default=0)

    warning_count = models.IntegerField(default=0)
    error_message = models.TextField(blank=True)

    celery_task_id = models.CharField(max_length=255, blank=True)
    langgraph_thread_id = models.CharField(max_length=255, blank=True)

    # Example:
    # {
    #   "output_formats": ["markdown", "pdf"],
    #   "max_revisions": 2,
    #   "final_failures_as_warnings": true
    # }
    config = models.JSONField(default=dict)

    final_summary = models.JSONField(default=dict)

    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def mark_running(self):
        self.status = self.Status.RUNNING
        self.current_stage = "starting"
        self.started_at = timezone.now()
        self.save(update_fields=["status", "current_stage", "started_at"])

    def mark_failed(self, message):
        self.status = self.Status.FAILED
        self.error_message = message
        self.completed_at = timezone.now()
        self.save(update_fields=["status", "error_message", "completed_at"])

    def mark_completed(self, warning_count=0):
        self.warning_count = warning_count
        self.status = (
            self.Status.COMPLETED_WITH_WARNINGS
            if warning_count > 0
            else self.Status.COMPLETED
        )
        self.current_stage = "completed"
        self.progress_percent = 100
        self.completed_at = timezone.now()
        self.save(
            update_fields=[
                "status",
                "current_stage",
                "progress_percent",
                "warning_count",
                "completed_at",
            ]
        )

    def __str__(self):
        return f"{self.bank.code} - {self.reporting_year} - {self.status}"


class GenerationWarning(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    job = models.ForeignKey(
        ReportGenerationJob,
        on_delete=models.CASCADE,
        related_name="warnings",
    )

    stage = models.CharField(max_length=100)
    warning_type = models.CharField(max_length=100)
    message = models.TextField()
    details = models.JSONField(default=dict)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.job_id} - {self.stage} - {self.warning_type}"


class ReportVersion(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        APPROVED = "approved", "Approved"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    job = models.OneToOneField(
        ReportGenerationJob,
        on_delete=models.CASCADE,
        related_name="report_version",
    )

    bank = models.ForeignKey("organizations.Bank", on_delete=models.CASCADE)
    reporting_year = models.IntegerField()
    version_number = models.IntegerField()

    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.DRAFT,
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("bank", "reporting_year", "version_number")
        ordering = ["bank__code", "-reporting_year", "-version_number"]

    def __str__(self):
        return f"{self.bank.code} - {self.reporting_year} - v{self.version_number}"


class ReportSection(models.Model):
    class Status(models.TextChoices):
        GENERATED = "generated", "Generated"
        VALIDATION_FAILED = "validation_failed", "Validation failed"
        REVISED = "revised", "Revised"
        APPROVED = "approved", "Approved"
        WARNING = "warning", "Warning"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    report_version = models.ForeignKey(
        ReportVersion,
        on_delete=models.CASCADE,
        related_name="sections",
    )

    section_key = models.CharField(max_length=100)
    status = models.CharField(
        max_length=50,
        choices=Status.choices,
        default=Status.GENERATED,
    )

    score = models.FloatField(null=True, blank=True)
    revision_count = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("report_version", "section_key")
        ordering = ["section_key"]

    def __str__(self):
        return f"{self.report_version} - {self.section_key}"