"""
validators.py — sufficiency / sanity checks run on every upload, BEFORE
process_payload(). These don't block processing (we still try to build a
dashboard from whatever is present) but every warning is surfaced to the
frontend so the analyst sees exactly what's thin or missing, instead of a
chart silently rendering with partial data.
"""

from __future__ import annotations

REQUIRED_TOP_LEVEL = ["bank", "reporting_kpis", "financial_summary"]

RECOMMENDED_TOP_LEVEL = [
    "scope1", "scope2", "financed_emissions", "climate_risk_register",
    "physical_risk_exposures", "climate_scenarios", "targets", "governance",
]


def validate_payload(payload: dict) -> tuple[bool, list[dict]]:
    """
    Returns (is_usable, warnings). is_usable=False only when a required
    section is entirely missing — i.e. we genuinely cannot build a
    dashboard. Everything else is a warning, not a hard failure.
    """
    warnings: list[dict] = []

    if not isinstance(payload, dict):
        return False, [{"level": "error", "message": "Uploaded file is not a JSON object."}]

    missing_required = [k for k in REQUIRED_TOP_LEVEL if not payload.get(k)]
    if missing_required:
        warnings.append({
            "level": "error",
            "message": f"Missing required section(s): {', '.join(missing_required)}. Cannot build a dashboard without these.",
        })
        return False, warnings

    missing_recommended = [k for k in RECOMMENDED_TOP_LEVEL if not payload.get(k)]
    if missing_recommended:
        warnings.append({
            "level": "warning",
            "message": f"Missing or empty section(s): {', '.join(missing_recommended)}. Related charts will be omitted.",
        })

    fin = payload.get("financial_summary", [])
    if isinstance(fin, list) and len(fin) < 2:
        warnings.append({
            "level": "warning",
            "message": "Fewer than 2 years of financial_summary — trend charts will show a single point.",
        })

    risks = payload.get("climate_risk_register", [])
    if isinstance(risks, list):
        missing_rating = sum(1 for r in risks if not r.get("risk_rating"))
        if missing_rating:
            warnings.append({
                "level": "warning",
                "message": f"{missing_rating} of {len(risks)} risk register rows have no risk_rating — excluded from the risk matrix.",
            })

    phys = payload.get("physical_risk_exposures", [])
    if isinstance(phys, list) and phys:
        no_cp = sum(1 for p in phys if not p.get("counterparty_id"))
        if no_cp:
            warnings.append({
                "level": "info",
                "message": f"{no_cp} of {len(phys)} physical risk rows have no counterparty_id and are excluded from the concentration table.",
            })

    gaps = payload.get("metadata", {}).get("data_gaps", []) if isinstance(payload.get("metadata"), dict) else []
    if gaps:
        warnings.append({
            "level": "info",
            "message": f"{len(gaps)} data gap(s) declared in metadata.data_gaps — see the data-quality panel for details.",
        })

    edq = payload.get("reporting_kpis", {}).get("emissions_data_quality_summary") if isinstance(payload.get("reporting_kpis"), dict) else None
    if not edq:
        warnings.append({
            "level": "info",
            "message": "No emissions_data_quality_summary found — the data-quality donut chart will be omitted.",
        })

    if not payload.get("climate_scenarios"):
        warnings.append({
            "level": "warning",
            "message": "No climate_scenarios — scenario revenue-at-risk and sensitivity charts will be omitted.",
        })

    return True, warnings
