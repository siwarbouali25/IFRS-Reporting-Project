from rest_framework import serializers

from payloads.models import PayloadManifest
from payloads.services import (
    PayloadStorageError,
    resolve_payload_directory,
)

from .models import (
    AssessmentResult,
    RiskAnalysis,
)


def _display_user(user) -> str:
    if user is None:
        return ""

    full_name = ""
    get_full_name = getattr(user, "get_full_name", None)

    if callable(get_full_name):
        full_name = (get_full_name() or "").strip()

    return (
        full_name
        or getattr(user, "full_name", "")
        or getattr(user, "name", "")
        or getattr(user, "email", "")
        or getattr(user, "username", "")
        or str(user)
    )


class StartRiskAnalysisSerializer(
    serializers.Serializer
):
    """
    Starts an analysis from a prepared PayloadManifest.

    `force=true` creates a fresh deterministic analysis even when a ready
    analysis already exists for the same user and manifest.
    """

    payload_manifest_id = serializers.IntegerField()
    force = serializers.BooleanField(
        required=False,
        default=False,
    )

    def validate_payload_manifest_id(
        self,
        value: int,
    ) -> int:
        try:
            manifest = (
                PayloadManifest.objects
                .select_related(
                    "bank",
                    "source_batch",
                )
                .get(
                    id=value,
                    status=PayloadManifest.Status.AVAILABLE,
                )
            )
        except PayloadManifest.DoesNotExist as exc:
            raise serializers.ValidationError(
                "The selected prepared dataset is not available."
            ) from exc

        try:
            resolve_payload_directory(manifest)
        except PayloadStorageError as exc:
            raise serializers.ValidationError(
                str(exc)
            ) from exc

        self.context["payload_manifest"] = manifest
        return value


class RiskAnalysisListSerializer(
    serializers.ModelSerializer
):
    payload_manifest_id = serializers.IntegerField(
        source="payload_manifest.id",
        read_only=True,
        allow_null=True,
    )
    payload_manifest_version = serializers.CharField(
        source="payload_manifest.version",
        read_only=True,
        allow_null=True,
    )
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = RiskAnalysis
        fields = [
            "id",
            "payload_manifest_id",
            "payload_manifest_version",
            "bank_id",
            "bank_name",
            "reporting_year",
            "status",
            "created_by_name",
            "created_at",
        ]

    def get_created_by_name(
        self,
        obj: RiskAnalysis,
    ) -> str:
        return _display_user(obj.uploaded_by)


class RiskAnalysisDetailSerializer(
    serializers.ModelSerializer
):
    payload_manifest_id = serializers.IntegerField(
        source="payload_manifest.id",
        read_only=True,
        allow_null=True,
    )
    payload_manifest_version = serializers.CharField(
        source="payload_manifest.version",
        read_only=True,
        allow_null=True,
    )
    created_by = serializers.ReadOnlyField(
        source="uploaded_by.pk",
        allow_null=True,
    )
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = RiskAnalysis
        fields = [
            "id",
            "payload_manifest_id",
            "payload_manifest_version",
            "bank_id",
            "bank_name",
            "reporting_year",
            "status",
            "processed",
            "validation_warnings",
            "error_message",
            "created_by",
            "created_by_name",
            "created_at",
            "updated_at",
        ]

    def get_created_by_name(
        self,
        obj: RiskAnalysis,
    ) -> str:
        return _display_user(obj.uploaded_by)


class AssessmentResultSerializer(
    serializers.ModelSerializer
):
    class Meta:
        model = AssessmentResult
        fields = [
            "id",
            "assessment_text",
            "recommendations",
            "avoid",
            "evidence",
            "model_used",
            "is_fallback",
            "created_at",
        ]
