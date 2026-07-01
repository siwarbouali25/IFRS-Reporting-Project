import json
import logging
from urllib import request

from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import llm, services, validators
from .models import AssessmentResult, RiskAnalysis
from .serializers import (
    AssessmentResultSerializer,
    RiskAnalysisDetailSerializer,
    RiskAnalysisListSerializer,
)

logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25MB


class RiskAnalysisUploadView(APIView):
    """
    POST /api/risk/upload/
    multipart/form-data, field name `file` — the reporting payload JSON.

    Workflow this endpoint drives end-to-end:
      1. read + parse the uploaded JSON
      2. validate (validators.validate_payload) — collects warnings,
         hard-fails only if a required section is entirely absent
      3. process (services.process_payload) — derives every chart series,
         KPI and the data-quality/peer/sensitivity augmentation; nothing
         here is hardcoded to a specific bank or year
      4. persist a RiskAnalysis row and return its id + the processed bundle
         + warnings, so the frontend can render immediately without a
         second round trip.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        upload = request.FILES.get("file")
        if not upload:
            return Response({"detail": "No file provided under field 'file'."}, status=status.HTTP_400_BAD_REQUEST)

        if upload.size > MAX_UPLOAD_BYTES:
            return Response({"detail": "File too large (max 25MB)."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            raw_bytes = upload.read()
            payload = json.loads(raw_bytes.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            return Response(
                {"detail": f"Uploaded file is not valid JSON: {exc}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        is_usable, warnings = validators.validate_payload(payload)

        analysis = RiskAnalysis.objects.create(
            uploaded_by=request.user if request.user.is_authenticated else None,
            original_filename=getattr(upload, "name", ""),
            raw_payload=payload,
            validation_warnings=warnings,
            status=RiskAnalysis.STATUS_PENDING,
        )

        if not is_usable:
            analysis.status = RiskAnalysis.STATUS_FAILED
            analysis.error_message = "; ".join(w["message"] for w in warnings if w["level"] == "error")
            analysis.save(update_fields=["status", "error_message"])
            return Response(
                RiskAnalysisDetailSerializer(analysis).data,
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        try:
            bundle = services.process_payload(payload)
            bank = payload.get("bank", {})
            metadata = payload.get("metadata", {})
            analysis.bank_id = (bank.get("bank_id") or "")[:64]
            analysis.bank_name = (bank.get("bank_name") or "")[:255]
            analysis.reporting_year = metadata.get("reporting_year")
            analysis.processed = bundle
            analysis.status = RiskAnalysis.STATUS_READY
            analysis.save()
        except Exception as exc:
            logger.exception("Failed to process uploaded payload for analysis %s", analysis.id)
            analysis.status = RiskAnalysis.STATUS_FAILED
            analysis.error_message = f"Processing error: {exc}"
            analysis.save(update_fields=["status", "error_message"])
            return Response(
                RiskAnalysisDetailSerializer(analysis).data,
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(RiskAnalysisDetailSerializer(analysis).data, status=status.HTTP_201_CREATED)


class RiskAnalysisListView(generics.ListAPIView):
    """GET /api/risk/analyses/ — list past uploads for the current user."""
    serializer_class = RiskAnalysisListSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return RiskAnalysis.objects.filter(uploaded_by=self.request.user)


class RiskAnalysisDetailView(generics.RetrieveAPIView):
    """GET /api/risk/analyses/<id>/ — the processed bundle for charts."""
    serializer_class = RiskAnalysisDetailSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "id"

    def get_queryset(self):
        return RiskAnalysis.objects.filter(uploaded_by=self.request.user)


class AssessmentGenerateView(APIView):
    """
    POST /api/risk/analyses/<id>/assessment/
    Triggers (or re-triggers) the LLM assessment for an already-processed
    analysis. Always returns 200/201 with either a live or fallback
    assessment — see llm.generate_assessment, which never raises.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, id):
        try:
            analysis = RiskAnalysis.objects.get(id=id, uploaded_by=request.user)
        except RiskAnalysis.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        if analysis.status != RiskAnalysis.STATUS_READY or not analysis.processed:
            return Response(
                {"detail": "Analysis is not ready yet. Wait for upload processing to complete."},
                status=status.HTTP_409_CONFLICT,
            )

        result = llm.generate_assessment(analysis.processed)

        record = AssessmentResult.objects.create(
            analysis=analysis,
            assessment_text=result["assessment"],
            recommendations=result["recommendations"],
            avoid=result["avoid"],
            evidence=analysis.processed.get("evidence", []),
            model_used=result["model_used"],
            is_fallback=result["is_fallback"],
        )
        return Response(AssessmentResultSerializer(record).data, status=status.HTTP_201_CREATED)


class AssessmentLatestView(generics.RetrieveAPIView):
    """GET /api/risk/analyses/<id>/assessment/latest/"""
    serializer_class = AssessmentResultSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        from django.http import Http404

        analysis_id = self.kwargs["id"]

        obj = (
            AssessmentResult.objects
            .filter(
                analysis_id=analysis_id,
                analysis__uploaded_by=self.request.user,
            )
            .order_by("-created_at")
            .first()
        )

        if obj is None:
            raise Http404("No assessment generated yet for this analysis.")

        return obj
