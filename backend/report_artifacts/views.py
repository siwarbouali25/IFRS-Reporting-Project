from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from .models import ReportArtifact
from .serializers import ReportArtifactSerializer


class ReportArtifactViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ReportArtifactSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return ReportArtifact.objects.select_related("job", "report_version").all().order_by("-created_at")