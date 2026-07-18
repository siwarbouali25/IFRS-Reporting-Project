from django.conf import settings
from django.http import Http404, HttpResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import ReportArtifact
from .serializers import ReportArtifactSerializer
from .storage import (
    ArtifactStorageError,
    get_artifact_download_url,
    read_artifact,
)


class ReportArtifactViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ReportArtifactSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = (
            ReportArtifact.objects.select_related(
                "job",
                "job__bank",
                "report_version",
            )
            .all()
            .order_by("-created_at")
        )

        job_id = self.request.query_params.get("job_id")
        report_version_id = self.request.query_params.get("report_version_id")
        artifact_type = self.request.query_params.get("artifact_type")

        if job_id:
            queryset = queryset.filter(job_id=job_id)
        if report_version_id:
            queryset = queryset.filter(report_version_id=report_version_id)
        if artifact_type:
            queryset = queryset.filter(artifact_type=artifact_type)
        return queryset

    @action(detail=True, methods=["get"], url_path="download")
    def download(self, request, pk=None):
        artifact = self.get_object()
        try:
            content = read_artifact(artifact.object_key)
        except ArtifactStorageError as exc:
            raise Http404("Artifact file was not found.") from exc

        inline = request.query_params.get("inline", "false").lower() == "true"
        filename = artifact.object_key.split("/")[-1]
        response = HttpResponse(
            content,
            content_type=artifact.content_type or "application/octet-stream",
        )
        disposition = "inline" if inline else "attachment"
        response["Content-Disposition"] = (
            f'{disposition}; filename="{filename}"'
        )
        return response

    @action(detail=True, methods=["get"], url_path="presigned-url")
    def presigned_url(self, request, pk=None):
        artifact = self.get_object()
        raw_expiry = request.query_params.get("expires")

        if raw_expiry is None:
            expires_seconds = int(
                getattr(settings, "MINIO_PRESIGNED_URL_EXPIRY_SECONDS", 3600)
            )
        else:
            try:
                expires_seconds = int(raw_expiry)
            except ValueError:
                return Response(
                    {"detail": "The expires parameter must be an integer."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        if expires_seconds <= 0:
            return Response(
                {"detail": "The expires parameter must be greater than zero."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            url = get_artifact_download_url(
                artifact.object_key,
                expires_seconds=expires_seconds,
            )
        except ArtifactStorageError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                "artifact_id": str(artifact.id),
                "filename": artifact.object_key.split("/")[-1],
                "download_url": url,
                "expires_seconds": expires_seconds,
            }
        )