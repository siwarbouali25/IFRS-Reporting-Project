from rest_framework import serializers

from .models import ReportArtifact


class ReportArtifactSerializer(serializers.ModelSerializer):
    job_id = serializers.UUIDField(source="job.id", read_only=True)

    class Meta:
        model = ReportArtifact
        fields = [
            "id",
            "job",
            "job_id",
            "report_version",
            "artifact_type",
            "bucket",
            "object_key",
            "content_type",
            "size_bytes",
            "checksum",
            "created_at",
        ]