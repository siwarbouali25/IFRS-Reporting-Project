from django.db import models


class Bank(models.Model):
    code = models.CharField(max_length=50, unique=True)  # Example: BANK01
    name = models.CharField(max_length=255)
    country = models.CharField(max_length=100, blank=True)
    sector = models.CharField(max_length=100, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} - {self.name}"