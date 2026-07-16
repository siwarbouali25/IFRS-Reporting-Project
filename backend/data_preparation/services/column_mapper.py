import json
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Tuple

from data_preparation.models import DataUploadBatch
from data_preparation.services.column_contract import (
    get_aliases_for_column,
    get_expected_columns_for_table,
    get_required_columns_for_table,
)
from data_preparation.services.notebook_contract import resolve_notebook_table_name
from data_preparation.services.table_detector import TABLE_SIGNATURES, normalize_name
from data_preparation.services.upload_extractor import get_mapping_folder


AUTO_MATCH_THRESHOLD = 0.86
REVIEW_MATCH_THRESHOLD = 0.70


def load_detected_tables(batch: DataUploadBatch) -> Dict:
    mapping_folder = get_mapping_folder(batch)
    detected_path = mapping_folder / "detected_tables.json"

    if not detected_path.exists():
        raise FileNotFoundError(
            "detected_tables.json not found. Run table detection before column mapping."
        )

    with open(detected_path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_header_lookup(headers: List[str]) -> Dict[str, str]:
    lookup = {}

    for header in headers:
        normalized = normalize_name(header)
        if normalized and normalized not in lookup:
            lookup[normalized] = header

    return lookup


def words(value: str) -> set:
    normalized = normalize_name(value)
    return {part for part in normalized.split("_") if part}


def token_score(a: str, b: str) -> float:
    a_words = words(a)
    b_words = words(b)

    if not a_words or not b_words:
        return 0.0

    overlap = len(a_words & b_words)
    union = len(a_words | b_words)

    return overlap / union if union else 0.0


def string_score(a: str, b: str) -> float:
    normalized_a = normalize_name(a)
    normalized_b = normalize_name(b)

    if not normalized_a or not normalized_b:
        return 0.0

    sequence_score = SequenceMatcher(None, normalized_a, normalized_b).ratio()
    overlap_score = token_score(normalized_a, normalized_b)

    return max(sequence_score, overlap_score)


def find_exact_or_alias_match(
    canonical_column: str,
    aliases: List[str],
    header_lookup: Dict[str, str],
) -> Optional[Dict]:
    normalized_canonical = normalize_name(canonical_column)

    if normalized_canonical in header_lookup:
        return {
            "source_column": header_lookup[normalized_canonical],
            "method": "exact",
            "confidence": 1.0,
            "matched_alias": canonical_column,
        }

    for alias in aliases:
        normalized_alias = normalize_name(alias)

        if normalized_alias in header_lookup:
            return {
                "source_column": header_lookup[normalized_alias],
                "method": "alias",
                "confidence": 0.95,
                "matched_alias": alias,
            }

    return None


def find_fuzzy_candidates(
    canonical_column: str,
    aliases: List[str],
    headers: List[str],
) -> List[Dict]:
    candidates = []

    comparison_terms = [canonical_column] + aliases

    for source_column in headers:
        best_score = 0.0
        best_term = None

        for term in comparison_terms:
            score = string_score(source_column, term)

            if score > best_score:
                best_score = score
                best_term = term

        if best_score >= REVIEW_MATCH_THRESHOLD:
            candidates.append(
                {
                    "source_column": source_column,
                    "confidence": round(best_score, 4),
                    "matched_term": best_term,
                    "method": "fuzzy",
                }
            )

    return sorted(candidates, key=lambda item: item["confidence"], reverse=True)


def get_expected_columns_from_signature(detected_table: str) -> List[str]:
    if detected_table not in TABLE_SIGNATURES:
        return []

    return list(TABLE_SIGNATURES[detected_table].get("columns", {}).keys())


def get_expected_columns(
    notebook_table_name: str,
    detected_table: str,
) -> List[str]:
    contract_columns = get_expected_columns_for_table(notebook_table_name)

    # If the resolved notebook table is different from the detected table,
    # trust the notebook contract. This avoids mixing wrong columns from
    # a bad detection, for example:
    # counterparty_emissions.csv detected as financial_summary.
    if notebook_table_name != detected_table:
        return contract_columns

    signature_columns = get_expected_columns_from_signature(detected_table)

    result = []
    seen = set()

    for column in contract_columns + signature_columns:
        if column not in seen:
            result.append(column)
            seen.add(column)

    return result


def generate_mapping_for_detection(detection: Dict) -> Dict:
    detected_table = detection.get("detected_table")
    source_filename = detection.get("source_filename")
    headers = detection.get("headers", [])

    notebook_table_name = resolve_notebook_table_name(
        source_filename=source_filename,
        detected_table=detected_table,
    )

    if not detected_table:
        return {
            "source_filename": source_filename,
            "source_path": detection.get("source_path"),
            "detected_table": detected_table,
            "notebook_table_name": notebook_table_name,
            "detection_confidence": detection.get("confidence"),
            "needs_review": True,
            "error": "No detected table.",
            "column_mapping": {},
            "final_column_mapping": {header: header for header in headers},
            "passthrough_columns": headers,
            "unmapped_required_columns": [],
            "unmapped_optional_columns": [],
            "unmapped_canonical_columns": [],
            "mapping_diagnostics": [],
            "review_suggestions": [],
            "extra_source_columns": headers,
        }

    header_lookup = build_header_lookup(headers)
    required_columns = get_required_columns_for_table(notebook_table_name)
    expected_columns = get_expected_columns(
        notebook_table_name=notebook_table_name,
        detected_table=detected_table,
    )

    column_mapping = {}
    mapped_source_columns = set()
    mapping_diagnostics = []
    review_suggestions = []

    unmapped_required_columns = []
    unmapped_optional_columns = []

    for canonical_column in expected_columns:
        aliases = get_aliases_for_column(notebook_table_name, canonical_column)

        match = find_exact_or_alias_match(
            canonical_column=canonical_column,
            aliases=aliases,
            header_lookup=header_lookup,
        )

        if match:
            source_column = match["source_column"]
            column_mapping[canonical_column] = source_column
            mapped_source_columns.add(source_column)

            mapping_diagnostics.append(
                {
                    "canonical_column": canonical_column,
                    "source_column": source_column,
                    "method": match["method"],
                    "confidence": match["confidence"],
                    "matched_alias": match["matched_alias"],
                    "status": "auto_mapped",
                }
            )
            continue

        fuzzy_candidates = find_fuzzy_candidates(
            canonical_column=canonical_column,
            aliases=aliases,
            headers=[
                header for header in headers
                if header not in mapped_source_columns
            ],
        )

        if fuzzy_candidates and fuzzy_candidates[0]["confidence"] >= AUTO_MATCH_THRESHOLD:
            best = fuzzy_candidates[0]
            source_column = best["source_column"]

            column_mapping[canonical_column] = source_column
            mapped_source_columns.add(source_column)

            mapping_diagnostics.append(
                {
                    "canonical_column": canonical_column,
                    "source_column": source_column,
                    "method": "fuzzy_auto",
                    "confidence": best["confidence"],
                    "matched_alias": best["matched_term"],
                    "status": "auto_mapped",
                }
            )
            continue

        column_mapping[canonical_column] = None

        suggestion_payload = {
            "canonical_column": canonical_column,
            "required": canonical_column in required_columns,
            "suggested_candidates": fuzzy_candidates[:5],
            "available_source_columns": headers,
        }

        if canonical_column in required_columns:
            unmapped_required_columns.append(canonical_column)
            review_suggestions.append(suggestion_payload)
        else:
            unmapped_optional_columns.append(canonical_column)
            if fuzzy_candidates:
                review_suggestions.append(suggestion_payload)

        mapping_diagnostics.append(
            {
                "canonical_column": canonical_column,
                "source_column": None,
                "method": "unmapped",
                "confidence": 0.0,
                "matched_alias": None,
                "status": "needs_review" if fuzzy_candidates else "unmapped",
            }
        )

    extra_source_columns = [
        header for header in headers
        if header not in mapped_source_columns
    ]

    passthrough_mapping = {
        header: header
        for header in extra_source_columns
    }

    final_column_mapping = {
        **column_mapping,
        **passthrough_mapping,
    }

    needs_review = bool(unmapped_required_columns)


    table_detection_low_confidence = (
        detection.get("needs_review", False)
        or detection.get("confidence", 0) < 0.35
    )

    return {
        "source_filename": source_filename,
        "source_path": detection.get("source_path"),
        "detected_table": detected_table,
        "notebook_table_name": notebook_table_name,
        "detection_confidence": detection.get("confidence"),
        "needs_review": needs_review,

        "column_mapping": column_mapping,
        "final_column_mapping": final_column_mapping,
        "passthrough_columns": extra_source_columns,

        "unmapped_required_columns": unmapped_required_columns,
        "unmapped_optional_columns": unmapped_optional_columns,
        "unmapped_canonical_columns": unmapped_required_columns + unmapped_optional_columns,

        "mapping_diagnostics": mapping_diagnostics,
        "review_suggestions": review_suggestions,
        "extra_source_columns": extra_source_columns,
    }


def generate_column_mappings_for_batch(batch: DataUploadBatch) -> Dict:
    mapping_folder = get_mapping_folder(batch)
    mapping_folder.mkdir(parents=True, exist_ok=True)

    detected_result = load_detected_tables(batch)

    mappings = []

    for detection in detected_result.get("detections", []):
        mapping = generate_mapping_for_detection(detection)
        mappings.append(mapping)

    result = {
        "batch_id": str(batch.id),
        "mappings": mappings,
        "needs_review": any(item["needs_review"] for item in mappings),
        "total_mapped_files": len(mappings),
    }

    output_path = mapping_folder / "column_mapping.json"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    result["output_path"] = str(output_path)

    return result