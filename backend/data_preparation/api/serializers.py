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

from data_preparation.models import (
    DataPreparationIssue,
    DataPreparationJob,
    DataUploadBatch,
    UploadedDataFile,
)
from data_preparation.services.canonical_builder import (
    build_canonical_csvs_for_batch,
)
from data_preparation.services.canonical_validator import (
    validate_canonical_batch,
)
from data_preparation.services.column_mapper import (
    generate_column_mappings_for_batch,
)
from data_preparation.services.notebook_pipeline_runner import (
    run_notebook_pipeline_for_batch,
)
from data_preparation.services.report_generation_bridge import (
    PayloadBundleError,
    register_payload_manifests_for_batch,
)
from data_preparation.services.table_detector import detect_tables_for_batch
from data_preparation.services.upload_extractor import extract_uploaded_sources
from payloads.serializers import PayloadManifestSerializer

from .serializers import (
    DataUploadBatchCreateSerializer,
    DataUploadBatchSerializer,
    UploadedDataFileSerializer,
)


def ensure_batch_folders(batch: DataUploadBatch) -> None:
    base_folder = (
        Path(settings.MEDIA_ROOT)
        / "data_preparation"
        / "batches"
        / str(batch.id)
    )

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


def create_preparation_job(batch: DataUploadBatch) -> DataPreparationJob:
    return DataPreparationJob.objects.create(
        batch=batch,
        status=DataPreparationJob.Status.RUNNING,
        progress=10,
        started_at=timezone.now(),
        raw_input_folder=batch.raw_folder,
        patched_output_folder=batch.patched_folder,
        payload_output_folder=batch.payload_folder,
        log_output_folder=batch.log_folder,
    )


def mark_job_failed(job: DataPreparationJob, message: str) -> None:
    job.status = DataPreparationJob.Status.FAILED
    job.progress = 100
    job.completed_at = timezone.now()
    job.error_message = message

    job.save(
        update_fields=[
            "status",
            "progress",
            "completed_at",
            "error_message",
            "updated_at",
        ]
    )


def mark_job_completed(
    job: DataPreparationJob,
    *,
    payload_output_folder: str | None = None,
    total_payloads_generated: int | None = None,
    total_section_payloads_generated: int | None = None,
) -> None:
    job.status = DataPreparationJob.Status.COMPLETED
    job.progress = 100
    job.completed_at = timezone.now()
    job.error_message = ""

    update_fields = [
        "status",
        "progress",
        "completed_at",
        "error_message",
        "updated_at",
    ]

    if payload_output_folder is not None:
        job.payload_output_folder = payload_output_folder
        update_fields.append("payload_output_folder")

    if total_payloads_generated is not None:
        job.total_payloads_generated = total_payloads_generated
        update_fields.append("total_payloads_generated")

    if total_section_payloads_generated is not None:
        job.total_section_payloads_generated = total_section_payloads_generated
        update_fields.append("total_section_payloads_generated")

    job.save(update_fields=update_fields)


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

        return Response(
            response_serializer.data,
            status=status.HTTP_201_CREATED,
        )


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
                {
                    "detail": (
                        "No files were uploaded. "
                        "Use the form field name 'files'."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        unsupported_files = [
            uploaded_file.name
            for uploaded_file in uploaded_files
            if Path(uploaded_file.name).suffix.lower()
            not in {".csv", ".zip"}
        ]

        if unsupported_files:
            return Response(
                {
                    "detail": (
                        "Only CSV and ZIP files are allowed. "
                        "Unsupported files: "
                        f"{', '.join(unsupported_files)}"
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        created_files = []

        for uploaded_file in uploaded_files:
            data_file = UploadedDataFile.objects.create(
                batch=batch,
                file=uploaded_file,
                original_filename=uploaded_file.name,
                size_bytes=uploaded_file.size,
                checksum_sha256=calculate_sha256(uploaded_file),
            )
            created_files.append(data_file)

        batch.status = DataUploadBatch.Status.UPLOADED
        batch.uploaded_files_count = batch.uploaded_files.count()
        batch.error_message = ""

        if created_files and not batch.original_filename:
            batch.original_filename = created_files[0].original_filename

        batch.save(
            update_fields=[
                "status",
                "uploaded_files_count",
                "original_filename",
                "error_message",
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

        job = create_preparation_job(batch)
        manifest = extract_uploaded_sources(batch)

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
            message = "No CSV files were extracted from the uploaded files."

            DataPreparationIssue.objects.create(
                job=job,
                severity=DataPreparationIssue.Severity.ERROR,
                code="NO_CSV_EXTRACTED",
                message=message,
                is_report_blocking=True,
                is_internal_only=True,
            )

            mark_job_failed(job, message)

            return Response(
                {
                    "batch_id": str(batch.id),
                    "job_id": str(job.id),
                    "status": "failed",
                    "manifest": manifest,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        mark_job_completed(job)

        return Response(
            {
                "batch_id": str(batch.id),
                "job_id": str(job.id),
                "status": "completed",
                "extracted_csv_count": manifest[
                    "total_extracted_csv_files"
                ],
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

        job = create_preparation_job(batch)
        result = detect_tables_for_batch(batch)

        if result["total_csv_files"] == 0:
            message = (
                "No extracted CSV files found. "
                "Run extraction before table detection."
            )

            DataPreparationIssue.objects.create(
                job=job,
                severity=DataPreparationIssue.Severity.ERROR,
                code="NO_EXTRACTED_CSV_FILES",
                message=message,
                is_report_blocking=True,
                is_internal_only=True,
            )

            mark_job_failed(job, message)

            return Response(
                {
                    **result,
                    "batch_id": str(batch.id),
                    "job_id": str(job.id),
                    "status": "failed",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        for item in result["detections"]:
            if item["needs_review"]:
                DataPreparationIssue.objects.create(
                    job=job,
                    severity=DataPreparationIssue.Severity.WARNING,
                    code="TABLE_DETECTION_NEEDS_REVIEW",
                    message=(
                        "Table detection needs review for file: "
                        f"{item['source_filename']}"
                    ),
                    table_name=item.get("detected_table") or "",
                    row_identifier=item["source_filename"],
                    is_report_blocking=False,
                    is_internal_only=True,
                )

        mark_job_completed(job)

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

        job = create_preparation_job(batch)

        try:
            result = generate_column_mappings_for_batch(batch)
        except FileNotFoundError as exc:
            message = str(exc)

            DataPreparationIssue.objects.create(
                job=job,
                severity=DataPreparationIssue.Severity.ERROR,
                code="DETECTED_TABLES_NOT_FOUND",
                message=message,
                is_report_blocking=True,
                is_internal_only=True,
            )

            mark_job_failed(job, message)

            return Response(
                {
                    "batch_id": str(batch.id),
                    "job_id": str(job.id),
                    "status": "failed",
                    "detail": message,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        for mapping in result["mappings"]:
            if mapping["needs_review"]:
                DataPreparationIssue.objects.create(
                    job=job,
                    severity=DataPreparationIssue.Severity.WARNING,
                    code="COLUMN_MAPPING_NEEDS_REVIEW",
                    message=(
                        "Column mapping needs review for file: "
                        f"{mapping['source_filename']}"
                    ),
                    table_name=mapping.get("detected_table") or "",
                    row_identifier=mapping["source_filename"],
                    is_report_blocking=False,
                    is_internal_only=True,
                )

        mark_job_completed(job)

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

        job = create_preparation_job(batch)

        try:
            result = build_canonical_csvs_for_batch(batch)
        except Exception as exc:
            message = str(exc)

            DataPreparationIssue.objects.create(
                job=job,
                severity=DataPreparationIssue.Severity.ERROR,
                code="CANONICAL_BUILD_FAILED",
                message=message,
                is_report_blocking=True,
                is_internal_only=True,
            )

            mark_job_failed(job, message)

            return Response(
                {
                    "batch_id": str(batch.id),
                    "job_id": str(job.id),
                    "status": "failed",
                    "detail": message,
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

            message = "Some canonical CSV files could not be built."
            mark_job_failed(job, message)

            return Response(
                {
                    "batch_id": str(batch.id),
                    "job_id": str(job.id),
                    "status": "failed",
                    "result": result,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        mark_job_completed(job)

        return Response(
            {
                "batch_id": str(batch.id),
                "job_id": str(job.id),
                "status": "completed",
                "canonical_folder": result["canonical_folder"],
                "total_canonical_files": result[
                    "total_canonical_files"
                ],
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

        job = create_preparation_job(batch)

        try:
            result = validate_canonical_batch(batch)
        except Exception as exc:
            message = str(exc)

            DataPreparationIssue.objects.create(
                job=job,
                severity=DataPreparationIssue.Severity.ERROR,
                code="CANONICAL_VALIDATION_FAILED",
                message=message,
                is_report_blocking=True,
                is_internal_only=True,
            )

            mark_job_failed(job, message)

            return Response(
                {
                    "batch_id": str(batch.id),
                    "job_id": str(job.id),
                    "status": "failed",
                    "detail": message,
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
            mark_job_completed(job)
            response_status = status.HTTP_200_OK
            response_state = "completed"
        else:
            mark_job_failed(job, "Canonical validation failed.")
            response_status = status.HTTP_400_BAD_REQUEST
            response_state = "failed"

        return Response(
            {
                "batch_id": str(batch.id),
                "job_id": str(job.id),
                "status": response_state,
                "is_valid": result["is_valid"],
                "total_validated_files": result[
                    "total_validated_files"
                ],
                "issues": result["issues"],
                "validations": result["validations"],
                "output_path": result["output_path"],
            },
            status=response_status,
        )


class DataUploadBatchRunNotebookPipelineAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, batch_id):
        batch = get_object_or_404(
            DataUploadBatch,
            id=batch_id,
            uploaded_by=request.user,
        )

        job = create_preparation_job(batch)

        try:
            manifest = run_notebook_pipeline_for_batch(batch)

            with transaction.atomic():
                batch.payload_folder = manifest["payloads_folder"]
                batch.status = DataUploadBatch.Status.READY
                batch.error_message = ""

                batch.save(
                    update_fields=[
                        "payload_folder",
                        "status",
                        "error_message",
                        "updated_at",
                    ]
                )

                payload_manifests = register_payload_manifests_for_batch(
                    batch=batch,
                    created_by=request.user,
                    source_manifest_path=manifest["manifest_path"],
                )

                total_payloads = int(manifest["payload_count"])
                total_section_payloads = max(
                    total_payloads - len(payload_manifests),
                    0,
                )

                mark_job_completed(
                    job,
                    payload_output_folder=manifest["payloads_folder"],
                    total_payloads_generated=total_payloads,
                    total_section_payloads_generated=(
                        total_section_payloads
                    ),
                )

        except Exception as exc:
            message = str(exc)

            with transaction.atomic():
                DataPreparationIssue.objects.create(
                    job=job,
                    severity=DataPreparationIssue.Severity.ERROR,
                    code=(
                        "NOTEBOOK_OR_MANIFEST_REGISTRATION_FAILED"
                    ),
                    message=message,
                    is_report_blocking=True,
                    is_internal_only=True,
                )

                mark_job_failed(job, message)

                batch.status = DataUploadBatch.Status.FAILED
                batch.error_message = message
                batch.save(
                    update_fields=[
                        "status",
                        "error_message",
                        "updated_at",
                    ]
                )

            response_status = (
                status.HTTP_400_BAD_REQUEST
                if isinstance(
                    exc,
                    (
                        FileNotFoundError,
                        PayloadBundleError,
                        RuntimeError,
                        ValueError,
                    ),
                )
                else status.HTTP_500_INTERNAL_SERVER_ERROR
            )

            return Response(
                {
                    "batch_id": str(batch.id),
                    "job_id": str(job.id),
                    "status": "failed",
                    "detail": message,
                },
                status=response_status,
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
                "executed_notebook_path": manifest[
                    "executed_notebook_path"
                ],
                "stderr_log": manifest["stderr_log"],
                "payload_manifests": (
                    PayloadManifestSerializer(
                        payload_manifests,
                        many=True,
                    ).data
                ),
            },
            status=status.HTTP_200_OK,
        )