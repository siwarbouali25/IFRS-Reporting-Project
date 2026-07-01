from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from .models import PayloadManifest
from .serializers import PayloadManifestSerializer


class PayloadManifestViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PayloadManifestSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = PayloadManifest.objects.select_related("bank").all()

        bank_code = self.request.query_params.get("bank_code")
        reporting_year = self.request.query_params.get("reporting_year")

        if bank_code:
            queryset = queryset.filter(bank__code=bank_code)

        if reporting_year:
            queryset = queryset.filter(reporting_year=reporting_year)

        return queryset