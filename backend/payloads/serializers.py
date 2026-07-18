from rest_framework import serializers

from .models import PayloadManifest


class PayloadManifestSerializer(serializers.ModelSerializer):
    bank_code = serializers.CharField(
        source="bank.code",
        read_only=True,
    )
    bank_name = serializers.CharField(
        source="bank.name",
        read_only=True,
    )
    source_batch_id = serializers.UUIDField(
        source="source_batch.id",
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = PayloadManifest
        fields = [
            "id",
            "bank",
            "bank_code",
            "bank_name",
            "source_batch_id",
            "reporting_year",
            "version",
            "storage_backend",
            "minio_prefix",
            "status",
            "checksum",
            "created_at",
        ]
        read_only_fields = fields