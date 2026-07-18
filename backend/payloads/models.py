from django.conf import settings
from django.db import models


class PayloadManifest(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = "available", "Available"
        INVALID = "invalid", "Invalid"
        ARCHIVED = "archived", "Archived"

    class StorageBackend(models.TextChoices):
        LOCAL = "local", "Local"
        MINIO = "minio", "MinIO"

    bank = models.ForeignKey(
        "organizations.Bank",
        on_delete=models.CASCADE,
        related_name="payload_manifests",
    )

    source_batch = models.ForeignKey(
        "data_preparation.DataUploadBatch",
        on_delete=models.PROTECT,
        related_name="payload_manifests",
        null=True,
        blank=True,
    )

    reporting_year = models.IntegerField()
    version = models.CharField(max_length=50)

    storage_backend = models.CharField(
        max_length=20,
        choices=StorageBackend.choices,
        default=StorageBackend.LOCAL,
    )

    # Used while files still exist locally.
    local_folder = models.CharField(
        max_length=1000,
        blank=True,
    )

    # Used after automatic MinIO storage is connected.
    minio_prefix = models.CharField(
        max_length=500,
        blank=True,
    )

    source_manifest_path = models.CharField(
        max_length=1000,
        blank=True,
    )

    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.AVAILABLE,
    )

    checksum = models.CharField(max_length=128, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = (
            "bank",
            "reporting_year",
            "version",
        )
        ordering = [
            "bank__code",
            "-reporting_year",
            "-created_at",
        ]

    def __str__(self):
        return (
            f"{self.bank.code} - "
            f"{self.reporting_year} - "
            f"{self.version}"
        )