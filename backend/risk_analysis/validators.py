"""
Validation for prepared sustainability datasets used by Risk Analysis.

Missing optional sections produce review notes. Processing is blocked only
when the reporting entity/year cannot be identified or when no usable
climate-risk information exists at all.
"""

from __future__ import annotations

from typing import Any


RISK_SOURCE_SECTIONS = [
    "climate_risk_register",
    "physical_risk_exposures",
    "climate_scenarios",
    "financed_emissions",
    "financed_emissions_by_asset_class",
    "climate_financial_effects",
]

RECOMMENDED_SECTIONS = [
    "climate_risk_register",
    "physical_risk_exposures",
    "climate_scenarios",
    "financed_emissions",
    "targets",
]


def _is_non_empty(value: Any) -> bool:
    if isinstance(value, (list, dict, str)):
        return bool(value)
    return value is not None


def _as_rows(value: Any) -> list[dict]:
    if isinstance(value, list):
        rows = [
            row
            for row in value
            if isinstance(row, dict)
        ]
    elif isinstance(value, dict):
        rows = [value]
    else:
        rows = []

    return [
        row
        for row in rows
        if row.get("is_synthetic") is not True
    ]


def _rows_for_year(
    value: Any,
    reporting_year: Any,
) -> list[dict]:
    rows = _as_rows(value)

    try:
        expected_year = int(reporting_year)
    except (TypeError, ValueError):
        return rows

    matching: list[dict] = []

    for row in rows:
        row_year = row.get("reporting_year")

        if row_year is None:
            matching.append(row)
            continue

        try:
            if int(row_year) == expected_year:
                matching.append(row)
        except (TypeError, ValueError):
            continue

    return matching


def _expected_rating(
    likelihood: int | float,
    severity: int | float,
) -> str:
    score = likelihood * severity

    if score >= 15:
        return "critical"

    if score >= 8:
        return "high"

    if score >= 3:
        return "medium"

    return "low"


def _is_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
    )


def validate_payload(
    payload: dict,
) -> tuple[bool, list[dict]]:
    warnings: list[dict] = []

    if not isinstance(payload, dict):
        return False, [
            {
                "level": "error",
                "code": "INVALID_DATASET",
                "message": (
                    "The prepared dataset is not a valid "
                    "JSON object."
                ),
            }
        ]

    bank = payload.get("bank")
    metadata = payload.get("metadata")
    context = payload.get(
        "general_requirements_context"
    )

    if not isinstance(bank, dict):
        bank = {}

    if not isinstance(metadata, dict):
        metadata = {}

    if not isinstance(context, dict):
        context = {}

    entity_name = (
        bank.get("bank_name")
        or context.get("reporting_entity")
    )

    reporting_year = (
        metadata.get("reporting_year")
        or context.get("reporting_year")
    )

    if not entity_name:
        warnings.append(
            {
                "level": "error",
                "code": "MISSING_ENTITY",
                "message": (
                    "The reporting institution could not "
                    "be identified."
                ),
            }
        )

    if not reporting_year:
        warnings.append(
            {
                "level": "error",
                "code": "MISSING_REPORTING_YEAR",
                "message": (
                    "The reporting year could not be "
                    "identified."
                ),
            }
        )

    available_risk_sources = [
        key
        for key in RISK_SOURCE_SECTIONS
        if _is_non_empty(payload.get(key))
    ]

    if not available_risk_sources:
        warnings.append(
            {
                "level": "error",
                "code": "NO_RISK_INFORMATION",
                "message": (
                    "No usable climate-risk, scenario, "
                    "physical-risk, or financed-emissions "
                    "information was found."
                ),
            }
        )

    if any(
        warning["level"] == "error"
        for warning in warnings
    ):
        return False, warnings

    missing_recommended = [
        key
        for key in RECOMMENDED_SECTIONS
        if not _is_non_empty(payload.get(key))
    ]

    if missing_recommended:
        warnings.append(
            {
                "level": "warning",
                "code": "PARTIAL_RISK_COVERAGE",
                "message": (
                    "Some risk-analysis areas are not "
                    "available. Related views will be "
                    "omitted."
                ),
                "details": {
                    "missing_sections": (
                        missing_recommended
                    ),
                },
            }
        )

    financial_rows = _as_rows(
        payload.get("financial_summary")
    )

    if financial_rows and len(financial_rows) < 2:
        warnings.append(
            {
                "level": "info",
                "code": "LIMITED_HISTORY",
                "message": (
                    "Only one year of financial history "
                    "is available, so trend analysis is "
                    "limited."
                ),
            }
        )

    risks = _rows_for_year(
        payload.get("climate_risk_register"),
        reporting_year,
    )

    invalid_matrix_rows = 0
    missing_rating_rows = 0
    inconsistent_rating_rows = 0

    for row in risks:
        likelihood = row.get(
            "likelihood_score"
        )
        severity = row.get(
            "severity_score"
        )

        if not row.get("risk_rating"):
            missing_rating_rows += 1

        if not (
            _is_number(likelihood)
            and _is_number(severity)
            and 1 <= likelihood <= 5
            and 1 <= severity <= 5
        ):
            invalid_matrix_rows += 1
            continue

        supplied_rating = str(
            row.get("risk_rating") or ""
        ).strip().lower()

        if (
            supplied_rating
            and supplied_rating
            != _expected_rating(
                likelihood,
                severity,
            )
        ):
            inconsistent_rating_rows += 1

    if invalid_matrix_rows:
        warnings.append(
            {
                "level": "warning",
                "code": "INVALID_RISK_MATRIX_ROWS",
                "message": (
                    f"{invalid_matrix_rows} risk-register "
                    "row(s) cannot be positioned on the "
                    "5×5 matrix because likelihood or "
                    "severity is missing or outside 1–5."
                ),
            }
        )

    if missing_rating_rows:
        warnings.append(
            {
                "level": "info",
                "code": "MISSING_RISK_RATING",
                "message": (
                    f"{missing_rating_rows} risk-register "
                    "row(s) do not include a rating label."
                ),
            }
        )

    if inconsistent_rating_rows:
        warnings.append(
            {
                "level": "warning",
                "code": "INCONSISTENT_RISK_RATING",
                "message": (
                    f"{inconsistent_rating_rows} risk-register "
                    "row(s) have a rating that does not match "
                    "the stated 5×5 likelihood × severity "
                    "methodology."
                ),
            }
        )

    physical_rows = _as_rows(
        payload.get("physical_risk_exposures")
    )

    missing_counterparties = sum(
        1
        for row in physical_rows
        if not row.get("counterparty_id")
    )

    if missing_counterparties:
        warnings.append(
            {
                "level": "info",
                "code": "MISSING_COUNTERPARTY_LINK",
                "message": (
                    f"{missing_counterparties} physical-risk "
                    "row(s) cannot be included in the "
                    "counterparty concentration view."
                ),
            }
        )

    negative_values = 0

    numeric_fields = [
        (
            "physical_risk_exposures",
            "exposure_amount_meur",
        ),
        (
            "physical_risk_exposures",
            "financial_impact_meur",
        ),
        (
            "climate_scenarios",
            "revenue_at_risk_meur",
        ),
        (
            "financed_emissions",
            "financed_em_loans_tco2e",
        ),
    ]

    for section, field in numeric_fields:
        for row in _as_rows(
            payload.get(section)
        ):
            value = row.get(field)

            if (
                _is_number(value)
                and value < 0
            ):
                negative_values += 1

    if negative_values:
        warnings.append(
            {
                "level": "warning",
                "code": "NEGATIVE_RISK_VALUES",
                "message": (
                    f"{negative_values} exposure or impact "
                    "value(s) are negative and should be "
                    "reviewed."
                ),
            }
        )

    declared_gaps = metadata.get(
        "data_gaps",
        [],
    )

    if isinstance(declared_gaps, list) and declared_gaps:
        warnings.append(
            {
                "level": "info",
                "code": "DECLARED_DATA_GAPS",
                "message": (
                    f"{len(declared_gaps)} declared data "
                    "gap(s) were retained as review notes."
                ),
            }
        )

    return True, warnings
