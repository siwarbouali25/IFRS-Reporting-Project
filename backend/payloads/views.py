from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from .models import PayloadManifest
from .serializers import PayloadManifestSerializer


class PayloadManifestViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PayloadManifestSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = (
            PayloadManifest.objects
            .select_related(
                "bank",
                "source_batch",
                "created_by",
            )
            .all()
        )

        bank_code = self.request.query_params.get("bank_code")
        reporting_year = self.request.query_params.get(
            "reporting_year"
        )
        source_batch_id = self.request.query_params.get(
            "source_batch_id"
        )
        manifest_status = self.request.query_params.get("status")

        if bank_code:
            queryset = queryset.filter(
                bank__code__iexact=bank_code.strip()
            )

        if reporting_year:
            queryset = queryset.filter(
                reporting_year=reporting_year
            )

        if source_batch_id:
            queryset = queryset.filter(
                source_batch_id=source_batch_id
            )

        if manifest_status:
            queryset = queryset.filter(status=manifest_status)

        return queryset