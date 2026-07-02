import hashlib
import json
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.files.base import ContentFile

from .models import ReportArtifact


class ArtifactStorageError(Exception):
    pass


def _get_local_root() -> Path:
    root = Path(settings.ARTIFACT_LOCAL_ROOT)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _calculate_checksum(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _write_local_file(object_key: str, content: bytes) -> Path:
    root = _get_local_root()
    file_path = root / object_key
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(content)
    return file_path


def save_text_artifact(
    *,
    job,
    artifact_type: str,
    object_key: str,
    text: str,
    content_type: str = "text/plain",
    report_version=None,
) -> ReportArtifact:
    content = text.encode("utf-8")

    if settings.ARTIFACT_STORAGE_BACKEND != "local":
        raise ArtifactStorageError("Only local artifact storage is implemented for now.")

    _write_local_file(object_key, content)

    return ReportArtifact.objects.create(
        job=job,
        report_version=report_version,
        artifact_type=artifact_type,
        bucket=settings.ARTIFACT_BUCKET_NAME,
        object_key=object_key,
        content_type=content_type,
        size_bytes=len(content),
        checksum=_calculate_checksum(content),
    )


def save_json_artifact(
    *,
    job,
    artifact_type: str,
    object_key: str,
    data: Any,
    report_version=None,
) -> ReportArtifact:
    text = json.dumps(data, indent=2, ensure_ascii=False)

    return save_text_artifact(
        job=job,
        report_version=report_version,
        artifact_type=artifact_type,
        object_key=object_key,
        text=text,
        content_type="application/json",
    )


def read_local_artifact(object_key: str) -> bytes:
    if settings.ARTIFACT_STORAGE_BACKEND != "local":
        raise ArtifactStorageError("Only local artifact storage is implemented for now.")

    file_path = _get_local_root() / object_key

    if not file_path.exists():
        raise ArtifactStorageError(f"Artifact not found: {object_key}")

    return file_path.read_bytes()