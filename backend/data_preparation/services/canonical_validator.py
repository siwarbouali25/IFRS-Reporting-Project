import csv
import json
from pathlib import Path
from typing import Dict, List

from data_preparation.models import DataUploadBatch
from data_preparation.services.canonical_builder import get_canonical_folder
from data_preparation.services.upload_extractor import get_mapping_folder


MINIMUM_REQUIRED_COLUMNS = {
    "banks": [
        "bank_id",
        "bank_name",
        "total_assets_meur",
        "reporting_currency",
        "fiscal_year_end",
    ],
    "board_minutes_extract": [
        "meeting_id",
        "committee_name",
        "meeting_date",
        "climate_agenda_flag",
        "climate_topics_discussed",
        "decision_summary",
    ],
    "financial_summary": [
        "bank_id",
        "reporting_year",
        "total_assets_meur",
        "total_loans_meur",
    ],
    "counterparty_emissions": [
        "counterparty_id",
        "reporting_year",
        "total_ghg_tco2e",
    ],
    "governance": [
        "bank_id",
        "reporting_year",
    ],
    "targets": [
        "target_id",
        "bank_id",
        "target_year",
    ],
    "investments": [
        "investment_id",
        "bank_id",
        "asset_class",
    ],
}


def load_canonical_manifest(batch: DataUploadBatch) -> Dict:
    mapping_folder = get_mapping_folder(batch)
    manifest_path = mapping_folder / "canonical_manifest.json"

    if not manifest_path.exists():
        raise FileNotFoundError(
            "canonical_manifest.json not found. Build canonical CSVs before validation."
        )

    with open(manifest_path, "r", encoding="utf-8") as f:
        return json.load(f)


def resolve_validation_table_name(manifest_item: Dict) -> str:
    """
    Validation must use the resolved notebook table name, not the raw detected table.

    Example:
    detected_table = financial_summary
    notebook_table_name = counterparty_emissions
    output_filename = counterparty_emissions.csv

    Correct validation table: counterparty_emissions
    """

    notebook_table_name = manifest_item.get("notebook_table_name")
    if notebook_table_name:
        return notebook_table_name

    output_filename = manifest_item.get("output_filename")
    if output_filename:
        return Path(output_filename).stem

    output_path = manifest_item.get("output_path")
    if output_path:
        return Path(output_path).stem

    return manifest_item.get("detected_table", "unknown")


def read_csv_preview(csv_path: Path, max_rows: int = 5) -> Dict:
    encodings = ["utf-8-sig", "utf-8", "latin-1"]

    for encoding in encodings:
        try:
            with open(csv_path, "r", encoding=encoding, newline="") as f:
                reader = csv.DictReader(f)
                headers = reader.fieldnames or []

                rows = []
                total_rows = 0

                for row in reader:
                    total_rows += 1
                    if len(rows) < max_rows:
                        rows.append(row)

                return {
                    "encoding": encoding,
                    "headers": headers,
                    "row_count": total_rows,
                    "preview_rows": rows,
                }

        except UnicodeDecodeError:
            continue

    raise ValueError(f"Could not decode CSV file: {csv_path}")


def find_duplicate_columns(headers: List[str]) -> List[str]:
    seen = set()
    duplicates = []

    for header in headers:
        if header in seen and header not in duplicates:
            duplicates.append(header)
        seen.add(header)

    return duplicates


def validate_canonical_file(table_name: str, csv_path: Path) -> Dict:
    issues = []

    if not csv_path.exists():
        return {
            "table_name": table_name,
            "file_path": str(csv_path),
            "is_valid": False,
            "issues": [
                {
                    "severity": "error",
                    "code": "CANONICAL_FILE_NOT_FOUND",
                    "message": f"Canonical CSV file not found for table {table_name}.",
                }
            ],
        }

    preview = read_csv_preview(csv_path)
    headers = preview["headers"]
    row_count = preview["row_count"]

    if not headers:
        issues.append(
            {
                "severity": "error",
                "code": "CANONICAL_FILE_HAS_NO_HEADERS",
                "message": f"Canonical CSV file for {table_name} has no headers.",
            }
        )

    if row_count == 0:
        issues.append(
            {
                "severity": "error",
                "code": "CANONICAL_FILE_HAS_NO_ROWS",
                "message": f"Canonical CSV file for {table_name} has no data rows.",
            }
        )

    duplicate_columns = find_duplicate_columns(headers)

    if duplicate_columns:
        issues.append(
            {
                "severity": "error",
                "code": "DUPLICATE_CANONICAL_COLUMNS",
                "message": f"Duplicate columns found in {table_name}: {duplicate_columns}",
            }
        )

    required_columns = MINIMUM_REQUIRED_COLUMNS.get(table_name, [])
    missing_columns = [
        column for column in required_columns
        if column not in headers
    ]

    if missing_columns:
        issues.append(
            {
                "severity": "error",
                "code": "MISSING_MINIMUM_CANONICAL_COLUMNS",
                "message": f"Missing minimum columns in {table_name}: {missing_columns}",
            }
        )

    return {
        "table_name": table_name,
        "file_path": str(csv_path),
        "is_valid": not any(issue["severity"] == "error" for issue in issues),
        "encoding": preview.get("encoding"),
        "row_count": row_count,
        "column_count": len(headers),
        "columns": headers,
        "issues": issues,
    }


def validate_canonical_batch(batch: DataUploadBatch) -> Dict:
    canonical_folder = get_canonical_folder(batch)
    mapping_folder = get_mapping_folder(batch)

    manifest = load_canonical_manifest(batch)

    validations = []
    all_issues = []

    for output in manifest.get("outputs", []):
        table_name = resolve_validation_table_name(output)
        output_filename = output.get("output_filename")

        if not table_name or not output_filename:
            continue

        csv_path = canonical_folder / output_filename
        validation = validate_canonical_file(table_name, csv_path)

        validations.append(validation)

        for issue in validation["issues"]:
            all_issues.append(
                {
                    "table_name": table_name,
                    **issue,
                }
            )

    result = {
        "batch_id": str(batch.id),
        "canonical_folder": str(canonical_folder),
        "total_validated_files": len(validations),
        "is_valid": not any(issue["severity"] == "error" for issue in all_issues),
        "validations": validations,
        "issues": all_issues,
    }

    output_path = mapping_folder / "canonical_validation.json"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    result["output_path"] = str(output_path)

    return result