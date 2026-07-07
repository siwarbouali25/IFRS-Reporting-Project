from rest_framework import serializers

from ifrs_assets.models import IFRSAssetBundle, StyleAssetBundle
from payloads.models import PayloadManifest

from .models import GenerationWarning, ReportGenerationJob, ReportSection, ReportVersion


class GenerationWarningSerializer(serializers.ModelSerializer):
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


class ReportGenerationJobSerializer(serializers.ModelSerializer):
    job_id = serializers.UUIDField(source="id", read_only=True)
    bank_code = serializers.CharField(source="bank.code", read_only=True)
    bank_name = serializers.CharField(source="bank.name", read_only=True)
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


class StartReportGenerationJobSerializer(serializers.Serializer):
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
        child=serializers.ChoiceField(choices=["markdown", "pdf"]),
        default=["markdown"],
    )

    max_revisions = serializers.IntegerField(default=2, min_value=0, max_value=5)

    def validate(self, attrs):
        bank_code = attrs["bank_code"]
        reporting_year = attrs["reporting_year"]
        payload_manifest_id = attrs["payload_manifest_id"]

        try:
            payload_manifest = PayloadManifest.objects.select_related("bank").get(
                id=payload_manifest_id,
                bank__code=bank_code,
                reporting_year=reporting_year,
                status=PayloadManifest.Status.AVAILABLE,
            )
        except PayloadManifest.DoesNotExist:
            raise serializers.ValidationError(
                "No available payload manifest found for this bank/year/version."
            )

        ifrs_asset_version = attrs.get("ifrs_asset_version")
        style_asset_version = attrs.get("style_asset_version")

        if ifrs_asset_version:
            try:
                ifrs_asset_bundle = IFRSAssetBundle.objects.get(
                    version=ifrs_asset_version,
                    status=IFRSAssetBundle.Status.ACTIVE,
                )
            except IFRSAssetBundle.DoesNotExist:
                raise serializers.ValidationError(
                    "IFRS asset bundle not found or inactive."
                )
        else:
            ifrs_asset_bundle = (
                IFRSAssetBundle.objects
                .filter(status=IFRSAssetBundle.Status.ACTIVE)
                .latest("created_at")
            )

        if style_asset_version:
            try:
                style_asset_bundle = StyleAssetBundle.objects.get(
                    version=style_asset_version,
                    status=StyleAssetBundle.Status.ACTIVE,
                )
            except StyleAssetBundle.DoesNotExist:
                raise serializers.ValidationError(
                    "Style asset bundle not found or inactive."
                )
        else:
            style_asset_bundle = (
                StyleAssetBundle.objects
                .filter(status=StyleAssetBundle.Status.ACTIVE)
                .latest("created_at")
            )

        attrs["payload_manifest"] = payload_manifest
        attrs["bank"] = payload_manifest.bank
        attrs["ifrs_asset_bundle"] = ifrs_asset_bundle
        attrs["style_asset_bundle"] = style_asset_bundle

        return attrs

    def create(self, validated_data):
        request = self.context["request"]

        output_formats = validated_data.get("output_formats", ["markdown"])
        max_revisions = validated_data.get("max_revisions", 2)

        job = ReportGenerationJob.objects.create(
            bank=validated_data["bank"],
            reporting_year=validated_data["reporting_year"],
            payload_manifest=validated_data["payload_manifest"],
            ifrs_asset_bundle=validated_data["ifrs_asset_bundle"],
            style_asset_bundle=validated_data["style_asset_bundle"],
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

        return job


class ReportVersionSerializer(serializers.ModelSerializer):
    bank_code = serializers.CharField(source="bank.code", read_only=True)
    bank_name = serializers.CharField(source="bank.name", read_only=True)
    job_id = serializers.UUIDField(source="job.id", read_only=True)

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


class ReportSectionSerializer(serializers.ModelSerializer):
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