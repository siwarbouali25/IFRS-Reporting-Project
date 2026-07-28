"""
Typed retrieval tools for exact structured ESG data.

Tool functions continue to use the historical ``bank_code`` argument name for
backward compatibility, but the value may now be either a real bank name or an
internal code. PayloadRepository resolves it. Every result is enriched with the
real ``bank_name`` so the model and UI can avoid exposing BANK01-style codes.
"""

from __future__ import annotations

from typing import Any, Callable

from .repository import (
    BankNotFound,
    PayloadNotFound,
    PayloadRepository,
)


def _ok(
    bank_identifier: str,
    data: Any,
    source: str,
    **extra: Any,
) -> dict:
    return {
        "ok": True,
        "bank_code": bank_identifier,
        "data": data,
        "provenance": {
            "bank_code": bank_identifier,
            "source": source,
            **extra,
        },
        "data_gaps": [],
    }


def _err(message: str) -> dict:
    return {
        "ok": False,
        "error": message,
    }


def _row_for_year(
    rows: list[dict],
    year: int | None,
) -> dict | None:
    if not rows:
        return None

    if year is None:
        return max(
            rows,
            key=lambda row: row.get(
                "reporting_year",
                0,
            ),
        )

    for row in rows:
        if (
            row.get("reporting_year")
            == year
        ):
            return row

    return None


def _gaps_for_fields(
    payload: dict,
    fields: set[str],
) -> list[dict]:
    gaps = (
        payload.get("metadata", {})
        .get("data_gaps", [])
        or []
    )
    output = []

    for gap in gaps:
        field = gap.get("field", "")

        if any(
            requested in field
            or field in requested
            for requested in fields
        ):
            output.append(
                {
                    "field": field,
                    "reason": gap.get(
                        "reason",
                        "",
                    ),
                    "instruction": gap.get(
                        "instruction",
                        "",
                    ),
                    "affected_years": gap.get(
                        "affected_years",
                        [],
                    ),
                }
            )

    return output


def list_available_banks(
    repo: PayloadRepository,
) -> dict:
    return {
        "ok": True,
        "data": repo.available_banks(),
        "provenance": {
            "source": "organizations.Bank",
        },
    }


def get_kpi(
    repo: PayloadRepository,
    bank_code: str,
    kpi_key: str | None = None,
) -> dict:
    payload = repo.get(bank_code)
    kpis = payload.get(
        "reporting_kpis",
        {},
    )

    if kpi_key:
        if kpi_key not in kpis:
            return _err(
                f"KPI '{kpi_key}' is not present. "
                f"Available keys: "
                f"{sorted(kpis.keys())}"
            )
        data = {
            kpi_key: kpis[kpi_key]
        }
    else:
        data = kpis

    result = _ok(
        bank_code,
        data,
        source="reporting_kpis",
    )
    result["data_gaps"] = (
        _gaps_for_fields(
            payload,
            set(data.keys()),
        )
    )
    return result


def get_emissions(
    repo: PayloadRepository,
    bank_code: str,
    scope: str,
    year: int | None = None,
) -> dict:
    payload = repo.get(bank_code)
    scope = scope.lower().strip()

    section_map = {
        "scope1": (
            "scope1",
            [
                "scope1_total_tco2e",
                "scope1_gas_tco2e",
                "scope1_fleet_tco2e",
            ],
        ),
        "scope2": (
            "scope2",
            [
                "scope2_location_tco2e",
                "scope2_market_tco2e",
            ],
        ),
        "scope3": (
            "scope3_travel",
            ["scope3_travel_tco2e"],
        ),
        "scope3_travel": (
            "scope3_travel",
            ["scope3_travel_tco2e"],
        ),
        "financed": (
            "financed_emissions",
            [
                "financed_em_loans_tco2e",
                "carbon_intensity_tco2e_per_meur_lending",
            ],
        ),
        "financed_emissions": (
            "financed_emissions",
            [
                "financed_em_loans_tco2e",
                "carbon_intensity_tco2e_per_meur_lending",
            ],
        ),
    }

    if scope not in section_map:
        return _err(
            f"Unknown scope '{scope}'. Use "
            "scope1, scope2, scope3, or "
            "financed_emissions."
        )

    section_key, fields = (
        section_map[scope]
    )
    rows = payload.get(
        section_key,
        [],
    )
    row = _row_for_year(
        rows,
        year,
    )

    if row is None:
        bank_name = repo.resolve_bank(
            bank_code
        ).name
        return _err(
            f"No {section_key} data is "
            f"available for {bank_name}"
            + (
                f" in {year}."
                if year is not None
                else "."
            )
        )

    data = {
        field: row.get(field)
        for field in fields
        if field in row
    }
    data["reporting_year"] = (
        row.get("reporting_year")
    )

    result = _ok(
        bank_code,
        data,
        source=section_key,
        reporting_year=row.get(
            "reporting_year"
        ),
    )
    result["data_gaps"] = (
        _gaps_for_fields(
            payload,
            set(fields),
        )
    )
    return result


def list_targets(
    repo: PayloadRepository,
    bank_code: str,
) -> dict:
    payload = repo.get(bank_code)
    targets = payload.get(
        "targets",
        [],
    )

    data = [
        {
            "target_id": target.get(
                "target_id"
            ),
            "target_type": target.get(
                "target_type"
            ),
            "scope": target.get(
                "scope"
            ),
            "baseline_year": target.get(
                "baseline_year"
            ),
            "baseline_value": target.get(
                "baseline_value"
            ),
            "target_year": target.get(
                "target_year"
            ),
            "target_value_pct_reduction": (
                target.get(
                    "target_value_pct_reduction"
                )
            ),
            "target_framework": target.get(
                "target_framework"
            ),
            "status": target.get(
                "status"
            ),
            "gross_or_net": target.get(
                "gross_or_net"
            ),
        }
        for target in targets
    ]

    return _ok(
        bank_code,
        data,
        source="targets",
    )


def get_financed_emissions_breakdown(
    repo: PayloadRepository,
    bank_code: str,
    dimension: str = "asset_class",
) -> dict:
    payload = repo.get(bank_code)
    holdings = (
        payload.get(
            "financed_emissions_equity",
            [],
        )
        + payload.get(
            "financed_emissions_sovereign",
            [],
        )
    )

    allowed_dimensions = {
        "asset_class",
        "nace_code",
        "esg_classification",
        "country",
    }

    if dimension not in allowed_dimensions:
        return _err(
            "dimension must be one of: "
            + ", ".join(
                sorted(allowed_dimensions)
            )
        )

    aggregation: dict[
        str,
        dict[str, float],
    ] = {}

    for holding in holdings:
        bucket = (
            holding.get(dimension)
            or "unknown"
        )
        entry = aggregation.setdefault(
            bucket,
            {
                "count": 0,
                "market_value_meur": 0.0,
            },
        )
        entry["count"] += 1
        entry["market_value_meur"] += float(
            holding.get(
                "market_value_meur"
            )
            or 0.0
        )

    result = _ok(
        bank_code,
        aggregation,
        source=(
            "financed_emissions_equity"
            "+sovereign"
        ),
        dimension=dimension,
    )
    result["data_gaps"] = (
        _gaps_for_fields(
            payload,
            {
                "investments",
                "counterparty_id",
            },
        )
    )
    return result


def get_governance(
    repo: PayloadRepository,
    bank_code: str,
) -> dict:
    payload = repo.get(bank_code)
    data = {
        "governance_maturity": (
            payload.get(
                "reporting_kpis",
                {},
            ).get(
                "governance_maturity",
                {},
            )
        ),
        "governance": payload.get(
            "governance",
            {},
        ),
    }

    return _ok(
        bank_code,
        data,
        source="governance",
    )


def get_climate_risks(
    repo: PayloadRepository,
    bank_code: str,
) -> dict:
    payload = repo.get(bank_code)
    data = {
        "climate_risk_register": (
            payload.get(
                "climate_risk_register",
                [],
            )
        ),
        "physical_risk_exposures": (
            payload.get(
                "physical_risk_exposures",
                [],
            )
        ),
        "climate_scenarios": (
            payload.get(
                "climate_scenarios",
                [],
            )
        ),
    }

    return _ok(
        bank_code,
        data,
        source=(
            "risk_register+physical+scenarios"
        ),
    )


def get_data_gaps(
    repo: PayloadRepository,
    bank_code: str,
) -> dict:
    payload = repo.get(bank_code)
    gaps = (
        payload.get("metadata", {})
        .get("data_gaps", [])
        or []
    )

    return _ok(
        bank_code,
        gaps,
        source="metadata.data_gaps",
    )


def compare_banks(
    repo: PayloadRepository,
    metric_key: str,
    bank_codes: list[str] | None = None,
) -> dict:
    requested = (
        bank_codes
        or [
            bank["bank_name"]
            for bank in (
                repo.available_banks()
            )
        ]
    )
    rows = []

    for identifier in requested:
        try:
            identity = repo.resolve_bank(
                identifier
            )
            payload = repo.get(
                identity.code
            )
        except (
            BankNotFound,
            PayloadNotFound,
        ):
            continue

        value = payload.get(
            "reporting_kpis",
            {},
        ).get(metric_key)

        rows.append(
            {
                "bank_name": identity.name,
                "bank_code": identity.code,
                "metric_key": metric_key,
                "value": value,
            }
        )

    if not rows:
        return _err(
            f"No banks with metric "
            f"'{metric_key}' are available."
        )

    return {
        "ok": True,
        "data": rows,
        "provenance": {
            "source": "reporting_kpis",
            "metric_key": metric_key,
        },
    }


def search_report_text(
    repo: PayloadRepository,
    bank_code: str,
    query: str,
) -> dict:
    from risk_analysis.models import (
        AssessmentResult,
    )

    identity = repo.resolve_bank(
        bank_code
    )
    terms = [
        term
        for term in query.lower().split()
        if len(term) > 3
    ]
    hits = []

    queryset = AssessmentResult.objects.filter(
        analysis__bank_id=identity.code
    ).order_by("-created_at")[:5]

    for assessment in queryset:
        text = (
            assessment.assessment_text
            or ""
        )
        score = sum(
            text.lower().count(term)
            for term in terms
        )

        if score:
            hits.append(
                {
                    "assessment_id": str(
                        assessment.id
                    ),
                    "score": score,
                    "excerpt": text[:600],
                    "model_used": (
                        assessment.model_used
                    ),
                }
            )

    hits.sort(
        key=lambda hit: hit["score"],
        reverse=True,
    )

    return {
        "ok": True,
        "data": hits[:3],
        "bank_name": identity.name,
        "bank_code": identity.code,
        "provenance": {
            "bank_name": identity.name,
            "bank_code": identity.code,
            "source": "AssessmentResult",
        },
    }


REGISTRY: dict[
    str,
    Callable[..., dict],
] = {
    "list_available_banks": (
        list_available_banks
    ),
    "get_kpi": get_kpi,
    "get_emissions": get_emissions,
    "list_targets": list_targets,
    "get_financed_emissions_breakdown": (
        get_financed_emissions_breakdown
    ),
    "get_governance": get_governance,
    "get_climate_risks": (
        get_climate_risks
    ),
    "get_data_gaps": get_data_gaps,
    "compare_banks": compare_banks,
    "search_report_text": (
        search_report_text
    ),
}

_UNSCOPED = {
    "list_available_banks",
    "compare_banks",
}


def _bank_arg() -> dict:
    return {
        "type": "string",
        "description": (
            "Real bank name, for example "
            "'Eurolux Universal Bank AG'. "
            "An internal bank code is also "
            "accepted for compatibility, but "
            "prefer the bank name."
        ),
    }


TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "list_available_banks",
            "description": (
                "List available banks using "
                "their real names."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_kpi",
            "description": (
                "Get headline reporting KPIs "
                "for a bank."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "bank_code": _bank_arg(),
                    "kpi_key": {
                        "type": "string",
                        "description": (
                            "Specific KPI key; "
                            "omit to get all KPIs."
                        ),
                    },
                },
                "required": ["bank_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_emissions",
            "description": (
                "Get exact emissions figures "
                "for a bank, scope, and year."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "bank_code": _bank_arg(),
                    "scope": {
                        "type": "string",
                        "enum": [
                            "scope1",
                            "scope2",
                            "scope3",
                            "financed_emissions",
                        ],
                    },
                    "year": {
                        "type": "integer",
                        "description": (
                            "Reporting year; "
                            "omit for latest."
                        ),
                    },
                },
                "required": [
                    "bank_code",
                    "scope",
                ],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_targets",
            "description": (
                "List a bank's climate "
                "targets and statuses."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "bank_code": _bank_arg(),
                },
                "required": ["bank_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": (
                "get_financed_emissions_breakdown"
            ),
            "description": (
                "Aggregate financed-emissions "
                "holdings by a dimension."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "bank_code": _bank_arg(),
                    "dimension": {
                        "type": "string",
                        "enum": [
                            "asset_class",
                            "nace_code",
                            "esg_classification",
                            "country",
                        ],
                    },
                },
                "required": ["bank_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_governance",
            "description": (
                "Get governance maturity and "
                "structure for a bank."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "bank_code": _bank_arg(),
                },
                "required": ["bank_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_climate_risks",
            "description": (
                "Get the climate risk register, "
                "physical exposures, and scenarios."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "bank_code": _bank_arg(),
                },
                "required": ["bank_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_data_gaps",
            "description": (
                "List declared data gaps and "
                "their reporting instructions."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "bank_code": _bank_arg(),
                },
                "required": ["bank_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare_banks",
            "description": (
                "Compare one KPI across banks, "
                "using real bank names."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "metric_key": {
                        "type": "string",
                    },
                    "bank_codes": {
                        "type": "array",
                        "items": {
                            "type": "string"
                        },
                        "description": (
                            "Real bank names to "
                            "compare; omit for all."
                        ),
                    },
                },
                "required": ["metric_key"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_report_text",
            "description": (
                "Search generated narrative "
                "text for a bank."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "bank_code": _bank_arg(),
                    "query": {
                        "type": "string"
                    },
                },
                "required": [
                    "bank_code",
                    "query",
                ],
            },
        },
    },
]


def _enrich_bank_identity(
    result: dict,
    repo: PayloadRepository,
    identifier: str | None,
) -> dict:
    if (
        not result.get("ok")
        or not identifier
    ):
        return result

    identity = repo.resolve_bank(
        identifier
    )
    result["bank_code"] = identity.code
    result["bank_name"] = identity.name

    provenance = result.get(
        "provenance"
    )

    if isinstance(provenance, dict):
        provenance["bank_code"] = (
            identity.code
        )
        provenance["bank_name"] = (
            identity.name
        )

    return result


def dispatch(
    name: str,
    arguments: dict,
    repo: PayloadRepository,
    bank_scope: str | None = None,
) -> dict:
    """
    Run a tool, enforce conversation scope, accept bank names, and enrich the
    result with the bank's real name.
    """

    function = REGISTRY.get(name)

    if function is None:
        return _err(
            f"Unknown tool '{name}'."
        )

    args = dict(arguments or {})

    if (
        bank_scope
        and name not in _UNSCOPED
    ):
        args["bank_code"] = bank_scope

    identifier = args.get("bank_code")

    try:
        result = function(
            repo,
            **args,
        )

        if (
            name not in _UNSCOPED
            and identifier
        ):
            result = _enrich_bank_identity(
                result,
                repo,
                identifier,
            )

        return result

    except (
        BankNotFound,
        PayloadNotFound,
    ) as exc:
        return _err(str(exc))

    except TypeError as exc:
        return _err(
            f"Bad arguments for {name}: "
            f"{exc}"
        )

    except Exception as exc:
        return _err(
            f"Tool {name} failed: {exc}"
        )
