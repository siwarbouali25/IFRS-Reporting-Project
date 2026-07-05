import re
from typing import Any

from generation_engine.config import DEFAULT_SECTION_KEYS, SECTION_TITLES
from generation_engine.schemas import (
    DeterministicValidationResult,
    GenerationWarningData,
)


MISSING_DATA_TERMS = [
    "missing data",
    "data gap",
    "data gaps",
    "not available",
    "unavailable data",
    "insufficient data",
]

PROTOTYPE_TERMS = [
    "deterministic writer skeleton",
    "placeholder",
    "will later be replaced",
    "draft section generated",
]

INTERNAL_PATH_PATTERN = re.compile(
    r"`?[a-zA-Z_][a-zA-Z0-9_]*(\[\d+\])?(\.[a-zA-Z_][a-zA-Z0-9_]*(\[\d+\])?)+`?"
)


def _check_report_not_empty(markdown: str) -> dict[str, Any]:
    passed = bool(markdown and markdown.strip())

    return {
        "check_id": "report_not_empty",
        "passed": passed,
        "severity": "error" if not passed else "info",
        "message": "Report markdown is not empty." if passed else "Report markdown is empty.",
    }


def _check_required_sections_present(markdown: str) -> dict[str, Any]:
    missing_sections: list[str] = []

    lowered = markdown.lower()

    for section_key in DEFAULT_SECTION_KEYS:
        section_title = SECTION_TITLES.get(section_key, section_key)
        if section_title.lower() not in lowered:
            missing_sections.append(section_title)

    passed = len(missing_sections) == 0

    return {
        "check_id": "required_sections_present",
        "passed": passed,
        "severity": "warning" if not passed else "info",
        "message": (
            "All required report sections are present."
            if passed
            else "Some required report sections are missing."
        ),
        "details": {
            "missing_sections": missing_sections,
        },
    }


def _check_missing_data_not_mentioned(markdown: str) -> dict[str, Any]:
    lowered = markdown.lower()

    found_terms = [
        term for term in MISSING_DATA_TERMS
        if term in lowered
    ]

    passed = len(found_terms) == 0

    return {
        "check_id": "missing_data_not_mentioned",
        "passed": passed,
        "severity": "warning" if not passed else "info",
        "message": (
            "Report does not mention missing data."
            if passed
            else "Report appears to mention missing data, which is not allowed."
        ),
        "details": {
            "found_terms": found_terms,
            "policy": "do_not_mention_missing_data_in_generated_report",
        },
    }


def _check_internal_payload_paths_not_exposed(markdown: str) -> dict[str, Any]:
    matches = INTERNAL_PATH_PATTERN.findall(markdown)

    # The regex has groups, so use finditer to recover full matches.
    full_matches = sorted({
        match.group(0).strip("`")
        for match in INTERNAL_PATH_PATTERN.finditer(markdown)
    })

    passed = len(full_matches) == 0

    return {
        "check_id": "internal_payload_paths_not_exposed",
        "passed": passed,
        "severity": "warning" if not passed else "info",
        "message": (
            "Report does not expose internal payload paths."
            if passed
            else "Report exposes internal payload paths. This is acceptable only in the prototype."
        ),
        "details": {
            "internal_paths_found_count": len(full_matches),
            "sample_internal_paths": full_matches[:20],
            "prototype_note": (
                "The deterministic placeholder writer currently exposes evidence paths. "
                "The final LLM writer should convert evidence into narrative text."
            ),
        },
    }


def _check_prototype_language_not_present(markdown: str) -> dict[str, Any]:
    lowered = markdown.lower()

    found_terms = [
        term for term in PROTOTYPE_TERMS
        if term in lowered
    ]

    passed = len(found_terms) == 0

    return {
        "check_id": "prototype_language_not_present",
        "passed": passed,
        "severity": "warning" if not passed else "info",
        "message": (
            "Report does not contain prototype placeholder language."
            if passed
            else "Report still contains prototype placeholder language."
        ),
        "details": {
            "found_terms": found_terms,
            "prototype_note": (
                "This is expected while the deterministic writer skeleton is active. "
                "The final report should not contain this language."
            ),
        },
    }


def run_deterministic_validation_gates(
    *,
    markdown: str,
) -> DeterministicValidationResult:
    """
    Run deterministic validation gates on the assembled draft report.

    Current policy:
    - errors and warnings are recorded internally
    - warnings do not fail the job
    - missing data issues must not reduce the report score
    """

    checks = [
        _check_report_not_empty(markdown),
        _check_required_sections_present(markdown),
        _check_missing_data_not_mentioned(markdown),
        _check_internal_payload_paths_not_exposed(markdown),
        _check_prototype_language_not_present(markdown),
    ]

    error_count = sum(
        1 for check in checks
        if check["severity"] == "error" and not check["passed"]
    )

    warning_count = sum(
        1 for check in checks
        if check["severity"] == "warning" and not check["passed"]
    )

    passed = error_count == 0

    warnings: list[GenerationWarningData] = []

    for check in checks:
        if check["passed"]:
            continue

        warnings.append(
            GenerationWarningData(
                stage="deterministic_validation",
                warning_type=check["check_id"],
                message=check["message"],
                details={
                    **check.get("details", {}),
                    "severity": check["severity"],
                    "workflow_impact": "warning_only"
                    if check["severity"] == "warning"
                    else "error",
                },
            )
        )

    summary = {
        "validation_type": "deterministic_draft_report_validation",
        "passed": passed,
        "checks_total": len(checks),
        "checks_passed": sum(1 for check in checks if check["passed"]),
        "checks_failed": sum(1 for check in checks if not check["passed"]),
        "error_count": error_count,
        "warning_count": warning_count,
        "policy": {
            "warnings_do_not_block_generation": True,
            "missing_data_does_not_reduce_score": True,
            "do_not_mention_missing_data_in_report": True,
        },
    }

    return DeterministicValidationResult(
        passed=passed,
        checks=checks,
        summary=summary,
        warnings=warnings,
    )