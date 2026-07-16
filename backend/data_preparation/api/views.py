import hashlib
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from data_preparation.models import DataUploadBatch, UploadedDataFile
from .serializers import (
    DataUploadBatchCreateSerializer,
    DataUploadBatchSerializer,
    UploadedDataFileSerializer,
)

from data_preparation.models import DataPreparationIssue, DataPreparationJob
from data_preparation.services.upload_extractor import extract_uploaded_sources
from data_preparation.services.table_detector import detect_tables_for_batch
from data_preparation.services.column_mapper import generate_column_mappings_for_batch
from data_preparation.services.canonical_builder import build_canonical_csvs_for_batch
from data_preparation.services.canonical_validator import validate_canonical_batch
from data_preparation.services.notebook_pipeline_runner import run_notebook_pipeline_for_batch

def ensure_batch_folders(batch: DataUploadBatch) -> None:
    base_folder = Path(settings.MEDIA_ROOT) / "data_preparation" / "batches" / str(batch.id)

    raw_folder = base_folder / "raw"
    patched_folder = base_folder / "patched"
    payload_folder = base_folder / "payloads"
    log_folder = base_folder / "logs"

    raw_folder.mkdir(parents=True, exist_ok=True)
    patched_folder.mkdir(parents=True, exist_ok=True)
    payload_folder.mkdir(parents=True, exist_ok=True)
    log_folder.mkdir(parents=True, exist_ok=True)

    batch.raw_folder = str(raw_folder)
    batch.patched_folder = str(patched_folder)
    batch.payload_folder = str(payload_folder)
    batch.log_folder = str(log_folder)
    batch.save(
        update_fields=[
            "raw_folder",
            "patched_folder",
            "payload_folder",
            "log_folder",
            "updated_at",
        ]
    )


def calculate_sha256(uploaded_file) -> str:
    sha256 = hashlib.sha256()

    for chunk in uploaded_file.chunks():
        sha256.update(chunk)

    uploaded_file.seek(0)
    return sha256.hexdigest()


class DataUploadBatchListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        batches = DataUploadBatch.objects.filter(uploaded_by=request.user)
        serializer = DataUploadBatchSerializer(batches, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = DataUploadBatchCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        batch = serializer.save(uploaded_by=request.user)
        ensure_batch_folders(batch)

        response_serializer = DataUploadBatchSerializer(batch)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class DataUploadBatchDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, batch_id):
        batch = get_object_or_404(
            DataUploadBatch.objects.prefetch_related(
                "uploaded_files",
                "preparation_jobs",
                "preparation_jobs__payload_artifacts",
                "preparation_jobs__issues",
            ),
            id=batch_id,
            uploaded_by=request.user,
        )

        serializer = DataUploadBatchSerializer(batch)
        return Response(serializer.data)


class DataUploadFileAPIView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    @transaction.atomic
    def post(self, request, batch_id):
        batch = get_object_or_404(
            DataUploadBatch,
            id=batch_id,
            uploaded_by=request.user,
        )

        ensure_batch_folders(batch)

        uploaded_files = request.FILES.getlist("files")

        if not uploaded_files:
            return Response(
                {"detail": "No files were uploaded. Use the form field name 'files'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        created_files = []

        for uploaded_file in uploaded_files:
            original_name = uploaded_file.name
            suffix = original_name.lower().split(".")[-1]

            if suffix not in ["csv", "zip"]:
                return Response(
                    {
                        "detail": f"Unsupported file type for '{original_name}'. Only CSV and ZIP files are allowed."
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            checksum = calculate_sha256(uploaded_file)

            data_file = UploadedDataFile.objects.create(
                batch=batch,
                file=uploaded_file,
                original_filename=original_name,
                size_bytes=uploaded_file.size,
                checksum_sha256=checksum,
            )

            created_files.append(data_file)

        batch.status = DataUploadBatch.Status.UPLOADED
        batch.uploaded_files_count = batch.uploaded_files.count()

        if created_files and not batch.original_filename:
            batch.original_filename = created_files[0].original_filename

        batch.save(
            update_fields=[
                "status",
                "uploaded_files_count",
                "original_filename",
                "updated_at",
            ]
        )

        serializer = UploadedDataFileSerializer(created_files, many=True)

        return Response(
            {
                "batch_id": str(batch.id),
                "status": batch.status,
                "uploaded_files_count": batch.uploaded_files_count,
                "files": serializer.data,
            },
            status=status.HTTP_201_CREATED,
        )
    


class DataUploadBatchExtractAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, batch_id):
        batch = get_object_or_404(
            DataUploadBatch,
            id=batch_id,
            uploaded_by=request.user,
        )

        job = DataPreparationJob.objects.create(
            batch=batch,
            status=DataPreparationJob.Status.RUNNING,
            progress=10,
            started_at=timezone.now(),
            raw_input_folder=batch.raw_folder,
            patched_output_folder=batch.patched_folder,
            payload_output_folder=batch.payload_folder,
            log_output_folder=batch.log_folder,
        )

        manifest = extract_uploaded_sources(batch)

        if manifest["errors"]:
            for error in manifest["errors"]:
                DataPreparationIssue.objects.create(
                    job=job,
                    severity=DataPreparationIssue.Severity.ERROR,
                    code="EXTRACTION_ERROR",
                    message=error["error"],
                    table_name="",
                    field_name="",
                    row_identifier=error.get("source_name", ""),
                    is_report_blocking=True,
                    is_internal_only=True,
                )

        if manifest["total_extracted_csv_files"] == 0:
            DataPreparationIssue.objects.create(
                job=job,
                severity=DataPreparationIssue.Severity.ERROR,
                code="NO_CSV_EXTRACTED",
                message="No CSV files were extracted from the uploaded files.",
                is_report_blocking=True,
                is_internal_only=True,
            )

            job.status = DataPreparationJob.Status.FAILED
            job.progress = 100
            job.completed_at = timezone.now()
            job.error_message = "No CSV files were extracted."
            job.save(
                update_fields=[
                    "status",
                    "progress",
                    "completed_at",
                    "error_message",
                    "updated_at",
                ]
            )

            return Response(
                {
                    "batch_id": str(batch.id),
                    "job_id": str(job.id),
                    "status": "failed",
                    "manifest": manifest,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        job.status = DataPreparationJob.Status.COMPLETED
        job.progress = 100
        job.completed_at = timezone.now()
        job.error_message = ""
        job.save(
            update_fields=[
                "status",
                "progress",
                "completed_at",
                "error_message",
                "updated_at",
            ]
        )

        return Response(
            {
                "batch_id": str(batch.id),
                "job_id": str(job.id),
                "status": "completed",
                "extracted_csv_count": manifest["total_extracted_csv_files"],
                "extracted_folder": manifest["extracted_folder"],
                "manifest_path": manifest["manifest_path"],
                "files": manifest["files"],
                "errors": manifest["errors"],
            },
            status=status.HTTP_200_OK,
        )
    

class DataUploadBatchDetectTablesAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, batch_id):
        batch = get_object_or_404(
            DataUploadBatch,
            id=batch_id,
            uploaded_by=request.user,
        )

        job = DataPreparationJob.objects.create(
            batch=batch,
            status=DataPreparationJob.Status.RUNNING,
            progress=10,
            started_at=timezone.now(),
            raw_input_folder=batch.raw_folder,
            patched_output_folder=batch.patched_folder,
            payload_output_folder=batch.payload_folder,
            log_output_folder=batch.log_folder,
        )

        result = detect_tables_for_batch(batch)

        if result["total_csv_files"] == 0:
            DataPreparationIssue.objects.create(
                job=job,
                severity=DataPreparationIssue.Severity.ERROR,
                code="NO_EXTRACTED_CSV_FILES",
                message="No extracted CSV files found. Run extraction before table detection.",
                is_report_blocking=True,
                is_internal_only=True,
            )

            job.status = DataPreparationJob.Status.FAILED
            job.progress = 100
            job.completed_at = timezone.now()
            job.error_message = "No extracted CSV files found."
            job.save(update_fields=["status", "progress", "completed_at", "error_message", "updated_at"])

            return Response(result, status=status.HTTP_400_BAD_REQUEST)

        for item in result["detections"]:
            if item["needs_review"]:
                DataPreparationIssue.objects.create(
                    job=job,
                    severity=DataPreparationIssue.Severity.WARNING,
                    code="TABLE_DETECTION_NEEDS_REVIEW",
                    message=f"Table detection needs review for file: {item['source_filename']}",
                    table_name=item.get("detected_table") or "",
                    row_identifier=item["source_filename"],
                    is_report_blocking=False,
                    is_internal_only=True,
                )

        job.status = DataPreparationJob.Status.COMPLETED
        job.progress = 100
        job.completed_at = timezone.now()
        job.error_message = ""
        job.save(update_fields=["status", "progress", "completed_at", "error_message", "updated_at"])

        return Response(
            {
                "batch_id": str(batch.id),
                "job_id": str(job.id),
                "status": "completed",
                "needs_review": result["needs_review"],
                "detected_tables": result["detected_tables"],
                "duplicates": result["duplicates"],
                "detections": result["detections"],
                "output_path": result["output_path"],
            },
            status=status.HTTP_200_OK,
        )
    
class DataUploadBatchColumnMappingAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, batch_id):
        batch = get_object_or_404(
            DataUploadBatch,
            id=batch_id,
            uploaded_by=request.user,
        )

        job = DataPreparationJob.objects.create(
            batch=batch,
            status=DataPreparationJob.Status.RUNNING,
            progress=10,
            started_at=timezone.now(),
            raw_input_folder=batch.raw_folder,
            patched_output_folder=batch.patched_folder,
            payload_output_folder=batch.payload_folder,
            log_output_folder=batch.log_folder,
        )

        try:
            result = generate_column_mappings_for_batch(batch)

        except FileNotFoundError as exc:
            DataPreparationIssue.objects.create(
                job=job,
                severity=DataPreparationIssue.Severity.ERROR,
                code="DETECTED_TABLES_NOT_FOUND",
                message=str(exc),
                is_report_blocking=True,
                is_internal_only=True,
            )

            job.status = DataPreparationJob.Status.FAILED
            job.progress = 100
            job.completed_at = timezone.now()
            job.error_message = str(exc)
            job.save(
                update_fields=[
                    "status",
                    "progress",
                    "completed_at",
                    "error_message",
                    "updated_at",
                ]
            )

            return Response(
                {
                    "batch_id": str(batch.id),
                    "job_id": str(job.id),
                    "status": "failed",
                    "detail": str(exc),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        for mapping in result["mappings"]:
            if mapping["needs_review"]:
                DataPreparationIssue.objects.create(
                    job=job,
                    severity=DataPreparationIssue.Severity.WARNING,
                    code="COLUMN_MAPPING_NEEDS_REVIEW",
                    message=f"Column mapping needs review for file: {mapping['source_filename']}",
                    table_name=mapping.get("detected_table") or "",
                    row_identifier=mapping["source_filename"],
                    is_report_blocking=False,
                    is_internal_only=True,
                )

        job.status = DataPreparationJob.Status.COMPLETED
        job.progress = 100
        job.completed_at = timezone.now()
        job.error_message = ""
        job.save(
            update_fields=[
                "status",
                "progress",
                "completed_at",
                "error_message",
                "updated_at",
            ]
        )

        return Response(
            {
                "batch_id": str(batch.id),
                "job_id": str(job.id),
                "status": "completed",
                "needs_review": result["needs_review"],
                "total_mapped_files": result["total_mapped_files"],
                "mappings": result["mappings"],
                "output_path": result["output_path"],
            },
            status=status.HTTP_200_OK,
        )
    

class DataUploadBatchBuildCanonicalAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, batch_id):
        batch = get_object_or_404(
            DataUploadBatch,
            id=batch_id,
            uploaded_by=request.user,
        )

        job = DataPreparationJob.objects.create(
            batch=batch,
            status=DataPreparationJob.Status.RUNNING,
            progress=10,
            started_at=timezone.now(),
            raw_input_folder=batch.raw_folder,
            patched_output_folder=batch.patched_folder,
            payload_output_folder=batch.payload_folder,
            log_output_folder=batch.log_folder,
        )

        try:
            result = build_canonical_csvs_for_batch(batch)

        except Exception as exc:
            DataPreparationIssue.objects.create(
                job=job,
                severity=DataPreparationIssue.Severity.ERROR,
                code="CANONICAL_BUILD_FAILED",
                message=str(exc),
                is_report_blocking=True,
                is_internal_only=True,
            )

            job.status = DataPreparationJob.Status.FAILED
            job.progress = 100
            job.completed_at = timezone.now()
            job.error_message = str(exc)
            job.save(
                update_fields=[
                    "status",
                    "progress",
                    "completed_at",
                    "error_message",
                    "updated_at",
                ]
            )

            return Response(
                {
                    "batch_id": str(batch.id),
                    "job_id": str(job.id),
                    "status": "failed",
                    "detail": str(exc),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if result["errors"]:
            for error in result["errors"]:
                DataPreparationIssue.objects.create(
                    job=job,
                    severity=DataPreparationIssue.Severity.ERROR,
                    code="CANONICAL_FILE_ERROR",
                    message=error["error"],
                    table_name=error.get("detected_table") or "",
                    row_identifier=error.get("source_filename") or "",
                    is_report_blocking=True,
                    is_internal_only=True,
                )

            job.status = DataPreparationJob.Status.FAILED
            job.progress = 100
            job.completed_at = timezone.now()
            job.error_message = "Some canonical CSV files could not be built."
            job.save(
                update_fields=[
                    "status",
                    "progress",
                    "completed_at",
                    "error_message",
                    "updated_at",
                ]
            )

            return Response(
                {
                    "batch_id": str(batch.id),
                    "job_id": str(job.id),
                    "status": "failed",
                    "result": result,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        job.status = DataPreparationJob.Status.COMPLETED
        job.progress = 100
        job.completed_at = timezone.now()
        job.error_message = ""
        job.save(
            update_fields=[
                "status",
                "progress",
                "completed_at",
                "error_message",
                "updated_at",
            ]
        )

        return Response(
            {
                "batch_id": str(batch.id),
                "job_id": str(job.id),
                "status": "completed",
                "canonical_folder": result["canonical_folder"],
                "total_canonical_files": result["total_canonical_files"],
                "outputs": result["outputs"],
                "manifest_path": result["manifest_path"],
            },
            status=status.HTTP_200_OK,
        )
    

class DataUploadBatchValidateCanonicalAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, batch_id):
        batch = get_object_or_404(
            DataUploadBatch,
            id=batch_id,
            uploaded_by=request.user,
        )

        job = DataPreparationJob.objects.create(
            batch=batch,
            status=DataPreparationJob.Status.RUNNING,
            progress=10,
            started_at=timezone.now(),
            raw_input_folder=batch.raw_folder,
            patched_output_folder=batch.patched_folder,
            payload_output_folder=batch.payload_folder,
            log_output_folder=batch.log_folder,
        )

        try:
            result = validate_canonical_batch(batch)

        except Exception as exc:
            DataPreparationIssue.objects.create(
                job=job,
                severity=DataPreparationIssue.Severity.ERROR,
                code="CANONICAL_VALIDATION_FAILED",
                message=str(exc),
                is_report_blocking=True,
                is_internal_only=True,
            )

            job.status = DataPreparationJob.Status.FAILED
            job.progress = 100
            job.completed_at = timezone.now()
            job.error_message = str(exc)
            job.save(
                update_fields=[
                    "status",
                    "progress",
                    "completed_at",
                    "error_message",
                    "updated_at",
                ]
            )

            return Response(
                {
                    "batch_id": str(batch.id),
                    "job_id": str(job.id),
                    "status": "failed",
                    "detail": str(exc),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        for issue in result["issues"]:
            severity = (
                DataPreparationIssue.Severity.ERROR
                if issue["severity"] == "error"
                else DataPreparationIssue.Severity.WARNING
            )

            DataPreparationIssue.objects.create(
                job=job,
                severity=severity,
                code=issue["code"],
                message=issue["message"],
                table_name=issue.get("table_name", ""),
                is_report_blocking=issue["severity"] == "error",
                is_internal_only=True,
            )

        if result["is_valid"]:
            job.status = DataPreparationJob.Status.COMPLETED
            job.error_message = ""
            response_status = status.HTTP_200_OK
        else:
            job.status = DataPreparationJob.Status.FAILED
            job.error_message = "Canonical validation failed."
            response_status = status.HTTP_400_BAD_REQUEST

        job.progress = 100
        job.completed_at = timezone.now()
        job.save(
            update_fields=[
                "status",
                "progress",
                "completed_at",
                "error_message",
                "updated_at",
            ]
        )

        return Response(
            {
                "batch_id": str(batch.id),
                "job_id": str(job.id),
                "status": "completed" if result["is_valid"] else "failed",
                "is_valid": result["is_valid"],
                "total_validated_files": result["total_validated_files"],
                "issues": result["issues"],
                "validations": result["validations"],
                "output_path": result["output_path"],
            },
            status=response_status,
        )
    

class DataUploadBatchRunNotebookPipelineAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, batch_id):
        batch = get_object_or_404(
            DataUploadBatch,
            id=batch_id,
            uploaded_by=request.user,
        )

        job = DataPreparationJob.objects.create(
            batch=batch,
            status=DataPreparationJob.Status.RUNNING,
            progress=10,
            started_at=timezone.now(),
            raw_input_folder=batch.raw_folder,
            patched_output_folder=batch.patched_folder,
            payload_output_folder=batch.payload_folder,
            log_output_folder=batch.log_folder,
        )

        try:
            manifest = run_notebook_pipeline_for_batch(batch)

        except Exception as exc:
            DataPreparationIssue.objects.create(
                job=job,
                severity=DataPreparationIssue.Severity.ERROR,
                code="NOTEBOOK_PIPELINE_FAILED",
                message=str(exc),
                is_report_blocking=True,
                is_internal_only=True,
            )

            job.status = DataPreparationJob.Status.FAILED
            job.progress = 100
            job.completed_at = timezone.now()
            job.error_message = str(exc)

            job.save(
                update_fields=[
                    "status",
                    "progress",
                    "completed_at",
                    "error_message",
                    "updated_at",
                ]
            )

            return Response(
                {
                    "batch_id": str(batch.id),
                    "job_id": str(job.id),
                    "status": "failed",
                    "detail": str(exc),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        job.status = DataPreparationJob.Status.COMPLETED
        job.progress = 100
        job.completed_at = timezone.now()
        job.error_message = ""
        job.payload_output_folder = manifest["payloads_folder"]

        job.save(
            update_fields=[
                "status",
                "progress",
                "completed_at",
                "error_message",
                "payload_output_folder",
                "updated_at",
            ]
        )

        return Response(
            {
                "batch_id": str(batch.id),
                "job_id": str(job.id),
                "status": "completed",
                "payload_count": manifest["payload_count"],
                "payloads_folder": manifest["payloads_folder"],
                "payload_outputs": manifest["payload_outputs"],
                "manifest_path": manifest["manifest_path"],
                "executed_notebook_path": manifest["executed_notebook_path"],
                "stderr_log": manifest["stderr_log"],
            },
            status=status.HTTP_200_OK,
        )