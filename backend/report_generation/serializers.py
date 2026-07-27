from django.db.models import Q
from rest_framework import serializers

from ifrs_assets.models import IFRSAssetBundle, StyleAssetBundle
from payloads.models import PayloadManifest
from payloads.services import PayloadStorageError, resolve_payload_directory

from .models import (
    GenerationWarning,
    ReportApprovalAction,
    ReportGenerationJob,
    ReportSection,
    ReportVersion,
)


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


class ReportApprovalActionSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source="actor.full_name", read_only=True)
    actor_email = serializers.EmailField(source="actor.email", read_only=True)

    class Meta:
        model = ReportApprovalAction
        fields = [
            "id",
            "action",
            "actor",
            "actor_name",
            "actor_email",
            "comment",
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
    report_version_id = serializers.SerializerMethodField()
    report_version_status = serializers.SerializerMethodField()

    def get_report_version_id(self, obj):
        try:
            return str(obj.report_version.id)
        except ReportVersion.DoesNotExist:
            return None

    def get_report_version_status(self, obj):
        try:
            return obj.report_version.status
        except ReportVersion.DoesNotExist:
            return None

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
            "report_version_id",
            "report_version_status",
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
        default=["markdown", "pdf"],
    )
    max_revisions = serializers.IntegerField(default=2, min_value=0, max_value=5)

    def _resolve_ifrs_asset_bundle(self, version: str | None) -> IFRSAssetBundle:
        queryset = IFRSAssetBundle.objects.filter(
            status=IFRSAssetBundle.Status.ACTIVE
        )

        if version:
            try:
                return queryset.get(version=version)
            except IFRSAssetBundle.DoesNotExist as exc:
                raise serializers.ValidationError(
                    {"ifrs_asset_version": "IFRS asset bundle not found or inactive."}
                ) from exc

        bundle = queryset.order_by("-created_at").first()

        if bundle is None:
            raise serializers.ValidationError(
                {"ifrs_asset_version": "No active IFRS asset bundle exists."}
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
            Q(bank=payload_manifest.bank) | Q(bank__isnull=True)
        )

        if version:
            try:
                return queryset.get(version=version)
            except StyleAssetBundle.DoesNotExist as exc:
                raise serializers.ValidationError(
                    {
                        "style_asset_version": (
                            "Style asset bundle not found, inactive, or assigned "
                            "to another bank."
                        )
                    }
                ) from exc

        bank_specific_bundle = (
            queryset.filter(bank=payload_manifest.bank)
            .order_by("-created_at")
            .first()
        )

        if bank_specific_bundle is not None:
            return bank_specific_bundle

        generic_bundle = (
            queryset.filter(bank__isnull=True)
            .order_by("-created_at")
            .first()
        )

        if generic_bundle is None:
            raise serializers.ValidationError(
                {
                    "style_asset_version": (
                        "No active bank-specific or generic style asset bundle exists."
                    )
                }
            )

        return generic_bundle

    def validate(self, attrs):
        bank_code = attrs["bank_code"].strip().upper()
        reporting_year = attrs["reporting_year"]
        payload_manifest_id = attrs["payload_manifest_id"]

        try:
            payload_manifest = (
                PayloadManifest.objects.select_related("bank", "source_batch").get(
                    id=payload_manifest_id,
                    bank__code__iexact=bank_code,
                    reporting_year=reporting_year,
                    status=PayloadManifest.Status.AVAILABLE,
                )
            )
        except PayloadManifest.DoesNotExist as exc:
            raise serializers.ValidationError(
                {
                    "payload_manifest_id": (
                        "No available payload manifest matches this bank and reporting year."
                    )
                }
            ) from exc

        try:
            resolve_payload_directory(payload_manifest)
        except PayloadStorageError as exc:
            raise serializers.ValidationError(
                {"payload_manifest_id": str(exc)}
            ) from exc

        attrs["bank_code"] = bank_code
        attrs["payload_manifest"] = payload_manifest
        attrs["bank"] = payload_manifest.bank
        attrs["ifrs_asset_bundle"] = self._resolve_ifrs_asset_bundle(
            attrs.get("ifrs_asset_version")
        )
        attrs["style_asset_bundle"] = self._resolve_style_asset_bundle(
            payload_manifest=payload_manifest,
            version=attrs.get("style_asset_version"),
        )
        return attrs

    def create(self, validated_data):
        request = self.context["request"]
        output_formats = validated_data.get(
            "output_formats",
            ["markdown", "pdf"],
        )
        max_revisions = validated_data.get("max_revisions", 2)

        return ReportGenerationJob.objects.create(
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


class ReportVersionSerializer(serializers.ModelSerializer):
    bank_code = serializers.CharField(source="bank.code", read_only=True)
    bank_name = serializers.CharField(source="bank.name", read_only=True)
    job_id = serializers.UUIDField(source="job.id", read_only=True)
    created_by_name = serializers.CharField(source="created_by.full_name", read_only=True)
    submitted_by_name = serializers.CharField(
        source="submitted_by.full_name",
        read_only=True,
    )
    reviewed_by_name = serializers.CharField(
        source="reviewed_by.full_name",
        read_only=True,
    )
    approval_actions = ReportApprovalActionSerializer(many=True, read_only=True)
    sections = ReportSectionSerializer(many=True, read_only=True)
    generation_status = serializers.CharField(source="job.status", read_only=True)
    generation_completed_at = serializers.DateTimeField(
        source="job.completed_at",
        read_only=True,
    )
    warning_count = serializers.IntegerField(source="job.warning_count", read_only=True)
    validation_summary = serializers.SerializerMethodField()
    is_creator = serializers.SerializerMethodField()
    can_submit = serializers.SerializerMethodField()
    can_review = serializers.SerializerMethodField()
    is_locked = serializers.SerializerMethodField()

    def _request_user(self):
        request = self.context.get("request")
        return getattr(request, "user", None)

    def get_validation_summary(self, obj):
        sections = list(obj.sections.all())
        scores = [section.score for section in sections if section.score is not None]
        warning_statuses = {ReportSection.Status.WARNING}
        failed_statuses = {
            ReportSection.Status.FAILED,
            ReportSection.Status.VALIDATION_FAILED,
        }
        ready_statuses = {
            ReportSection.Status.GENERATED,
            ReportSection.Status.REVISED,
            ReportSection.Status.APPROVED,
            ReportSection.Status.WARNING,
        }
        return {
            "total_sections": len(sections),
            "ready_sections": sum(
                section.status in ready_statuses for section in sections
            ),
            "approved_sections": sum(
                section.status == ReportSection.Status.APPROVED
                for section in sections
            ),
            "warning_sections": sum(
                section.status in warning_statuses for section in sections
            ),
            "failed_sections": sum(
                section.status in failed_statuses for section in sections
            ),
            "average_score": round(sum(scores) / len(scores), 1) if scores else None,
        }

    def get_is_creator(self, obj):
        user = self._request_user()
        return bool(user and user.is_authenticated and obj.created_by_id == user.id)

    def get_can_submit(self, obj):
        user = self._request_user()
        if not user or not user.is_authenticated:
            return False
        if obj.status not in {
            ReportVersion.Status.DRAFT,
            ReportVersion.Status.CHANGES_REQUESTED,
        }:
            return False
        if user.role == "admin":
            return True
        return user.role == "auditor" and obj.created_by_id == user.id

    def get_can_review(self, obj):
        user = self._request_user()
        if not user or not user.is_authenticated:
            return False
        if obj.status != ReportVersion.Status.PENDING_REVIEW:
            return False
        if user.role == "admin":
            return True
        return user.role == "expert_reviewer" and obj.created_by_id != user.id

    def get_is_locked(self, obj):
        return obj.status == ReportVersion.Status.APPROVED

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
            "created_by_name",
            "submitted_by",
            "submitted_by_name",
            "submitted_at",
            "reviewed_by",
            "reviewed_by_name",
            "reviewed_at",
            "review_comment",
            "approval_actions",
            "sections",
            "generation_status",
            "generation_completed_at",
            "warning_count",
            "validation_summary",
            "is_creator",
            "can_submit",
            "can_review",
            "is_locked",
            "created_at",
        ]


class ReportReviewCommentSerializer(serializers.Serializer):
    comment = serializers.CharField(
        required=False,
        allow_blank=True,
        trim_whitespace=True,
        max_length=5000,
    )
