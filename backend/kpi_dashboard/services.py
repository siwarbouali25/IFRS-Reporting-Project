import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from django.conf import settings

from data_preparation.models import DataUploadBatch


# ============================================================
# File loading helpers
# ============================================================

def get_batch_base_folder(batch: DataUploadBatch) -> Path:
    return Path(settings.MEDIA_ROOT) / "data_preparation" / "batches" / str(batch.id)


def get_payloads_folder(batch: DataUploadBatch) -> Path:
    return get_batch_base_folder(batch) / "payloads"


def get_mapping_folder(batch: DataUploadBatch) -> Path:
    return get_batch_base_folder(batch) / "mapping"


def load_payload(batch: DataUploadBatch, bank_id: str) -> Dict[str, Any]:
    payload_path = get_payloads_folder(batch) / f"payload_{bank_id}.json"

    if not payload_path.exists():
        raise FileNotFoundError(
            f"Payload not found for bank_id={bank_id}. Expected file: {payload_path}"
        )

    with open(payload_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_validation_result(batch: DataUploadBatch) -> Dict[str, Any]:
    validation_path = get_mapping_folder(batch) / "canonical_validation.json"

    if not validation_path.exists():
        return {
            "is_valid": False,
            "issues": [],
        }

    with open(validation_path, "r", encoding="utf-8") as f:
        return json.load(f)


# ============================================================
# Generic helpers
# ============================================================

def as_records(value: Any) -> List[Dict[str, Any]]:
    if value is None:
        return []

    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]

    if isinstance(value, dict):
        return [value]

    return []


def to_float(value: Any) -> Optional[float]:
    if value in [None, "", "null", "None"]:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def safe_round(value: Any, decimals: int = 2) -> Optional[float]:
    numeric_value = to_float(value)

    if numeric_value is None:
        return None

    return round(numeric_value, decimals)


def latest_record(
    records: List[Dict[str, Any]],
    reporting_year: Optional[int] = None,
) -> Dict[str, Any]:
    if not records:
        return {}

    if reporting_year is not None:
        year_records = [
            row
            for row in records
            if str(row.get("reporting_year")) == str(reporting_year)
            or str(row.get("year")) == str(reporting_year)
            or str(row.get("invoice_year")) == str(reporting_year)
            or str(row.get("target_year")) == str(reporting_year)
            or str(row.get("scenario_year")) == str(reporting_year)
        ]

        if year_records:
            return year_records[0]

    sortable = []

    for row in records:
        year = (
            to_float(row.get("reporting_year"))
            or to_float(row.get("year"))
            or to_float(row.get("invoice_year"))
            or to_float(row.get("target_year"))
            or to_float(row.get("scenario_year"))
            or 0
        )
        sortable.append((year, row))

    sortable.sort(key=lambda item: item[0], reverse=True)

    return sortable[0][1]


def sum_fields(records: List[Dict[str, Any]], field_names: List[str]) -> float:
    total = 0.0

    for row in records:
        for field in field_names:
            value = to_float(row.get(field))

            if value is not None:
                total += value
                break

    return round(total, 4)


def sum_first_available_metric(
    payload: Dict[str, Any],
    payload_keys: List[str],
    candidate_fields: List[str],
) -> float:
    """
    Tries several payload sections and several possible field names.
    Returns the first non-zero sum found.
    """

    for payload_key in payload_keys:
        records = as_records(payload.get(payload_key))

        if not records:
            continue

        total = sum_fields(records, candidate_fields)

        if total != 0:
            return round(total, 4)

    return 0.0


def count_by_text_value(
    records: List[Dict[str, Any]],
    field_name: str,
    expected_value: str,
) -> int:
    return sum(
        1
        for row in records
        if str(row.get(field_name, "")).strip().lower() == expected_value.lower()
    )


def is_truthy(value: Any) -> bool:
    return str(value).strip().lower() in [
        "true",
        "1",
        "yes",
        "y",
        "high",
        "oui",
    ]


def build_kpi(
    key: str,
    label: str,
    value: Any,
    unit: str = "",
    description: str = "",
    category: str = "general",
) -> Dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "value": value,
        "unit": unit,
        "description": description,
        "category": category,
    }


# ============================================================
# Chart helpers
# ============================================================

def collect_records(
    payload: Dict[str, Any],
    payload_keys: List[str],
) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []

    for key in payload_keys:
        records.extend(as_records(payload.get(key)))

    return records


def get_record_year(
    row: Dict[str, Any],
    fallback_year: Optional[int] = None,
) -> Optional[int]:
    for field in [
        "reporting_year",
        "year",
        "invoice_year",
        "target_year",
        "scenario_year",
        "analysis_conducted_year",
        "assessment_year",
    ]:
        value = to_float(row.get(field))

        if value is not None:
            return int(value)

    return fallback_year


def get_available_years(
    record_groups: List[List[Dict[str, Any]]],
    fallback_year: Optional[int],
) -> List[int]:
    years = set()

    for records in record_groups:
        for row in records:
            year = get_record_year(row, fallback_year)

            if year is not None:
                years.add(year)

    if not years and fallback_year is not None:
        years.add(fallback_year)

    return sorted(years)


def sum_fields_for_year(
    records: List[Dict[str, Any]],
    year: int,
    field_names: List[str],
    fallback_year: Optional[int],
) -> float:
    year_records = [
        row
        for row in records
        if get_record_year(row, fallback_year) == year
    ]

    return sum_fields(year_records, field_names)


def first_value_for_year(
    records: List[Dict[str, Any]],
    year: int,
    field_names: List[str],
    fallback_year: Optional[int],
) -> Optional[float]:
    year_records = [
        row
        for row in records
        if get_record_year(row, fallback_year) == year
    ]

    for row in year_records:
        for field in field_names:
            value = to_float(row.get(field))

            if value is not None:
                return value

    return None


def get_text_value(
    row: Dict[str, Any],
    candidate_fields: List[str],
    default: str = "Unknown",
) -> str:
    for field in candidate_fields:
        value = row.get(field)

        if value not in [None, "", "null", "None"]:
            return str(value).strip()

    return default


def group_sum_top(
    records: List[Dict[str, Any]],
    label_fields: List[str],
    value_fields: List[str],
    top_n: int = 8,
) -> Dict[str, Any]:
    grouped: Dict[str, float] = {}

    for row in records:
        label = get_text_value(row, label_fields)
        value = 0.0

        for field in value_fields:
            candidate = to_float(row.get(field))

            if candidate is not None:
                value = candidate
                break

        if value == 0:
            continue

        grouped[label] = grouped.get(label, 0.0) + value

    sorted_rows = sorted(
        grouped.items(),
        key=lambda item: item[1],
        reverse=True,
    )[:top_n]

    return {
        "labels": [item[0] for item in sorted_rows],
        "datasets": [
            {
                "label": "Value",
                "data": [round(item[1], 4) for item in sorted_rows],
            }
        ],
    }


def group_count_percentage(
    records: List[Dict[str, Any]],
    label_fields: List[str],
    top_n: int = 8,
) -> Dict[str, Any]:
    grouped: Dict[str, int] = {}

    for row in records:
        label = get_text_value(row, label_fields)

        if label == "Unknown":
            continue

        grouped[label] = grouped.get(label, 0) + 1

    total = sum(grouped.values())

    if total == 0:
        return {
            "labels": [],
            "datasets": [
                {
                    "label": "%",
                    "data": [],
                }
            ],
        }

    sorted_rows = sorted(
        grouped.items(),
        key=lambda item: item[1],
        reverse=True,
    )[:top_n]

    return {
        "labels": [item[0] for item in sorted_rows],
        "datasets": [
            {
                "label": "%",
                "data": [round((count / total) * 100, 2) for _, count in sorted_rows],
            }
        ],
    }


def calculate_delta_pct(current: Optional[float], previous: Optional[float]) -> Optional[float]:
    if current is None or previous in [None, 0]:
        return None

    return round(((current - previous) / previous) * 100, 2)


def format_compact_value(value: Any, decimals: int = 2) -> str:
    numeric_value = to_float(value)

    if numeric_value is None:
        return "—"

    abs_value = abs(numeric_value)

    if abs_value >= 1_000_000:
        return f"{numeric_value / 1_000_000:.{decimals}f}M"

    if abs_value >= 1_000:
        return f"{numeric_value / 1_000:.1f}K"

    if numeric_value.is_integer():
        return str(int(numeric_value))

    return f"{numeric_value:.{decimals}f}"


def format_delta(delta_pct: Optional[float], lower_is_better: bool = False) -> Dict[str, Any]:
    if delta_pct is None:
        return {
            "delta": None,
            "delta_type": "neutral",
        }

    arrow = "▲" if delta_pct > 0 else "▼"

    if delta_pct == 0:
        arrow = "→"

    good = delta_pct < 0 if lower_is_better else delta_pct > 0

    if delta_pct == 0:
        delta_type = "neutral"
    elif good:
        delta_type = "good"
    else:
        delta_type = "bad"

    return {
        "delta": f"{arrow} {abs(delta_pct):.1f}% YoY",
        "delta_type": delta_type,
    }


# ============================================================
# ESG score helpers
# ============================================================

def clamp_score(value: float) -> float:
    return round(max(0, min(100, value)), 2)


def score_high_good(
    value: Any,
    target: float,
    minimum: float = 0,
) -> Optional[float]:
    value = to_float(value)

    if value is None:
        return None

    if target == minimum:
        return None

    score = ((value - minimum) / (target - minimum)) * 100

    return clamp_score(score)


def score_low_good(
    value: Any,
    good_threshold: float,
    bad_threshold: float,
) -> Optional[float]:
    value = to_float(value)

    if value is None:
        return None

    if value <= good_threshold:
        return 100.0

    if value >= bad_threshold:
        return 0.0

    score = 100 - ((value - good_threshold) / (bad_threshold - good_threshold)) * 100

    return clamp_score(score)


def score_boolean(value: Any) -> Optional[float]:
    if value in [None, "", "null", "None"]:
        return None

    normalized = str(value).strip().lower()

    if normalized in [
        "true",
        "1",
        "yes",
        "y",
        "oui",
        "limited assurance",
        "reasonable assurance",
    ]:
        return 100.0

    if normalized in [
        "false",
        "0",
        "no",
        "n",
        "non",
        "none",
    ]:
        return 0.0

    return 100.0


def score_balanced_percentage(
    value: Any,
    ideal: float = 50,
) -> Optional[float]:
    value = to_float(value)

    if value is None:
        return None

    distance = abs(value - ideal)
    score = 100 - (distance * 2)

    return clamp_score(score)


def average_available(scores: List[Optional[float]]) -> Optional[float]:
    available_scores = [
        score
        for score in scores
        if score is not None
    ]

    if not available_scores:
        return None

    return round(sum(available_scores) / len(available_scores), 2)


def weighted_average_available(
    weighted_scores: List[Tuple[Optional[float], float]],
) -> Optional[float]:
    available = [
        (score, weight)
        for score, weight in weighted_scores
        if score is not None
    ]

    if not available:
        return None

    total_weight = sum(weight for _, weight in available)

    if total_weight == 0:
        return None

    score = sum(score * weight for score, weight in available) / total_weight

    return round(score, 2)


def build_esg_score(
    *,
    total_assets: Optional[float],
    total_loans: Optional[float],
    green_loans_pct: Optional[float],
    total_financed_emissions: float,
    scope1_emissions: float,
    scope2_market_emissions: float,
    travel_emissions_tco2e: float,
    high_physical_risk_exposure: float,
    high_carbon_exposure: float,
    governance_row: Dict[str, Any],
    employees: List[Dict[str, Any]],
    reporting_year: Optional[int],
) -> Dict[str, Any]:
    financed_emissions_intensity = None

    if total_loans:
        financed_emissions_intensity = total_financed_emissions / total_loans

    operational_emissions = (
        (scope1_emissions or 0)
        + (scope2_market_emissions or 0)
        + (travel_emissions_tco2e or 0)
    )

    operational_emissions_intensity = None

    if total_assets:
        operational_emissions_intensity = operational_emissions / total_assets

    high_carbon_exposure_pct = None

    if total_loans:
        high_carbon_exposure_pct = (high_carbon_exposure / total_loans) * 100

    high_physical_risk_exposure_pct = None

    if total_loans:
        high_physical_risk_exposure_pct = min(
            (high_physical_risk_exposure / total_loans) * 100,
            100,
        )

    environmental_indicators = {
        "green_loans_score": score_high_good(
            green_loans_pct,
            target=25,
        ),
        "financed_emissions_intensity_score": score_low_good(
            financed_emissions_intensity,
            good_threshold=250,
            bad_threshold=2000,
        ),
        "operational_emissions_intensity_score": score_low_good(
            operational_emissions_intensity,
            good_threshold=0.05,
            bad_threshold=1.0,
        ),
        "high_carbon_exposure_score": score_low_good(
            high_carbon_exposure_pct,
            good_threshold=5,
            bad_threshold=50,
        ),
        "physical_risk_exposure_score": score_low_good(
            high_physical_risk_exposure_pct,
            good_threshold=5,
            bad_threshold=100,
        ),
    }

    environmental_score = average_available(
        list(environmental_indicators.values())
    )

    employee_row = latest_record(employees, reporting_year)

    social_indicators = {
        "female_balance_score": score_balanced_percentage(
            employee_row.get("female_pct")
        ),
        "training_score": score_high_good(
            employee_row.get("avg_training_hours_per_employee"),
            target=40,
        ),
        "esg_training_score": score_high_good(
            employee_row.get("esg_training_hours_per_employee"),
            target=12,
        ),
        "turnover_score": score_low_good(
            employee_row.get("voluntary_turnover_pct"),
            good_threshold=5,
            bad_threshold=25,
        ),
        "injury_score": score_low_good(
            employee_row.get("lost_time_injury_rate"),
            good_threshold=0.5,
            bad_threshold=5,
        ),
    }

    social_score = average_available(
        list(social_indicators.values())
    )

    governance_indicators = {
        "esg_committee_score": score_boolean(
            governance_row.get("esg_committee_exists")
        ),
        "board_climate_expertise_score": score_high_good(
            governance_row.get("board_climate_expertise_pct"),
            target=60,
        ),
        "erm_integration_score": score_boolean(
            governance_row.get("erm_integration_flag")
        ),
        "external_assurance_score": score_boolean(
            governance_row.get("external_assurance")
        ),
        "ceo_esg_compensation_score": score_high_good(
            governance_row.get("ceo_esg_compensation_pct"),
            target=30,
        ),
        "climate_reporting_to_board_score": score_boolean(
            governance_row.get("climate_risk_reporting_to_board")
        ),
    }

    governance_score = average_available(
        list(governance_indicators.values())
    )

    overall_score = weighted_average_available(
        [
            (environmental_score, 0.50),
            (social_score, 0.15),
            (governance_score, 0.35),
        ]
    )

    return {
        "overall": overall_score,
        "environmental": environmental_score,
        "social": social_score,
        "governance": governance_score,
        "weights": {
            "environmental": 0.50,
            "social": 0.15,
            "governance": 0.35,
        },
        "methodology": (
            "Internal ESG score calculated from available environmental, social, "
            "and governance indicators. Missing values are ignored and do not "
            "reduce the score."
        ),
        "environmental_inputs": {
            "financed_emissions_intensity_tco2e_per_meur_loans": (
                round(financed_emissions_intensity, 4)
                if financed_emissions_intensity is not None
                else None
            ),
            "operational_emissions_intensity_tco2e_per_meur_assets": (
                round(operational_emissions_intensity, 4)
                if operational_emissions_intensity is not None
                else None
            ),
            "high_carbon_exposure_pct": (
                round(high_carbon_exposure_pct, 2)
                if high_carbon_exposure_pct is not None
                else None
            ),
            "high_physical_risk_exposure_pct": (
                round(high_physical_risk_exposure_pct, 2)
                if high_physical_risk_exposure_pct is not None
                else None
            ),
        },
        "indicator_scores": {
            "environmental": environmental_indicators,
            "social": social_indicators,
            "governance": governance_indicators,
        },
    }


# ============================================================
# Dynamic chart builders
# ============================================================

def build_operations_trend_chart(
    *,
    scope1: List[Dict[str, Any]],
    scope2: List[Dict[str, Any]],
    travel_records: List[Dict[str, Any]],
    reporting_year: Optional[int],
) -> Dict[str, Any]:
    years = get_available_years(
        [scope1, scope2, travel_records],
        reporting_year,
    )

    scope1_values = [
        sum_fields_for_year(
            scope1,
            year,
            [
                "scope1_tco2e",
                "scope1_total_tco2e",
                "scope1_gas_tco2e",
                "scope1_tco2e_2024_clean",
                "scope1_tco2e_2024",
            ],
            reporting_year,
        )
        for year in years
    ]

    scope2_market_values = [
        sum_fields_for_year(
            scope2,
            year,
            [
                "scope2_market_tco2e",
                "scope2_market_based_tco2e",
                "market_based_scope2",
            ],
            reporting_year,
        )
        for year in years
    ]

    scope2_location_values = [
        sum_fields_for_year(
            scope2,
            year,
            [
                "scope2_location_tco2e",
                "scope2_location_based_tco2e",
                "location_based_scope2",
            ],
            reporting_year,
        )
        for year in years
    ]

    travel_values = [
        sum_fields_for_year(
            travel_records,
            year,
            [
                "emissions_tco2e",
                "travel_emissions_tco2e",
                "business_travel_emissions_tco2e",
                "scope3_travel_tco2e",
            ],
            reporting_year,
        )
        for year in years
    ]

    return {
        "labels": [str(year) for year in years],
        "datasets": [
            {
                "type": "bar",
                "label": "Scope 1",
                "data": scope1_values,
                "stack": "operations",
            },
            {
                "type": "bar",
                "label": "Scope 2 market-based",
                "data": scope2_market_values,
                "stack": "operations",
            },
            {
                "type": "bar",
                "label": "Business travel",
                "data": travel_values,
                "stack": "operations",
            },
            {
                "type": "line",
                "label": "Scope 2 location-based",
                "data": scope2_location_values,
            },
        ],
    }


def build_financed_emissions_trend_chart(
    *,
    financed_records: List[Dict[str, Any]],
    financial_summary: List[Dict[str, Any]],
    total_loans: Optional[float],
    reporting_year: Optional[int],
) -> Dict[str, Any]:
    years = get_available_years(
        [financed_records, financial_summary],
        reporting_year,
    )

    financed_values = [
        sum_fields_for_year(
            financed_records,
            year,
            [
                "financed_emissions_tco2e",
                "total_financed_emissions_tco2e",
                "attributed_emissions_tco2e",
                "total_attributed_emissions_tco2e",
                "attributed_ghg_tco2e",
                "portfolio_emissions_tco2e",
                "emissions_tco2e",
            ],
            reporting_year,
        )
        for year in years
    ]

    loan_values = [
        first_value_for_year(
            financial_summary,
            year,
            [
                "total_loans_meur",
                "gross_loans_meur",
                "loan_book_meur",
            ],
            reporting_year,
        )
        or total_loans
        or 0
        for year in years
    ]

    intensity_values = []

    for financed_value, loans_value in zip(financed_values, loan_values):
        if loans_value:
            intensity_values.append(round(financed_value / loans_value, 4))
        else:
            intensity_values.append(0)

    return {
        "labels": [str(year) for year in years],
        "datasets": [
            {
                "type": "bar",
                "label": "Financed emissions",
                "data": [round(value / 1_000_000, 4) for value in financed_values],
                "unit": "Mt CO₂e",
                "y_axis_id": "y",
            },
            {
                "type": "line",
                "label": "Intensity",
                "data": intensity_values,
                "unit": "tCO₂e / €m",
                "y_axis_id": "y1",
            },
        ],
    }


def build_scope3_categories_chart(
    *,
    payload: Dict[str, Any],
    travel_emissions_tco2e: float,
) -> Dict[str, Any]:
    scope3_category_records = collect_records(
        payload,
        [
            "scope3_categories",
            "scope3_category_summary",
            "scope3_emissions_by_category",
        ],
    )

    chart = group_sum_top(
        scope3_category_records,
        [
            "category",
            "scope3_category",
            "category_name",
            "emission_category",
        ],
        [
            "emissions_tco2e",
            "category_emissions_tco2e",
            "scope3_emissions_tco2e",
            "total_emissions_tco2e",
        ],
        top_n=8,
    )

    if not chart["labels"] and travel_emissions_tco2e:
        chart = {
            "labels": ["Business travel"],
            "datasets": [
                {
                    "label": "tCO₂e",
                    "data": [travel_emissions_tco2e],
                }
            ],
        }

    return chart


def build_data_quality_chart(
    *,
    payload: Dict[str, Any],
    financed_records: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build the financed-emissions data-quality distribution.

    Prefer the prepared aggregate in
    ``reporting_kpis.emissions_data_quality_summary`` because it represents
    the intended percentage split. When that summary is unavailable, fall
    back to counting source/calculation categories on the financed-emissions
    records.
    """

    reporting_kpis = payload.get("reporting_kpis", {})
    summary = (
        reporting_kpis.get("emissions_data_quality_summary", {})
        if isinstance(reporting_kpis, dict)
        else {}
    )

    if isinstance(summary, dict):
        label_overrides = {
            "audited_report": "Audited report",
            "cdp_disclosure": "CDP disclosure",
            "estimated_economic": "Estimated economic",
            "estimated_physical": "Estimated physical",
            "proxy_model": "Proxy model",
            "reported": "Reported",
        }

        rows = []
        for key, raw_value in summary.items():
            value = to_float(raw_value)
            if value is None or value < 0:
                continue

            label = label_overrides.get(
                str(key),
                str(key).replace("_", " ").strip().title(),
            )
            rows.append((label, value))

        if rows:
            total = sum(value for _, value in rows)

            # Some sources express shares as fractions that sum to roughly 1.
            # Convert those to percentages while preserving already-percent
            # summaries such as 0.7 + 35.5 + 47.5 + 16.3 = 100.
            multiplier = 100 if total <= 1.01 else 1

            return {
                "labels": [label for label, _ in rows],
                "datasets": [
                    {
                        "label": "%",
                        "data": [
                            round(value * multiplier, 2)
                            for _, value in rows
                        ],
                    }
                ],
            }

    return group_count_percentage(
        financed_records,
        [
            "data_quality",
            "data_quality_category",
            "data_source",
            "source_type",
            "calculation_method",
            "estimation_method",
            "emissions_source",
        ],
        top_n=6,
    )


def build_scenario_analysis_chart(
    *,
    scenario_records: List[Dict[str, Any]],
    reporting_year: Optional[int] = None,
) -> Dict[str, Any]:
    """Aggregate physical and transition losses by time horizon.

    The prepared BANK payload uses
    ``*_risk_loss_pct_capital`` and ``analysis_conducted_year``. Older
    payloads used shorter field names, so both formats remain supported.
    Multiple scenarios for the same horizon are averaged to avoid duplicate
    x-axis labels and to provide a readable horizon-level comparison.
    """

    horizon_order = {
        "short_term": 0,
        "medium_term": 1,
        "long_term": 2,
    }
    horizon_labels = {
        "short_term": "Short term",
        "medium_term": "Medium term",
        "long_term": "Long term",
    }

    grouped: Dict[str, Dict[str, List[float]]] = {}

    def first_numeric(row: Dict[str, Any], fields: List[str]) -> Optional[float]:
        for field in fields:
            value = to_float(row.get(field))
            if value is not None:
                return value
        return None

    for row in scenario_records:
        row_year = get_record_year(row)

        if (
            reporting_year is not None
            and row_year is not None
            and row_year != reporting_year
        ):
            continue

        raw_horizon = get_text_value(
            row,
            [
                "horizon",
                "time_horizon",
                "scenario_horizon",
                "period",
            ],
            default="",
        )
        horizon_key = raw_horizon.strip().lower().replace(" ", "_")

        if not horizon_key:
            horizon_year = to_float(row.get("horizon_year"))
            horizon_key = (
                str(int(horizon_year))
                if horizon_year is not None
                else "scenario"
            )

        transition = first_numeric(
            row,
            [
                "transition_risk_loss_pct_capital",
                "transition_loss_pct",
                "transition_risk_loss_pct",
                "transition_impact_pct",
                "transition_var_pct",
            ],
        )
        physical = first_numeric(
            row,
            [
                "physical_risk_loss_pct_capital",
                "physical_loss_pct",
                "physical_risk_loss_pct",
                "physical_impact_pct",
                "physical_var_pct",
            ],
        )

        if transition is None and physical is None:
            continue

        bucket = grouped.setdefault(
            horizon_key,
            {"transition": [], "physical": []},
        )

        if transition is not None:
            bucket["transition"].append(transition)

        if physical is not None:
            bucket["physical"].append(physical)

    ordered_horizons = sorted(
        grouped,
        key=lambda key: (
            horizon_order.get(key, 99),
            key,
        ),
    )

    def average(values: List[float]) -> Optional[float]:
        if not values:
            return None
        return round(sum(values) / len(values), 2)

    return {
        "labels": [
            horizon_labels.get(
                horizon,
                horizon.replace("_", " ").title(),
            )
            for horizon in ordered_horizons
        ],
        "datasets": [
            {
                "label": "Transition risk",
                "data": [
                    average(grouped[horizon]["transition"])
                    for horizon in ordered_horizons
                ],
                "unit": "%",
            },
            {
                "label": "Physical risk",
                "data": [
                    average(grouped[horizon]["physical"])
                    for horizon in ordered_horizons
                ],
                "unit": "%",
            },
        ],
    }


def build_physical_risk_by_hazard_chart(
    *,
    physical_risk_exposures: List[Dict[str, Any]],
) -> Dict[str, Any]:
    return group_sum_top(
        physical_risk_exposures,
        [
            "hazard",
            "hazard_type",
            "climate_hazard",
            "risk_type",
            "physical_risk_type",
        ],
        [
            "exposure_amount_meur",
            "financial_impact_meur",
            "exposure_meur",
            "amount_meur",
        ],
        top_n=8,
    )


def build_country_exposure_chart(
    *,
    physical_risk_exposures: List[Dict[str, Any]],
) -> Dict[str, Any]:
    exposure_by_country: Dict[str, float] = {}
    impact_by_country: Dict[str, float] = {}

    for row in physical_risk_exposures:
        country = get_text_value(
            row,
            [
                "country",
                "country_code",
                "location_country",
                "region",
            ],
            default="Unknown",
        )

        if country == "Unknown":
            continue

        exposure = (
            to_float(row.get("exposure_amount_meur"))
            or to_float(row.get("exposure_meur"))
            or to_float(row.get("amount_meur"))
            or 0
        )

        impact = (
            to_float(row.get("financial_impact_meur"))
            or to_float(row.get("impact_meur"))
            or 0
        )

        exposure_by_country[country] = exposure_by_country.get(country, 0) + exposure
        impact_by_country[country] = impact_by_country.get(country, 0) + impact

    top_countries = sorted(
        exposure_by_country.items(),
        key=lambda item: item[1],
        reverse=True,
    )[:8]

    labels = [country for country, _ in top_countries]

    return {
        "labels": labels,
        "datasets": [
            {
                "type": "bar",
                "label": "Exposure €m",
                "data": [round(exposure_by_country.get(country, 0), 4) for country in labels],
                "y_axis_id": "y",
            },
            {
                "type": "line",
                "label": "Impact €m",
                "data": [round(impact_by_country.get(country, 0), 4) for country in labels],
                "y_axis_id": "y1",
            },
        ],
    }


def build_opportunities_chart(
    *,
    opportunity_records: List[Dict[str, Any]],
) -> Dict[str, Any]:
    return group_sum_top(
        opportunity_records,
        [
            "opportunity_type",
            "opportunity",
            "opportunity_name",
            "category",
            "theme",
        ],
        [
            "revenue_opportunity_meur",
            "expected_revenue_meur",
            "opportunity_value_meur",
            "financial_impact_meur",
            "value_meur",
        ],
        top_n=8,
    )


def build_investment_emissions_chart(
    *,
    investment_records: List[Dict[str, Any]],
) -> Dict[str, Any]:
    return group_sum_top(
        investment_records,
        [
            "investment_id",
            "security_id",
            "issuer_name",
            "counterparty_name",
            "counterparty_id",
            "asset_name",
            "country",
        ],
        [
            "attributed_emissions_tco2e",
            "financed_emissions_tco2e",
            "emissions_tco2e",
            "portfolio_emissions_tco2e",
        ],
        top_n=8,
    )


def rating_to_score(value: Any) -> int:
    normalized = str(value).strip().lower()

    if normalized in ["critical", "very high", "severe"]:
        return 5

    if normalized in ["high"]:
        return 4

    if normalized in ["medium", "moderate"]:
        return 3

    if normalized in ["low"]:
        return 2

    if normalized in ["very low"]:
        return 1

    numeric_value = to_float(value)

    if numeric_value is None:
        return 3

    return int(max(1, min(5, numeric_value)))


def build_risk_matrix(
    *,
    climate_risk_register: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    grouped: Dict[Tuple[int, int], Dict[str, Any]] = {}

    for row in climate_risk_register:
        likelihood = rating_to_score(
            row.get("likelihood_score")
            or row.get("likelihood")
            or row.get("probability_score")
            or row.get("probability")
            or 3
        )

        severity = rating_to_score(
            row.get("severity_score")
            or row.get("severity")
            or row.get("impact_score")
            or row.get("impact")
            or row.get("risk_rating")
            or 3
        )

        impact = (
            to_float(row.get("financial_impact_meur"))
            or to_float(row.get("estimated_impact_meur"))
            or to_float(row.get("impact_meur"))
            or 0
        )

        key = (likelihood, severity)

        if key not in grouped:
            grouped[key] = {
                "likelihood": likelihood,
                "severity": severity,
                "count": 0,
                "impact": 0.0,
            }

        grouped[key]["count"] += 1
        grouped[key]["impact"] += impact

    cells = []

    for likelihood in range(5, 0, -1):
        for severity in range(1, 6):
            key = (likelihood, severity)
            existing = grouped.get(key)
            score = likelihood * severity

            if not existing:
                level = "empty"
                count = 0
                impact = 0.0
            else:
                count = existing["count"]
                impact = existing["impact"]

                if score >= 15:
                    level = "high"
                elif score >= 8:
                    level = "medium"
                else:
                    level = "low"

            cells.append(
                {
                    "likelihood": likelihood,
                    "severity": severity,
                    "count": count,
                    "impact": round(impact, 2),
                    "level": level,
                }
            )

    return cells


def build_governance_tiles(
    *,
    governance_row: Dict[str, Any],
    board_climate_expertise_pct: Optional[float],
) -> List[Dict[str, Any]]:
    return [
        {
            "label": "ESG committee",
            "value": "Yes" if is_truthy(governance_row.get("esg_committee_exists")) else "No",
            "unit": "",
        },
        {
            "label": "Board climate expertise",
            "value": board_climate_expertise_pct,
            "unit": "%",
        },
        {
            "label": "CEO ESG-linked pay",
            "value": safe_round(governance_row.get("ceo_esg_compensation_pct"), 2),
            "unit": "%",
        },
        {
            "label": "External assurance",
            "value": governance_row.get("external_assurance") or "Not specified",
            "unit": "",
        },
    ]


def build_methodology_notes(
    *,
    validation: Dict[str, Any],
    payload: Dict[str, Any],
) -> List[Dict[str, Any]]:
    notes = []

    issues = validation.get("issues", [])

    for issue in issues[:6]:
        notes.append(
            {
                "field": issue.get("field") or issue.get("table") or issue.get("code") or "validation_issue",
                "reason": issue.get("message") or "Validation issue detected.",
                "years": str(issue.get("year") or issue.get("years") or "N/A"),
            }
        )

    if not notes:
        notes.append(
            {
                "field": "canonical_validation",
                "reason": "Prepared canonical data passed validation with no blocking issues.",
                "years": str(payload.get("reporting_year") or "current reporting cycle"),
            }
        )

    return notes


def build_mini_kpis(
    *,
    total_financed_emissions: float,
    total_loans: Optional[float],
    scope1_emissions: float,
    scope2_market_emissions: float,
    scope2_location_emissions: float,
    green_loans_pct: Optional[float],
    high_carbon_exposure: float,
    high_carbon_exposure_pct: Optional[float],
    climate_capex_meur: Optional[float],
    internal_carbon_price: Optional[float],
    financed_trend_chart: Dict[str, Any],
    operations_trend_chart: Dict[str, Any],
) -> List[Dict[str, Any]]:
    financed_intensity = None

    if total_loans:
        financed_intensity = total_financed_emissions / total_loans

    financed_values = []

    if financed_trend_chart.get("datasets"):
        financed_values = financed_trend_chart["datasets"][0].get("data", [])

    financed_delta = None

    if len(financed_values) >= 2:
        financed_delta = calculate_delta_pct(
            financed_values[-1],
            financed_values[-2],
        )

    operations_total = scope1_emissions + scope2_market_emissions

    return [
        {
            "key": "financed_emissions",
            "label": "Financed emissions",
            "value": round(total_financed_emissions / 1_000_000, 2),
            "unit": "Mt CO₂e",
            **format_delta(financed_delta, lower_is_better=True),
            "note": "Scope 3 Cat.15",
        },
        {
            "key": "carbon_intensity",
            "label": "Carbon intensity",
            "value": safe_round(financed_intensity, 2),
            "unit": "t/€m lent",
            **format_delta(None, lower_is_better=True),
            "note": "Financed emissions / loans",
        },
        {
            "key": "scope_1_2",
            "label": "Scope 1 + 2",
            "value": safe_round(operations_total, 2),
            "unit": "tCO₂e",
            **format_delta(None, lower_is_better=True),
            "note": "market-based",
        },
        {
            "key": "scope2_location",
            "label": "Scope 2 location",
            "value": safe_round(scope2_location_emissions, 2),
            "unit": "tCO₂e",
            **format_delta(None, lower_is_better=True),
            "note": "location-based",
        },
        {
            "key": "green_loans",
            "label": "Green loans",
            "value": safe_round(green_loans_pct, 2),
            "unit": "%",
            **format_delta(None, lower_is_better=False),
            "note": "loan portfolio",
        },
        {
            "key": "climate_capex",
            "label": "Climate capex",
            "value": safe_round(climate_capex_meur, 2),
            "unit": "€m",
            **format_delta(None, lower_is_better=False),
            "note": "transition spend",
        },
        {
            "key": "high_carbon_exposure",
            "label": "High-carbon exposure",
            "value": safe_round(high_carbon_exposure_pct, 2),
            "unit": "%",
            **format_delta(None, lower_is_better=True),
            "note": f"€{format_compact_value(high_carbon_exposure, 1)}m",
        },
        {
            "key": "internal_carbon_price",
            "label": "Internal carbon price",
            "value": safe_round(internal_carbon_price, 2),
            "unit": "€/tCO₂e",
            **format_delta(None, lower_is_better=False),
            "note": "internal planning",
        },
    ]


def build_dashboard_charts(
    *,
    payload: Dict[str, Any],
    validation: Dict[str, Any],
    reporting_year: Optional[int],
    total_loans: Optional[float],
    green_loans_pct: Optional[float],
    total_financed_emissions: float,
    scope1_emissions: float,
    scope2_market_emissions: float,
    travel_emissions_tco2e: float,
    high_physical_risk_exposure: float,
    high_carbon_exposure: float,
    board_climate_expertise_pct: Optional[float],
    governance_row: Dict[str, Any],
    climate_risk_register: List[Dict[str, Any]],
    physical_risk_exposures: List[Dict[str, Any]],
    portfolio_composition: List[Dict[str, Any]],
    financial_summary: List[Dict[str, Any]],
) -> Dict[str, Any]:
    scope1 = as_records(payload.get("scope1"))
    scope2 = as_records(payload.get("scope2"))

    travel_records = collect_records(
        payload,
        [
            "scope3_travel",
            "travel_records",
            "business_travel",
        ],
    )

    financed_records = collect_records(
        payload,
        [
            "financed_emissions",
            "financed_emissions_by_asset_class",
            "financed_emissions_by_sector",
            "financed_emissions_loans_detail",
            "financed_emissions_equity",
            "financed_emissions_sovereign",
        ],
    )

    scenario_records = collect_records(
        payload,
        [
            "climate_scenarios",
            "scenario_analysis",
            "climate_scenario_analysis",
        ],
    )

    opportunity_records = collect_records(
        payload,
        [
            "climate_opportunities",
            "opportunities",
            "climate_opportunity_register",
        ],
    )

    investment_records = collect_records(
        payload,
        [
            "investments",
            "financed_emissions_equity",
            "financed_emissions_sovereign",
            "investment_emissions",
        ],
    )

    internal_carbon_price_records = collect_records(
        payload,
        [
            "internal_carbon_price",
            "carbon_price",
        ],
    )

    transition_plan_records = collect_records(
        payload,
        [
            "transition_plan",
            "climate_capex",
            "climate_financial_effects",
        ],
    )

    scope2_location_emissions = sum_fields(
        scope2,
        [
            "scope2_location_tco2e",
            "scope2_location_based_tco2e",
            "location_based_scope2",
        ],
    )

    internal_carbon_price_row = latest_record(
        internal_carbon_price_records,
        reporting_year,
    )

    internal_carbon_price = (
        to_float(internal_carbon_price_row.get("price_eur_per_tco2e"))
        or to_float(internal_carbon_price_row.get("carbon_price_eur"))
        or to_float(internal_carbon_price_row.get("internal_carbon_price_eur"))
    )

    climate_capex_meur = sum_fields(
        transition_plan_records,
        [
            "climate_capex_meur",
            "capex_meur",
            "transition_capex_meur",
            "planned_capex_meur",
        ],
    )

    high_carbon_exposure_pct = None

    if total_loans:
        high_carbon_exposure_pct = (high_carbon_exposure / total_loans) * 100

    high_physical_risk_exposure_pct = None

    if total_loans:
        high_physical_risk_exposure_pct = (high_physical_risk_exposure / total_loans) * 100

    operations_trend = build_operations_trend_chart(
        scope1=scope1,
        scope2=scope2,
        travel_records=travel_records,
        reporting_year=reporting_year,
    )

    financed_trend = build_financed_emissions_trend_chart(
        financed_records=financed_records,
        financial_summary=financial_summary,
        total_loans=total_loans,
        reporting_year=reporting_year,
    )

    mini_kpis = build_mini_kpis(
        total_financed_emissions=total_financed_emissions,
        total_loans=total_loans,
        scope1_emissions=scope1_emissions,
        scope2_market_emissions=scope2_market_emissions,
        scope2_location_emissions=scope2_location_emissions,
        green_loans_pct=green_loans_pct,
        high_carbon_exposure=high_carbon_exposure,
        high_carbon_exposure_pct=high_carbon_exposure_pct,
        climate_capex_meur=climate_capex_meur,
        internal_carbon_price=internal_carbon_price,
        financed_trend_chart=financed_trend,
        operations_trend_chart=operations_trend,
    )

    green_loans_amount = 0.0

    if total_loans and green_loans_pct is not None:
        green_loans_amount = total_loans * (green_loans_pct / 100)

    other_loans_amount = max((total_loans or 0) - green_loans_amount, 0)

    return {
        "mini_kpis": mini_kpis,
        "materiality": {
            "financed_emissions_pct": (
                round(
                    (
                        total_financed_emissions
                        / (
                            total_financed_emissions
                            + scope1_emissions
                            + scope2_market_emissions
                            + travel_emissions_tco2e
                        )
                    )
                    * 100,
                    2,
                )
                if (
                    total_financed_emissions
                    + scope1_emissions
                    + scope2_market_emissions
                    + travel_emissions_tco2e
                )
                else None
            ),
            "operations_emissions_tco2e": round(
                scope1_emissions + scope2_market_emissions + travel_emissions_tco2e,
                4,
            ),
            "financed_emissions_tco2e": total_financed_emissions,
        },
        "operations_trend": operations_trend,
        "financed_emissions_trend": financed_trend,
        "scope3_categories": build_scope3_categories_chart(
            payload=payload,
            travel_emissions_tco2e=travel_emissions_tco2e,
        ),
        "data_quality": build_data_quality_chart(
            payload=payload,
            financed_records=financed_records,
        ),
        "scenario_analysis": build_scenario_analysis_chart(
            scenario_records=scenario_records,
            reporting_year=reporting_year,
        ),
        "physical_risk_by_hazard": build_physical_risk_by_hazard_chart(
            physical_risk_exposures=physical_risk_exposures,
        ),
        "country_exposure": build_country_exposure_chart(
            physical_risk_exposures=physical_risk_exposures,
        ),
        "opportunities": build_opportunities_chart(
            opportunity_records=opportunity_records,
        ),
        "investment_emissions": build_investment_emissions_chart(
            investment_records=investment_records,
        ),
        "portfolio_mix": {
            "labels": ["Green loans", "Other loans"],
            "datasets": [
                {
                    "label": "€m",
                    "data": [
                        round(green_loans_amount, 4),
                        round(other_loans_amount, 4),
                    ],
                }
            ],
        },
        "climate_exposure_ratios": {
            "labels": [
                "Green loans",
                "High-carbon exposure",
                "Physical risk exposure",
            ],
            "datasets": [
                {
                    "label": "% of loans",
                    "data": [
                        safe_round(green_loans_pct, 2) or 0,
                        safe_round(high_carbon_exposure_pct, 2) or 0,
                        safe_round(high_physical_risk_exposure_pct, 2) or 0,
                    ],
                }
            ],
        },
        "risk_matrix": build_risk_matrix(
            climate_risk_register=climate_risk_register,
        ),
        "governance_tiles": build_governance_tiles(
            governance_row=governance_row,
            board_climate_expertise_pct=board_climate_expertise_pct,
        ),
        "methodology_notes": build_methodology_notes(
            validation=validation,
            payload=payload,
        ),
    }


# ============================================================
# Main KPI dashboard builder
# ============================================================

def build_kpi_dashboard(
    batch: DataUploadBatch,
    bank_id: str,
    reporting_year: Optional[int] = 2024,
) -> Dict[str, Any]:
    payload = load_payload(batch, bank_id)
    validation = load_validation_result(batch)

    bank = as_records(payload.get("bank"))
    financial_summary = as_records(payload.get("financial_summary"))
    scope1 = as_records(payload.get("scope1"))
    scope2 = as_records(payload.get("scope2"))
    climate_risk_register = as_records(payload.get("climate_risk_register"))
    physical_risk_exposures = as_records(payload.get("physical_risk_exposures"))
    portfolio_composition = as_records(payload.get("portfolio_composition"))
    governance = as_records(payload.get("governance"))
    employees = as_records(payload.get("employees"))

    bank_row = latest_record(bank, reporting_year)
    financial_row = latest_record(financial_summary, reporting_year)
    governance_row = latest_record(governance, reporting_year)

    total_assets = (
        to_float(financial_row.get("total_assets_meur"))
        or to_float(bank_row.get("total_assets_meur"))
    )

    total_loans = (
        to_float(financial_row.get("total_loans_meur"))
        or to_float(bank_row.get("total_loans_meur"))
    )

    green_loans_pct = to_float(financial_row.get("green_loans_pct"))

    if green_loans_pct is None:
        green_loans = to_float(financial_row.get("green_loans_meur"))

        if green_loans is not None and total_loans:
            green_loans_pct = round((green_loans / total_loans) * 100, 2)

    total_financed_emissions = sum_first_available_metric(
        payload,
        [
            "financed_emissions",
            "financed_emissions_by_asset_class",
            "financed_emissions_by_sector",
            "financed_emissions_loans_detail",
            "financed_emissions_equity",
            "financed_emissions_sovereign",
        ],
        [
            "financed_emissions_tco2e",
            "total_financed_emissions_tco2e",
            "attributed_emissions_tco2e",
            "total_attributed_emissions_tco2e",
            "attributed_ghg_tco2e",
            "portfolio_emissions_tco2e",
            "emissions_tco2e",
        ],
    )

    scope1_emissions = sum_fields(
        scope1,
        [
            "scope1_tco2e",
            "scope1_total_tco2e",
            "scope1_gas_tco2e",
            "scope1_tco2e_2024_clean",
            "scope1_tco2e_2024",
        ],
    )

    scope2_market_emissions = sum_fields(
        scope2,
        [
            "scope2_market_tco2e",
            "scope2_market_based_tco2e",
            "market_based_scope2",
        ],
    )

    travel_emissions_tco2e = sum_first_available_metric(
        payload,
        [
            "scope3_travel",
            "travel_records",
            "business_travel",
        ],
        [
            "emissions_tco2e",
            "travel_emissions_tco2e",
            "business_travel_emissions_tco2e",
            "scope3_travel_tco2e",
            "total_travel_emissions_tco2e",
        ],
    )

    if travel_emissions_tco2e == 0:
        travel_emissions_kg = sum_first_available_metric(
            payload,
            [
                "scope3_travel",
                "travel_records",
                "business_travel",
            ],
            [
                "emissions_kg_co2e",
                "travel_emissions_kg",
                "business_travel_emissions_kg",
            ],
        )

        travel_emissions_tco2e = round(travel_emissions_kg / 1000, 4)

    critical_climate_risks = count_by_text_value(
        climate_risk_register,
        "risk_rating",
        "critical",
    )

    high_physical_risk_by_key: Dict[str, float] = {}

    for row in physical_risk_exposures:
        high_flag = is_truthy(row.get("high_risk_flag"))
        acute_score = to_float(row.get("acute_risk_score")) or 0
        chronic_score = to_float(row.get("chronic_risk_score")) or 0

        if high_flag or acute_score >= 4 or chronic_score >= 4:
            risk_key = (
                row.get("exposure_id")
                or row.get("counterparty_id")
                or row.get("physical_risk_id")
            )

            exposure_value = (
                to_float(row.get("exposure_amount_meur"))
                or to_float(row.get("financial_impact_meur"))
                or 0
            )

            if risk_key:
                current_value = high_physical_risk_by_key.get(str(risk_key), 0)
                high_physical_risk_by_key[str(risk_key)] = max(
                    current_value,
                    exposure_value,
                )
            else:
                fallback_key = f"row_{len(high_physical_risk_by_key)}"
                high_physical_risk_by_key[fallback_key] = exposure_value

    high_physical_risk_exposure = round(
        sum(high_physical_risk_by_key.values()),
        4,
    )

    high_carbon_exposure = sum_fields(
        portfolio_composition,
        [
            "high_carbon_exposure_meur",
        ],
    )

    board_climate_expertise_pct = to_float(
        governance_row.get("board_climate_expertise_pct")
    )

    payload_exists = (get_payloads_folder(batch) / f"payload_{bank_id}.json").exists()
    validation_passed = validation.get("is_valid") is True
    blocking_issues = len(validation.get("issues", []))

    if validation_passed and payload_exists:
        report_readiness_score = 100
    elif validation_passed:
        report_readiness_score = 75
    elif blocking_issues:
        report_readiness_score = 40
    else:
        report_readiness_score = 0

    esg_score = build_esg_score(
        total_assets=total_assets,
        total_loans=total_loans,
        green_loans_pct=green_loans_pct,
        total_financed_emissions=total_financed_emissions,
        scope1_emissions=scope1_emissions,
        scope2_market_emissions=scope2_market_emissions,
        travel_emissions_tco2e=travel_emissions_tco2e,
        high_physical_risk_exposure=high_physical_risk_exposure,
        high_carbon_exposure=high_carbon_exposure,
        governance_row=governance_row,
        employees=employees,
        reporting_year=reporting_year,
    )

    charts = build_dashboard_charts(
        payload=payload,
        validation=validation,
        reporting_year=reporting_year,
        total_loans=total_loans,
        green_loans_pct=green_loans_pct,
        total_financed_emissions=total_financed_emissions,
        scope1_emissions=scope1_emissions,
        scope2_market_emissions=scope2_market_emissions,
        travel_emissions_tco2e=travel_emissions_tco2e,
        high_physical_risk_exposure=high_physical_risk_exposure,
        high_carbon_exposure=high_carbon_exposure,
        board_climate_expertise_pct=board_climate_expertise_pct,
        governance_row=governance_row,
        climate_risk_register=climate_risk_register,
        physical_risk_exposures=physical_risk_exposures,
        portfolio_composition=portfolio_composition,
        financial_summary=financial_summary,
    )

    kpis = [
        build_kpi(
            "internal_esg_score",
            "Internal ESG Score",
            esg_score.get("overall"),
            "/100",
            "Internal ESG benchmark based on climate exposure, workforce indicators, governance oversight and reporting readiness.",
            "esg",
        ),
        build_kpi(
            "total_assets_meur",
            "Total Assets",
            total_assets,
            "€m",
            "Total assets for the selected bank.",
            "financial",
        ),
        build_kpi(
            "total_loans_meur",
            "Total Loans",
            total_loans,
            "€m",
            "Total lending portfolio.",
            "financial",
        ),
        build_kpi(
            "green_loans_pct",
            "Green Loans",
            green_loans_pct,
            "%",
            "Share of loans classified as green.",
            "portfolio",
        ),
        build_kpi(
            "total_financed_emissions_tco2e",
            "Total Financed Emissions",
            total_financed_emissions,
            "tCO₂e",
            "Emissions linked to financed activities.",
            "emissions",
        ),
        build_kpi(
            "scope1_emissions_tco2e",
            "Scope 1 Emissions",
            scope1_emissions,
            "tCO₂e",
            "Direct operational emissions.",
            "emissions",
        ),
        build_kpi(
            "scope2_market_emissions_tco2e",
            "Scope 2 Market-Based Emissions",
            scope2_market_emissions,
            "tCO₂e",
            "Electricity-related market-based emissions.",
            "emissions",
        ),
        build_kpi(
            "business_travel_emissions_tco2e",
            "Business Travel Emissions",
            travel_emissions_tco2e,
            "tCO₂e",
            "Scope 3 business travel emissions.",
            "emissions",
        ),
        build_kpi(
            "critical_climate_risks",
            "Critical Climate Risks",
            critical_climate_risks,
            "",
            "Number of climate risks rated critical.",
            "risk",
        ),
        build_kpi(
            "high_physical_risk_exposure_meur",
            "High Physical Risk Exposure",
            high_physical_risk_exposure,
            "€m",
            "Exposure linked to high physical climate risk.",
            "risk",
        ),
        build_kpi(
            "high_carbon_exposure_meur",
            "High-Carbon Exposure",
            high_carbon_exposure,
            "€m",
            "Portfolio exposure to high-carbon sectors.",
            "portfolio",
        ),
        build_kpi(
            "board_climate_expertise_pct",
            "Board Climate Expertise",
            board_climate_expertise_pct,
            "%",
            "Board members with climate-related expertise.",
            "governance",
        ),
        build_kpi(
            "report_readiness_score",
            "Report Readiness Score",
            report_readiness_score,
            "%",
            "Readiness of data for IFRS S1/S2 report generation.",
            "readiness",
        ),
    ]

    return {
        "batch_id": str(batch.id),
        "bank_id": bank_id,
        "reporting_year": reporting_year,
        "bank_name": bank_row.get("bank_name"),
        "validation_passed": validation_passed,
        "payload_exists": payload_exists,
        "esg_score": esg_score,
        "kpis": kpis,
        "charts": charts,
    }