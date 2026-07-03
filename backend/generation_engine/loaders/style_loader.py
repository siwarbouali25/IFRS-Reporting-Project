from pathlib import Path
from typing import Any

from generation_engine.config import DEFAULT_SECTION_KEYS
from generation_engine.schemas import GenerationWarningData, LoaderResult
from generation_engine.utils import read_json_file, read_text_file


STYLE_FILE_NAMES = {
    "general_requirements": "general_requirements_style.json",
    "governance": "governance_style.json",
    "strategy": "strategy_style.json",
    "risk_management": "risk_management_style.json",
    "metrics_targets": "metrics_and_targets_style.json",
}


BLUEPRINT_FILE_NAMES = {
    "general_requirements": "general_requirements_blueprint.json",
    "governance": "governance_blueprint.json",
    "strategy": "strategy_blueprint.json",
    "risk_management": "risk_management_blueprint.json",
    "metrics_targets": "metrics_and_targets_blueprint.json",
}


GLOBAL_STYLE_FILES = {
    "global_style": {
        "file_name": "global_style_guide.json",
        "type": "json",
        "required": False,
    },
    "no_copying_rules": {
        "file_name": "no_copying_rules.md",
        "type": "text",
        "required": False,
    },
    "forbidden_terms": {
        "file_name": "forbidden_reference_terms.json",
        "type": "json",
        "required": False,
    },
    "table_patterns": {
        "file_name": "table_patterns.json",
        "type": "json",
        "required": False,
    },
    "style_rubric": {
        "file_name": "style_compliance_rubric.json",
        "type": "json",
        "required": False,
    },
    "layout_style_guide": {
        "file_name": "layout_style_guide.json",
        "type": "json",
        "required": False,
    },
}


def _read_style_file(file_path: Path, file_type: str) -> Any:
    if file_type == "json":
        return read_json_file(file_path)

    if file_type == "text":
        return read_text_file(file_path)

    raise ValueError(f"Unsupported style file type: {file_type}")


def load_style_assets_from_prefix(
    *,
    input_root: str | Path,
    minio_prefix: str,
) -> LoaderResult:
    """
    Load the full style system from a local folder.

    Current expected flat structure:

    style-assets/BANK01/style-v1/
      global_style_guide.json
      no_copying_rules.md
      forbidden_reference_terms.json
      table_patterns.json
      style_compliance_rubric.json
      layout_style_guide.json

      governance_style.json
      governance_blueprint.json
      ...

    Missing style files are warnings, not hard failures.
    The workflow can continue with defaults later.
    """

    base_path = Path(input_root) / minio_prefix.strip("/")

    if not base_path.exists():
        raise FileNotFoundError(f"Style assets folder does not exist: {base_path}")

    assets: dict[str, Any] = {
        "global_style": {},
        "no_copying_rules": "",
        "forbidden_terms": {},
        "table_patterns": {},
        "style_rubric": {},
        "layout_style_guide": {},
        "section_styles": {},
        "section_blueprints": {},
    }

    loaded_files: list[str] = []
    missing_files: list[str] = []
    warnings: list[GenerationWarningData] = []

    # Load global style-system files.
    for asset_key, file_config in GLOBAL_STYLE_FILES.items():
        file_name = file_config["file_name"]
        file_type = file_config["type"]
        file_path = base_path / file_name

        if file_path.exists():
            assets[asset_key] = _read_style_file(file_path, file_type)
            loaded_files.append(str(file_path))
        else:
            missing_files.append(str(file_path))
            warnings.append(
                GenerationWarningData(
                    stage="load_style_assets",
                    warning_type="missing_global_style_file",
                    message=f"Global style-system file was not found: {file_name}",
                    details={
                        "asset_key": asset_key,
                        "file": file_name,
                        "path": str(file_path),
                    },
                )
            )

    # Load section style guides and section blueprints.
    for section_key in DEFAULT_SECTION_KEYS:
        style_file_name = STYLE_FILE_NAMES[section_key]
        style_path = base_path / style_file_name

        if style_path.exists():
            assets["section_styles"][section_key] = read_json_file(style_path)
            loaded_files.append(str(style_path))
        else:
            assets["section_styles"][section_key] = {}
            missing_files.append(str(style_path))
            warnings.append(
                GenerationWarningData(
                    stage="load_style_assets",
                    warning_type="missing_section_style_file",
                    message=f"Section style file was not found: {style_file_name}",
                    details={
                        "section": section_key,
                        "file": style_file_name,
                        "path": str(style_path),
                    },
                )
            )

        blueprint_file_name = BLUEPRINT_FILE_NAMES[section_key]
        blueprint_path = base_path / blueprint_file_name

        if blueprint_path.exists():
            assets["section_blueprints"][section_key] = read_json_file(blueprint_path)
            loaded_files.append(str(blueprint_path))
        else:
            assets["section_blueprints"][section_key] = {}
            missing_files.append(str(blueprint_path))
            warnings.append(
                GenerationWarningData(
                    stage="load_style_assets",
                    warning_type="missing_section_blueprint_file",
                    message=f"Section blueprint file was not found: {blueprint_file_name}",
                    details={
                        "section": section_key,
                        "file": blueprint_file_name,
                        "path": str(blueprint_path),
                    },
                )
            )

    return LoaderResult(
        data=assets,
        loaded_files=loaded_files,
        missing_files=missing_files,
        warnings=warnings,
    )