from django.db import models


class IFRSAssetBundle(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        ARCHIVED = "archived", "Archived"

    name = models.CharField(max_length=255)
    version = models.CharField(max_length=100, unique=True)

    # Example: ifrs-assets/IFRS-S1-S2/2024/
    minio_prefix = models.CharField(max_length=500)

    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.ACTIVE,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} - {self.version}"


class StyleAssetBundle(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        ARCHIVED = "archived", "Archived"

    name = models.CharField(max_length=255)
    version = models.CharField(max_length=100, unique=True)

    # Optional: style can be generic or bank-specific
    bank = models.ForeignKey(
        "organizations.Bank",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )

    # Example: style-assets/BANK01/style-v1/
    minio_prefix = models.CharField(max_length=500)

    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.ACTIVE,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        if self.bank:
            return f"{self.bank.code} - {self.name} - {self.version}"
        return f"{self.name} - {self.version}"