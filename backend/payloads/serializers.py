from rest_framework import serializers

from .models import PayloadManifest


class PayloadManifestSerializer(serializers.ModelSerializer):
    bank_code = serializers.CharField(source="bank.code", read_only=True)
    bank_name = serializers.CharField(source="bank.name", read_only=True)

    class Meta:
        model = PayloadManifest
        fields = [
            "id",
            "bank",
            "bank_code",
            "bank_name",
            "reporting_year",
            "version",
            "minio_prefix",
            "status",
            "checksum",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]