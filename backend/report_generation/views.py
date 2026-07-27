from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from report_artifacts.models import ReportArtifact
from report_artifacts.serializers import ReportArtifactSerializer

from .models import (
    GenerationWarning,
    ReportApprovalAction,
    ReportGenerationJob,
    ReportVersion,
)
from .permissions import CanReviewReport, CanSubmitReportForReview
from .serializers import (
    GenerationWarningSerializer,
    ReportGenerationJobSerializer,
    ReportReviewCommentSerializer,
    ReportVersionSerializer,
    StartReportGenerationJobSerializer,
)
from .tasks import run_real_report_generation_job


class ReportGenerationJobViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        return (
            ReportGenerationJob.objects.select_related(
                "bank",
                "payload_manifest",
                "ifrs_asset_bundle",
                "style_asset_bundle",
                "created_by",
            )
            .all()
            .order_by("-created_at")
        )

    def get_serializer_class(self):
        if self.action == "create":
            return StartReportGenerationJobSerializer
        return ReportGenerationJobSerializer

    def create(self, request, *args, **kwargs):
        serializer = StartReportGenerationJobSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        job = serializer.save()
        task = run_real_report_generation_job.delay(str(job.id))
        job.celery_task_id = task.id
        job.save(update_fields=["celery_task_id"])
        return Response(
            ReportGenerationJobSerializer(job).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["get"], url_path="warnings")
    def warnings(self, request, pk=None):
        warnings = GenerationWarning.objects.filter(
            job=self.get_object()
        ).order_by("created_at")
        return Response(GenerationWarningSerializer(warnings, many=True).data)

    @action(detail=True, methods=["get"], url_path="artifacts")
    def artifacts(self, request, pk=None):
        artifacts = ReportArtifact.objects.filter(job=self.get_object())
        include_internal = (
            request.query_params.get("include_internal", "false").lower()
            == "true"
        )

        if not include_internal:
            artifacts = artifacts.filter(
                Q(
                    artifact_type=ReportArtifact.ArtifactType.FINAL_PDF,
                    object_key__contains="/final/",
                )
                | Q(
                    artifact_type=ReportArtifact.ArtifactType.FINAL_MARKDOWN,
                    object_key__contains="/final/",
                )
            )

        return Response(
            ReportArtifactSerializer(
                artifacts.order_by("created_at"),
                many=True,
            ).data
        )


class ReportVersionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ReportVersionSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.action == "submit_for_review":
            permission_classes = [CanSubmitReportForReview]
        elif self.action in {"approve", "request_changes", "reject"}:
            permission_classes = [CanReviewReport]
        else:
            permission_classes = self.permission_classes
        return [permission() for permission in permission_classes]

    def get_queryset(self):
        queryset = (
            ReportVersion.objects.select_related(
                "job",
                "bank",
                "created_by",
                "submitted_by",
                "reviewed_by",
            )
            .prefetch_related(
                "approval_actions",
                "approval_actions__actor",
                "sections",
            )
            .all()
            .order_by("-created_at")
        )

        bank_code = self.request.query_params.get("bank_code")
        reporting_year = self.request.query_params.get("reporting_year")
        report_status = self.request.query_params.get("status")

        if bank_code:
            queryset = queryset.filter(bank__code__iexact=bank_code)
        if reporting_year:
            queryset = queryset.filter(reporting_year=reporting_year)
        if report_status:
            queryset = queryset.filter(status=report_status)
        return queryset

    def _read_comment(self, request) -> str:
        serializer = ReportReviewCommentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data.get("comment", "")

    def _response(self, report_version: ReportVersion) -> Response:
        refreshed = self.get_queryset().get(id=report_version.id)
        return Response(self.get_serializer(refreshed).data)

    @action(detail=True, methods=["post"], url_path="submit-for-review")
    def submit_for_review(self, request, pk=None):
        comment = self._read_comment(request)

        with transaction.atomic():
            report_version = (
                ReportVersion.objects.select_related("created_by")
                .select_for_update(of=("self",))
                .get(id=pk)
            )
            self.check_object_permissions(request, report_version)
            if report_version.status not in {
                ReportVersion.Status.DRAFT,
                ReportVersion.Status.CHANGES_REQUESTED,
            }:
                return Response(
                    {
                        "detail": (
                            "Only a draft report or a report with requested changes "
                            "can be submitted for review."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            report_version.status = ReportVersion.Status.PENDING_REVIEW
            report_version.submitted_by = request.user
            report_version.submitted_at = timezone.now()
            report_version.reviewed_by = None
            report_version.reviewed_at = None
            report_version.review_comment = ""
            report_version.save(
                update_fields=[
                    "status",
                    "submitted_by",
                    "submitted_at",
                    "reviewed_by",
                    "reviewed_at",
                    "review_comment",
                ]
            )
            ReportApprovalAction.objects.create(
                report_version=report_version,
                action=ReportApprovalAction.Action.SUBMITTED,
                actor=request.user,
                comment=comment,
            )

        return self._response(report_version)

    @action(detail=True, methods=["post"], url_path="approve")
    def approve(self, request, pk=None):
        comment = self._read_comment(request)

        with transaction.atomic():
            report_version = (
                ReportVersion.objects.select_related("created_by")
                .select_for_update(of=("self",))
                .get(id=pk)
            )
            self.check_object_permissions(request, report_version)
            if report_version.status != ReportVersion.Status.PENDING_REVIEW:
                return Response(
                    {"detail": "Only a report pending review can be approved."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            report_version.status = ReportVersion.Status.APPROVED
            report_version.reviewed_by = request.user
            report_version.reviewed_at = timezone.now()
            report_version.review_comment = comment
            report_version.save(
                update_fields=[
                    "status",
                    "reviewed_by",
                    "reviewed_at",
                    "review_comment",
                ]
            )
            ReportApprovalAction.objects.create(
                report_version=report_version,
                action=ReportApprovalAction.Action.APPROVED,
                actor=request.user,
                comment=comment,
            )

        return self._response(report_version)

    @action(detail=True, methods=["post"], url_path="request-changes")
    def request_changes(self, request, pk=None):
        comment = self._read_comment(request)
        if not comment:
            return Response(
                {"comment": ["A comment is required when requesting changes."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            report_version = (
                ReportVersion.objects.select_related("created_by")
                .select_for_update(of=("self",))
                .get(id=pk)
            )
            self.check_object_permissions(request, report_version)
            if report_version.status != ReportVersion.Status.PENDING_REVIEW:
                return Response(
                    {
                        "detail": (
                            "Only a report pending review can receive change requests."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            report_version.status = ReportVersion.Status.CHANGES_REQUESTED
            report_version.reviewed_by = request.user
            report_version.reviewed_at = timezone.now()
            report_version.review_comment = comment
            report_version.save(
                update_fields=[
                    "status",
                    "reviewed_by",
                    "reviewed_at",
                    "review_comment",
                ]
            )
            ReportApprovalAction.objects.create(
                report_version=report_version,
                action=ReportApprovalAction.Action.CHANGES_REQUESTED,
                actor=request.user,
                comment=comment,
            )

        return self._response(report_version)

    @action(detail=True, methods=["post"], url_path="reject")
    def reject(self, request, pk=None):
        comment = self._read_comment(request)
        if not comment:
            return Response(
                {"comment": ["A rejection reason is required."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            report_version = (
                ReportVersion.objects.select_related("created_by")
                .select_for_update(of=("self",))
                .get(id=pk)
            )
            self.check_object_permissions(request, report_version)
            if report_version.status != ReportVersion.Status.PENDING_REVIEW:
                return Response(
                    {"detail": "Only a report pending review can be rejected."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            report_version.status = ReportVersion.Status.REJECTED
            report_version.reviewed_by = request.user
            report_version.reviewed_at = timezone.now()
            report_version.review_comment = comment
            report_version.save(
                update_fields=[
                    "status",
                    "reviewed_by",
                    "reviewed_at",
                    "review_comment",
                ]
            )
            ReportApprovalAction.objects.create(
                report_version=report_version,
                action=ReportApprovalAction.Action.REJECTED,
                actor=request.user,
                comment=comment,
            )

        return self._response(report_version)
