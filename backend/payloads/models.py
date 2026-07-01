from django.conf import settings
from django.db import models


class PayloadManifest(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = "available", "Available"
        INVALID = "invalid", "Invalid"
        ARCHIVED = "archived", "Archived"

    bank = models.ForeignKey("organizations.Bank", on_delete=models.CASCADE)
    reporting_year = models.IntegerField()
    version = models.CharField(max_length=50)  # Example: v1

    # MinIO prefix where the clean payload files are stored
    # Example: payloads/BANK01/2024/v1/
    minio_prefix = models.CharField(max_length=500)

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
        unique_together = ("bank", "reporting_year", "version")
        ordering = ["bank__code", "-reporting_year", "-created_at"]

    def __str__(self):
        return f"{self.bank.code} - {self.reporting_year} - {self.version}"