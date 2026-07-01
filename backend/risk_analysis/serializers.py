from rest_framework import serializers

from .models import AssessmentResult, RiskAnalysis


class RiskAnalysisUploadSerializer(serializers.Serializer):
    """
    Accepts a single JSON file upload (multipart) under the field name
    `file`. We don't deserialize it into a fixed schema — the payload is
    arbitrary JSON, validated by validators.validate_payload at view level.
    """
    file = serializers.FileField()


class RiskAnalysisListSerializer(serializers.ModelSerializer):
    class Meta:
        model = RiskAnalysis
        fields = [
            "id", "original_filename", "bank_id", "bank_name",
            "reporting_year", "status", "created_at",
        ]


class RiskAnalysisDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = RiskAnalysis
        fields = [
            "id", "original_filename", "bank_id", "bank_name", "reporting_year",
            "status", "processed", "validation_warnings", "error_message",
            "created_at", "updated_at",
        ]


class AssessmentResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssessmentResult
        fields = [
            "id", "assessment_text", "recommendations", "avoid",
            "evidence", "model_used", "is_fallback", "created_at",
        ]
