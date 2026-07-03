from pathlib import Path
from typing import Any

from generation_engine.schemas import GenerationWarningData, LoaderResult
from generation_engine.utils import read_json_file


def load_requirements_from_prefix(
    *,
    input_root: str | Path,
    minio_prefix: str,
) -> LoaderResult:
    """
    Load IFRS requirement JSON files from a local folder.

    This is flexible because your extracted IFRS requirements may be stored as:
    - one big JSON file
    - one JSON file per section
    - nested JSON files
    """

    base_path = Path(input_root) / minio_prefix.strip("/")

    if not base_path.exists():
        raise FileNotFoundError(f"IFRS requirements folder does not exist: {base_path}")

    requirements: dict[str, Any] = {}
    loaded_files: list[str] = []
    warnings: list[GenerationWarningData] = []

    json_files = sorted(base_path.rglob("*.json"))

    if not json_files:
        raise FileNotFoundError(f"No IFRS requirement JSON files found in {base_path}")

    for file_path in json_files:
        key = file_path.stem
        requirements[key] = read_json_file(file_path)
        loaded_files.append(str(file_path))

    return LoaderResult(
        data=requirements,
        loaded_files=loaded_files,
        missing_files=[],
        warnings=warnings,
    )