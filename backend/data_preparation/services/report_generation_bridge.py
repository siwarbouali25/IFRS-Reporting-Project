from pathlib import Path
from typing import Any, Dict

from data_preparation.models import DataUploadBatch


SECTION_FILENAMES = {
    "full": "payload_{bank_code}.json",
    "general_requirements": (
        "payload_{bank_code}_general_requirements.json"
    ),
    "governance": "payload_{bank_code}_governance.json",
    "strategy": "payload_{bank_code}_strategy.json",
    "risk_management": (
        "payload_{bank_code}_risk_management.json"
    ),
    "metrics_targets": (
        "payload_{bank_code}_metrics_targets.json"
    ),
}


class PayloadBundleError(Exception):
    """Raised when a report-generation payload bundle is incomplete."""


def resolve_payload_folder(batch: DataUploadBatch) -> Path:
    """
    Resolve the local payload output directory of a preparation batch.
    """

    folder_value = getattr(batch, "payload_folder", None)

    if not folder_value:
        raise PayloadBundleError(
            f"Batch {batch.id} does not have a payload folder."
        )

    payload_folder = Path(folder_value)

    if not payload_folder.exists():
        raise PayloadBundleError(
            f"Payload folder does not exist: {payload_folder}"
        )

    if not payload_folder.is_dir():
        raise PayloadBundleError(
            f"Payload path is not a directory: {payload_folder}"
        )

    return payload_folder


def build_payload_bundle(
    batch: DataUploadBatch,
    bank_code: str,
    reporting_year: int,
) -> Dict[str, Any]:
    """
    Build and validate the payload bundle consumed by report generation.

    This function does not generate payloads. It only resolves payloads
    already produced by the data-preparation pipeline.
    """

    normalized_bank_code = bank_code.strip().upper()

    if not normalized_bank_code:
        raise PayloadBundleError("A bank code is required.")

    payload_folder = resolve_payload_folder(batch)

    payloads: Dict[str, str] = {}
    missing_files = []

    for section, filename_template in SECTION_FILENAMES.items():
        filename = filename_template.format(
            bank_code=normalized_bank_code
        )

        file_path = payload_folder / filename

        if not file_path.exists():
            missing_files.append(filename)
            continue

        payloads[section] = str(file_path.resolve())

    if missing_files:
        raise PayloadBundleError(
            "The report-generation payload bundle is incomplete. "
            f"Missing files: {', '.join(missing_files)}"
        )

    return {
        "batch_id": str(batch.id),
        "bank_code": normalized_bank_code,
        "reporting_year": int(reporting_year),
        "storage_backend": "local",
        "payload_folder": str(payload_folder.resolve()),
        "payloads": payloads,
    }