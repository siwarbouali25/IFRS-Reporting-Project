import json
import os
import re
import math
import datetime
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any


STOP_MARKER = "CELL 9B — STRICT EVIDENCE"


@contextmanager
def temporary_env(values: dict[str, str]):
    old_values = {}

    for key, value in values.items():
        old_values[key] = os.environ.get(key)
        os.environ[key] = value

    try:
        yield
    finally:
        for key, old_value in old_values.items():
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value


@contextmanager
def temporary_working_directory(path: Path):
    old_cwd = Path.cwd()

    os.chdir(path)

    try:
        yield
    finally:
        os.chdir(old_cwd)


def _read_notebook_cells(notebook_path: Path) -> list[dict[str, Any]]:
    if not notebook_path.exists():
        raise FileNotFoundError(f"Notebook not found: {notebook_path}")

    with notebook_path.open("r", encoding="utf-8") as f:
        notebook = json.load(f)

    return notebook.get("cells", [])


def _get_cell_source(cell: dict[str, Any]) -> str:
    source = cell.get("source", "")

    if isinstance(source, list):
        return "".join(source)

    return str(source)


def _is_notebook_only_cell(source: str) -> bool:
    """
    Skip cells that are safe in a notebook but unsafe/useless inside Django.
    We still execute normal Python cells in order.
    """

    stripped = source.strip()
    lowered = stripped.lower()

    if not stripped:
        return True

    notebook_only_markers = [
        "!pip",
        "%pip",
        "pip install",
        "!python",
        "%matplotlib",
        "ipywidgets",
    ]

    return any(marker in lowered for marker in notebook_only_markers)


def _select_notebook_cells_until_stop_marker(
    cells: list[dict[str, Any]],
    stop_marker: str,
) -> list[tuple[str, str]]:
    """
    Execute the notebook the way the notebook actually runs:
    from the beginning up to and including the strict evidence stage.
    """

    selected: list[tuple[str, str]] = []
    stop_found = False

    for index, cell in enumerate(cells):
        if cell.get("cell_type") != "code":
            continue

        source = _get_cell_source(cell)

        if _is_notebook_only_cell(source):
            continue

        selected.append((f"cell_{index}", source))

        if stop_marker in source:
            stop_found = True
            break

    if not stop_found:
        raise RuntimeError(
            f"Could not find stop marker in notebook: {stop_marker}"
        )

    return selected


def _prefix_to_path(input_root: Path, prefix: str) -> Path:
    return (Path(input_root) / str(prefix).strip("/")).resolve()


def _build_env_values(
    *,
    payload_dir: Path,
    requirements_dir: Path,
    style_system_dir: Path,
    output_dir: Path,
) -> dict[str, str]:
    """
    Set multiple aliases because the notebook may read different env names
    depending on the patched cell version.
    """

    return {
        # Payload aliases
        "PAYLOAD_DIR": str(payload_dir),
        "PAYLOADS_DIR": str(payload_dir),
        "BANK_PAYLOAD_DIR": str(payload_dir),
        "INPUT_PAYLOAD_DIR": str(payload_dir),

        # IFRS requirements aliases
        "IFRS_REQUIREMENTS_DIR": str(requirements_dir),
        "REQUIREMENTS_DIR": str(requirements_dir),
        "IFRS_ASSET_DIR": str(requirements_dir),

        # Style aliases
        "STYLE_SYSTEM_DIR": str(style_system_dir),
        "STYLE_ASSET_DIR": str(style_system_dir),
        "STYLE_ASSETS_DIR": str(style_system_dir),

        # Output aliases
        "GENERATION_OUTPUT_DIR": str(output_dir),
        "OUTPUT_DIR": str(output_dir),
        "REPORT_OUTPUT_DIR": str(output_dir),
        "AGENTIC_REPORT_OUTPUT_DIR": str(output_dir),

        # Behaviour flags
        "USE_FUZZY_EVIDENCE_MAPPER": "false",
        "ENABLE_FUZZY_EVIDENCE_MAPPER": "false",
        "RUN_FUZZY_EVIDENCE_MAPPER": "false",
    }


def _build_namespace_values(
    *,
    notebook_path: Path,
    input_root: Path,
    payload_dir: Path,
    requirements_dir: Path,
    style_system_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """
    The notebook does not only read from os.environ.
    Some cells expect variables like STYLE_SYSTEM_DIR to already exist.
    So we inject the same aliases directly into the notebook namespace.
    """

    return {
        "__name__": "__notebook_evidence_bridge__",
        "__file__": str(notebook_path),

        "os": os,
        "json": json,
        "Path": Path,
        "re": re,
        "math": math,
        "datetime": datetime,
        "time": time,

        # Root aliases
        "BASE_DIR": notebook_path.parent,
        "PROJECT_ROOT": notebook_path.parent,
        "INPUT_ROOT": input_root,

        # Payload aliases
        "PAYLOAD_DIR": payload_dir,
        "PAYLOADS_DIR": payload_dir,
        "BANK_PAYLOAD_DIR": payload_dir,
        "INPUT_PAYLOAD_DIR": payload_dir,

        # IFRS requirements aliases
        "IFRS_REQUIREMENTS_DIR": requirements_dir,
        "REQUIREMENTS_DIR": requirements_dir,
        "IFRS_ASSET_DIR": requirements_dir,

        # Style aliases
        "STYLE_SYSTEM_DIR": style_system_dir,
        "STYLE_ASSET_DIR": style_system_dir,
        "STYLE_ASSETS_DIR": style_system_dir,

                # Section constants expected by notebook cells
                # Section constants expected by the notebook
        # Important: these must be notebook display names, not Django slugs.
        "SECTIONS": [
            "General Requirements",
            "Governance",
            "Strategy",
            "Risk Management",
            "Metrics and Targets",
        ],

        "SECTION_SLUGS": {
            "General Requirements": "general_requirements",
            "Governance": "governance",
            "Strategy": "strategy",
            "Risk Management": "risk_management",
            "Metrics and Targets": "metrics_and_targets",
        },

        "SECTION_KEYS": {
            "General Requirements": "general_requirements",
            "Governance": "governance",
            "Strategy": "strategy",
            "Risk Management": "risk_management",
            "Metrics and Targets": "metrics_targets",
        },

        # Output aliases
        "GENERATION_OUTPUT_DIR": output_dir,
        "OUTPUT_DIR": output_dir,
        "REPORT_OUTPUT_DIR": output_dir,
        "AGENTIC_REPORT_OUTPUT_DIR": output_dir,

        # Behaviour flags
        "USE_FUZZY_EVIDENCE_MAPPER": False,
        "ENABLE_FUZZY_EVIDENCE_MAPPER": False,
        "RUN_FUZZY_EVIDENCE_MAPPER": False,
    }


def _serialise_warning_safe(value: Any) -> Any:
    """
    Keep return object JSON-safe enough for Django commands/artifact saving.
    """

    try:
        json.dumps(value, default=str)
        return value
    except TypeError:
        return str(value)


def run_notebook_evidence_stage(
    *,
    notebook_path: Path,
    input_root: Path,
    payload_prefix: str,
    ifrs_asset_prefix: str,
    style_asset_prefix: str,
    output_dir: Path,
) -> dict[str, Any]:
    """
    Runs the notebook evidence-mapping stage by executing notebook code cells
    in order from the beginning until CELL 9B — STRICT EVIDENCE.

    This is intentionally a bridge step.

    Goal:
    - match notebook outputs first
    - then refactor the exact notebook logic into clean production modules
    - later LangGraph nodes call those modules instead of executing notebook cells
    """

    notebook_path = Path(notebook_path).resolve()
    input_root = Path(input_root).resolve()
    output_dir = Path(output_dir).resolve()

    payload_dir = _prefix_to_path(input_root, payload_prefix)
    requirements_dir = _prefix_to_path(input_root, ifrs_asset_prefix)
    style_system_dir = _prefix_to_path(input_root, style_asset_prefix)

    if not payload_dir.exists():
        raise FileNotFoundError(f"Payload directory not found: {payload_dir}")

    if not requirements_dir.exists():
        raise FileNotFoundError(
            f"IFRS requirements directory not found: {requirements_dir}"
        )

    if not style_system_dir.exists():
        raise FileNotFoundError(
            f"Style system directory not found: {style_system_dir}"
        )

    output_dir.mkdir(parents=True, exist_ok=True)

    cells = _read_notebook_cells(notebook_path)
    selected_cells = _select_notebook_cells_until_stop_marker(
        cells=cells,
        stop_marker=STOP_MARKER,
    )

    namespace: dict[str, Any] = _build_namespace_values(
        notebook_path=notebook_path,
        input_root=input_root,
        payload_dir=payload_dir,
        requirements_dir=requirements_dir,
        style_system_dir=style_system_dir,
        output_dir=output_dir,
    )

    env_values = _build_env_values(
        payload_dir=payload_dir,
        requirements_dir=requirements_dir,
        style_system_dir=style_system_dir,
        output_dir=output_dir,
    )

    executed_cells: list[str] = []

    with temporary_env(env_values):
        with temporary_working_directory(notebook_path.parent):
            for cell_name, source in selected_cells:
                compiled = compile(
                    source,
                    filename=f"<notebook:{cell_name}>",
                    mode="exec",
                )

                exec(compiled, namespace)
                executed_cells.append(cell_name)

    required_outputs = [
        "requirements_by_section",
        "payloads_by_section",
        "evidence_maps_by_section",
        "evidence_map_summaries",
        "coverage_by_section",
        "missing_registers_by_section",
        "SECTION_SLUGS",
    ]

    missing_outputs = [
        key
        for key in required_outputs
        if key not in namespace
    ]

    if missing_outputs:
        available_keys = sorted(
            key for key in namespace.keys()
            if not key.startswith("__")
        )

        raise RuntimeError(
            "Notebook evidence bridge did not produce expected outputs: "
            + ", ".join(missing_outputs)
            + "\n\nAvailable notebook variables:\n"
            + "\n".join(available_keys[:300])
        )

    return {
        "requirements_by_section": _serialise_warning_safe(
            namespace["requirements_by_section"]
        ),
        "payloads_by_section": _serialise_warning_safe(
            namespace["payloads_by_section"]
        ),
        "evidence_maps_by_section": _serialise_warning_safe(
            namespace["evidence_maps_by_section"]
        ),
        "evidence_map_summaries": _serialise_warning_safe(
            namespace["evidence_map_summaries"]
        ),
        "coverage_by_section": _serialise_warning_safe(
            namespace["coverage_by_section"]
        ),
        "missing_registers_by_section": _serialise_warning_safe(
            namespace["missing_registers_by_section"]
        ),
        "section_slugs": _serialise_warning_safe(
            namespace["SECTION_SLUGS"]
        ),
        "output_dir": str(output_dir),
        "executed_cells": executed_cells,
        "executed_cells_count": len(executed_cells),
        "stop_marker": STOP_MARKER,
    }