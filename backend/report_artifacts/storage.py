import hashlib
import json
import mimetypes
from pathlib import Path
from typing import Any

from django.conf import settings
from minio.error import S3Error

from object_storage.minio_client import (
    ensure_bucket_exists,
    get_minio_client,
    get_presigned_url,
    upload_bytes_to_minio,
)

from .models import ReportArtifact


class ArtifactStorageError(Exception):
    pass


IGNORED_DIRECTORY_NAMES = {".git", ".ipynb_checkpoints", "__pycache__"}
IGNORED_FILE_SUFFIXES = {".pyc", ".pyo", ".tmp"}


def _storage_backend() -> str:
    backend = str(
        getattr(settings, "ARTIFACT_STORAGE_BACKEND", "minio")
    ).strip().lower()
    if backend not in {"local", "minio"}:
        raise ArtifactStorageError(
            "ARTIFACT_STORAGE_BACKEND must be 'local' or 'minio'."
        )
    return backend


def _artifact_bucket_name() -> str:
    return str(
        getattr(
            settings,
            "ARTIFACT_BUCKET_NAME",
            getattr(settings, "MINIO_BUCKET", "ifrs-platform"),
        )
    )


def _get_local_root() -> Path:
    root = Path(settings.ARTIFACT_LOCAL_ROOT)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _calculate_checksum(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _write_local_file(object_key: str, content: bytes) -> Path:
    file_path = _get_local_root() / object_key
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(content)
    return file_path


def _persist_artifact_record(
    *,
    job,
    report_version,
    artifact_type: str,
    object_key: str,
    content_type: str,
    size_bytes: int,
    checksum: str,
) -> ReportArtifact:
    artifact, _created = ReportArtifact.objects.update_or_create(
        job=job,
        object_key=object_key,
        defaults={
            "report_version": report_version,
            "artifact_type": artifact_type,
            "bucket": _artifact_bucket_name(),
            "content_type": content_type,
            "size_bytes": size_bytes,
            "checksum": checksum,
        },
    )
    return artifact


def save_bytes_artifact(
    *,
    job,
    artifact_type: str,
    object_key: str,
    content: bytes,
    content_type: str = "application/octet-stream",
    report_version=None,
) -> ReportArtifact:
    object_key = object_key.replace("\\", "/").lstrip("/")
    if not object_key:
        raise ArtifactStorageError("An artifact object key is required.")

    try:
        if _storage_backend() == "local":
            _write_local_file(object_key, content)
        else:
            ensure_bucket_exists()
            upload_bytes_to_minio(
                data=content,
                object_name=object_key,
                content_type=content_type,
            )
    except Exception as exc:
        raise ArtifactStorageError(
            f"Could not store artifact '{object_key}': {exc}"
        ) from exc

    return _persist_artifact_record(
        job=job,
        report_version=report_version,
        artifact_type=artifact_type,
        object_key=object_key,
        content_type=content_type,
        size_bytes=len(content),
        checksum=_calculate_checksum(content),
    )


def save_text_artifact(
    *,
    job,
    artifact_type: str,
    object_key: str,
    text: str,
    content_type: str = "text/plain",
    report_version=None,
) -> ReportArtifact:
    return save_bytes_artifact(
        job=job,
        report_version=report_version,
        artifact_type=artifact_type,
        object_key=object_key,
        content=text.encode("utf-8"),
        content_type=content_type,
    )


def save_json_artifact(
    *,
    job,
    artifact_type: str,
    object_key: str,
    data: Any,
    report_version=None,
) -> ReportArtifact:
    return save_text_artifact(
        job=job,
        report_version=report_version,
        artifact_type=artifact_type,
        object_key=object_key,
        text=json.dumps(data, indent=2, ensure_ascii=False, default=str),
        content_type="application/json",
    )


def save_file_artifact(
    *,
    job,
    artifact_type: str,
    object_key: str,
    local_file_path: str | Path,
    content_type: str | None = None,
    report_version=None,
) -> ReportArtifact:
    file_path = Path(local_file_path)
    if not file_path.exists() or not file_path.is_file():
        raise ArtifactStorageError(f"Artifact source file was not found: {file_path}")

    return save_bytes_artifact(
        job=job,
        report_version=report_version,
        artifact_type=artifact_type,
        object_key=object_key,
        content=file_path.read_bytes(),
        content_type=(
            content_type
            or mimetypes.guess_type(file_path.name)[0]
            or "application/octet-stream"
        ),
    )


def infer_artifact_type(file_path: Path) -> str:
    normalized = file_path.as_posix().lower()
    filename = file_path.name.lower()

    if file_path.suffix.lower() == ".pdf":
        return ReportArtifact.ArtifactType.FINAL_PDF
    if "approved_report_markdown" in filename:
        return ReportArtifact.ArtifactType.FINAL_MARKDOWN
    if "evidence_map" in normalized:
        return ReportArtifact.ArtifactType.EVIDENCE_MAP
    if "coverage" in normalized:
        return ReportArtifact.ArtifactType.COVERAGE
    if "missing" in normalized and "requirement" in normalized:
        return ReportArtifact.ArtifactType.MISSING_REQUIREMENTS
    if "disclosure_plan" in normalized:
        return ReportArtifact.ArtifactType.DISCLOSURE_PLAN
    if "claims_register" in normalized:
        return ReportArtifact.ArtifactType.CLAIMS_REGISTER
    if "approved_section" in normalized:
        return ReportArtifact.ArtifactType.APPROVED_SECTION
    if "draft" in normalized and "section" in normalized:
        return ReportArtifact.ArtifactType.DRAFT_SECTION
    if any(
        token in normalized
        for token in ("validation", "deterministic_gate", "judge", "quality", "connectivity")
    ):
        return ReportArtifact.ArtifactType.VALIDATION_RESULT
    if "audit" in normalized:
        return ReportArtifact.ArtifactType.AUDIT_SUMMARY
    if "warning" in normalized:
        return ReportArtifact.ArtifactType.WARNING_SUMMARY
    return ReportArtifact.ArtifactType.LOG


def upload_output_directory(
    *,
    job,
    report_version,
    local_directory: str | Path,
    object_prefix: str,
) -> list[ReportArtifact]:
    root = Path(local_directory)
    if not root.exists() or not root.is_dir():
        raise ArtifactStorageError(f"Report output directory was not found: {root}")

    uploaded_artifacts = []
    for file_path in sorted(root.rglob("*")):
        if not file_path.is_file():
            continue
        relative_path = file_path.relative_to(root)
        if any(part in IGNORED_DIRECTORY_NAMES for part in relative_path.parts):
            continue
        if file_path.suffix.lower() in IGNORED_FILE_SUFFIXES:
            continue

        uploaded_artifacts.append(
            save_file_artifact(
                job=job,
                report_version=report_version,
                artifact_type=infer_artifact_type(relative_path),
                object_key=f"{object_prefix.rstrip('/')}/{relative_path.as_posix()}",
                local_file_path=file_path,
            )
        )
    return uploaded_artifacts


def read_artifact(object_key: str) -> bytes:
    object_key = object_key.replace("\\", "/").lstrip("/")
    if _storage_backend() == "local":
        file_path = _get_local_root() / object_key
        if not file_path.exists():
            raise ArtifactStorageError(f"Artifact not found: {object_key}")
        return file_path.read_bytes()

    client = get_minio_client()
    try:
        response = client.get_object(
            bucket_name=_artifact_bucket_name(),
            object_name=object_key,
        )
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()
    except S3Error as exc:
        raise ArtifactStorageError(
            f"Artifact not found in MinIO: {object_key}"
        ) from exc


def get_artifact_download_url(
    object_key: str,
    expires_seconds: int | None = None,
) -> str:
    if _storage_backend() != "minio":
        raise ArtifactStorageError("Presigned URLs require MinIO artifact storage.")

    expiry = expires_seconds or int(
        getattr(settings, "MINIO_PRESIGNED_URL_EXPIRY_SECONDS", 3600)
    )
    return get_presigned_url(object_name=object_key, expires_seconds=expiry)