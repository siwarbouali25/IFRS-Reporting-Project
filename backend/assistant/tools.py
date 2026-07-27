"""
Typed retrieval tools. Each tool reads the structured payload and returns a
uniform envelope containing the exact value(s), provenance for citation, and
any data-gap caveats that apply to the requested fields. The model only ever
phrases answers around these values -- it never sees a raw blob to guess from.

Every tool has a matching JSON schema in TOOL_SCHEMAS (OpenAI tool-calling
format). dispatch() runs a tool by name, injecting the repository and enforcing
the conversation's bank scope.
"""

from __future__ import annotations

from typing import Any, Callable

from .repository import PayloadNotFound, PayloadRepository


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _ok(bank_code: str, data: Any, source: str, **extra: Any) -> dict:
    env = {
        "ok": True,
        "bank_code": bank_code,
        "data": data,
        "provenance": {"bank_code": bank_code, "source": source, **extra},
        "data_gaps": [],
    }
    return env


def _err(msg: str) -> dict:
    return {"ok": False, "error": msg}


def _row_for_year(rows: list[dict], year: int | None) -> dict | None:
    if not rows:
        return None
    if year is None:
        # newest available year
        return max(rows, key=lambda r: r.get("reporting_year", 0))
    for r in rows:
        if r.get("reporting_year") == year:
            return r
    return None


def _gaps_for_fields(payload: dict, fields: set[str]) -> list[dict]:
    gaps = payload.get("metadata", {}).get("data_gaps", []) or []
    out = []
    for g in gaps:
        field = g.get("field", "")
        if any(f in field or field in f for f in fields):
            out.append(
                {
                    "field": field,
                    "reason": g.get("reason", ""),
                    "instruction": g.get("instruction", ""),
                    "affected_years": g.get("affected_years", []),
                }
            )
    return out


# --------------------------------------------------------------------------- #
# tools
# --------------------------------------------------------------------------- #
def list_available_banks(repo: PayloadRepository) -> dict:
    return {"ok": True, "data": repo.available_banks()}


def get_kpi(repo: PayloadRepository, bank_code: str, kpi_key: str | None = None) -> dict:
    payload = repo.get(bank_code)
    kpis = payload.get("reporting_kpis", {})
    if kpi_key:
        if kpi_key not in kpis:
            return _err(
                f"KPI '{kpi_key}' not present for {bank_code}. "
                f"Available keys: {sorted(kpis.keys())}"
            )
        data = {kpi_key: kpis[kpi_key]}
    else:
        data = kpis
    env = _ok(bank_code, data, source="reporting_kpis")
    env["data_gaps"] = _gaps_for_fields(payload, set(data.keys()))
    return env


def get_emissions(
    repo: PayloadRepository,
    bank_code: str,
    scope: str,
    year: int | None = None,
) -> dict:
    payload = repo.get(bank_code)
    scope = scope.lower().strip()

    section_map = {
        "scope1": ("scope1", ["scope1_total_tco2e", "scope1_gas_tco2e", "scope1_fleet_tco2e"]),
        "scope2": ("scope2", ["scope2_location_tco2e", "scope2_market_tco2e"]),
        "scope3": ("scope3_travel", ["scope3_travel_tco2e"]),
        "scope3_travel": ("scope3_travel", ["scope3_travel_tco2e"]),
        "financed": ("financed_emissions", ["financed_em_loans_tco2e", "carbon_intensity_tco2e_per_meur_lending"]),
        "financed_emissions": ("financed_emissions", ["financed_em_loans_tco2e", "carbon_intensity_tco2e_per_meur_lending"]),
    }
    if scope not in section_map:
        return _err(
            f"Unknown scope '{scope}'. Use one of: "
            "scope1, scope2, scope3, financed_emissions."
        )

    key, fields = section_map[scope]
    rows = payload.get(key, [])
    row = _row_for_year(rows, year)
    if row is None:
        return _err(
            f"No {key} data for {bank_code}"
            + (f" in {year}." if year else ".")
        )
    data = {f: row.get(f) for f in fields if f in row}
    data["reporting_year"] = row.get("reporting_year")
    env = _ok(bank_code, data, source=key, reporting_year=row.get("reporting_year"))
    env["data_gaps"] = _gaps_for_fields(payload, set(fields))
    return env


def list_targets(repo: PayloadRepository, bank_code: str) -> dict:
    payload = repo.get(bank_code)
    targets = payload.get("targets", [])
    slim = [
        {
            "target_id": t.get("target_id"),
            "target_type": t.get("target_type"),
            "scope": t.get("scope"),
            "baseline_year": t.get("baseline_year"),
            "baseline_value": t.get("baseline_value"),
            "target_year": t.get("target_year"),
            "target_value_pct_reduction": t.get("target_value_pct_reduction"),
            "target_framework": t.get("target_framework"),
            "status": t.get("status"),
            "gross_or_net": t.get("gross_or_net"),
        }
        for t in targets
    ]
    return _ok(bank_code, slim, source="targets")


def get_financed_emissions_breakdown(
    repo: PayloadRepository,
    bank_code: str,
    dimension: str = "asset_class",
) -> dict:
    payload = repo.get(bank_code)
    holdings = (
        payload.get("financed_emissions_equity", [])
        + payload.get("financed_emissions_sovereign", [])
    )
    if dimension not in {"asset_class", "nace_code", "esg_classification", "country"}:
        return _err(
            "dimension must be one of: asset_class, nace_code, "
            "esg_classification, country."
        )
    agg: dict[str, dict[str, float]] = {}
    for h in holdings:
        bucket = h.get(dimension) or "unknown"
        entry = agg.setdefault(bucket, {"count": 0, "market_value_meur": 0.0})
        entry["count"] += 1
        entry["market_value_meur"] += float(h.get("market_value_meur") or 0.0)
    env = _ok(bank_code, agg, source="financed_emissions_equity+sovereign", dimension=dimension)
    env["data_gaps"] = _gaps_for_fields(payload, {"investments", "counterparty_id"})
    return env


def get_governance(repo: PayloadRepository, bank_code: str) -> dict:
    payload = repo.get(bank_code)
    data = {
        "governance_maturity": payload.get("reporting_kpis", {}).get("governance_maturity", {}),
        "governance": payload.get("governance", {}),
    }
    return _ok(bank_code, data, source="governance")


def get_climate_risks(repo: PayloadRepository, bank_code: str) -> dict:
    payload = repo.get(bank_code)
    data = {
        "climate_risk_register": payload.get("climate_risk_register", []),
        "physical_risk_exposures": payload.get("physical_risk_exposures", []),
        "climate_scenarios": payload.get("climate_scenarios", []),
    }
    return _ok(bank_code, data, source="risk_register+physical+scenarios")


def get_data_gaps(repo: PayloadRepository, bank_code: str) -> dict:
    payload = repo.get(bank_code)
    gaps = payload.get("metadata", {}).get("data_gaps", []) or []
    return _ok(bank_code, gaps, source="metadata.data_gaps")


def compare_banks(
    repo: PayloadRepository,
    metric_key: str,
    bank_codes: list[str] | None = None,
) -> dict:
    banks = bank_codes or [b["bank_code"] for b in repo.available_banks()]
    rows = []
    for code in banks:
        try:
            payload = repo.get(code)
        except PayloadNotFound:
            continue
        value = payload.get("reporting_kpis", {}).get(metric_key)
        rows.append({"bank_code": code, "metric_key": metric_key, "value": value})
    if not rows:
        return _err(f"No banks with metric '{metric_key}' available.")
    return {"ok": True, "data": rows, "provenance": {"source": "reporting_kpis", "metric_key": metric_key}}


def search_report_text(
    repo: PayloadRepository,
    bank_code: str,
    query: str,
) -> dict:
    """
    Narrative retrieval over generated prose. MVP: keyword scan of the latest
    risk-assessment text. Phase 2: replace the scan below with a vector search
    over ReportArtifact final markdown + AssessmentResult, and return chunk ids
    as citations.
    """
    from risk_analysis.models import AssessmentResult

    terms = [t for t in query.lower().split() if len(t) > 3]
    hits = []
    qs = AssessmentResult.objects.filter(
        analysis__bank_id=bank_code
    ).order_by("-created_at")[:5]
    for a in qs:
        text = a.assessment_text or ""
        score = sum(text.lower().count(t) for t in terms)
        if score:
            hits.append(
                {
                    "assessment_id": str(a.id),
                    "score": score,
                    "excerpt": text[:600],
                    "model_used": a.model_used,
                }
            )
    hits.sort(key=lambda h: h["score"], reverse=True)
    return {
        "ok": True,
        "data": hits[:3],
        "provenance": {"bank_code": bank_code, "source": "AssessmentResult"},
    }


# --------------------------------------------------------------------------- #
# registry + schemas
# --------------------------------------------------------------------------- #
REGISTRY: dict[str, Callable[..., dict]] = {
    "list_available_banks": list_available_banks,
    "get_kpi": get_kpi,
    "get_emissions": get_emissions,
    "list_targets": list_targets,
    "get_financed_emissions_breakdown": get_financed_emissions_breakdown,
    "get_governance": get_governance,
    "get_climate_risks": get_climate_risks,
    "get_data_gaps": get_data_gaps,
    "compare_banks": compare_banks,
    "search_report_text": search_report_text,
}

# Tools that take no bank_code (must not be forced into a bank scope).
_UNSCOPED = {"list_available_banks", "compare_banks"}


def _bank_arg() -> dict:
    return {
        "type": "string",
        "description": "Bank code, e.g. 'BANK01'.",
    }


TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "list_available_banks",
            "description": "List the banks the assistant can answer questions about.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_kpi",
            "description": "Get headline reporting KPIs for a bank. Omit kpi_key to get all KPIs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "bank_code": _bank_arg(),
                    "kpi_key": {
                        "type": "string",
                        "description": "Specific KPI key, e.g. 'financed_emissions_2024_tco2e'.",
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
            "description": "Get emissions figures for a scope and year.",
            "parameters": {
                "type": "object",
                "properties": {
                    "bank_code": _bank_arg(),
                    "scope": {
                        "type": "string",
                        "enum": ["scope1", "scope2", "scope3", "financed_emissions"],
                    },
                    "year": {"type": "integer", "description": "Reporting year; omit for latest."},
                },
                "required": ["bank_code", "scope"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_targets",
            "description": "List a bank's climate targets with status and framework.",
            "parameters": {
                "type": "object",
                "properties": {"bank_code": _bank_arg()},
                "required": ["bank_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_financed_emissions_breakdown",
            "description": "Aggregate financed-emissions holdings by a dimension.",
            "parameters": {
                "type": "object",
                "properties": {
                    "bank_code": _bank_arg(),
                    "dimension": {
                        "type": "string",
                        "enum": ["asset_class", "nace_code", "esg_classification", "country"],
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
            "description": "Get governance maturity and structure for a bank.",
            "parameters": {
                "type": "object",
                "properties": {"bank_code": _bank_arg()},
                "required": ["bank_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_climate_risks",
            "description": "Get the climate risk register, physical risk exposures, and scenarios.",
            "parameters": {
                "type": "object",
                "properties": {"bank_code": _bank_arg()},
                "required": ["bank_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_data_gaps",
            "description": "List declared data gaps and their reporting instructions for a bank.",
            "parameters": {
                "type": "object",
                "properties": {"bank_code": _bank_arg()},
                "required": ["bank_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare_banks",
            "description": "Compare one KPI across several banks.",
            "parameters": {
                "type": "object",
                "properties": {
                    "metric_key": {"type": "string", "description": "KPI key from reporting_kpis."},
                    "bank_codes": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Banks to compare; omit for all.",
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
            "description": "Search generated narrative text (risk assessments) for a bank.",
            "parameters": {
                "type": "object",
                "properties": {
                    "bank_code": _bank_arg(),
                    "query": {"type": "string"},
                },
                "required": ["bank_code", "query"],
            },
        },
    },
]


def dispatch(
    name: str,
    arguments: dict,
    repo: PayloadRepository,
    bank_scope: str | None = None,
) -> dict:
    """Run a tool by name. Enforces bank_scope when the conversation is scoped."""
    fn = REGISTRY.get(name)
    if fn is None:
        return _err(f"Unknown tool '{name}'.")

    args = dict(arguments or {})
    if bank_scope and name not in _UNSCOPED:
        # Hard scope: ignore any bank the model tried to pass.
        args["bank_code"] = bank_scope

    try:
        return fn(repo, **args)
    except PayloadNotFound as exc:
        return _err(str(exc))
    except TypeError as exc:
        return _err(f"Bad arguments for {name}: {exc}")
    except Exception as exc:  # defensive: never crash the graph on a tool
        return _err(f"Tool {name} failed: {exc}")
