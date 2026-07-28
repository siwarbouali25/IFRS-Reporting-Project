import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class ReportGenerationJob(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        PAUSED = "paused", "Paused"
        COMPLETED = "completed", "Completed"
        COMPLETED_WITH_WARNINGS = (
            "completed_with_warnings",
            "Completed with warnings",
        )
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
    pause_requested = models.BooleanField(default=False)
    paused_at = models.DateTimeField(null=True, blank=True)
    langgraph_thread_id = models.CharField(max_length=255, blank=True)
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
        if self.started_at is None:
            self.started_at = timezone.now()
        self.save(update_fields=["status", "current_stage", "started_at"])

    def request_pause(self):
        self.pause_requested = True
        if self.status != self.Status.PAUSED:
            self.current_stage = "pause_requested"
        self.save(update_fields=["pause_requested", "current_stage"])

    def mark_paused(self, *, stage=None, progress_percent=None):
        self.status = self.Status.PAUSED
        self.pause_requested = True
        self.paused_at = timezone.now()
        if stage:
            self.current_stage = stage
        if progress_percent is not None:
            self.progress_percent = progress_percent

        update_fields = [
            "status",
            "pause_requested",
            "paused_at",
            "current_stage",
        ]
        if progress_percent is not None:
            update_fields.append("progress_percent")

        self.save(update_fields=update_fields)

    def resume(self):
        self.pause_requested = False
        self.status = self.Status.RUNNING
        self.current_stage = "resuming"
        self.paused_at = None
        self.save(
            update_fields=[
                "pause_requested",
                "status",
                "current_stage",
                "paused_at",
            ]
        )

    def mark_failed(self, message):
        self.status = self.Status.FAILED
        self.error_message = message
        self.completed_at = timezone.now()
        self.pause_requested = False
        self.paused_at = None
        self.save(
            update_fields=[
                "status",
                "error_message",
                "completed_at",
                "pause_requested",
                "paused_at",
            ]
        )

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
        self.pause_requested = False
        self.paused_at = None
        self.save(
            update_fields=[
                "status",
                "current_stage",
                "progress_percent",
                "warning_count",
                "completed_at",
                "pause_requested",
                "paused_at",
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
        PENDING_REVIEW = "pending_review", "Pending review"
        CHANGES_REQUESTED = "changes_requested", "Changes requested"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
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
        related_name="created_report_versions",
    )
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="submitted_report_versions",
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_report_versions",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("bank", "reporting_year", "version_number")
        ordering = ["bank__code", "-reporting_year", "-version_number"]

    def __str__(self):
        return f"{self.bank.code} - {self.reporting_year} - v{self.version_number}"


class ReportApprovalAction(models.Model):
    class Action(models.TextChoices):
        SUBMITTED = "submitted", "Submitted for review"
        APPROVED = "approved", "Approved"
        CHANGES_REQUESTED = "changes_requested", "Changes requested"
        REJECTED = "rejected", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    report_version = models.ForeignKey(
        ReportVersion,
        on_delete=models.CASCADE,
        related_name="approval_actions",
    )
    action = models.CharField(max_length=40, choices=Action.choices)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="report_approval_actions",
    )
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.report_version_id} - {self.action}"


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