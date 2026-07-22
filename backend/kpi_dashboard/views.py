from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from data_preparation.models import DataUploadBatch

from .services import build_kpi_dashboard


class KPIDashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, batch_id):
        bank_id = (
            request.query_params.get("bank_id", "BANK01")
            .strip()
            .upper()
        )

        try:
            reporting_year = int(
                request.query_params.get("reporting_year", "2024")
            )
        except (TypeError, ValueError):
            return Response(
                {"detail": "reporting_year must be a valid integer."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        batches = DataUploadBatch.objects.all()

        if not (request.user.is_superuser or request.user.is_staff):
            batches = batches.filter(uploaded_by=request.user)

        try:
            batch = batches.get(id=batch_id)
        except DataUploadBatch.DoesNotExist:
            return Response(
                {
                    "detail": (
                        "The selected data-preparation batch does not exist "
                        "or is not accessible to this account."
                    )
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if str(batch.status).lower() != DataUploadBatch.Status.READY:
            return Response(
                {
                    "detail": "The selected data-preparation batch is not ready.",
                    "batch_id": str(batch.id),
                    "batch_status": batch.status,
                },
                status=status.HTTP_409_CONFLICT,
            )

        try:
            result = build_kpi_dashboard(
                batch=batch,
                bank_id=bank_id,
                reporting_year=reporting_year,
            )
        except FileNotFoundError as exc:
            return Response(
                {
                    "detail": str(exc),
                    "batch_id": str(batch.id),
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        except (TypeError, ValueError) as exc:
            return Response(
                {
                    "detail": "The prepared KPI payload could not be read.",
                    "error": str(exc),
                    "batch_id": str(batch.id),
                },
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        return Response(result, status=status.HTTP_200_OK)
