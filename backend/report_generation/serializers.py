from django.db.models import Q
from rest_framework import serializers

from ifrs_assets.models import (
    IFRSAssetBundle,
    StyleAssetBundle,
)
from payloads.models import PayloadManifest
from payloads.services import (
    PayloadStorageError,
    resolve_payload_directory,
)

from .models import (
    GenerationWarning,
    ReportGenerationJob,
    ReportSection,
    ReportVersion,
)


class GenerationWarningSerializer(
    serializers.ModelSerializer
):
    class Meta:
        model = GenerationWarning
        fields = [
            "id",
            "job",
            "stage",
            "warning_type",
            "message",
            "details",
            "created_at",
        ]


class ReportGenerationJobSerializer(
    serializers.ModelSerializer
):
    job_id = serializers.UUIDField(
        source="id",
        read_only=True,
    )
    bank_code = serializers.CharField(
        source="bank.code",
        read_only=True,
    )
    bank_name = serializers.CharField(
        source="bank.name",
        read_only=True,
    )
    payload_manifest_version = serializers.CharField(
        source="payload_manifest.version",
        read_only=True,
    )
    ifrs_asset_version = serializers.CharField(
        source="ifrs_asset_bundle.version",
        read_only=True,
    )
    style_asset_version = serializers.CharField(
        source="style_asset_bundle.version",
        read_only=True,
    )

    class Meta:
        model = ReportGenerationJob
        fields = [
            "job_id",
            "bank",
            "bank_code",
            "bank_name",
            "reporting_year",
            "payload_manifest",
            "payload_manifest_version",
            "ifrs_asset_bundle",
            "ifrs_asset_version",
            "style_asset_bundle",
            "style_asset_version",
            "status",
            "current_stage",
            "progress_percent",
            "warning_count",
            "error_message",
            "celery_task_id",
            "config",
            "final_summary",
            "created_at",
            "started_at",
            "completed_at",
        ]


class StartReportGenerationJobSerializer(
    serializers.Serializer
):
    bank_code = serializers.CharField()
    reporting_year = serializers.IntegerField()
    payload_manifest_id = serializers.IntegerField()

    ifrs_asset_version = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
    )
    style_asset_version = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
    )

    output_formats = serializers.ListField(
        child=serializers.ChoiceField(
            choices=["markdown", "pdf"]
        ),
        default=["markdown"],
    )

    max_revisions = serializers.IntegerField(
        default=2,
        min_value=0,
        max_value=5,
    )

    def _resolve_ifrs_asset_bundle(
        self,
        version: str | None,
    ) -> IFRSAssetBundle:
        queryset = IFRSAssetBundle.objects.filter(
            status=IFRSAssetBundle.Status.ACTIVE
        )

        if version:
            try:
                return queryset.get(version=version)
            except IFRSAssetBundle.DoesNotExist as exc:
                raise serializers.ValidationError(
                    {
                        "ifrs_asset_version": (
                            "IFRS asset bundle not found "
                            "or inactive."
                        )
                    }
                ) from exc

        bundle = queryset.order_by("-created_at").first()

        if bundle is None:
            raise serializers.ValidationError(
                {
                    "ifrs_asset_version": (
                        "No active IFRS asset bundle exists."
                    )
                }
            )

        return bundle

    def _resolve_style_asset_bundle(
        self,
        *,
        payload_manifest: PayloadManifest,
        version: str | None,
    ) -> StyleAssetBundle:
        queryset = StyleAssetBundle.objects.filter(
            status=StyleAssetBundle.Status.ACTIVE
        ).filter(
            Q(bank=payload_manifest.bank)
            | Q(bank__isnull=True)
        )

        if version:
            try:
                return queryset.get(version=version)
            except StyleAssetBundle.DoesNotExist as exc:
                raise serializers.ValidationError(
                    {
                        "style_asset_version": (
                            "Style asset bundle not found, "
                            "inactive, or assigned to another "
                            "bank."
                        )
                    }
                ) from exc

        bank_specific_bundle = (
            queryset
            .filter(bank=payload_manifest.bank)
            .order_by("-created_at")
            .first()
        )

        if bank_specific_bundle is not None:
            return bank_specific_bundle

        generic_bundle = (
            queryset
            .filter(bank__isnull=True)
            .order_by("-created_at")
            .first()
        )

        if generic_bundle is None:
            raise serializers.ValidationError(
                {
                    "style_asset_version": (
                        "No active bank-specific or generic "
                        "style asset bundle exists."
                    )
                }
            )

        return generic_bundle

    def validate(self, attrs):
        bank_code = attrs["bank_code"].strip().upper()
        reporting_year = attrs["reporting_year"]
        payload_manifest_id = attrs[
            "payload_manifest_id"
        ]

        try:
            payload_manifest = (
                PayloadManifest.objects
                .select_related(
                    "bank",
                    "source_batch",
                )
                .get(
                    id=payload_manifest_id,
                    bank__code__iexact=bank_code,
                    reporting_year=reporting_year,
                    status=(
                        PayloadManifest.Status.AVAILABLE
                    ),
                )
            )
        except PayloadManifest.DoesNotExist as exc:
            raise serializers.ValidationError(
                {
                    "payload_manifest_id": (
                        "No available payload manifest "
                        "matches this bank and reporting year."
                    )
                }
            ) from exc

        try:
            resolve_payload_directory(payload_manifest)
        except PayloadStorageError as exc:
            raise serializers.ValidationError(
                {
                    "payload_manifest_id": str(exc),
                }
            ) from exc

        ifrs_asset_bundle = (
            self._resolve_ifrs_asset_bundle(
                attrs.get("ifrs_asset_version")
            )
        )

        style_asset_bundle = (
            self._resolve_style_asset_bundle(
                payload_manifest=payload_manifest,
                version=attrs.get(
                    "style_asset_version"
                ),
            )
        )

        attrs["bank_code"] = bank_code
        attrs["payload_manifest"] = payload_manifest
        attrs["bank"] = payload_manifest.bank
        attrs["ifrs_asset_bundle"] = (
            ifrs_asset_bundle
        )
        attrs["style_asset_bundle"] = (
            style_asset_bundle
        )

        return attrs

    def create(self, validated_data):
        request = self.context["request"]

        output_formats = validated_data.get(
            "output_formats",
            ["markdown"],
        )
        max_revisions = validated_data.get(
            "max_revisions",
            2,
        )

        return ReportGenerationJob.objects.create(
            bank=validated_data["bank"],
            reporting_year=validated_data[
                "reporting_year"
            ],
            payload_manifest=validated_data[
                "payload_manifest"
            ],
            ifrs_asset_bundle=validated_data[
                "ifrs_asset_bundle"
            ],
            style_asset_bundle=validated_data[
                "style_asset_bundle"
            ],
            created_by=request.user,
            status=ReportGenerationJob.Status.QUEUED,
            current_stage="queued",
            progress_percent=0,
            config={
                "output_formats": output_formats,
                "max_revisions": max_revisions,
                "final_failures_as_warnings": True,
            },
        )


class ReportVersionSerializer(
    serializers.ModelSerializer
):
    bank_code = serializers.CharField(
        source="bank.code",
        read_only=True,
    )
    bank_name = serializers.CharField(
        source="bank.name",
        read_only=True,
    )
    job_id = serializers.UUIDField(
        source="job.id",
        read_only=True,
    )

    class Meta:
        model = ReportVersion
        fields = [
            "id",
            "job",
            "job_id",
            "bank",
            "bank_code",
            "bank_name",
            "reporting_year",
            "version_number",
            "status",
            "created_by",
            "created_at",
        ]


class ReportSectionSerializer(
    serializers.ModelSerializer
):
    class Meta:
        model = ReportSection
        fields = [
            "id",
            "report_version",
            "section_key",
            "status",
            "score",
            "revision_count",
            "created_at",
        ]