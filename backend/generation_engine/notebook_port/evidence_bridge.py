import copy
import datetime
import hashlib
import itertools
import json
import math
import os
import random
import re
import shutil
import statistics
import time
import traceback
import urllib
import urllib.error
import urllib.request
import uuid
import warnings
from collections import Counter, OrderedDict, defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from pydoc import resolve
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union


try:
    import pandas as pd
except Exception:
    pd = None


try:
    import numpy as np
except Exception:
    np = None


EVIDENCE_STOP_MARKER = "CELL 9B — STRICT EVIDENCE"
FULL_REPORT_STOP_MARKER = "CELL 22 — AUDIT SUMMARY"


def _noop_display(*args, **kwargs):
    return None


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
    Skip only real notebook/shell command cells.

    Important:
    do not skip a cell just because it contains the text "pip install"
    inside a Python string/error message. CELL 1 contains:
    "Install python-dotenv first: pip install python-dotenv"
    and must execute.
    """

    stripped = source.strip()

    if not stripped:
        return True

    for line in stripped.splitlines():
        clean = line.strip().lower()

        if not clean:
            continue

        if clean.startswith("!pip"):
            return True

        if clean.startswith("%pip"):
            return True

        if clean.startswith("!python"):
            return True

        if clean.startswith("%matplotlib"):
            return True

        if clean.startswith("pip install"):
            return True

        if clean.startswith("python -m pip"):
            return True

        if clean.startswith("import ipywidgets"):
            return True

        if clean.startswith("from ipywidgets"):
            return True

    return False


def _select_notebook_cells_until_stop_marker(
    cells: list[dict[str, Any]],
    stop_marker: str,
) -> list[tuple[str, str]]:
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


def _build_notebook_dirs(output_dir: Path) -> dict[str, Path]:
    """
    Exact notebook output directory structure.
    Includes later directories introduced by patch cells.
    """

    return {
        "evidence_maps": output_dir / "01_evidence_maps",
        "coverage": output_dir / "02_coverage",
        "missing_requirements": output_dir / "03_missing_requirements",
        "plans": output_dir / "04_disclosure_plans",
        "drafts": output_dir / "05_draft_sections",
        "claims": output_dir / "06_claims_registers",
        "gates": output_dir / "07_deterministic_gates",
        "judges": output_dir / "08_judge_results",
        "revisions": output_dir / "09_revised_sections",
        "approved": output_dir / "10_approved_sections",
        "connectivity": output_dir / "11_connectivity",
        "handoff": output_dir / "12_pdf_handoff",
        "final_quality": output_dir / "13_final_quality",
        "quality_refinement": output_dir / "14_quality_refinement",
        "final_editorial": output_dir / "15_final_editorial",
        "audit_logs": output_dir / "audit_logs",
    }


def _ensure_notebook_dirs(output_dir: Path) -> dict[str, Path]:
    dirs = _build_notebook_dirs(output_dir)

    for folder in dirs.values():
        folder.mkdir(parents=True, exist_ok=True)

    return dirs


def _build_env_values(
    *,
    input_root: Path,
    payload_dir: Path,
    requirements_dir: Path,
    style_system_dir: Path,
    output_dir: Path,
) -> dict[str, str]:
    """
    Environment aliases for notebook cells that read os.environ.
    """

    return {
        # Data root
        "GEN_DATA_DIR": str(input_root),

        # Payload aliases
        "PAYLOAD_DIR": str(payload_dir),
        "PAYLOADS_DIR": str(payload_dir),
        "BANK_PAYLOAD_DIR": str(payload_dir),
        "INPUT_PAYLOAD_DIR": str(payload_dir),

        # IFRS requirements aliases
        "IFRS_REQUIREMENTS_DIR": str(requirements_dir),
        "REQUIREMENTS_DIR": str(requirements_dir),
        "IFRS_ASSET_DIR": str(requirements_dir),
        "IFRS_REQUIREMENTS_PATH": str(requirements_dir),

        # Style aliases
        "STYLE_SYSTEM_DIR": str(style_system_dir),
        "STYLE_ASSET_DIR": str(style_system_dir),
        "STYLE_ASSETS_DIR": str(style_system_dir),
        "STYLE_SYSTEM_PATH": str(style_system_dir),

        # Output aliases
        "GENERATION_OUTPUT_DIR": str(output_dir),
        "GENERATED_REPORTS_DIR": str(output_dir),
        "OUTPUT_DIR": str(output_dir),
        "REPORT_OUTPUT_DIR": str(output_dir),
        "AGENTIC_REPORT_OUTPUT_DIR": str(output_dir),

        # Pipeline controls
        "PIPELINE_MODE": "synthetic_demo",
        "ALLOW_PARTIAL_COVERAGE": "true",
        "USE_FUZZY_EVIDENCE_MAPPER": "false",
        "ENABLE_FUZZY_EVIDENCE_MAPPER": "false",
        "RUN_FUZZY_EVIDENCE_MAPPER": "false",
        "MAX_REVISION_LOOPS": "2",
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
    Initial namespace used when executing notebook cells outside Jupyter.

    CELL 1 defines the official notebook variables. These values are safe
    fallbacks and Django-controlled path overrides.
    """

    notebook_dir = notebook_path.parent
    dirs = _ensure_notebook_dirs(output_dir)

    return {
        "__name__": "__notebook_bridge__",
        "__file__": str(notebook_path),

        # Display fallback for non-Jupyter execution
        "display": _noop_display,

        # Common modules
        "os": os,
        "json": json,
        "re": re,
        "math": math,
        "datetime": datetime,
        "time": time,
        "copy": copy,
        "hashlib": hashlib,
        "itertools": itertools,
        "statistics": statistics,
        "traceback": traceback,
        "warnings": warnings,
        "uuid": uuid,
        "shutil": shutil,
        "random": random,
        "urllib": urllib,
        "pd": pd,
        "np": np,

        # Common classes/functions
        "Path": Path,
        "Counter": Counter,
        "defaultdict": defaultdict,
        "OrderedDict": OrderedDict,
        "dataclass": dataclass,
        "field": field,
        "resolve": resolve,
        "Any": Any,
        "Dict": Dict,
        "List": List,
        "Tuple": Tuple,
        "Optional": Optional,
        "Union": Union,
        "Iterable": Iterable,
        "Sequence": Sequence,

        # Root aliases
        "CURRENT_DIR": notebook_dir,
        "CURRENT_PATH": notebook_dir,
        "WORKING_DIR": notebook_dir,
        "NOTEBOOK_DIR": notebook_dir,
        "BASE_DIR": notebook_dir,
        "PROJECT_ROOT": notebook_dir,
        "ROOT_DIR": notebook_dir,

        # Data root
        "INPUT_ROOT": input_root,
        "GEN_DATA_DIR": input_root,

        # Input paths
        "PAYLOAD_DIR": payload_dir,
        "PAYLOADS_DIR": payload_dir,
        "BANK_PAYLOAD_DIR": payload_dir,
        "INPUT_PAYLOAD_DIR": payload_dir,

        "REQUIREMENTS_DIR": requirements_dir,
        "IFRS_REQUIREMENTS_DIR": requirements_dir,
        "IFRS_ASSET_DIR": requirements_dir,
        "IFRS_REQUIREMENTS_PATH": requirements_dir,

        "STYLE_SYSTEM_DIR": style_system_dir,
        "STYLE_ASSET_DIR": style_system_dir,
        "STYLE_ASSETS_DIR": style_system_dir,
        "STYLE_SYSTEM_PATH": style_system_dir,

        # Output paths
        "OUTPUT_DIR": output_dir,
        "GENERATION_OUTPUT_DIR": output_dir,
        "GENERATED_REPORTS_DIR": output_dir,
        "REPORT_OUTPUT_DIR": output_dir,
        "AGENTIC_REPORT_OUTPUT_DIR": output_dir,

        "DIRS": dirs,

        # Notebook section constants
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

        # Pipeline controls
        "PIPELINE_MODE": "synthetic_demo",
        "FORBID_INVENTION": True,
        "ALLOW_PARTIAL_COVERAGE": True,
        "USE_FUZZY_EVIDENCE_MAPPER": False,
        "ENABLE_FUZZY_EVIDENCE_MAPPER": False,
        "RUN_FUZZY_EVIDENCE_MAPPER": False,
        "MAX_REVISION_LOOPS": 2,
    }


def _refresh_runtime_namespace(
    namespace: dict[str, Any],
    *,
    input_root: Path,
    payload_dir: Path,
    requirements_dir: Path,
    style_system_dir: Path,
    output_dir: Path,
) -> None:
    """
    Reapply Django-controlled paths before and after each notebook cell.

    Do not override SECTIONS here. CELL 1 should define the exact notebook
    section names.
    """

    notebook_dir = namespace.get("NOTEBOOK_DIR", Path.cwd())
    dirs = _ensure_notebook_dirs(output_dir)

    namespace.update(
        {
            "display": _noop_display,

            "CURRENT_DIR": notebook_dir,
            "CURRENT_PATH": notebook_dir,
            "WORKING_DIR": notebook_dir,
            "NOTEBOOK_DIR": notebook_dir,

            "INPUT_ROOT": input_root,
            "GEN_DATA_DIR": input_root,

            "PAYLOAD_DIR": payload_dir,
            "PAYLOADS_DIR": payload_dir,
            "BANK_PAYLOAD_DIR": payload_dir,
            "INPUT_PAYLOAD_DIR": payload_dir,

            "REQUIREMENTS_DIR": requirements_dir,
            "IFRS_REQUIREMENTS_DIR": requirements_dir,
            "IFRS_ASSET_DIR": requirements_dir,
            "IFRS_REQUIREMENTS_PATH": requirements_dir,

            "STYLE_SYSTEM_DIR": style_system_dir,
            "STYLE_ASSET_DIR": style_system_dir,
            "STYLE_ASSETS_DIR": style_system_dir,
            "STYLE_SYSTEM_PATH": style_system_dir,

            "OUTPUT_DIR": output_dir,
            "GENERATION_OUTPUT_DIR": output_dir,
            "GENERATED_REPORTS_DIR": output_dir,
            "REPORT_OUTPUT_DIR": output_dir,
            "AGENTIC_REPORT_OUTPUT_DIR": output_dir,

            "DIRS": dirs,

            "USE_FUZZY_EVIDENCE_MAPPER": False,
            "ENABLE_FUZZY_EVIDENCE_MAPPER": False,
            "RUN_FUZZY_EVIDENCE_MAPPER": False,
        }
    )


def _serialise_warning_safe(value: Any) -> Any:
    try:
        json.dumps(value, default=str)
        return value
    except TypeError:
        return str(value)


def _execute_notebook_until_marker(
    *,
    notebook_path: Path,
    input_root: Path,
    payload_prefix: str,
    ifrs_asset_prefix: str,
    style_asset_prefix: str,
    output_dir: Path,
    stop_marker: str,
) -> tuple[dict[str, Any], list[str]]:
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
    _ensure_notebook_dirs(output_dir)

    cells = _read_notebook_cells(notebook_path)
    selected_cells = _select_notebook_cells_until_stop_marker(
        cells=cells,
        stop_marker=stop_marker,
    )

    namespace = _build_namespace_values(
        notebook_path=notebook_path,
        input_root=input_root,
        payload_dir=payload_dir,
        requirements_dir=requirements_dir,
        style_system_dir=style_system_dir,
        output_dir=output_dir,
    )

    env_values = _build_env_values(
        input_root=input_root,
        payload_dir=payload_dir,
        requirements_dir=requirements_dir,
        style_system_dir=style_system_dir,
        output_dir=output_dir,
    )

    executed_cells: list[str] = []

    with temporary_env(env_values):
        with temporary_working_directory(notebook_path.parent):
            for cell_name, source in selected_cells:
                _refresh_runtime_namespace(
                    namespace,
                    input_root=input_root,
                    payload_dir=payload_dir,
                    requirements_dir=requirements_dir,
                    style_system_dir=style_system_dir,
                    output_dir=output_dir,
                )

                compiled = compile(
                    source,
                    filename=f"<notebook:{cell_name}>",
                    mode="exec",
                )

                try:
                    exec(compiled, namespace)
                except Exception as exc:
                    raise RuntimeError(
                        f"Notebook bridge failed while executing {cell_name}: {exc}"
                    ) from exc

                executed_cells.append(cell_name)

                _refresh_runtime_namespace(
                    namespace,
                    input_root=input_root,
                    payload_dir=payload_dir,
                    requirements_dir=requirements_dir,
                    style_system_dir=style_system_dir,
                    output_dir=output_dir,
                )

    return namespace, executed_cells


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
    Runs notebook cells from the start until strict evidence.
    Kept for evidence parity testing.
    """

    namespace, executed_cells = _execute_notebook_until_marker(
        notebook_path=notebook_path,
        input_root=input_root,
        payload_prefix=payload_prefix,
        ifrs_asset_prefix=ifrs_asset_prefix,
        style_asset_prefix=style_asset_prefix,
        output_dir=output_dir,
        stop_marker=EVIDENCE_STOP_MARKER,
    )

    required_outputs = [
        "requirements_by_section",
        "payloads_by_section",
        "evidence_maps_by_section",
        "evidence_map_summaries",
        "coverage_by_section",
        "missing_registers_by_section",
        "SECTION_SLUGS",
    ]

    missing_outputs = [key for key in required_outputs if key not in namespace]

    if missing_outputs:
        available_keys = sorted(
            key for key in namespace.keys()
            if not key.startswith("__")
        )

        raise RuntimeError(
            "Notebook evidence bridge did not produce expected outputs: "
            + ", ".join(missing_outputs)
            + "\n\nAvailable notebook variables:\n"
            + "\n".join(available_keys[:400])
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
        "section_slugs": _serialise_warning_safe(namespace["SECTION_SLUGS"]),
        "output_dir": str(namespace.get("OUTPUT_DIR", "")),
        "executed_cells": executed_cells,
        "executed_cells_count": len(executed_cells),
        "stop_marker": EVIDENCE_STOP_MARKER,
    }


def run_notebook_full_generation_stage(
    *,
    notebook_path: Path,
    input_root: Path,
    payload_prefix: str,
    ifrs_asset_prefix: str,
    style_asset_prefix: str,
    output_dir: Path,
) -> dict[str, Any]:
    """
    Runs the full notebook report-generation pipeline.

    Temporary bridge mode:
    - exact notebook logic
    - exact notebook outputs
    - no placeholder Django generation logic
    """

    namespace, executed_cells = _execute_notebook_until_marker(
        notebook_path=notebook_path,
        input_root=input_root,
        payload_prefix=payload_prefix,
        ifrs_asset_prefix=ifrs_asset_prefix,
        style_asset_prefix=style_asset_prefix,
        output_dir=output_dir,
        stop_marker=FULL_REPORT_STOP_MARKER,
    )

    required_outputs = [
        "requirements_by_section",
        "payloads_by_section",
        "evidence_maps_by_section",
        "coverage_by_section",
        "missing_registers_by_section",
        "plans_by_section",
        "section_results",
        "final_markdown",
        "handoff_manifest",
        "summary",
    ]

    missing_outputs = [key for key in required_outputs if key not in namespace]

    if missing_outputs:
        available_keys = sorted(
            key for key in namespace.keys()
            if not key.startswith("__")
        )

        raise RuntimeError(
            "Full notebook bridge did not produce expected outputs: "
            + ", ".join(missing_outputs)
            + "\n\nAvailable notebook variables:\n"
            + "\n".join(available_keys[:500])
        )

    return {
        "requirements_by_section": _serialise_warning_safe(
            namespace.get("requirements_by_section")
        ),
        "payloads_by_section": _serialise_warning_safe(
            namespace.get("payloads_by_section")
        ),
        "evidence_maps_by_section": _serialise_warning_safe(
            namespace.get("evidence_maps_by_section")
        ),
        "evidence_map_summaries": _serialise_warning_safe(
            namespace.get("evidence_map_summaries")
        ),
        "coverage_by_section": _serialise_warning_safe(
            namespace.get("coverage_by_section")
        ),
        "missing_registers_by_section": _serialise_warning_safe(
            namespace.get("missing_registers_by_section")
        ),
        "plans_by_section": _serialise_warning_safe(
            namespace.get("plans_by_section")
        ),
        "section_results": _serialise_warning_safe(
            namespace.get("section_results")
        ),
        "quality_refinement_result": _serialise_warning_safe(
            namespace.get("quality_refinement_result")
        ),
        "final_quality_result": _serialise_warning_safe(
            namespace.get("final_quality_result")
        ),
        "final_editorial_result": _serialise_warning_safe(
            namespace.get("final_editorial_result")
        ),
        "connectivity_result": _serialise_warning_safe(
            namespace.get("connectivity_result")
        ),
        "final_markdown": namespace.get("final_markdown", ""),
        "final_markdown_path": str(namespace.get("final_markdown_path", "")),
        "handoff_manifest": _serialise_warning_safe(
            namespace.get("handoff_manifest")
        ),
        "audit_summary": _serialise_warning_safe(namespace.get("summary")),
        "section_slugs": _serialise_warning_safe(namespace.get("SECTION_SLUGS")),
        "dirs": _serialise_warning_safe(namespace.get("DIRS")),
        "output_dir": str(namespace.get("OUTPUT_DIR", "")),
        "executed_cells": executed_cells,
        "executed_cells_count": len(executed_cells),
        "stop_marker": FULL_REPORT_STOP_MARKER,
    }