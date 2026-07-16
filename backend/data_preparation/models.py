import uuid
from pathlib import Path

from django.conf import settings
from django.db import models


class DataUploadBatch(models.Model):
    class Status(models.TextChoices):
        CREATED = "created", "Created"
        UPLOADED = "uploaded", "Uploaded"
        VALIDATING = "validating", "Validating"
        READY = "ready", "Ready"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    name = models.CharField(max_length=255, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="data_upload_batches",
    )

    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.CREATED,
    )

    raw_folder = models.CharField(max_length=500, blank=True)
    patched_folder = models.CharField(max_length=500, blank=True)
    payload_folder = models.CharField(max_length=500, blank=True)
    log_folder = models.CharField(max_length=500, blank=True)

    original_filename = models.CharField(max_length=255, blank=True)
    uploaded_files_count = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name or self.id} - {self.status}"


def uploaded_data_file_path(instance, filename):
    batch_id = instance.batch_id or "unassigned"
    return f"data_preparation/batches/{batch_id}/raw/{filename}"


class UploadedDataFile(models.Model):
    class FileType(models.TextChoices):
        CSV = "csv", "CSV"
        ZIP = "zip", "ZIP"
        OTHER = "other", "Other"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    batch = models.ForeignKey(
        DataUploadBatch,
        on_delete=models.CASCADE,
        related_name="uploaded_files",
    )

    file = models.FileField(upload_to=uploaded_data_file_path)
    original_filename = models.CharField(max_length=255)
    stored_filename = models.CharField(max_length=255, blank=True)

    file_type = models.CharField(
        max_length=20,
        choices=FileType.choices,
        default=FileType.OTHER,
    )

    size_bytes = models.BigIntegerField(default=0)
    checksum_sha256 = models.CharField(max_length=64, blank=True)

    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["original_filename"]

    def save(self, *args, **kwargs):
        if self.file and not self.stored_filename:
            self.stored_filename = Path(self.file.name).name

        if self.original_filename:
            suffix = self.original_filename.lower().split(".")[-1]
            if suffix == "csv":
                self.file_type = self.FileType.CSV
            elif suffix == "zip":
                self.file_type = self.FileType.ZIP
            else:
                self.file_type = self.FileType.OTHER

        super().save(*args, **kwargs)

    def __str__(self):
        return self.original_filename


class DataPreparationJob(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    batch = models.ForeignKey(
        DataUploadBatch,
        on_delete=models.CASCADE,
        related_name="preparation_jobs",
    )

    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.QUEUED,
    )

    progress = models.PositiveSmallIntegerField(default=0)

    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    raw_input_folder = models.CharField(max_length=500, blank=True)
    patched_output_folder = models.CharField(max_length=500, blank=True)
    payload_output_folder = models.CharField(max_length=500, blank=True)
    log_output_folder = models.CharField(max_length=500, blank=True)

    total_payloads_generated = models.PositiveIntegerField(default=0)
    total_section_payloads_generated = models.PositiveIntegerField(default=0)

    celery_task_id = models.CharField(max_length=255, blank=True)
    error_message = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Job {self.id} - {self.status}"


def prepared_payload_file_path(instance, filename):
    job_id = instance.job_id or "unassigned"
    return f"data_preparation/jobs/{job_id}/payloads/{filename}"


class PreparedPayloadArtifact(models.Model):
    class PayloadType(models.TextChoices):
        FULL = "full", "Full payload"
        SECTION = "section", "Section payload"
        AUDIT = "audit", "Audit artifact"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    job = models.ForeignKey(
        DataPreparationJob,
        on_delete=models.CASCADE,
        related_name="payload_artifacts",
    )

    bank_id = models.CharField(max_length=50)
    reporting_year = models.PositiveIntegerField(default=2024)

    payload_type = models.CharField(
        max_length=30,
        choices=PayloadType.choices,
        default=PayloadType.FULL,
    )

    section_name = models.CharField(max_length=100, blank=True)
    filename = models.CharField(max_length=255)
    file = models.FileField(upload_to=prepared_payload_file_path)

    size_bytes = models.BigIntegerField(default=0)
    checksum_sha256 = models.CharField(max_length=64, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["bank_id", "payload_type", "section_name"]
        indexes = [
            models.Index(fields=["bank_id", "reporting_year"]),
            models.Index(fields=["payload_type"]),
        ]

    def __str__(self):
        return self.filename


class DataPreparationIssue(models.Model):
    class Severity(models.TextChoices):
        INFO = "info", "Info"
        WARNING = "warning", "Warning"
        ERROR = "error", "Error"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    job = models.ForeignKey(
        DataPreparationJob,
        on_delete=models.CASCADE,
        related_name="issues",
    )

    severity = models.CharField(
        max_length=20,
        choices=Severity.choices,
        default=Severity.INFO,
    )

    code = models.CharField(max_length=100, blank=True)
    message = models.TextField()

    table_name = models.CharField(max_length=100, blank=True)
    field_name = models.CharField(max_length=100, blank=True)
    row_identifier = models.CharField(max_length=255, blank=True)

    is_report_blocking = models.BooleanField(default=False)
    is_internal_only = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["severity", "created_at"]

    def __str__(self):
        return f"{self.severity}: {self.message[:80]}"