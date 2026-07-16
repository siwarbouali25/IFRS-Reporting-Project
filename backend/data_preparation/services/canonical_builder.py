import csv
import json
import shutil
from pathlib import Path
from typing import Dict, List

from django.conf import settings

from data_preparation.models import DataUploadBatch
from data_preparation.services.notebook_contract import resolve_notebook_table_name
from data_preparation.services.upload_extractor import get_mapping_folder


def get_batch_base_folder(batch: DataUploadBatch) -> Path:
    return Path(settings.MEDIA_ROOT) / "data_preparation" / "batches" / str(batch.id)


def get_canonical_folder(batch: DataUploadBatch) -> Path:
    return get_batch_base_folder(batch) / "canonical"


def load_column_mapping(batch: DataUploadBatch) -> Dict:
    mapping_folder = get_mapping_folder(batch)
    mapping_path = mapping_folder / "column_mapping.json"

    if not mapping_path.exists():
        raise FileNotFoundError(
            "column_mapping.json not found. Run column mapping before building canonical CSVs."
        )

    with open(mapping_path, "r", encoding="utf-8") as f:
        return json.load(f)


def clean_canonical_folder(canonical_folder: Path) -> None:
    if canonical_folder.exists():
        shutil.rmtree(canonical_folder)

    canonical_folder.mkdir(parents=True, exist_ok=True)


def read_csv_rows(csv_path: Path) -> List[Dict]:
    encodings = ["utf-8-sig", "utf-8", "latin-1"]

    for encoding in encodings:
        try:
            with open(csv_path, "r", encoding=encoding, newline="") as f:
                reader = csv.DictReader(f)
                return list(reader)
        except UnicodeDecodeError:
            continue

    raise UnicodeDecodeError(
        "csv",
        b"",
        0,
        1,
        f"Could not decode CSV file: {csv_path}",
    )


def write_csv_rows(csv_path: Path, fieldnames: List[str], rows: List[Dict]) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_canonical_rows(source_rows: List[Dict], final_column_mapping: Dict) -> List[Dict]:
    canonical_rows = []

    for source_row in source_rows:
        canonical_row = {}

        for canonical_column, source_column in final_column_mapping.items():
            if source_column is None:
                canonical_row[canonical_column] = ""
            else:
                canonical_row[canonical_column] = source_row.get(source_column, "")

        canonical_rows.append(canonical_row)

    return canonical_rows


def resolve_mapping_notebook_table_name(mapping: Dict) -> str:
    """
    Resolve the final CSV/table name expected by the notebook.

    This uses the uploaded/source filename first, then detector output.
    This is important because the detector can misclassify a file, while the source
    filename may already be the exact notebook table name.
    """
    return resolve_notebook_table_name(
        source_filename=mapping.get("source_filename"),
        detected_table=mapping.get("detected_table"),
    )


def build_canonical_csv_for_mapping(mapping: Dict, canonical_folder: Path) -> Dict:
    detected_table = mapping.get("detected_table")
    source_filename = mapping.get("source_filename")
    source_path = Path(mapping.get("source_path"))
    final_column_mapping = mapping.get("final_column_mapping", {})

    notebook_table_name = resolve_mapping_notebook_table_name(mapping)

    if not notebook_table_name:
        raise ValueError(
            f"Could not resolve notebook table name for file {source_filename}. "
            f"Detected table: {detected_table}"
        )

    if not source_path.exists():
        raise FileNotFoundError(f"Source CSV file not found: {source_path}")

    if not final_column_mapping:
        raise ValueError(
            f"No final column mapping found for file {source_filename}. "
            f"Detected table: {detected_table}"
        )

    source_rows = read_csv_rows(source_path)
    canonical_rows = build_canonical_rows(source_rows, final_column_mapping)

    canonical_columns = list(final_column_mapping.keys())
    output_filename = f"{notebook_table_name}.csv"
    output_path = canonical_folder / output_filename

    write_csv_rows(
        csv_path=output_path,
        fieldnames=canonical_columns,
        rows=canonical_rows,
    )

    return {
        "detected_table": detected_table,
        "notebook_table_name": notebook_table_name,
        "source_filename": source_filename,
        "output_filename": output_filename,
        "output_path": str(output_path),
        "row_count": len(canonical_rows),
        "column_count": len(canonical_columns),
        "columns": canonical_columns,
    }


def build_canonical_csvs_for_batch(batch: DataUploadBatch) -> Dict:
    mapping_result = load_column_mapping(batch)

    hard_blocking_mappings = []

    for mapping in mapping_result.get("mappings", []):
        notebook_table_name = resolve_mapping_notebook_table_name(mapping)
        final_column_mapping = mapping.get("final_column_mapping", {})

        if not notebook_table_name or not final_column_mapping:
            hard_blocking_mappings.append(
                {
                    "source_filename": mapping.get("source_filename"),
                    "detected_table": mapping.get("detected_table"),
                    "resolved_notebook_table_name": notebook_table_name,
                    "reason": "Missing resolved notebook table name or final column mapping.",
                }
            )

    if hard_blocking_mappings:
        raise ValueError(
            f"Some files cannot be converted to canonical CSVs: {hard_blocking_mappings}"
        )

    canonical_folder = get_canonical_folder(batch)
    mapping_folder = get_mapping_folder(batch)

    clean_canonical_folder(canonical_folder)

    outputs = []
    errors = []
    seen_output_files = {}

    for mapping in mapping_result.get("mappings", []):
        try:
            output = build_canonical_csv_for_mapping(
                mapping=mapping,
                canonical_folder=canonical_folder,
            )

            output_filename = output["output_filename"]
            if output_filename in seen_output_files:
                raise ValueError(
                    f"Duplicate canonical output file {output_filename}. "
                    f"Previous source: {seen_output_files[output_filename]}, "
                    f"current source: {mapping.get('source_filename')}"
                )

            seen_output_files[output_filename] = mapping.get("source_filename")
            outputs.append(output)

        except Exception as exc:
            errors.append(
                {
                    "source_filename": mapping.get("source_filename"),
                    "detected_table": mapping.get("detected_table"),
                    "resolved_notebook_table_name": resolve_mapping_notebook_table_name(mapping),
                    "error": str(exc),
                }
            )

    result = {
        "batch_id": str(batch.id),
        "canonical_folder": str(canonical_folder),
        "total_canonical_files": len(outputs),
        "outputs": outputs,
        "errors": errors,
    }

    output_manifest_path = mapping_folder / "canonical_manifest.json"

    with open(output_manifest_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    result["manifest_path"] = str(output_manifest_path)

    return result
