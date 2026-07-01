"""
services.py — turns an uploaded reporting payload into everything the
dashboard needs: KPI cards, chart series, an evidence catalogue, and the
data-quality / peer-benchmark / scenario-sensitivity augmentation.

Design intent: nothing here is specific to BANK01, 2024, or any fixed set of
risk categories/hazard types/scenario names. Every function reads the shape
and values of whatever payload is uploaded. If a bank uploads 5 years of
history instead of 3, or 40 risks instead of 16, this still works — the
charts and KPIs are built from list comprehensions and groupbys over
whatever rows are present, not from indices or fixed-length assumptions.

If a section is missing or a key is absent, the corresponding chart/KPI is
simply omitted and a validation warning is recorded separately (see
validators.py). We do not synthesize required reporting fields here; we only
ADD clearly-labeled supplementary context (peer benchmark, sensitivity
bands, a data-quality rollup) on top of what exists.
"""

from __future__ import annotations

import random
import statistics
from collections import defaultdict


def _last(seq, key_year="reporting_year"):
    if not seq:
        return None
    return sorted(seq, key=lambda r: r.get(key_year, 0))[-1]


def _safe_div(a, b, default=None):
    try:
        if b in (0, None) or a is None:
            return default
        return a / b
    except (TypeError, ZeroDivisionError):
        return default


def _round(v, nd=2):
    return round(v, nd) if isinstance(v, (int, float)) else v


def _num(v, default=0):
    """Coalesce None (declared data gaps use null) to a numeric default."""
    return v if isinstance(v, (int, float)) else default



# ---------------------------------------------------------------------------
# KPI cards
# ---------------------------------------------------------------------------
def build_kpis(P):
    kpis = []
    k = P.get("reporting_kpis", {})
    fin = sorted(P.get("financial_summary", []), key=lambda r: r.get("reporting_year", 0))
    fe = sorted(P.get("financed_emissions", []), key=lambda r: r.get("reporting_year", 0))
    risks = P.get("climate_risk_register", [])
    phys = P.get("physical_risk_exposures", [])
    scenarios = P.get("climate_scenarios", [])
    bank = P.get("bank", {})

    if fe:
        fe_first, fe_last = fe[0], fe[-1]
        delta_pct = _safe_div(
            (fe_last.get("financed_em_loans_tco2e", 0) - fe_first.get("financed_em_loans_tco2e", 0)),
            fe_first.get("financed_em_loans_tco2e", 0),
        )
        kpis.append({
            "title": f"Financed emissions {fe_last.get('reporting_year', '')}",
            "value": _round(fe_last.get("financed_em_loans_tco2e", 0) / 1e6, 1),
            "suffix": "Mt CO\u2082e",
            "change": f"{delta_pct*100:+.1f}% vs {fe_first.get('reporting_year', '')}" if delta_pct is not None else "n/a",
            "cls": "up" if (delta_pct or 0) < 0 else "down",
        })

    intensity = k.get("carbon_intensity_2024_tco2e_per_meur") or (fin[-1].get("carbon_intensity_tco2e_per_meur_lending") if fin else None)
    if intensity is not None:
        target = bank.get("target_intensity_tco2e_per_meur")
        kpis.append({
            "title": "Carbon intensity",
            "value": _round(intensity, 0),
            "suffix": "t/M\u20ac",
            "change": f"target {target} t/M\u20ac" if target is not None else "no target set",
            "cls": "down",
        })

    if risks:
        crit = sum(1 for r in risks if r.get("risk_rating") == "critical")
        high = sum(1 for r in risks if r.get("risk_rating") == "high")
        kpis.append({
            "title": "Critical / high risks",
            "value": crit,
            "suffix": f"+{high} high",
            "change": f"{len(risks)} in register",
            "cls": "down",
        })

    if phys:
        high_phys = [p for p in phys if p.get("high_risk_flag")]
        kpis.append({
            "title": "Physical high-risk exposure",
            "value": _round(sum(_num(p.get("exposure_amount_meur")) for p in high_phys), 0),
            "suffix": "M\u20ac",
            "change": f"{len(high_phys)} of {len(phys)} counterparties",
            "cls": "down",
        })

    if scenarios:
        worst = max((s.get("revenue_at_risk_meur", 0) for s in scenarios), default=0)
        kpis.append({
            "title": "Worst-case revenue at risk",
            "value": _round(worst, 0),
            "suffix": "M\u20ac",
            "change": f"{bank.get('cet1_ratio_pct', '?')}% CET1 buffer" if bank.get("cet1_ratio_pct") else "n/a",
            "cls": "flat",
        })

    return kpis


# ---------------------------------------------------------------------------
# Chart series
# ---------------------------------------------------------------------------
def build_intensity_trend(P):
    fin = sorted(P.get("financial_summary", []), key=lambda r: r.get("reporting_year", 0))
    targets = P.get("targets", [])
    tgt = next((t for t in targets if t.get("metric") == "tco2e_per_meur_lending"), None)
    milestones = {m["year"]: m["value"] for m in (tgt.get("milestones_parsed") or [])} if tgt else {}

    rows = [
        {
            "year": str(r["reporting_year"]),
            "actual": r.get("carbon_intensity_tco2e_per_meur_lending"),
            "target": tgt["baseline_value"] if tgt and r["reporting_year"] == tgt.get("baseline_year") else None,
        }
        for r in fin
    ]
    rows += [{"year": str(y), "actual": None, "target": v} for y, v in sorted(milestones.items())]
    return rows


def build_op_emissions(P):
    s1 = {r["reporting_year"]: r for r in P.get("scope1", [])}
    s2 = {r["reporting_year"]: r for r in P.get("scope2", [])}
    s3 = {r["reporting_year"]: r for r in P.get("scope3_travel", [])}
    years = sorted(set(s1) | set(s2) | set(s3))
    return [
        {
            "year": str(y),
            "Scope 1": s1.get(y, {}).get("scope1_total_tco2e", 0),
            "Scope 2 (market)": s2.get(y, {}).get("scope2_market_tco2e", 0),
            "Scope 3 travel": s3.get(y, {}).get("scope3_travel_tco2e", 0),
        }
        for y in years
    ]


def build_financed_composition(P):
    fe = _last(P.get("financed_emissions", []))
    eq_sum = sum((r.get("attributed_emissions_proxy_tco2e") or 0) for r in P.get("financed_emissions_equity", []))
    sov_sum = sum((r.get("attributed_emissions_tco2e") or 0) for r in P.get("financed_emissions_sovereign", []))
    out = []
    if fe:
        out.append({"name": "Corporate loans", "value": fe.get("financed_em_loans_tco2e", 0), "proxy": False})
    if P.get("financed_emissions_sovereign"):
        out.append({"name": "Sovereign bonds", "value": sov_sum, "proxy": False})
    if P.get("financed_emissions_equity"):
        out.append({"name": "Listed equity (proxy)", "value": eq_sum, "proxy": True})
    return out


def build_risk_matrix(P):
    return [
        {
            "x": r.get("likelihood_score"), "y": r.get("severity_score"),
            "z": r.get("financial_impact_meur", 0), "name": r.get("risk_name"),
            "rating": r.get("risk_rating"), "id": r.get("risk_id"),
            "horizon": r.get("time_horizon"), "ifrs": r.get("ifrs_s2_para_evidence"),
        }
        for r in P.get("climate_risk_register", [])
    ]


def build_risk_by_category(P):
    cat = {}
    for r in P.get("climate_risk_register", []):
        c = r.get("risk_category", "unknown")
        cat.setdefault(c, {"name": c.replace("_", " ")})
        rating = r.get("risk_rating", "unrated")
        cat[c][rating] = cat[c].get(rating, 0) + 1
    rows = list(cat.values())
    for row in rows:
        row["total"] = sum(v for k, v in row.items() if k != "name" and isinstance(v, (int, float)))
    rows.sort(key=lambda r: -r["total"])
    return rows


def build_physical_by_hazard(P):
    hz = {}
    for p in P.get("physical_risk_exposures", []):
        h = p.get("hazard_type", "unknown")
        hz.setdefault(h, {"hazard": h.replace("_", " "), "exposure": 0.0, "count": 0, "high": 0})
        hz[h]["exposure"] += _num(p.get("exposure_amount_meur"))
        hz[h]["count"] += 1
        if p.get("high_risk_flag"):
            hz[h]["high"] += 1
    rows = sorted(hz.values(), key=lambda r: -r["exposure"])
    for r in rows:
        r["exposure"] = _round(r["exposure"], 1)
    return rows


def build_scenarios(P):
    horizon_order = {"short_term": 0, "medium_term": 1, "long_term": 2}
    by_h = {}
    for s in P.get("climate_scenarios", []):
        h = s.get("horizon", "unknown")
        by_h.setdefault(h, {"horizon": h.replace("_", " ")})
        by_h[h][s.get("scenario_type", "unknown")] = s.get("revenue_at_risk_meur")
    rows = list(by_h.values())
    rows.sort(key=lambda r: horizon_order.get(r["horizon"].replace(" ", "_"), 99))
    return rows


# ---------------------------------------------------------------------------
# Augmentation: data quality / assurance register
# ---------------------------------------------------------------------------
def build_data_quality_register(P):
    gov = _last(P.get("governance", [])) or {}
    edq = P.get("reporting_kpis", {}).get("emissions_data_quality_summary", {})
    fe = _last(P.get("financed_emissions", [])) or {}

    def is_synth(section_name):
        rows = P.get(section_name, [])
        return bool(rows) and all(r.get("is_synthetic") for r in rows if isinstance(r, dict))

    register = []

    if P.get("scope1") or P.get("scope2"):
        register.append({
            "domain": "scope1_scope2", "label": "Scope 1 & 2 operational emissions",
            "assurance_level": gov.get("external_assurance", "unknown"),
            "assurance_provider": gov.get("assurance_provider"),
            "assurance_standard": gov.get("assurance_standard"),
            "is_synthetic": False, "confidence": "high" if gov.get("external_assurance") else "medium",
            "note": "Operational emissions; check governance.assurance_scope for exact coverage.",
        })

    if P.get("scope3_travel"):
        register.append({
            "domain": "scope3_travel", "label": "Scope 3 business travel",
            "assurance_level": "none", "assurance_provider": None, "assurance_standard": None,
            "is_synthetic": False, "confidence": "medium",
            "note": "Typically unassured unless governance states otherwise.",
        })

    if P.get("scope3_categories"):
        register.append({
            "domain": "scope3_categories", "label": "Scope 3 value-chain categories",
            "assurance_level": "none", "assurance_provider": None, "assurance_standard": None,
            "is_synthetic": is_synth("scope3_categories"), "confidence": "low",
            "note": "Spend-based/estimated category emissions carry inherently higher uncertainty.",
        })

    if P.get("financed_emissions"):
        register.append({
            "domain": "financed_emissions_loans", "label": "Financed emissions \u2014 corporate loans",
            "assurance_level": "none", "assurance_provider": None, "assurance_standard": None,
            "is_synthetic": False, "confidence": "medium",
            "note": "Usually the largest single line; verify if it carries any assurance.",
        })

    if P.get("financed_emissions_equity"):
        register.append({
            "domain": "financed_emissions_equity", "label": "Financed emissions \u2014 listed equity",
            "assurance_level": "none", "assurance_provider": None, "assurance_standard": None,
            "is_synthetic": False, "confidence": "low",
            "note": "Check emissions_proxy_used / proxy_confidence fields on each row.",
        })

    if P.get("financed_emissions_sovereign"):
        gap_n = sum(1 for r in P["financed_emissions_sovereign"] if r.get("data_gap_flag"))
        register.append({
            "domain": "financed_emissions_sovereign", "label": "Financed emissions \u2014 sovereign bonds",
            "assurance_level": "none", "assurance_provider": None, "assurance_standard": None,
            "is_synthetic": False, "confidence": "medium",
            "note": f"{gap_n} of {len(P['financed_emissions_sovereign'])} sovereign rows flagged with a data gap.",
        })

    if P.get("physical_risk_exposures"):
        register.append({
            "domain": "physical_risk_exposures", "label": "Physical risk exposures",
            "assurance_level": "none", "assurance_provider": None, "assurance_standard": None,
            "is_synthetic": False, "confidence": "medium",
            "note": "External hazard source data; financial-impact translation is modelled.",
        })

    if P.get("climate_financial_effects"):
        register.append({
            "domain": "climate_financial_effects", "label": "Financial-statement climate effects",
            "assurance_level": "none", "assurance_provider": None, "assurance_standard": None,
            "is_synthetic": is_synth("climate_financial_effects"), "confidence": "low",
            "note": "Balance-sheet/P&L linkage; verify against filed accounts before external use.",
        })

    summary = {
        "audited_report_pct": edq.get("audited_report"),
        "cdp_disclosure_pct": edq.get("cdp_disclosure"),
        "estimated_economic_pct": edq.get("estimated_economic"),
        "proxy_model_pct": edq.get("proxy_model"),
    }
    if all(v is not None for v in summary.values()):
        modeled = round(summary["estimated_economic_pct"] + summary["proxy_model_pct"], 1)
        summary["interpretation"] = (
            f"{summary['audited_report_pct']}% of group emissions data traces to an audited "
            f"report; ~{modeled}% is modelled or proxy-based."
        )
    return register, summary


# ---------------------------------------------------------------------------
# Augmentation: synthetic peer benchmark
# ---------------------------------------------------------------------------
def build_peer_benchmark(P, seed=None):
    k = P.get("reporting_kpis", {})
    bank = P.get("bank", {})
    own_intensity = k.get("carbon_intensity_2024_tco2e_per_meur")
    if own_intensity is None:
        return None

    rng = random.Random(seed if seed is not None else bank.get("bank_id", "seed"))

    def jitter(val, lo, hi):
        return round(val * rng.uniform(lo, hi), 2) if val is not None else None

    own = {
        "peer_name": bank.get("bank_name", "This bank"), "is_synthetic": False,
        "carbon_intensity_tco2e_per_meur": own_intensity,
        "green_loans_pct": k.get("green_loans_pct_2024"),
        "fossil_fuel_exposure_pct": k.get("fossil_fuel_exposure_pct"),
        "high_carbon_sector_exposure_pct": k.get("high_carbon_sector_exposure_pct"),
    }

    archetype = bank.get("archetype", "bank").replace("_", " ")
    peers = []
    for label in ["Peer A", "Peer B", "Peer C"]:
        peers.append({
            "peer_name": f"{label} ({archetype})", "is_synthetic": True,
            "source": "synthetic_estimate \u2014 no real disclosure; illustrative only",
            "carbon_intensity_tco2e_per_meur": jitter(own_intensity, 0.65, 1.15),
            "green_loans_pct": jitter(own["green_loans_pct"], 0.7, 1.6),
            "fossil_fuel_exposure_pct": jitter(own["fossil_fuel_exposure_pct"], 0.6, 1.2),
            "high_carbon_sector_exposure_pct": jitter(own["high_carbon_sector_exposure_pct"], 0.6, 1.2),
        })

    def avg(field):
        vals = [p[field] for p in peers if p[field] is not None]
        return round(statistics.mean(vals), 2) if vals else None

    sector_avg = {
        "peer_name": f"Sector average ({archetype})", "is_synthetic": True,
        "source": "synthetic_estimate \u2014 illustrative midpoint, not an official benchmark",
        "carbon_intensity_tco2e_per_meur": avg("carbon_intensity_tco2e_per_meur"),
        "green_loans_pct": avg("green_loans_pct"),
        "fossil_fuel_exposure_pct": avg("fossil_fuel_exposure_pct"),
        "high_carbon_sector_exposure_pct": avg("high_carbon_sector_exposure_pct"),
    }

    return {
        "bank_own": own, "peers": peers, "sector_average": sector_avg,
        "disclaimer": (
            "Peer and sector figures are SYNTHETIC, generated for relative-positioning "
            "illustration only. They are not sourced from any peer bank's actual disclosure "
            "and must not be cited as real benchmark data in any external-facing report."
        ),
    }


# ---------------------------------------------------------------------------
# Augmentation: counterparty concentration (real data where available)
# ---------------------------------------------------------------------------
def build_counterparty_drilldown(P, top_n=20):
    phys = P.get("physical_risk_exposures", [])
    by_cp = defaultdict(lambda: {
        "exposure_meur": 0.0, "financial_impact_meur": 0.0,
        "hazard_types": set(), "country": None, "high_risk_count": 0, "n_exposures": 0,
    })
    for p in phys:
        cid = p.get("counterparty_id")
        if not cid:
            continue
        c = by_cp[cid]
        c["exposure_meur"] += _num(p.get("exposure_amount_meur"))
        c["financial_impact_meur"] += _num(p.get("financial_impact_meur"))
        c["hazard_types"].add(p.get("hazard_type", "unknown"))
        c["country"] = p.get("country")
        c["high_risk_count"] += 1 if p.get("high_risk_flag") else 0
        c["n_exposures"] += 1

    top = sorted(
        [
            {
                "counterparty_id": cid, "country": v["country"],
                "exposure_meur": _round(v["exposure_meur"]), "financial_impact_meur": _round(v["financial_impact_meur"]),
                "hazard_types": sorted(v["hazard_types"]), "high_risk_count": v["high_risk_count"],
                "n_exposures": v["n_exposures"], "is_synthetic": False,
            }
            for cid, v in by_cp.items()
        ],
        key=lambda r: -r["exposure_meur"],
    )[:top_n]

    equity_rows = P.get("financed_emissions_equity", [])
    equity_has_real_cp = any(r.get("counterparty_id") for r in equity_rows)
    equity_map = []
    if equity_rows and not equity_has_real_cp:
        for i, r in enumerate(equity_rows):
            equity_map.append({
                "investment_id": r.get("investment_id"), "issuer_name": r.get("issuer_name"),
                "nace_code": r.get("nace_code"), "country": r.get("country"),
                "market_value_meur": r.get("market_value_meur"),
                "attributed_emissions_proxy_tco2e": r.get("attributed_emissions_proxy_tco2e"),
                "pcaf_data_quality_score": r.get("pcaf_data_quality_score"),
                "synthetic_counterparty_id": f"SYN-CP-{i+1:03d}",
                "counterparty_id_is_synthetic": True,
                "note": "counterparty_id is null in source data for this row \u2014 placeholder for drill-down UX only.",
            })

    return {
        "physical_risk_top_by_exposure": top,
        "physical_risk_basis": "real counterparty_id from source data",
        "equity_synthetic_counterparty_map": equity_map,
        "equity_has_real_counterparty_id": equity_has_real_cp,
    }


# ---------------------------------------------------------------------------
# Augmentation: scenario sensitivity band
# ---------------------------------------------------------------------------
def build_scenario_sensitivity(P, band_pct=0.15):
    scenarios = P.get("climate_scenarios", [])
    if not scenarios:
        return []
    by_h = {}
    for s in scenarios:
        base = s.get("revenue_at_risk_meur")
        if base is None:
            continue
        h = s.get("horizon", "unknown").replace("_", " ")
        by_h.setdefault(h, {"horizon": h, "low": 0.0, "mid": 0.0, "high": 0.0, "n": 0})
        by_h[h]["low"] += base * (1 - band_pct)
        by_h[h]["mid"] += base
        by_h[h]["high"] += base * (1 + band_pct)
        by_h[h]["n"] += 1
    out = []
    for row in by_h.values():
        n = row.pop("n") or 1
        out.append({
            "horizon": row["horizon"],
            "low": round(row["low"] / n, 0), "mid": round(row["mid"] / n, 0), "high": round(row["high"] / n, 0),
        })
    return out


# ---------------------------------------------------------------------------
# Evidence catalogue — the fixed set of citable, sourced facts the LLM may
# reference. Built dynamically; an item is only included if its underlying
# data is present in the upload.
# ---------------------------------------------------------------------------
def build_evidence(P, derived):
    ev = []
    k = P.get("reporting_kpis", {})
    bank = P.get("bank", {})
    fe = _last(P.get("financed_emissions", []))
    risks = P.get("climate_risk_register", [])
    phys_by_hazard = derived.get("phys_by_hazard", [])
    scenarios = P.get("climate_scenarios", [])
    targets = P.get("targets", [])
    fin = sorted(P.get("financial_summary", []), key=lambda r: r.get("reporting_year", 0))
    dq_summary = derived.get("dq_summary", {})
    dq_register = derived.get("dq_register", [])
    peer = derived.get("peer_benchmark")

    def add(eid, label, value, source, ifrs, detail):
        ev.append({"id": eid, "label": label, "value": value, "source": source, "ifrs": ifrs, "detail": detail})

    if k.get("carbon_intensity_2024_tco2e_per_meur") is not None and bank.get("target_intensity_tco2e_per_meur"):
        ratio = k["carbon_intensity_2024_tco2e_per_meur"] / bank["target_intensity_tco2e_per_meur"]
        add("E1", "Carbon intensity vs target",
            f"{k['carbon_intensity_2024_tco2e_per_meur']:.0f} t/M\u20ac \u2014 {ratio:.1f}\u00d7 the {bank['target_intensity_tco2e_per_meur']} t/M\u20ac target",
            "financial_summary", "IFRS S2 \u00a729(a)",
            "Lending-book carbon intensity is usually the dominant exposure relative to the stated target.")

    if fe:
        add("E2", "Financed emissions", f"{fe.get('financed_em_loans_tco2e', 0)/1e6:.1f} Mt CO\u2082e (Scope 3 Cat.15)",
            "financed_emissions", "IFRS S2 \u00a729(g)", "Usually the dominant share of the group footprint.")

    if risks:
        crit = sum(1 for r in risks if r.get("risk_rating") == "critical")
        high = sum(1 for r in risks if r.get("risk_rating") == "high")
        add("E3", "Critical risks", f"{crit} critical + {high} high of {len(risks)}",
            "climate_risk_register", "IFRS S2 \u00a725(a)", "Rating = likelihood \u00d7 severity on a 5\u00d75 matrix.")

    if phys_by_hazard:
        top = phys_by_hazard[0]
        add("E4", "Top physical hazard", f"{top['hazard']}: \u20ac{top['exposure']:.0f}M across {top['count']} counterparties",
            "physical_risk_exposures", "IFRS S2 \u00a7A2", "Largest single acute/chronic hazard concentration in the book.")

    if scenarios:
        worst = max(s.get("revenue_at_risk_meur", 0) for s in scenarios)
        add("E5", "Worst-case revenue at risk", f"\u20ac{worst:.0f}M",
            "climate_scenarios", "IFRS S2 \u00a722", "Peak revenue-at-risk across all scenario/horizon cells.")

    if k.get("fossil_fuel_exposure_pct") is not None:
        add("E6", "Fossil-fuel exposure", f"{k['fossil_fuel_exposure_pct']}% (\u20ac{k.get('fossil_fuel_exposure_meur', 0):.0f}M)",
            "reporting_kpis", "IFRS S2 \u00a729(a)", "Transition-risk concentration in lending.")

    if k.get("green_loans_pct_2024") is not None:
        add("E7", "Green-loan share", f"{k['green_loans_pct_2024']}% of lending",
            "reporting_kpis", "IFRS S2 \u00a729(c)", "Check trend across years for stagnation.")

    eq = P.get("financed_emissions_equity", [])
    if eq and any(r.get("emissions_proxy_used") for r in eq):
        add("E8", "Equity emissions are proxy", "PCAF B61 revenue proxy \u2014 not verified issuer emissions",
            "financed_emissions_equity", "PCAF \u00a7B61", "Revenue-substituted, must be disclosed as such.")

    if targets and any(t.get("progress_is_schedule_proxy") for t in targets):
        add("E9", "Target progress is a schedule proxy", "schedule-elapsed only; actual % typically null",
            "targets", "IFRS S2 \u00a736", "Time elapsed is not the same as a measured reduction.")

    if len(fin) >= 2:
        add("E10", "Profitability trend", f"ROE {fin[0].get('return_on_equity_pct')}% \u2192 {fin[-1].get('return_on_equity_pct')}%",
            "financial_summary", "IFRS S2 \u00a716", "Affects capacity to absorb transition/physical losses.")

    s2 = sorted(P.get("scope2", []), key=lambda r: r.get("reporting_year", 0))
    if len(s2) >= 2:
        add("E11", "Scope 2 market-based trend", f"{s2[0]['scope2_market_tco2e']:.0f} \u2192 {s2[-1]['scope2_market_tco2e']:.0f} t",
            "scope2", "IFRS S2 \u00a729(a)", "Check REC/PPA procurement narrative for the driver.")

    gaps = P.get("metadata", {}).get("data_gaps", [])
    if any(g.get("field") == "total_loans_meur" for g in gaps):
        add("E12", "Loan denominator may be constant", "check metadata.data_gaps for total_loans_meur",
            "metadata.data_gaps", "IFRS S2 \u00a7B8", "If constant, intensity trend reflects emissions only, not loan growth.")

    s12 = next((r for r in dq_register if r["domain"] == "scope1_scope2"), None)
    if s12 and fe:
        add("E13", "Assurance coverage is narrow",
            f"Scope 1+2 {s12['assurance_level']}-assured; financed emissions (~{fe.get('financed_em_loans_tco2e', 0)/1e6:.1f} Mt) unassured",
            "data_quality_assurance_register", "IFRS S2 \u00a7B58", "Most of the footprint sits outside any assurance scope.")

    if dq_summary.get("audited_report_pct") is not None:
        modeled = round((dq_summary.get("estimated_economic_pct") or 0) + (dq_summary.get("proxy_model_pct") or 0), 1)
        add("E14", "Share of modeled emissions data", f"audited {dq_summary['audited_report_pct']}% \u00b7 modeled/proxy {modeled}%",
            "data_quality_summary", "IFRS S2 \u00a7B58", "Self-disclosed split between audited and modeled/proxy data.")

    if peer:
        add("E15", "Intensity vs synthetic peer set",
            f"{k.get('carbon_intensity_2024_tco2e_per_meur'):.0f} t/M\u20ac vs sector-avg {peer['sector_average']['carbon_intensity_tco2e_per_meur']:.0f} t/M\u20ac (synthetic)",
            "peer_benchmark", "n/a \u2014 illustrative only", "Peer/sector figures are synthetic placeholders, not real disclosed benchmarks.")

    return ev


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------
def process_payload(payload):
    """
    Single entry point called by the upload view. Returns the fully derived
    bundle the frontend renders directly — no further client-side
    aggregation of raw rows is required, though the frontend MAY recompute
    presentation-only details (formatting, colours) from this bundle.
    """
    P = payload

    dq_register, dq_summary = build_data_quality_register(P)
    peer_benchmark = build_peer_benchmark(P)
    phys_by_hazard = build_physical_by_hazard(P)

    derived_for_evidence = {
        "phys_by_hazard": phys_by_hazard,
        "dq_register": dq_register,
        "dq_summary": dq_summary,
        "peer_benchmark": peer_benchmark,
    }

    bundle = {
        "bank": P.get("bank", {}),
        "metadata": P.get("metadata", {}),
        "general_requirements_context": P.get("general_requirements_context", {}),
        "reporting_kpis": P.get("reporting_kpis", {}),
        "kpis": build_kpis(P),
        "intensity_trend": build_intensity_trend(P),
        "op_emissions": build_op_emissions(P),
        "financed_composition": build_financed_composition(P),
        "risk_matrix": build_risk_matrix(P),
        "risk_by_category": build_risk_by_category(P),
        "physical_by_hazard": phys_by_hazard,
        "scenarios": build_scenarios(P),
        "data_quality_register": dq_register,
        "data_quality_summary": dq_summary,
        "peer_benchmark": peer_benchmark,
        "counterparty_drilldown": build_counterparty_drilldown(P),
        "scenario_sensitivity": build_scenario_sensitivity(P),
    }
    bundle["evidence"] = build_evidence(P, derived_for_evidence)
    return bundle
