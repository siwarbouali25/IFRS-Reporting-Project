from rest_framework import serializers

from data_preparation.models import (
    DataPreparationIssue,
    DataPreparationJob,
    DataUploadBatch,
    PreparedPayloadArtifact,
    UploadedDataFile,
)


class UploadedDataFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UploadedDataFile
        fields = [
            "id",
            "original_filename",
            "stored_filename",
            "file_type",
            "size_bytes",
            "checksum_sha256",
            "uploaded_at",
        ]


class PreparedPayloadArtifactSerializer(serializers.ModelSerializer):
    class Meta:
        model = PreparedPayloadArtifact
        fields = [
            "id",
            "bank_id",
            "reporting_year",
            "payload_type",
            "section_name",
            "filename",
            "size_bytes",
            "checksum_sha256",
            "created_at",
        ]


class DataPreparationIssueSerializer(serializers.ModelSerializer):
    class Meta:
        model = DataPreparationIssue
        fields = [
            "id",
            "severity",
            "code",
            "message",
            "table_name",
            "field_name",
            "row_identifier",
            "is_report_blocking",
            "is_internal_only",
            "created_at",
        ]


class DataPreparationJobSerializer(serializers.ModelSerializer):
    payload_artifacts = PreparedPayloadArtifactSerializer(many=True, read_only=True)
    issues = DataPreparationIssueSerializer(many=True, read_only=True)

    class Meta:
        model = DataPreparationJob
        fields = [
            "id",
            "batch",
            "status",
            "progress",
            "started_at",
            "completed_at",
            "raw_input_folder",
            "patched_output_folder",
            "payload_output_folder",
            "log_output_folder",
            "total_payloads_generated",
            "total_section_payloads_generated",
            "error_message",
            "created_at",
            "updated_at",
            "payload_artifacts",
            "issues",
        ]


class DataUploadBatchSerializer(serializers.ModelSerializer):
    uploaded_files = UploadedDataFileSerializer(many=True, read_only=True)
    preparation_jobs = DataPreparationJobSerializer(many=True, read_only=True)

    class Meta:
        model = DataUploadBatch
        fields = [
            "id",
            "name",
            "status",
            "raw_folder",
            "patched_folder",
            "payload_folder",
            "log_folder",
            "original_filename",
            "uploaded_files_count",
            "error_message",
            "created_at",
            "updated_at",
            "uploaded_files",
            "preparation_jobs",
        ]


class DataUploadBatchCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = DataUploadBatch
        fields = ["name"]