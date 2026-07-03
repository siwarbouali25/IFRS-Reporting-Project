from pathlib import Path
from typing import Any

from generation_engine.config import DEFAULT_SECTION_KEYS
from generation_engine.schemas import GenerationWarningData, LoaderResult
from generation_engine.utils import read_json_file


PAYLOAD_FILE_NAMES = {
    "entity": "payload_{bank_code}.json",
    "general_requirements": "payload_{bank_code}_general_requirements.json",
    "governance": "payload_{bank_code}_governance.json",
    "strategy": "payload_{bank_code}_strategy.json",
    "risk_management": "payload_{bank_code}_risk_management.json",
    "metrics_targets": "payload_{bank_code}_metrics_targets.json",
}


def load_payloads_from_prefix(
    *,
    input_root: str | Path,
    minio_prefix: str,
    bank_code: str,
) -> LoaderResult:
    """
    Load clean payload JSON files from a local folder that mirrors the future MinIO prefix.

    Example:
    input_root = backend/generation_inputs
    minio_prefix = payloads/BANK01/2024/v1/

    Full resolved folder:
    backend/generation_inputs/payloads/BANK01/2024/v1/
    """

    base_path = Path(input_root) / minio_prefix.strip("/")

    payloads: dict[str, Any] = {}
    loaded_files: list[str] = []
    missing_files: list[str] = []
    warnings: list[GenerationWarningData] = []

    for key, pattern in PAYLOAD_FILE_NAMES.items():
        file_name = pattern.format(bank_code=bank_code)
        file_path = base_path / file_name

        if not file_path.exists():
            missing_files.append(str(file_path))
            payloads[key] = {}

            warnings.append(
                GenerationWarningData(
                    stage="load_payloads",
                    warning_type="missing_payload_file",
                    message=f"Payload file was not found: {file_name}",
                    details={
                        "section": key,
                        "file": file_name,
                        "path": str(file_path),
                    },
                )
            )

            continue

        payloads[key] = read_json_file(file_path)
        loaded_files.append(str(file_path))

    if not loaded_files:
        raise FileNotFoundError(
            f"No payload files were found in {base_path}. "
            "At least one payload file is required."
        )

    return LoaderResult(
        data=payloads,
        loaded_files=loaded_files,
        missing_files=missing_files,
        warnings=warnings,
    )