from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from data_preparation.models import DataUploadBatch

from .services import build_kpi_dashboard


class KPIDashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, batch_id):
        bank_id = request.query_params.get("bank_id", "BANK01")
        reporting_year = request.query_params.get("reporting_year", "2024")

        try:
            reporting_year = int(reporting_year)
        except ValueError:
            reporting_year = 2024

        batch = DataUploadBatch.objects.get(id=batch_id)

        result = build_kpi_dashboard(
            batch=batch,
            bank_id=bank_id,
            reporting_year=reporting_year,
        )

        return Response(result)