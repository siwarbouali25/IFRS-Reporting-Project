from django.http import FileResponse, Http404
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from django.core.files.base import ContentFile
from .models import ReportArtifact
from .serializers import ReportArtifactSerializer
from .storage import ArtifactStorageError, read_local_artifact


class ReportArtifactViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ReportArtifactSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            ReportArtifact.objects
            .select_related("job", "report_version")
            .all()
            .order_by("-created_at")
        )

    @action(detail=True, methods=["get"], url_path="download")
    def download(self, request, pk=None):
        artifact = self.get_object()

        try:
            content = read_local_artifact(artifact.object_key)
        except ArtifactStorageError:
            raise Http404("Artifact file not found.")

        response = FileResponse(
            ContentFile(content),
            content_type=artifact.content_type or "application/octet-stream",
        )

        filename = artifact.object_key.split("/")[-1]
        response["Content-Disposition"] = f'attachment; filename="{filename}"'

        return response