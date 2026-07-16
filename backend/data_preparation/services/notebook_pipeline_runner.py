import csv
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List

from django.conf import settings

from data_preparation.models import DataUploadBatch
from data_preparation.services.canonical_builder import get_canonical_folder
from data_preparation.services.notebook_contract import (
    find_missing_required_notebook_tables,
    list_available_notebook_tables,
)


def get_batch_base_folder(batch: DataUploadBatch) -> Path:
    return Path(settings.MEDIA_ROOT) / "data_preparation" / "batches" / str(batch.id)


def get_payloads_folder(batch: DataUploadBatch) -> Path:
    return get_batch_base_folder(batch) / "payloads"


def get_logs_folder(batch: DataUploadBatch) -> Path:
    return get_batch_base_folder(batch) / "logs"


def collect_payload_files(payloads_folder: Path) -> List[Dict]:
    payload_files = sorted(payloads_folder.glob("payload_BANK*.json"))

    return [
        {
            "filename": path.name,
            "path": str(path),
            "size_bytes": path.stat().st_size,
        }
        for path in payload_files
    ]


def clean_old_payload_outputs(payloads_folder: Path) -> None:
    payloads_folder.mkdir(parents=True, exist_ok=True)

    for path in payloads_folder.glob("payload_BANK*.json"):
        path.unlink()

    manifest = payloads_folder / "payload_manifest.json"
    if manifest.exists():
        manifest.unlink()


def _read_csv_rows(csv_path: Path) -> tuple[List[str], List[Dict[str, str]], str]:
    encodings = ["utf-8-sig", "utf-8", "latin-1"]

    for encoding in encodings:
        try:
            with open(csv_path, "r", encoding=encoding, newline="") as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames or []
                rows = list(reader)
            return fieldnames, rows, encoding
        except UnicodeDecodeError:
            continue

    raise ValueError(f"Could not decode CSV file: {csv_path}")


def _write_csv_rows(csv_path: Path, fieldnames: List[str], rows: List[Dict[str, str]]) -> None:
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _ensure_csv_columns(csv_path: Path, column_defaults: Dict[str, object]) -> List[str]:
    """
    Adds missing compatibility columns expected by the notebook.

    This is a defensive bridge while the notebook is still used as the
    execution engine. It prevents a notebook KeyError when a valid canonical
    CSV uses a slightly different but accepted column contract.
    """

    if not csv_path.exists():
        return []

    fieldnames, rows, _encoding = _read_csv_rows(csv_path)
    added_columns = []

    for column_name, default_value in column_defaults.items():
        if column_name in fieldnames:
            continue

        fieldnames.append(column_name)
        added_columns.append(column_name)

        for row in rows:
            if callable(default_value):
                row[column_name] = default_value(row)
            else:
                row[column_name] = default_value

    if added_columns:
        _write_csv_rows(csv_path, fieldnames, rows)

    return added_columns


def patch_canonical_compatibility_for_notebook(canonical_folder: Path) -> Dict:
    """
    Compatibility patch before running the data-prep notebook.

    The current notebook still expects some legacy/helper columns directly.
    The canonical layer may generate valid modern names, so this function adds
    safe fallback columns without changing source uploads or report scoring.
    """

    patch_summary = {
        "patched_files": [],
        "added_columns": {},
    }

    collateral_path = canonical_folder / "collateral.csv"
    collateral_added = _ensure_csv_columns(
        collateral_path,
        {
            "flood_zone_class": lambda row: (
                row.get("flood_zone_class")
                or row.get("flood_risk_score")
                or "unknown"
            ),
            "property_type": "unknown",
            "epc_rating": "unknown",
            "country": "unknown",
            "physical_risk_score": "0",
            "exposure_amount_meur": "0",
            "market_value_meur": "0",
            "ltv_pct": "",
        },
    )

    if collateral_added:
        patch_summary["patched_files"].append("collateral.csv")
        patch_summary["added_columns"]["collateral.csv"] = collateral_added

    return patch_summary


def run_notebook_pipeline_for_batch(batch: DataUploadBatch) -> Dict:
    canonical_folder = get_canonical_folder(batch)
    payloads_folder = get_payloads_folder(batch)
    logs_folder = get_logs_folder(batch)

    payloads_folder.mkdir(parents=True, exist_ok=True)
    logs_folder.mkdir(parents=True, exist_ok=True)

    notebook_path = Path(settings.DATA_PREP_NOTEBOOK_PATH)
    requirements_dir = Path(settings.IFRS_REQUIREMENTS_DIR)

    if not notebook_path.exists():
        raise FileNotFoundError(f"Data-prep notebook not found: {notebook_path}")

    if not canonical_folder.exists():
        raise FileNotFoundError(
            f"Canonical folder not found: {canonical_folder}. Build canonical CSVs first."
        )

    missing_required_tables = find_missing_required_notebook_tables(canonical_folder)

    if missing_required_tables:
        available_tables = list_available_notebook_tables(canonical_folder)

        raise FileNotFoundError(
            "Canonical folder is missing required notebook tables.\n"
            f"Missing tables: {missing_required_tables}\n"
            f"Available tables: {available_tables}\n"
            f"Canonical folder: {canonical_folder}\n"
            "Fix table detection/mapping before running the notebook."
        )

    if not requirements_dir.exists():
        raise FileNotFoundError(f"IFRS requirements folder not found: {requirements_dir}")

    compatibility_patch = patch_canonical_compatibility_for_notebook(canonical_folder)

    clean_old_payload_outputs(payloads_folder)

    executed_notebook_path = logs_folder / "executed_data_prep_pipeline.ipynb"
    stdout_path = logs_folder / "notebook_stdout.log"
    stderr_path = logs_folder / "notebook_stderr.log"

    env = os.environ.copy()
    env["IFRS_PROJECT_ROOT"] = str(settings.BASE_DIR)
    env["IFRS_DATA_DIR"] = str(canonical_folder)
    env["IFRS_OUTPUT_DIR"] = str(payloads_folder)
    env["IFRS_REQUIREMENTS_DIR"] = str(requirements_dir)

    command = [
        sys.executable,
        "-m",
        "jupyter",
        "nbconvert",
        "--to",
        "notebook",
        "--execute",
        str(notebook_path),
        "--output",
        executed_notebook_path.name,
        "--output-dir",
        str(logs_folder),
        "--ExecutePreprocessor.timeout=1800",
    ]

    completed = subprocess.run(
        command,
        cwd=str(settings.BASE_DIR),
        env=env,
        capture_output=True,
        text=True,
    )

    stdout_path.write_text(completed.stdout or "", encoding="utf-8")
    stderr_path.write_text(completed.stderr or "", encoding="utf-8")

    if completed.returncode != 0:
        raise RuntimeError(
            "Notebook data-prep pipeline failed. "
            f"Check stderr log: {stderr_path}"
        )

    payload_outputs = collect_payload_files(payloads_folder)

    manifest = {
        "batch_id": str(batch.id),
        "canonical_folder": str(canonical_folder),
        "payloads_folder": str(payloads_folder),
        "requirements_dir": str(requirements_dir),
        "executed_notebook_path": str(executed_notebook_path),
        "stdout_log": str(stdout_path),
        "stderr_log": str(stderr_path),
        "compatibility_patch": compatibility_patch,
        "payload_count": len(payload_outputs),
        "payload_outputs": payload_outputs,
    }

    manifest_path = payloads_folder / "payload_manifest.json"

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    manifest["manifest_path"] = str(manifest_path)

    return manifest
