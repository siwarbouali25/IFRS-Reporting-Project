from pathlib import Path

from django.conf import settings

from data_preparation.services.report_generation_bridge import (
    SECTION_FILENAMES,
)
from payloads.models import PayloadManifest


class PayloadStorageError(Exception):
    """Raised when a payload manifest cannot be materialized."""


def _validate_payload_directory(
    *,
    payload_directory: Path,
    bank_code: str,
) -> Path:
    payload_directory = payload_directory.resolve()

    if not payload_directory.exists():
        raise PayloadStorageError(
            f"Payload directory does not exist: "
            f"{payload_directory}"
        )

    if not payload_directory.is_dir():
        raise PayloadStorageError(
            f"Payload path is not a directory: "
            f"{payload_directory}"
        )

    missing_files = []

    for template in SECTION_FILENAMES.values():
        filename = template.format(
            bank_code=bank_code.upper()
        )

        if not (payload_directory / filename).is_file():
            missing_files.append(filename)

    if missing_files:
        raise PayloadStorageError(
            "The payload manifest points to an incomplete "
            "payload directory. Missing files: "
            + ", ".join(missing_files)
        )

    return payload_directory


def resolve_payload_directory(
    manifest: PayloadManifest,
) -> Path:
    bank_code = manifest.bank.code

    if (
        manifest.storage_backend
        == PayloadManifest.StorageBackend.LOCAL
    ):
        candidates = []

        if manifest.local_folder:
            candidates.append(Path(manifest.local_folder))

        if (
            manifest.source_batch_id
            and manifest.source_batch.payload_folder
        ):
            candidates.append(
                Path(manifest.source_batch.payload_folder)
            )

        # Compatibility with old seeded manifests whose
        # "minio_prefix" was actually a path relative to
        # GENERATION_INPUT_ROOT.
        if manifest.minio_prefix:
            candidates.append(
                Path(settings.GENERATION_INPUT_ROOT)
                / manifest.minio_prefix.strip("/\\")
            )

        validation_errors = []

        for candidate in candidates:
            try:
                return _validate_payload_directory(
                    payload_directory=candidate,
                    bank_code=bank_code,
                )
            except PayloadStorageError as exc:
                validation_errors.append(str(exc))

        if validation_errors:
            raise PayloadStorageError(
                "No valid local payload directory could be "
                "resolved for this manifest. "
                + " | ".join(validation_errors)
            )

        raise PayloadStorageError(
            "This local payload manifest does not contain a "
            "local folder or a compatible legacy prefix."
        )

    if (
        manifest.storage_backend
        == PayloadManifest.StorageBackend.MINIO
    ):
        raise PayloadStorageError(
            "MinIO payload materialization is not connected "
            "to report generation yet. Keep the manifest on "
            "the local storage backend until that step is "
            "implemented."
        )

    raise PayloadStorageError(
        "Unsupported payload storage backend: "
        f"{manifest.storage_backend}"
    )