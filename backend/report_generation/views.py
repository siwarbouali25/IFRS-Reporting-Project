from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from report_artifacts.models import ReportArtifact
from report_artifacts.serializers import ReportArtifactSerializer

from .models import GenerationWarning, ReportGenerationJob, ReportVersion
from .serializers import (
    GenerationWarningSerializer,
    ReportGenerationJobSerializer,
    ReportVersionSerializer,
    StartReportGenerationJobSerializer,
)
from .tasks import run_real_report_generation_job


class ReportGenerationJobViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        return (
            ReportGenerationJob.objects
            .select_related(
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

        response_serializer = ReportGenerationJobSerializer(job)

        return Response(
            response_serializer.data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["get"], url_path="warnings")
    def warnings(self, request, pk=None):
        job = self.get_object()

        warnings = (
            GenerationWarning.objects
            .filter(job=job)
            .order_by("created_at")
        )

        serializer = GenerationWarningSerializer(warnings, many=True)

        return Response(serializer.data)

    @action(detail=True, methods=["get"], url_path="artifacts")
    def artifacts(self, request, pk=None):
        job = self.get_object()

        artifacts = (
            ReportArtifact.objects
            .filter(job=job)
            .order_by("created_at")
        )

        serializer = ReportArtifactSerializer(artifacts, many=True)

        return Response(serializer.data)


class ReportVersionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ReportVersionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = (
            ReportVersion.objects
            .select_related(
                "job",
                "bank",
                "created_by",
            )
            .all()
            .order_by("-created_at")
        )

        bank_code = self.request.query_params.get("bank_code")
        reporting_year = self.request.query_params.get("reporting_year")

        if bank_code:
            queryset = queryset.filter(bank__code=bank_code)

        if reporting_year:
            queryset = queryset.filter(reporting_year=reporting_year)

        return queryset