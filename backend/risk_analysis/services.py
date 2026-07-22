"""
Deterministic processing for Risk Analysis.

The module accepts the combined payload produced by Data Preparation and also
supports the section-specific payload files used by Report Generation. It
does not create synthetic peers, counterparty identifiers, or arbitrary
scenario sensitivity bands.
"""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any


FORBIDDEN_IMPROVED_KEYS = {
    "_augmentation_disclaimer",
    "peer_benchmark",
    "scenario_sensitivity",
    "counterparty_drilldown",
    "data_quality_assurance_register",
    "data_quality_summary",
}


class RiskPayloadError(Exception):
    pass


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8")
        )
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:
        raise RiskPayloadError(
            f"Could not read canonical payload "
            f"{path.name}: {exc}"
        ) from exc

    if not isinstance(value, dict):
        raise RiskPayloadError(
            f"Canonical payload {path.name} "
            "does not contain a JSON object."
        )

    return value


def _find_exact_payload(
    payload_dir: Path,
    filename: str,
) -> Path | None:
    matches = [
        path
        for path in payload_dir.rglob("*.json")
        if path.name.lower() == filename.lower()
    ]

    if len(matches) > 1:
        raise RiskPayloadError(
            f"More than one {filename} file was found "
            "in the prepared dataset."
        )

    return matches[0] if matches else None


def load_canonical_payload(
    payload_dir: str | Path,
    *,
    bank_code: str,
    bank_name: str,
    reporting_year: int,
) -> tuple[dict, str]:
    """
    Load one canonical combined payload only.

    Preferred filename:
        payload_<BANK>_v2.json

    Backwards-compatible filename:
        payload_<BANK>.json

    The loader deliberately does not scan, merge, or consume:
      - *_improved.json
      - section-specific report payloads
      - precomputed peer benchmarks
      - precomputed scenario sensitivity
      - synthetic counterparty drill-downs

    Risk Analysis derives its dashboard bundle dynamically from the same
    canonical source used by the reporting workflow.
    """
    directory = Path(payload_dir)

    if not directory.exists():
        raise RiskPayloadError(
            "The prepared dataset folder does not exist."
        )

    code = bank_code.strip().upper()
    preferred_names = [
        f"payload_{code}_v2.json",
        f"payload_{code}.json",
    ]

    selected_path: Path | None = None

    for filename in preferred_names:
        selected_path = _find_exact_payload(
            directory,
            filename,
        )

        if selected_path is not None:
            break

    if selected_path is None:
        improved_name = (
            f"payload_{code}_improved.json"
        )
        improved_path = _find_exact_payload(
            directory,
            improved_name,
        )

        if improved_path is not None:
            raise RiskPayloadError(
                "Only an improved/augmented payload was "
                "found. Risk Analysis requires the "
                "canonical V2 payload."
            )

        raise RiskPayloadError(
            "The canonical combined payload was not found. "
            f"Expected {preferred_names[0]} or "
            f"{preferred_names[1]}."
        )

    payload = _read_json(selected_path)

    forbidden_present = sorted(
        key
        for key in FORBIDDEN_IMPROVED_KEYS
        if key in payload
    )

    if forbidden_present:
        raise RiskPayloadError(
            "The selected file contains improved-payload "
            "augmentation sections and cannot be used as "
            "the canonical source: "
            + ", ".join(forbidden_present)
        )

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

    source_code = (
        bank.get("bank_id")
        or metadata.get("bank_id")
        or context.get("bank_id")
    )

    if (
        source_code
        and str(source_code).strip().upper()
        != code
    ):
        raise RiskPayloadError(
            "The canonical payload belongs to a "
            "different institution."
        )

    source_year = (
        metadata.get("reporting_year")
        or context.get("reporting_year")
    )

    if source_year is not None:
        try:
            source_year_int = int(source_year)
        except (TypeError, ValueError) as exc:
            raise RiskPayloadError(
                "The canonical payload has an invalid "
                "reporting year."
            ) from exc

        if source_year_int != int(reporting_year):
            raise RiskPayloadError(
                "The canonical payload reporting year "
                "does not match the selected prepared "
                "dataset."
            )

    source_name = (
        bank.get("bank_name")
        or context.get("reporting_entity")
    )

    if (
        source_name
        and bank_name
        and str(source_name).strip().casefold()
        != str(bank_name).strip().casefold()
    ):
        raise RiskPayloadError(
            "The canonical payload institution name "
            "does not match the selected prepared "
            "dataset."
        )

    return payload, selected_path.name


def _as_rows(
    value: Any,
    *,
    include_synthetic: bool = False,
) -> list[dict]:
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

    if include_synthetic:
        return rows

    return [
        row
        for row in rows
        if row.get("is_synthetic") is not True
    ]


def _rows_for_reporting_year(
    payload: dict,
    section: str,
) -> list[dict]:
    rows = _as_rows(
        payload.get(section)
    )
    metadata = payload.get(
        "metadata",
        {},
    )

    if not isinstance(metadata, dict):
        metadata = {}

    reporting_year = _number(
        metadata.get("reporting_year")
    )

    if reporting_year is None:
        return rows

    matching = [
        row
        for row in rows
        if (
            row.get("reporting_year") is None
            or _number(
                row.get("reporting_year")
            )
            == reporting_year
        )
    ]

    return matching


def _number(
    value: Any,
) -> float | None:
    if (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
    ):
        return float(value)

    try:
        if value in (
            None,
            "",
            "null",
            "None",
        ):
            return None

        return float(value)
    except (
        TypeError,
        ValueError,
    ):
        return None


def _rounded(
    value: Any,
    digits: int = 2,
) -> float | None:
    number = _number(value)

    if number is None:
        return None

    return round(number, digits)


def _latest(
    rows: Any,
    year_key: str = "reporting_year",
) -> dict:
    records = _as_rows(rows)

    if not records:
        return {}

    def sort_key(row: dict) -> float:
        return (
            _number(row.get(year_key))
            or _number(
                row.get("year")
            )
            or 0
        )

    return sorted(
        records,
        key=sort_key,
    )[-1]


def _dynamic_kpi(
    kpis: dict,
    *,
    base_names: list[str],
    reporting_year: int | None,
) -> float | None:
    candidate_keys: list[str] = []

    for base in base_names:
        candidate_keys.append(base)

        if reporting_year:
            candidate_keys.extend(
                [
                    f"{base}_{reporting_year}",
                    (
                        f"{base}_{reporting_year}"
                        "_tco2e"
                    ),
                    (
                        f"{base}_{reporting_year}"
                        "_tco2e_per_meur"
                    ),
                    (
                        f"{base}_{reporting_year}"
                        "_meur"
                    ),
                    (
                        f"{base}_{reporting_year}"
                        "_pct"
                    ),
                ]
            )

    for key in candidate_keys:
        value = _number(
            kpis.get(key)
        )

        if value is not None:
            return value

    for key, value in kpis.items():
        key_lower = key.lower()

        if any(
            base.lower() in key_lower
            for base in base_names
        ):
            number = _number(value)

            if number is not None:
                return number

    return None


def _format_number(
    value: float | None,
    digits: int = 1,
) -> str:
    if value is None:
        return "Not available"

    return f"{value:,.{digits}f}"


def build_kpis(payload: dict) -> list[dict]:
    kpis: list[dict] = []
    bank = payload.get("bank", {})
    metadata = payload.get("metadata", {})
    reporting_year = metadata.get(
        "reporting_year"
    )
    reporting_kpis = payload.get(
        "reporting_kpis",
        {},
    )

    financed_rows = sorted(
        _as_rows(
            payload.get(
                "financed_emissions"
            )
        ),
        key=lambda row: (
            _number(
                row.get("reporting_year")
            )
            or 0
        ),
    )

    if financed_rows:
        latest = financed_rows[-1]
        latest_value = _number(
            latest.get(
                "financed_em_loans_tco2e"
            )
        )

        if latest_value is not None:
            change_label = (
                "Latest available year"
            )
            tone = "neutral"

            if len(financed_rows) >= 2:
                first = financed_rows[0]
                first_value = _number(
                    first.get(
                        "financed_em_loans_tco2e"
                    )
                )

                if (
                    first_value is not None
                    and first_value != 0
                ):
                    delta = (
                        latest_value
                        - first_value
                    ) / first_value * 100

                    change_label = (
                        f"{delta:+.1f}% vs "
                        f"{first.get('reporting_year', '')}"
                    )
                    tone = (
                        "positive"
                        if delta < 0
                        else "negative"
                    )

            kpis.append(
                {
                    "title": (
                        "Financed emissions"
                    ),
                    "value": round(
                        latest_value / 1_000_000,
                        1,
                    ),
                    "suffix": "Mt CO₂e",
                    "change": change_label,
                    "cls": tone,
                }
            )

    financial_latest = _latest(
        payload.get("financial_summary")
    )

    intensity = (
        _number(
            financial_latest.get(
                "carbon_intensity_tco2e_per_meur_lending"
            )
        )
        or _dynamic_kpi(
            reporting_kpis,
            base_names=[
                "carbon_intensity",
            ],
            reporting_year=reporting_year,
        )
    )

    target_intensity = _number(
        bank.get(
            "target_intensity_tco2e_per_meur"
        )
    )

    if intensity is not None:
        change = "No target provided"
        tone = "neutral"

        if target_intensity is not None:
            change = (
                f"Target "
                f"{target_intensity:,.0f} t/M€"
            )
            tone = (
                "positive"
                if intensity <= target_intensity
                else "negative"
            )

        kpis.append(
            {
                "title": "Carbon intensity",
                "value": round(
                    intensity,
                    0,
                ),
                "suffix": "t/M€",
                "change": change,
                "cls": tone,
            }
        )

    risks = _rows_for_reporting_year(
        payload,
        "climate_risk_register",
    )

    if risks:
        critical = sum(
            1
            for row in risks
            if str(
                row.get("risk_rating", "")
            ).lower() == "critical"
        )
        high = sum(
            1
            for row in risks
            if str(
                row.get("risk_rating", "")
            ).lower() == "high"
        )

        kpis.append(
            {
                "title": (
                    "Critical and high risks"
                ),
                "value": critical,
                "suffix": (
                    f"+{high} high"
                ),
                "change": (
                    f"{len(risks)} risks assessed"
                ),
                "cls": (
                    "negative"
                    if critical or high
                    else "positive"
                ),
            }
        )

    physical_rows = _as_rows(
        payload.get(
            "physical_risk_exposures"
        )
    )

    if physical_rows:
        high_rows = [
            row
            for row in physical_rows
            if row.get("high_risk_flag")
        ]
        exposure = sum(
            _number(
                row.get(
                    "exposure_amount_meur"
                )
            )
            or 0
            for row in high_rows
        )
        counterparties = {
            row.get("counterparty_id")
            for row in high_rows
            if row.get("counterparty_id")
        }

        kpis.append(
            {
                "title": (
                    "High physical-risk exposure"
                ),
                "value": round(
                    exposure,
                    0,
                ),
                "suffix": "M€",
                "change": (
                    f"{len(counterparties)} "
                    "linked counterparties"
                ),
                "cls": (
                    "negative"
                    if exposure > 0
                    else "positive"
                ),
            }
        )

    scenarios = _as_rows(
        payload.get(
            "climate_scenarios"
        )
    )
    scenario_values = [
        _number(
            row.get(
                "revenue_at_risk_meur"
            )
        )
        for row in scenarios
    ]
    scenario_values = [
        value
        for value in scenario_values
        if value is not None
    ]

    if scenario_values:
        worst = max(scenario_values)

        kpis.append(
            {
                "title": (
                    "Highest revenue at risk"
                ),
                "value": round(
                    worst,
                    0,
                ),
                "suffix": "M€",
                "change": (
                    "Across available scenarios"
                ),
                "cls": "negative",
            }
        )

    return kpis


def _find_intensity_target(
    payload: dict,
) -> dict:
    targets = _as_rows(
        payload.get("targets")
    )

    for target in targets:
        metric = str(
            target.get("metric", "")
        ).lower()
        target_type = str(
            target.get("type", "")
        ).lower()
        scope = str(
            target.get("scope", "")
        ).lower()

        if (
            "tco2e_per_meur" in metric
            or "intensity" in metric
            or "intensity" in target_type
            or "cat15" in scope
        ):
            return target

    return {}


def build_intensity_trend(
    payload: dict,
) -> list[dict]:
    rows_by_year: dict[int, dict] = {}

    for row in _as_rows(
        payload.get("financial_summary")
    ):
        year = _number(
            row.get("reporting_year")
        )
        actual = _number(
            row.get(
                "carbon_intensity_tco2e_per_meur_lending"
            )
        )

        if year is None:
            continue

        rows_by_year[int(year)] = {
            "year": str(int(year)),
            "actual": actual,
            "target": None,
        }

    target = _find_intensity_target(
        payload
    )

    baseline_year = _number(
        target.get("baseline_year")
    )
    baseline_value = _number(
        target.get("baseline_value")
    )

    if baseline_year is not None:
        year = int(baseline_year)
        rows_by_year.setdefault(
            year,
            {
                "year": str(year),
                "actual": None,
                "target": None,
            },
        )
        rows_by_year[year][
            "target"
        ] = baseline_value

    milestones = (
        target.get("milestones_parsed")
        or target.get("milestones")
        or []
    )

    if isinstance(milestones, dict):
        milestones = [
            {
                "year": key,
                "value": value,
            }
            for key, value
            in milestones.items()
        ]

    for milestone in _as_rows(
        milestones
    ):
        year = _number(
            milestone.get("year")
            or milestone.get(
                "target_year"
            )
        )
        value = _number(
            milestone.get("value")
            or milestone.get(
                "target_value"
            )
        )

        if year is None:
            continue

        year_int = int(year)
        rows_by_year.setdefault(
            year_int,
            {
                "year": str(year_int),
                "actual": None,
                "target": None,
            },
        )
        rows_by_year[year_int][
            "target"
        ] = value

    target_year = _number(
        target.get("target_year")
    )
    target_value = _number(
        target.get("target_value")
    )

    if target_year is not None:
        year_int = int(target_year)
        rows_by_year.setdefault(
            year_int,
            {
                "year": str(year_int),
                "actual": None,
                "target": None,
            },
        )

        if target_value is not None:
            rows_by_year[year_int][
                "target"
            ] = target_value

    return [
        rows_by_year[year]
        for year in sorted(rows_by_year)
    ]


def build_financed_composition(
    payload: dict,
) -> list[dict]:
    aggregated = _as_rows(
        payload.get(
            "financed_emissions_by_asset_class"
        )
    )

    if aggregated:
        output = []

        for row in aggregated:
            name = (
                row.get("pcaf_asset_class")
                or row.get("asset_class")
                or "Other"
            )
            value = _number(
                row.get(
                    "financed_emissions_tco2e"
                )
                or row.get(
                    "attributed_emissions_tco2e"
                )
            )

            if value is None:
                continue

            output.append(
                {
                    "name": str(name).replace(
                        "_",
                        " ",
                    ),
                    "value": value,
                    "proxy": bool(
                        row.get("proxy")
                        or row.get(
                            "emissions_proxy_used"
                        )
                    ),
                }
            )

        return sorted(
            output,
            key=lambda row: -row["value"],
        )

    output = []
    financed_latest = _latest(
        payload.get(
            "financed_emissions"
        )
    )

    corporate = _number(
        financed_latest.get(
            "financed_em_loans_tco2e"
        )
    )

    if corporate is not None:
        output.append(
            {
                "name": "Corporate loans",
                "value": corporate,
                "proxy": False,
            }
        )

    sovereign_rows = _as_rows(
        payload.get(
            "financed_emissions_sovereign"
        )
    )
    sovereign_values = [
        _number(
            row.get(
                "attributed_emissions_tco2e"
            )
        )
        for row in sovereign_rows
    ]
    sovereign_total = sum(
        value
        for value in sovereign_values
        if value is not None
    )

    if sovereign_values:
        output.append(
            {
                "name": "Sovereign bonds",
                "value": sovereign_total,
                "proxy": False,
            }
        )

    equity_rows = _as_rows(
        payload.get(
            "financed_emissions_equity"
        )
    )
    equity_values = [
        _number(
            row.get(
                "attributed_emissions_proxy_tco2e"
            )
            or row.get(
                "attributed_emissions_tco2e"
            )
        )
        for row in equity_rows
    ]
    equity_total = sum(
        value
        for value in equity_values
        if value is not None
    )

    if equity_values:
        output.append(
            {
                "name": "Listed equity",
                "value": equity_total,
                "proxy": any(
                    row.get(
                        "emissions_proxy_used"
                    )
                    or (
                        row.get(
                            "attributed_emissions_proxy_tco2e"
                        )
                        is not None
                    )
                    for row in equity_rows
                ),
            }
        )

    return output


def build_risk_matrix(
    payload: dict,
) -> list[dict]:
    output = []

    for row in _rows_for_reporting_year(
        payload,
        "climate_risk_register",
    ):
        likelihood = _number(
            row.get("likelihood_score")
        )
        severity = _number(
            row.get("severity_score")
        )

        if not (
            likelihood is not None
            and severity is not None
            and 1 <= likelihood <= 5
            and 1 <= severity <= 5
        ):
            continue

        output.append(
            {
                "x": int(likelihood),
                "y": int(severity),
                "z": (
                    _number(
                        row.get(
                            "financial_impact_meur"
                        )
                    )
                    or 0
                ),
                "name": (
                    row.get("risk_name")
                    or row.get(
                        "description"
                    )
                    or "Unnamed risk"
                ),
                "rating": (
                    row.get("risk_rating")
                    or "unrated"
                ),
                "id": (
                    row.get("risk_id")
                    or ""
                ),
                "horizon": (
                    row.get("time_horizon")
                    or ""
                ),
                "category": (
                    row.get("risk_category")
                    or "other"
                ),
                "ifrs": (
                    row.get(
                        "ifrs_s2_para_evidence"
                    )
                    or ""
                ),
            }
        )

    return output


def build_risk_by_category(
    payload: dict,
) -> list[dict]:
    grouped: dict[str, dict] = {}

    for row in _rows_for_reporting_year(
        payload,
        "climate_risk_register",
    ):
        category = str(
            row.get("risk_category")
            or "other"
        )
        rating = str(
            row.get("risk_rating")
            or "unrated"
        ).lower()

        grouped.setdefault(
            category,
            {
                "name": category.replace(
                    "_",
                    " ",
                )
            },
        )
        grouped[category][rating] = (
            grouped[category].get(
                rating,
                0,
            )
            + 1
        )

    output = list(grouped.values())

    for row in output:
        row["total"] = sum(
            value
            for key, value in row.items()
            if (
                key != "name"
                and isinstance(
                    value,
                    (int, float),
                )
            )
        )

    return sorted(
        output,
        key=lambda row: -row["total"],
    )


def build_physical_by_hazard(
    payload: dict,
) -> list[dict]:
    grouped: dict[str, dict] = {}

    for row in _as_rows(
        payload.get(
            "physical_risk_exposures"
        )
    ):
        hazard = str(
            row.get("hazard_type")
            or "other"
        )

        grouped.setdefault(
            hazard,
            {
                "hazard": hazard.replace(
                    "_",
                    " ",
                ),
                "exposure": 0.0,
                "count": 0,
                "high": 0,
            },
        )

        exposure = _number(
            row.get(
                "exposure_amount_meur"
            )
        )

        if exposure is not None:
            grouped[hazard][
                "exposure"
            ] += exposure

        grouped[hazard]["count"] += 1

        if row.get("high_risk_flag"):
            grouped[hazard]["high"] += 1

    output = list(grouped.values())

    for row in output:
        row["exposure"] = round(
            row["exposure"],
            1,
        )

    return sorted(
        output,
        key=lambda row: -row["exposure"],
    )


def build_physical_by_country(
    payload: dict,
) -> list[dict]:
    grouped: dict[str, dict] = {}

    for row in _as_rows(
        payload.get(
            "physical_risk_exposures"
        )
    ):
        country = str(
            row.get("country")
            or "Unspecified"
        )

        grouped.setdefault(
            country,
            {
                "country": country,
                "exposure": 0.0,
                "financial_impact": 0.0,
                "high_risk_count": 0,
            },
        )

        grouped[country]["exposure"] += (
            _number(
                row.get(
                    "exposure_amount_meur"
                )
            )
            or 0
        )
        grouped[country][
            "financial_impact"
        ] += (
            _number(
                row.get(
                    "financial_impact_meur"
                )
            )
            or 0
        )

        if row.get("high_risk_flag"):
            grouped[country][
                "high_risk_count"
            ] += 1

    output = list(grouped.values())

    for row in output:
        row["exposure"] = round(
            row["exposure"],
            1,
        )
        row[
            "financial_impact"
        ] = round(
            row["financial_impact"],
            1,
        )

    return sorted(
        output,
        key=lambda row: -row["exposure"],
    )


def build_scenarios(
    payload: dict,
) -> list[dict]:
    """
    Return one series per real scenario name.

    The previous prototype grouped by scenario type, which caused multiple
    orderly/disorderly/hot-house scenarios to overwrite each other at the
    same horizon.
    """
    horizon_order = {
        "short_term": 0,
        "medium_term": 1,
        "long_term": 2,
    }
    grouped: dict[str, dict] = {}

    for row in _as_rows(
        payload.get("climate_scenarios")
    ):
        horizon_raw = str(
            row.get("horizon")
            or row.get("time_horizon")
            or "other"
        )
        horizon_label = horizon_raw.replace(
            "_",
            " ",
        )
        scenario_name = str(
            row.get("scenario_name")
            or row.get("scenario_type")
            or "scenario"
        )

        value = _number(
            row.get(
                "revenue_at_risk_meur"
            )
        )

        if value is None:
            value = _number(
                row.get(
                    "financial_impact_meur"
                )
            )

        grouped.setdefault(
            horizon_raw,
            {
                "horizon": horizon_label,
            },
        )
        grouped[horizon_raw][
            scenario_name
        ] = value

    return [
        value
        for _, value in sorted(
            grouped.items(),
            key=lambda item: (
                horizon_order.get(
                    item[0],
                    99,
                )
            ),
        )
    ]


def _assurance_applies(
    scope: str,
    domain_terms: list[str],
) -> bool:
    lowered = scope.lower()

    return any(
        term.lower() in lowered
        for term in domain_terms
    )


def _pcaf_confidence(
    scores: list[float],
) -> tuple[str, str]:
    if not scores:
        return (
            "not assessed",
            "No PCAF quality score was provided.",
        )

    average = statistics.mean(scores)

    if average <= 2:
        label = "high"
    elif average <= 3.5:
        label = "medium"
    else:
        label = "low"

    return (
        label,
        (
            "Platform-assessed from the average "
            f"PCAF data-quality score ({average:.2f})."
        ),
    )


def build_data_quality_register(
    payload: dict,
) -> tuple[list[dict], dict]:
    context = payload.get(
        "general_requirements_context",
        {},
    )
    reporting_kpis = payload.get(
        "reporting_kpis",
        {},
    )
    assurance_level = str(
        context.get("external_assurance")
        or "not specified"
    )
    assurance_scope = str(
        context.get("assurance_scope")
        or ""
    )
    assurance_provider = context.get(
        "assurance_provider"
    )
    assurance_standard = context.get(
        "assurance_standard"
    )

    register: list[dict] = []

    if (
        _as_rows(payload.get("scope1"))
        or _as_rows(payload.get("scope2"))
    ):
        applies = _assurance_applies(
            assurance_scope,
            [
                "scope 1",
                "scope 2",
                "scope1",
                "scope2",
                "operational emissions",
            ],
        )

        register.append(
            {
                "domain": "scope1_scope2",
                "label": (
                    "Scope 1 and 2 operational "
                    "emissions"
                ),
                "assurance_level": (
                    assurance_level
                    if applies
                    else "not specified"
                ),
                "assurance_provider": (
                    assurance_provider
                    if applies
                    else None
                ),
                "assurance_standard": (
                    assurance_standard
                    if applies
                    else None
                ),
                "is_synthetic": False,
                "confidence": (
                    "assured"
                    if applies
                    else "not assessed"
                ),
                "confidence_basis": (
                    "Based on the reported assurance scope."
                    if applies
                    else (
                        "The provided assurance scope does "
                        "not explicitly cover this domain."
                    )
                ),
                "note": (
                    assurance_scope
                    or "No assurance scope was provided."
                ),
            }
        )

    loan_details = _as_rows(
        payload.get(
            "financed_emissions_loans_detail"
        )
    )
    loan_scores = [
        score
        for score in (
            _number(
                row.get(
                    "pcaf_data_quality_score"
                )
            )
            for row in loan_details
        )
        if score is not None
    ]

    if (
        _as_rows(
            payload.get("financed_emissions")
        )
        or loan_details
    ):
        confidence, basis = (
            _pcaf_confidence(
                loan_scores
            )
        )
        applies = _assurance_applies(
            assurance_scope,
            [
                "financed emissions",
                "scope 3 category 15",
                "scope3 category 15",
            ],
        )

        register.append(
            {
                "domain": (
                    "financed_emissions_loans"
                ),
                "label": (
                    "Financed emissions — lending"
                ),
                "assurance_level": (
                    assurance_level
                    if applies
                    else "not specified"
                ),
                "assurance_provider": (
                    assurance_provider
                    if applies
                    else None
                ),
                "assurance_standard": (
                    assurance_standard
                    if applies
                    else None
                ),
                "is_synthetic": False,
                "confidence": confidence,
                "confidence_basis": basis,
                "note": (
                    f"{len(loan_scores)} source row(s) "
                    "included a PCAF quality score."
                    if loan_scores
                    else (
                        "No row-level PCAF score was "
                        "available."
                    )
                ),
            }
        )

    equity_rows = _as_rows(
        payload.get(
            "financed_emissions_equity"
        )
    )
    equity_scores = [
        score
        for score in (
            _number(
                row.get(
                    "pcaf_data_quality_score"
                )
            )
            for row in equity_rows
        )
        if score is not None
    ]

    if equity_rows:
        confidence, basis = (
            _pcaf_confidence(
                equity_scores
            )
        )
        proxy_count = sum(
            1
            for row in equity_rows
            if (
                row.get(
                    "emissions_proxy_used"
                )
                or row.get(
                    "attributed_emissions_proxy_tco2e"
                )
                is not None
            )
        )

        register.append(
            {
                "domain": (
                    "financed_emissions_equity"
                ),
                "label": (
                    "Financed emissions — listed "
                    "equity"
                ),
                "assurance_level": (
                    "not specified"
                ),
                "assurance_provider": None,
                "assurance_standard": None,
                "is_synthetic": False,
                "confidence": confidence,
                "confidence_basis": basis,
                "note": (
                    f"{proxy_count} of "
                    f"{len(equity_rows)} row(s) use "
                    "a proxy method."
                ),
            }
        )

    physical_rows = _as_rows(
        payload.get(
            "physical_risk_exposures"
        )
    )

    if physical_rows:
        sources = {
            str(
                row.get("data_source")
            )
            for row in physical_rows
            if row.get("data_source")
        }

        register.append(
            {
                "domain": (
                    "physical_risk_exposures"
                ),
                "label": (
                    "Physical-risk exposure"
                ),
                "assurance_level": (
                    "not specified"
                ),
                "assurance_provider": None,
                "assurance_standard": None,
                "is_synthetic": False,
                "confidence": (
                    "not assessed"
                ),
                "confidence_basis": (
                    "No standardised confidence score "
                    "was present in the prepared data."
                ),
                "note": (
                    "Reported source(s): "
                    + ", ".join(sorted(sources))
                    if sources
                    else (
                        "No source label was provided."
                    )
                ),
            }
        )

    summary = reporting_kpis.get(
        "emissions_data_quality_summary",
        {},
    )

    if not isinstance(summary, dict):
        summary = {}

    result_summary = {
        "audited_report_pct": _number(
            summary.get("audited_report")
        ),
        "cdp_disclosure_pct": _number(
            summary.get("cdp_disclosure")
        ),
        "estimated_economic_pct": _number(
            summary.get(
                "estimated_economic"
            )
        ),
        "proxy_model_pct": _number(
            summary.get("proxy_model")
        ),
    }

    available_values = [
        value
        for value
        in result_summary.values()
        if value is not None
    ]

    if available_values:
        modeled = sum(
            value
            for key, value
            in result_summary.items()
            if (
                key
                in {
                    "estimated_economic_pct",
                    "proxy_model_pct",
                }
                and value is not None
            )
        )
        result_summary[
            "interpretation"
        ] = (
            "The prepared data identifies "
            f"{modeled:.1f}% as estimated or "
            "proxy-based."
        )

    return register, result_summary


def build_counterparty_drilldown(
    payload: dict,
    top_n: int = 20,
) -> dict:
    grouped = defaultdict(
        lambda: {
            "exposure_meur": 0.0,
            "financial_impact_meur": 0.0,
            "hazard_types": set(),
            "country": None,
            "high_risk_count": 0,
            "n_exposures": 0,
        }
    )

    excluded_rows = 0

    for row in _as_rows(
        payload.get(
            "physical_risk_exposures"
        )
    ):
        counterparty_id = row.get(
            "counterparty_id"
        )

        if not counterparty_id:
            excluded_rows += 1
            continue

        item = grouped[counterparty_id]
        item["exposure_meur"] += (
            _number(
                row.get(
                    "exposure_amount_meur"
                )
            )
            or 0
        )
        item[
            "financial_impact_meur"
        ] += (
            _number(
                row.get(
                    "financial_impact_meur"
                )
            )
            or 0
        )

        hazard = row.get("hazard_type")

        if hazard:
            item[
                "hazard_types"
            ].add(str(hazard))

        item["country"] = (
            row.get("country")
            or item["country"]
        )
        item[
            "high_risk_count"
        ] += (
            1
            if row.get("high_risk_flag")
            else 0
        )
        item["n_exposures"] += 1

    rows = [
        {
            "counterparty_id": (
                counterparty_id
            ),
            "country": value["country"],
            "exposure_meur": round(
                value["exposure_meur"],
                2,
            ),
            "financial_impact_meur": round(
                value[
                    "financial_impact_meur"
                ],
                2,
            ),
            "hazard_types": sorted(
                value["hazard_types"]
            ),
            "high_risk_count": value[
                "high_risk_count"
            ],
            "n_exposures": value[
                "n_exposures"
            ],
        }
        for counterparty_id, value
        in grouped.items()
    ]

    rows.sort(
        key=lambda row: -row[
            "exposure_meur"
        ]
    )

    equity_rows = _as_rows(
        payload.get(
            "financed_emissions_equity"
        )
    )
    unlinked_equity_rows = sum(
        1
        for row in equity_rows
        if not row.get("counterparty_id")
    )

    return {
        "physical_risk_top_by_exposure": (
            rows[:top_n]
        ),
        "physical_risk_basis": (
            "Aggregated from source counterparty "
            "identifiers."
        ),
        "excluded_physical_rows": (
            excluded_rows
        ),
        "unlinked_equity_rows": (
            unlinked_equity_rows
        ),
    }


def build_evidence(
    payload: dict,
    derived: dict,
) -> list[dict]:
    evidence: list[dict] = []

    def add(
        key: str,
        label: str,
        value: str,
        source: str,
        ifrs: str,
        detail: str,
    ) -> None:
        evidence.append(
            {
                "id": (
                    f"E{len(evidence) + 1}"
                ),
                "key": key,
                "label": label,
                "value": value,
                "source": source,
                "ifrs": ifrs,
                "detail": detail,
            }
        )

    bank = payload.get("bank", {})
    metadata = payload.get("metadata", {})
    reporting_year = metadata.get(
        "reporting_year"
    )
    reporting_kpis = payload.get(
        "reporting_kpis",
        {},
    )

    financial_latest = _latest(
        payload.get("financial_summary")
    )
    intensity = (
        _number(
            financial_latest.get(
                "carbon_intensity_tco2e_per_meur_lending"
            )
        )
        or _dynamic_kpi(
            reporting_kpis,
            base_names=[
                "carbon_intensity",
            ],
            reporting_year=reporting_year,
        )
    )
    intensity_target = _number(
        bank.get(
            "target_intensity_tco2e_per_meur"
        )
    )

    if intensity is not None:
        value = (
            f"{intensity:,.0f} tCO₂e/M€"
        )

        if intensity_target is not None:
            value += (
                f" versus a stated target of "
                f"{intensity_target:,.0f} "
                "tCO₂e/M€"
            )

        add(
            "carbon_intensity",
            "Carbon intensity",
            value,
            "financial_summary / reporting_kpis",
            "IFRS S2 metrics and targets",
            (
                "Latest available lending-book "
                "carbon-intensity value."
            ),
        )

    financed_latest = _latest(
        payload.get(
            "financed_emissions"
        )
    )
    financed_value = _number(
        financed_latest.get(
            "financed_em_loans_tco2e"
        )
    )

    if financed_value is not None:
        add(
            "financed_emissions",
            "Financed emissions",
            (
                f"{financed_value / 1_000_000:,.1f} "
                "Mt CO₂e"
            ),
            "financed_emissions",
            "IFRS S2 financed emissions",
            (
                "Latest available financed-emissions "
                "total for lending."
            ),
        )

    risks = _rows_for_reporting_year(
        payload,
        "climate_risk_register",
    )

    if risks:
        critical = sum(
            1
            for row in risks
            if str(
                row.get("risk_rating", "")
            ).lower() == "critical"
        )
        high = sum(
            1
            for row in risks
            if str(
                row.get("risk_rating", "")
            ).lower() == "high"
        )

        add(
            "risk_register",
            "Risk-register severity",
            (
                f"{critical} critical and {high} high "
                f"out of {len(risks)} risks"
            ),
            "climate_risk_register",
            "IFRS S2 risk identification",
            (
                "Counted directly from the prepared "
                "risk register."
            ),
        )

    hazards = derived.get(
        "physical_by_hazard",
        [],
    )

    if hazards:
        top = hazards[0]

        add(
            "physical_hazard",
            "Largest physical-risk hazard",
            (
                f"{top['hazard']}: "
                f"€{top['exposure']:,.1f}M across "
                f"{top['count']} exposure row(s)"
            ),
            "physical_risk_exposures",
            "IFRS S2 physical climate risk",
            (
                "Largest aggregated hazard exposure "
                "in the prepared data."
            ),
        )

    scenarios = _as_rows(
        payload.get("climate_scenarios")
    )
    scenario_values = [
        (
            _number(
                row.get(
                    "revenue_at_risk_meur"
                )
                or row.get(
                    "financial_impact_meur"
                )
            ),
            row,
        )
        for row in scenarios
    ]
    scenario_values = [
        item
        for item in scenario_values
        if item[0] is not None
    ]

    if scenario_values:
        worst_value, worst_row = max(
            scenario_values,
            key=lambda item: item[0],
        )

        scenario_name = str(
            worst_row.get("scenario_name")
            or worst_row.get("scenario_type")
            or "highest-impact scenario"
        ).replace("_", " ")
        scenario_type = str(
            worst_row.get("scenario_type")
            or ""
        ).replace("_", " ")
        horizon = str(
            worst_row.get("horizon")
            or worst_row.get("time_horizon")
            or ""
        ).replace("_", " ")

        scenario_parts = [
            scenario_name
        ]

        if (
            scenario_type
            and scenario_type.casefold()
            != scenario_name.casefold()
        ):
            scenario_parts.append(
                f"({scenario_type})"
            )

        if horizon:
            scenario_parts.append(
                f"— {horizon}"
            )

        scenario_description = " ".join(
            scenario_parts
        )

        add(
            "scenario_impact",
            "Highest scenario impact",
            (
                f"€{worst_value:,.1f}M under "
                f"{scenario_description}"
            ),
            "climate_scenarios",
            "IFRS S2 climate resilience",
            (
                "Highest available revenue-at-risk "
                "or financial-impact estimate, with "
                "the scenario name, type, and horizon "
                "retained for interpretation."
            ),
        )

    fossil_pct = _dynamic_kpi(
        reporting_kpis,
        base_names=[
            "fossil_fuel_exposure_pct",
        ],
        reporting_year=reporting_year,
    )

    if fossil_pct is not None:
        add(
            "fossil_fuel_exposure",
            "Fossil-fuel exposure",
            f"{fossil_pct:,.1f}% of lending",
            "reporting_kpis",
            "IFRS S2 transition risk",
            (
                "Prepared transition-risk exposure "
                "indicator."
            ),
        )

    green_pct = _dynamic_kpi(
        reporting_kpis,
        base_names=[
            "green_loans_pct",
        ],
        reporting_year=reporting_year,
    )

    if green_pct is not None:
        add(
            "green_loan_share",
            "Green-loan share",
            f"{green_pct:,.1f}% of lending",
            "reporting_kpis",
            "IFRS S2 opportunity metrics",
            (
                "Prepared lending-portfolio "
                "classification indicator."
            ),
        )

    equity_rows = _as_rows(
        payload.get(
            "financed_emissions_equity"
        )
    )
    proxy_rows = sum(
        1
        for row in equity_rows
        if (
            row.get(
                "emissions_proxy_used"
            )
            or row.get(
                "attributed_emissions_proxy_tco2e"
            )
            is not None
        )
    )

    if proxy_rows:
        add(
            "equity_proxy",
            "Equity-emissions proxy use",
            (
                f"{proxy_rows} of "
                f"{len(equity_rows)} equity row(s) "
                "use a proxy method"
            ),
            "financed_emissions_equity",
            "PCAF data quality",
            (
                "Proxy use must remain visible when "
                "the result is interpreted."
            ),
        )

    targets = _as_rows(
        payload.get("targets")
    )
    schedule_proxy_count = sum(
        1
        for row in targets
        if row.get(
            "progress_is_schedule_proxy"
        )
    )

    if schedule_proxy_count:
        add(
            "schedule_proxy",
            "Target-progress basis",
            (
                f"{schedule_proxy_count} target(s) "
                "use schedule elapsed rather than "
                "measured achieved progress"
            ),
            "targets",
            "IFRS S2 targets",
            (
                "Schedule elapsed must not be "
                "presented as actual reduction."
            ),
        )

    quality_summary = derived.get(
        "data_quality_summary",
        {},
    )
    estimated = (
        _number(
            quality_summary.get(
                "estimated_economic_pct"
            )
        )
        or 0
    )
    proxy = (
        _number(
            quality_summary.get(
                "proxy_model_pct"
            )
        )
        or 0
    )

    if estimated or proxy:
        add(
            "modeled_data",
            "Estimated or proxy-based data",
            (
                f"{estimated + proxy:,.1f}% of the "
                "reported emissions-data mix"
            ),
            "reporting_kpis.emissions_data_quality_summary",
            "IFRS S2 measurement uncertainty",
            (
                "Calculated from the institution's "
                "prepared data-quality summary."
            ),
        )

    return evidence


def process_payload(
    payload: dict,
) -> dict:
    """
    Build the stable, business-facing bundle returned to Angular.
    """
    physical_by_hazard = (
        build_physical_by_hazard(payload)
    )
    data_quality_register, (
        data_quality_summary
    ) = build_data_quality_register(
        payload
    )

    derived = {
        "physical_by_hazard": (
            physical_by_hazard
        ),
        "data_quality_summary": (
            data_quality_summary
        ),
    }

    bundle = {
        "bank": payload.get("bank", {}),
        "metadata": payload.get(
            "metadata",
            {},
        ),
        "general_requirements_context": (
            payload.get(
                "general_requirements_context",
                {},
            )
        ),
        "reporting_kpis": payload.get(
            "reporting_kpis",
            {},
        ),
        "kpis": build_kpis(payload),
        "intensity_trend": (
            build_intensity_trend(payload)
        ),
        "financed_composition": (
            build_financed_composition(
                payload
            )
        ),
        "risk_matrix": (
            build_risk_matrix(payload)
        ),
        "risk_by_category": (
            build_risk_by_category(payload)
        ),
        "physical_by_hazard": (
            physical_by_hazard
        ),
        "physical_by_country": (
            build_physical_by_country(
                payload
            )
        ),
        "scenarios": (
            build_scenarios(payload)
        ),
        "data_quality_register": (
            data_quality_register
        ),
        "data_quality_summary": (
            data_quality_summary
        ),
        "counterparty_drilldown": (
            build_counterparty_drilldown(
                payload
            )
        ),
    }

    bundle["evidence"] = (
        build_evidence(
            payload,
            derived,
        )
    )

    return bundle
