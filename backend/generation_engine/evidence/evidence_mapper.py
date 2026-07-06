
from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any, Optional

from generation_engine.schemas import EvidenceMapResult, GenerationWarningData


# ============================================================
# Notebook-parity deterministic evidence mapper
# Ported from the cleaned notebook evidence mapper:
# - CELL 7 deterministic payload-aware mapper
# - CELL 9B strict evidence post-processor
#
# Key intent:
# - keep requirement-centered evidence maps
# - use notebook-style section root routing
# - avoid broad/generic manual routes
# - keep missing data as audit/warning-only downstream
# ============================================================


SECTION_META = {
    "general_requirements": {
        "title": "General Requirements",
        "slug": "general_requirements",
        "aliases": {
            "general_requirements",
            "general requirements",
            "general",
            "general_requirements_payload",
        },
    },
    "governance": {
        "title": "Governance",
        "slug": "governance",
        "aliases": {"governance", "governance_payload"},
    },
    "strategy": {
        "title": "Strategy",
        "slug": "strategy",
        "aliases": {"strategy", "strategy_payload"},
    },
    "risk_management": {
        "title": "Risk Management",
        "slug": "risk_management",
        "aliases": {
            "risk_management",
            "risk management",
            "risk",
            "risk_management_payload",
        },
    },
    "metrics_targets": {
        "title": "Metrics and Targets",
        "slug": "metrics_and_targets",
        "aliases": {
            "metrics_targets",
            "metrics_and_targets",
            "metrics targets",
            "metrics and targets",
            "metrics_targets_payload",
        },
    },
}

SECTION_ORDER = [
    "general_requirements",
    "governance",
    "strategy",
    "risk_management",
    "metrics_targets",
]

TITLE_TO_KEY = {
    meta["title"].lower(): key
    for key, meta in SECTION_META.items()
}

SLUG_TO_KEY = {
    meta["slug"]: key
    for key, meta in SECTION_META.items()
}


STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "into", "about", "their",
    "shall", "should", "must", "entity", "entities", "information", "disclose",
    "disclosure", "disclosed", "disclosures", "related", "sustainability", "climate",
    "risks", "risk", "opportunities", "opportunity", "reporting", "period",
    "including", "describe", "explain", "enable", "users", "general", "purpose",
    "financial", "reports", "understand", "specific", "specifically", "current",
    "anticipated", "effects", "used", "uses", "use", "accordance", "paragraph",
    "paragraphs", "standard", "standards", "ifrs", "prepare", "preparing",
}

SECTION_ROOTS = {
    "General Requirements": {
        "metadata", "bank", "financial_summary", "general_requirements_context",
        "targets", "scope1", "scope2", "scope3_travel", "financed_emissions",
        "reporting_kpis",
    },
    "Governance": {
        "bank", "governance", "board_minutes", "climate_risk_register",
        "reporting_kpis",
    },
    "Strategy": {
        "metadata", "bank", "financial_summary", "climate_scenarios",
        "climate_risk_register", "value_chain_map", "climate_opportunities",
        "targets", "transition_plan", "resilience_assessment",
        "climate_financial_effects", "reporting_kpis",
    },
    "Risk Management": {
        "metadata", "bank", "climate_risk_register", "physical_risk_exposures",
        "value_chain_map", "governance", "climate_financial_effects",
        "reporting_kpis",
    },
    "Metrics and Targets": {
        "metadata", "bank", "financial_summary", "scope1", "scope2",
        "scope3_travel", "financed_emissions", "financed_emissions_equity",
        "financed_emissions_sovereign", "targets", "carbon_credits",
        "internal_carbon_price", "scope3_categories", "ghg_methodology",
        "scope12_consolidation", "reporting_kpis",
    },
}

TAG_ROOTS = {
    "governance_body": {"governance", "board_minutes"},
    "management_role": {"governance", "board_minutes"},
    "remuneration": {"governance", "board_minutes"},
    "risk_process": {
        "climate_risk_register",
        "physical_risk_exposures",
        "governance",
        "climate_financial_effects",
    },
    "scenario_analysis": {
        "climate_scenarios",
        "climate_risk_register",
        "physical_risk_exposures",
        "resilience_assessment",
    },
    "business_model_value_chain": {
        "value_chain_map",
        "climate_scenarios",
        "climate_risk_register",
        "climate_financial_effects",
    },
    "strategy_decision_making": {
        "transition_plan",
        "targets",
        "climate_opportunities",
        "climate_scenarios",
        "climate_risk_register",
    },
    "financial_effects": {
        "financial_summary",
        "climate_financial_effects",
        "climate_scenarios",
        "reporting_kpis",
    },
    "metrics": {
        "scope1",
        "scope2",
        "scope3_travel",
        "financed_emissions",
        "targets",
        "financial_summary",
        "reporting_kpis",
        "ghg_methodology",
        "scope12_consolidation",
        "scope3_categories",
        "internal_carbon_price",
        "carbon_credits",
        "financed_emissions_equity",
        "financed_emissions_sovereign",
    },
    "targets": {"targets", "reporting_kpis", "governance"},
    "ghg_emissions": {
        "scope1",
        "scope2",
        "scope3_travel",
        "financed_emissions",
        "ghg_methodology",
        "scope12_consolidation",
        "scope3_categories",
    },
    "scope_1": {"scope1", "scope12_consolidation"},
    "scope_2": {"scope2", "scope12_consolidation"},
    "scope_3": {"scope3_travel", "scope3_categories", "financed_emissions"},
    "materiality": {
        "general_requirements_context",
        "metadata",
        "climate_risk_register",
        "value_chain_map",
    },
    "connected_information": {
        "general_requirements_context",
        "financial_summary",
        "bank",
        "metadata",
    },
    "source_guidance": {
        "general_requirements_context",
        "metadata",
        "ghg_methodology",
    },
}

PHRASE_RULES = [
    (
        ["governance body", "body", "board", "committee", "charged with governance"],
        ["governance", "board_minutes"],
        ["board", "committee", "governance", "members_present", "meeting"],
    ),
    (
        ["skills", "competencies", "competence"],
        ["governance"],
        ["skill", "expertise", "training", "development", "competenc"],
    ),
    (
        ["how often", "informed"],
        ["governance", "board_minutes"],
        ["frequency", "meeting", "minutes", "agenda", "reporting_to_board", "climate_risk_reporting"],
    ),
    (
        ["major transactions", "trade-offs", "trade offs"],
        ["governance", "board_minutes", "transition_plan"],
        ["major_transactions", "decision", "trade", "transition_plan"],
    ),
    (
        ["targets", "progress"],
        ["targets", "governance", "reporting_kpis"],
        ["target", "progress", "baseline", "remuneration"],
    ),
    (
        ["remuneration", "compensation"],
        ["governance"],
        ["compensation", "remuneration", "ceo", "exec"],
    ),
    (
        ["management", "controls", "procedures"],
        ["governance", "climate_risk_register"],
        ["management", "committee", "erm", "control", "integrated"],
    ),
    (
        ["identify", "assess", "prioritise", "prioritize", "monitor"],
        ["climate_risk_register", "physical_risk_exposures"],
        [
            "risk_rating",
            "likelihood",
            "severity",
            "monitoring_frequency",
            "risk_name",
            "risk_category",
            "risk_description",
            "high_risk_flag",
        ],
    ),
    (
        ["scenario analysis"],
        ["climate_scenarios", "climate_risk_register", "resilience_assessment"],
        ["scenario", "scenario_analysis", "framework", "horizon", "methodology", "resilience"],
    ),
    (
        ["changed", "previous reporting period"],
        ["climate_risk_register"],
        ["changed_since_prior_period"],
    ),
    (
        ["integrated", "overall risk management"],
        ["climate_risk_register", "governance"],
        ["erm_integrated", "erm_integration", "management"],
    ),
    (
        ["business model", "value chain"],
        ["value_chain_map"],
        ["value_chain", "node", "upstream", "downstream", "business_model"],
    ),
    (
        ["financial position", "financial performance", "cash flows", "financial effects"],
        ["climate_financial_effects", "financial_summary"],
        [
            "affected_statement",
            "line_item",
            "quantitative_effect",
            "financial",
            "cash",
            "performance",
            "revenue",
            "profit",
        ],
    ),
    (
        ["resilience", "climate resilience"],
        ["resilience_assessment", "climate_scenarios"],
        ["resilience", "capacity", "scenario", "uncertainties"],
    ),
    (
        ["transition plan"],
        ["transition_plan", "climate_scenarios", "targets"],
        ["transition_plan", "net_zero", "dependencies", "resourcing", "assumptions"],
    ),
    (
        ["greenhouse gas", "ghg", "emissions", "co2"],
        ["scope1", "scope2", "scope3_travel", "financed_emissions", "ghg_methodology"],
        ["scope", "emissions", "tco2e", "ghg"],
    ),
    (["scope 1"], ["scope1", "scope12_consolidation"], ["scope1"]),
    (["scope 2"], ["scope2", "scope12_consolidation"], ["scope2", "market", "location"]),
    (
        ["scope 3", "financed emissions"],
        [
            "scope3_travel",
            "financed_emissions",
            "scope3_categories",
            "financed_emissions_equity",
            "financed_emissions_sovereign",
        ],
        ["scope3", "financed", "category", "attributed"],
    ),
    (
        ["carbon price", "internal carbon"],
        ["internal_carbon_price", "climate_scenarios"],
        ["carbon_price", "internal_carbon"],
    ),
    (
        ["capital deployment", "capital expenditure", "financing", "investment deployed"],
        ["financial_summary", "reporting_kpis"],
        ["capex", "opex", "climate_capex", "investment", "financing"],
    ),
    (
        ["comparative", "revised comparative", "redefines", "replaces", "estimate"],
        ["financial_summary", "scope1", "scope2", "financed_emissions", "metadata"],
        ["2022", "2023", "comparative", "estimate", "data_gaps"],
    ),
    (
        ["data source", "inputs", "parameters", "measurement approach", "method"],
        [
            "metadata",
            "ghg_methodology",
            "scope12_consolidation",
            "climate_scenarios",
            "physical_risk_exposures",
        ],
        ["method", "source", "data_source", "input", "assumption", "basis", "scope"],
    ),
    (
        ["reporting entity", "same reporting entity", "financial statements", "currency", "reporting period"],
        ["bank", "general_requirements_context", "financial_summary"],
        ["reporting", "currency", "entity", "period", "fiscal", "boundary"],
    ),
    (
        ["material"],
        ["general_requirements_context", "metadata", "climate_risk_register"],
        ["materiality", "material", "risk_rating", "high_risk"],
    ),
]

STRICT_EXTRA_PHRASE_RULES = [
    (
        [
            "risks and opportunities that could reasonably be expected",
            "risks and opportunities",
            "affect the entity's prospects",
            "affect the entity’s prospects",
        ],
        ["climate_risk_register", "climate_opportunities", "value_chain_map"],
        ["risk_name", "risk_description", "risk_category", "description", "opportunity", "time_horizon", "materiality"],
    ),
    (
        [
            "strategy and decision-making",
            "strategy and decision making",
            "responded to",
            "plans to respond",
            "strategic response",
        ],
        ["transition_plan", "climate_scenarios", "climate_opportunities", "targets", "climate_financial_effects"],
        ["transition_plan", "resilience", "scenario", "target", "progress", "opportunity", "financial_effect", "mitigation"],
    ),
    (
        [
            "fair presentation",
            "complete, neutral and accurate",
            "faithful representation",
            "statement of compliance",
            "apply this standard",
        ],
        ["general_requirements_context", "metadata", "bank"],
        ["standards_basis", "assurance", "reporting", "regulatory_regime", "source_systems"],
    ),
    (
        [
            "judgements",
            "approximations",
            "assumptions",
            "measurement uncertainty",
            "sources of measurement uncertainty",
        ],
        ["general_requirements_context", "metadata", "ghg_methodology", "scope12_consolidation", "financial_summary", "reporting_kpis"],
        ["methodology", "assumption", "estimate", "data_gaps", "quality", "source", "pcaf", "scope2_rec_reconciliation"],
    ),
]

_existing_rule_keys = {tuple(rule[0]) for rule in PHRASE_RULES}
for rule in reversed(STRICT_EXTRA_PHRASE_RULES):
    if tuple(rule[0]) not in _existing_rule_keys:
        PHRASE_RULES.insert(0, rule)

TAG_ROOTS.update({
    "reporting_basis": {"general_requirements_context", "metadata", "bank"},
    "compliance_basis": {"general_requirements_context", "metadata", "bank"},
    "measurement_uncertainty": {
        "general_requirements_context",
        "metadata",
        "ghg_methodology",
        "scope12_consolidation",
        "reporting_kpis",
    },
    "strategy_response": {
        "transition_plan",
        "climate_scenarios",
        "climate_opportunities",
        "targets",
        "climate_financial_effects",
    },
    "risks_opportunities": {
        "climate_risk_register",
        "climate_opportunities",
        "value_chain_map",
    },
})

# IMPORTANT:
# This is intentionally narrow, matching the notebook.
# Do not add broad governance/metrics route hints here; that caused the Django
# maps to over-map all clauses to the same first rows.
REQUIREMENT_ID_ROUTE_HINTS = {
    "IFRS_S1_29_C01": (
        {"climate_risk_register", "climate_opportunities"},
        {"risk_name", "risk_description", "risk_category", "description", "opportunity_name", "time_horizon"},
    ),
    "IFRS_S1_30_C01": (
        {"climate_risk_register", "climate_opportunities"},
        {"risk_name", "risk_description", "risk_category", "description", "opportunity_name", "time_horizon"},
    ),
    "IFRS_S2_9_C01": (
        {"climate_risk_register", "climate_opportunities", "climate_scenarios"},
        {"risk_name", "risk_description", "risk_category", "scenario", "description", "time_horizon"},
    ),
    "IFRS_S2_10_C01": (
        {"climate_risk_register", "climate_opportunities", "climate_scenarios"},
        {"risk_name", "risk_description", "risk_category", "scenario", "description", "time_horizon"},
    ),
    "IFRS_S2_10_C02": (
        {"climate_risk_register"},
        {"risk_category", "risk_name", "risk_description", "physical", "transition"},
    ),
    "IFRS_S1_29_C03": (
        {"transition_plan", "climate_scenarios", "climate_opportunities", "targets", "climate_financial_effects"},
        {"transition_plan", "resilience", "methodology_notes", "target", "progress", "opportunity", "mitigation_actions"},
    ),
    "IFRS_S1_33_C01": (
        {"transition_plan", "climate_scenarios", "climate_opportunities", "targets", "climate_financial_effects"},
        {"transition_plan", "resilience", "methodology_notes", "target", "progress", "opportunity", "mitigation_actions"},
    ),
    "IFRS_S2_9_C03": (
        {"transition_plan", "climate_scenarios", "targets", "climate_financial_effects"},
        {"transition_plan", "resilience", "methodology_notes", "target", "progress"},
    ),
    "IFRS_S1_5_C01": (
        {"general_requirements_context", "metadata", "bank"},
        {"standards_basis", "regulatory_regime", "source_systems"},
    ),
    "IFRS_S1_11_C01": (
        {"general_requirements_context", "metadata"},
        {"standards_basis", "source_systems", "assurance", "risk_rating_methodology"},
    ),
    "IFRS_S1_13_C01": (
        {"general_requirements_context", "metadata"},
        {"standards_basis", "source_systems", "assurance", "risk_rating_methodology"},
    ),
    "IFRS_S1_15_C01": (
        {"general_requirements_context", "metadata", "reporting_kpis"},
        {"assurance", "source_systems", "emissions_data_quality", "data_quality"},
    ),
    "IFRS_S1_21_C01": (
        {"general_requirements_context", "metadata", "financial_summary", "reporting_kpis"},
        {"source_systems", "reporting", "financial", "data_gaps"},
    ),
    "IFRS_S1_B39_C01": (
        {"general_requirements_context", "metadata", "financial_summary", "reporting_kpis"},
        {"source_systems", "reporting", "financial", "data_gaps"},
    ),
    "IFRS_S1_25_C02": (
        {"climate_scenarios", "transition_plan", "climate_opportunities", "targets", "financial_summary"},
        {"transition_plan", "resilience", "scenario", "target", "opportunity", "climate_capex"},
    ),
}

NOISE_PATH_FRAGMENTS = {
    "coherence_fixes_applied",
}

MISSING_LIKE_STRINGS = {
    "", "nan", "none", "null", "na", "n/a", "not applicable", "not_applicable",
}

GENERIC_CONTEXT_LEAVES = {
    "reporting_year", "bank_id", "summary_id", "id", "country", "lei_code",
    "fiscal_year_end", "boundary_type", "reporting_currency", "established_year",
    "headcount", "in_scope_esg_flag", "regulatory_regime",
}

GENERIC_ALLOWED_TERMS = {
    "reporting period", "reporting year", "same reporting", "reporting entity",
    "financial statements", "presentation currency", "currency", "fiscal",
    "comparative", "preceding period", "prior period", "boundary",
    "general purpose financial reports", "same time", "period covered",
    "longer or shorter than 12 months",
}

AUDIT_ONLY_PATH_FRAGMENTS = {
    "data_gaps",
    "data_gap",
    "missing_requirement",
    "missing_requirements",
    "not_available",
    "unavailable",
}

AUDIT_ONLY_LEAVES = {
    "sovereign_bonds_with_data_gaps",
    "listed_equity_emissions_are_proxy",
}


_REQUIREMENT_TEXT_BLOB_CACHE: dict[str, str] = {}
_REQUIREMENT_KEYWORDS_CACHE: dict[str, list[str]] = {}
_FIELD_KEYWORDS_CACHE: dict[tuple[str, str, str], list[str]] = {}


def tokens(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z][a-zA-Z0-9_'-]*|\d+(?:\.\d+)?", str(text).lower())


def value_preview(value: Any, limit: int = 240) -> str:
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False, default=str)
    else:
        text = str(value)
    text = " ".join(text.replace("\n", " ").split())
    if len(text) > limit:
        return text[:limit].rstrip() + "..."
    return text


def root_of_path(path: str) -> str:
    return re.split(r"[.\[]", str(path), maxsplit=1)[0]


def path_leaf(path: str) -> str:
    parts = re.split(r"[.\[\]]+", str(path))
    return next((p for p in reversed(parts) if p and not p.isdigit()), "")


def flatten_json(value: Any, prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}

    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            out.update(flatten_json(child, path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            path = f"{prefix}[{index}]" if prefix else f"[{index}]"
            out.update(flatten_json(child, path))
    else:
        out[prefix] = value

    return out


def get_by_path(payload: Any, path: str) -> Any:
    if not path:
        return None

    current = payload
    parts = re.findall(r"([^. \[\]]+)|\[(\d+)\]", str(path))

    for key, index in parts:
        if key:
            if not isinstance(current, dict) or key not in current:
                return None
            current = current[key]
        else:
            idx = int(index)
            if not isinstance(current, list) or idx >= len(current):
                return None
            current = current[idx]

    return current


def is_missing_like_value(value: Any) -> bool:
    if value is None:
        return True

    if isinstance(value, str):
        return value.strip().lower() in MISSING_LIKE_STRINGS

    if isinstance(value, (list, dict)):
        return len(value) == 0

    # Simple NaN check without pandas dependency.
    try:
        return value != value
    except Exception:
        return False


def is_empty_value(value: Any) -> bool:
    return is_missing_like_value(value)


def normalize_section_key(value: Any) -> Optional[str]:
    if value is None:
        return None

    text = str(value).strip()
    lowered = text.lower().replace("-", "_")

    if lowered in SECTION_META:
        return lowered

    if lowered in TITLE_TO_KEY:
        return TITLE_TO_KEY[lowered]

    if lowered in SLUG_TO_KEY:
        return SLUG_TO_KEY[lowered]

    compact = lowered.replace("_", " ").strip()
    if compact in TITLE_TO_KEY:
        return TITLE_TO_KEY[compact]

    for key, meta in SECTION_META.items():
        if lowered in meta["aliases"] or compact in meta["aliases"]:
            return key

    # Loose fallback for file names such as payload_BANK01_metrics_targets.
    if "general" in lowered and "require" in lowered:
        return "general_requirements"
    if "governance" in lowered:
        return "governance"
    if "strategy" in lowered:
        return "strategy"
    if "risk" in lowered and "management" in lowered:
        return "risk_management"
    if "metrics" in lowered or "targets" in lowered:
        return "metrics_targets"

    return None


def requirement_text_blob(req: dict[str, Any]) -> str:
    rid = str(req.get("requirement_id", id(req)))
    if rid in _REQUIREMENT_TEXT_BLOB_CACHE:
        return _REQUIREMENT_TEXT_BLOB_CACHE[rid]

    tags = req.get("evidence_tags", [])
    if isinstance(tags, str):
        try:
            tags = json.loads(tags)
        except Exception:
            tags = [tags]
    elif not isinstance(tags, list):
        tags = [tags] if tags else []

    text = " ".join([
        str(req.get("requirement_text", "")),
        str(req.get("clause_path", "")),
        " ".join(str(tag).replace("_", " ") for tag in tags),
    ]).lower()

    _REQUIREMENT_TEXT_BLOB_CACHE[rid] = text
    return text


def allowed_roots_for_requirement(section_name: str, req: dict[str, Any]) -> set[str]:
    roots = set(SECTION_ROOTS.get(section_name, set()))

    tags = req.get("evidence_tags", [])
    if isinstance(tags, str):
        try:
            tags = json.loads(tags)
        except Exception:
            tags = re.split(r"[,;|]", tags)
    elif not isinstance(tags, list):
        tags = [tags] if tags else []

    for tag in tags:
        roots |= TAG_ROOTS.get(str(tag), set())

    text = requirement_text_blob(req)
    for phrases, preferred_roots, _path_hints in PHRASE_RULES:
        if any(phrase in text for phrase in phrases):
            roots |= set(preferred_roots)

    return roots


def requirement_keywords(req: dict[str, Any]) -> list[str]:
    rid = str(req.get("requirement_id", id(req)))
    if rid in _REQUIREMENT_KEYWORDS_CACHE:
        return _REQUIREMENT_KEYWORDS_CACHE[rid]

    parts = [
        req.get("requirement_text", ""),
        req.get("clause_path", ""),
        req.get("obligation_type", ""),
        req.get("banking_relevance", ""),
    ]

    tags = req.get("evidence_tags", [])
    if isinstance(tags, str):
        try:
            tags = json.loads(tags)
        except Exception:
            tags = re.split(r"[,;|]", tags)
    elif not isinstance(tags, list):
        tags = [tags] if tags else []

    parts.extend(str(tag).replace("_", " ") for tag in tags)

    kws: list[str] = []
    for part in parts:
        kws.extend(tokens(str(part).replace("_", " ")))

    result = sorted({kw for kw in kws if kw not in STOPWORDS and len(kw) > 2})
    _REQUIREMENT_KEYWORDS_CACHE[rid] = result
    return result


def field_keywords(path: str, value: Any) -> list[str]:
    key = (
        str(path),
        type(value).__name__,
        value_preview(value, limit=200) if not isinstance(value, (int, float, bool)) else str(value),
    )
    if key in _FIELD_KEYWORDS_CACHE:
        return _FIELD_KEYWORDS_CACHE[key]

    text = str(path).replace("_", " ").replace(".", " ")
    if isinstance(value, (str, int, float, bool)):
        text += " " + str(value).replace("_", " ")
    elif isinstance(value, (dict, list)):
        text += " " + value_preview(value, limit=500).replace("_", " ")

    result = [tok for tok in tokens(text) if tok not in STOPWORDS and len(tok) > 2]
    _FIELD_KEYWORDS_CACHE[key] = result
    return result


def phrase_path_boost(req: dict[str, Any], path: str, value: Any) -> tuple[int, list[str]]:
    text = requirement_text_blob(req)
    path_text = str(path).lower().replace("_", " ")
    value_text = str(value).lower().replace("_", " ") if isinstance(value, (str, int, float, bool)) else ""
    root = root_of_path(path)

    total = 0
    hits: list[str] = []

    for phrases, preferred_roots, path_hints in PHRASE_RULES:
        if not any(phrase in text for phrase in phrases):
            continue

        matched_hints = [
            hint
            for hint in path_hints
            if hint.replace("_", " ") in path_text
            or hint.replace("_", " ") in value_text
        ]

        if matched_hints:
            total += 4
            hits.extend(matched_hints[:4])
        elif root in preferred_roots:
            total += 2

    return total, sorted(set(hits))


def metadata_allowed_for_requirement(req: dict[str, Any], path: str) -> bool:
    text = requirement_text_blob(req)
    relevant_terms = [
        "data", "comparative", "estimate", "measurement", "method", "source",
        "unavailable", "gap", "limitation", "scope", "basis", "assumption",
        "currency", "period", "reporting entity", "financial statements",
        "guidance",
    ]

    if "metadata.data_gaps" in path:
        return any(term in text for term in relevant_terms)

    if "metadata.pcaf_methodology" in path:
        return any(term in text for term in ["method", "source", "emission", "financed", "scope 3", "data", "estimate"])

    return True


def is_audit_only_evidence_path(path: str) -> bool:
    lowered = str(path).lower()
    leaf = path_leaf(path)
    return any(fragment in lowered for fragment in AUDIT_ONLY_PATH_FRAGMENTS) or leaf in AUDIT_ONLY_LEAVES


def writer_evidence_path_allowed(path: str) -> bool:
    return not is_audit_only_evidence_path(path)


def requirement_allows_generic_context(req: dict[str, Any], path: str) -> bool:
    leaf = path_leaf(path)
    if leaf not in GENERIC_CONTEXT_LEAVES:
        return True
    text = requirement_text_blob(req)
    return any(term in text for term in GENERIC_ALLOWED_TERMS)


def manual_route_bonus(req: dict[str, Any], path: str) -> tuple[int, list[str], bool]:
    rid = str(req.get("requirement_id", ""))
    if rid not in REQUIREMENT_ID_ROUTE_HINTS:
        return 0, [], False

    roots, hints = REQUIREMENT_ID_ROUTE_HINTS[rid]
    root = root_of_path(path)
    path_text = str(path).lower()

    matched = sorted(hint for hint in hints if hint.lower() in path_text)

    if root in roots and matched:
        return 7, matched[:5], True

    if root in roots:
        return 3, [], True

    return -2, [], False


def evidence_candidate_allowed(req: dict[str, Any], section_name: str, path: str, value: Any) -> tuple[bool, str]:
    path = str(path)

    if any(fragment in path for fragment in NOISE_PATH_FRAGMENTS):
        return False, "excluded_noise_path"

    if is_missing_like_value(value):
        return False, "excluded_missing_like_value"

    if not requirement_allows_generic_context(req, path):
        return False, "excluded_generic_context_field"

    if root_of_path(path) == "metadata" and not metadata_allowed_for_requirement(req, path):
        return False, "excluded_metadata_not_relevant"

    return True, "allowed"


def base_evidence_score(req: dict[str, Any], section_name: str, path: str, value: Any) -> tuple[int, list[str], str]:
    root = root_of_path(path)

    if any(fragment in str(path) for fragment in NOISE_PATH_FRAGMENTS):
        return -999, [], "excluded_noise_path"

    if root == "metadata" and not metadata_allowed_for_requirement(req, str(path)):
        return -999, [], "metadata_not_relevant_to_requirement"

    allowed_roots = allowed_roots_for_requirement(section_name, req)

    req_kws = set(requirement_keywords(req))
    f_kws = set(field_keywords(path, value))
    overlap = sorted(req_kws.intersection(f_kws))

    score = len(overlap)

    path_lower = str(path).lower()
    for kw in req_kws:
        if len(kw) > 3 and kw in path_lower:
            score += 1

    route_reason = "lexical"

    if allowed_roots:
        if root in allowed_roots:
            score += 3
            route_reason = "payload_root_routing+lexical"
        else:
            score -= 3
            route_reason = "outside_expected_payload_root"

    boost, phrase_hits = phrase_path_boost(req, path, value)
    if boost:
        score += boost
        route_reason = "payload_root_routing+phrase_boost+lexical"

    if "reporting_year" in path_lower or "2024" in str(value):
        score += 1

    return score, sorted(set(overlap + phrase_hits)), route_reason


def strict_evidence_score(req: dict[str, Any], section_name: str, path: str, value: Any) -> tuple[int, list[str], str]:
    allowed, reason = evidence_candidate_allowed(req, section_name, path, value)
    if not allowed:
        return -999, [], reason

    root = root_of_path(path)
    allowed_roots = allowed_roots_for_requirement(section_name, req)

    manual_bonus, manual_hits, manual_routed = manual_route_bonus(req, path)
    if manual_routed:
        allowed_roots = set(allowed_roots) | {root}

    req_kws = set(requirement_keywords(req))
    f_kws = set(field_keywords(path, value))
    overlap = sorted(req_kws.intersection(f_kws))

    score = len(overlap)

    path_lower = str(path).lower()
    for kw in req_kws:
        if len(kw) > 3 and kw in path_lower:
            score += 1

    route_reason = "lexical"

    if allowed_roots:
        if root in allowed_roots:
            score += 3
            route_reason = "payload_root_routing+lexical"
        else:
            score -= 4
            route_reason = "outside_expected_payload_root"

    boost, phrase_hits = phrase_path_boost(req, path, value)
    if boost:
        score += boost
        route_reason = "payload_root_routing+phrase_boost+lexical"

    if manual_bonus:
        score += manual_bonus
        route_reason = "manual_requirement_route+" + route_reason

    matched = sorted(set(overlap + phrase_hits + manual_hits))
    return score, matched, route_reason


def evidence_strength(candidate: dict[str, Any]) -> str:
    score = int(candidate.get("match_score", 0) or 0)
    matched = candidate.get("matched_keywords", []) or []
    reason = str(candidate.get("mapping_reason", ""))

    if candidate.get("audit_only_evidence") or candidate.get("generic_context_field"):
        return "medium" if score >= 6 else "weak"

    if score >= 10 and (
        len(matched) >= 2
        or "manual_requirement_route" in reason
        or "phrase_boost" in reason
    ):
        return "strong"

    if score >= 6:
        return "medium"

    return "weak"


def make_strict_candidate(req: dict[str, Any], section_name: str, path: str, value: Any) -> Optional[dict[str, Any]]:
    score, matched_terms, reason = strict_evidence_score(req, section_name, path, value)

    if score < 6:
        return None

    candidate = {
        "payload_path": path,
        "payload_root": root_of_path(path),
        "value_preview": value_preview(value),
        "value_type": type(value).__name__,
        "match_score": score,
        "matched_keywords": matched_terms,
        "mapping_reason": reason,
        "generic_context_field": path_leaf(path) in GENERIC_CONTEXT_LEAVES,
        "audit_only_evidence": is_audit_only_evidence_path(path),
        "writer_safe": writer_evidence_path_allowed(path),
        "missing_like_value": False,
    }

    candidate["evidence_strength"] = evidence_strength(candidate)
    return candidate


def build_base_evidence_map_for_section(
    section_name: str,
    requirements: list[dict[str, Any]],
    payload: dict[str, Any],
    top_k: int = 8,
    min_score: int = 5,
) -> list[dict[str, Any]]:
    flat = flatten_json(payload)
    non_empty_items = [(path, value) for path, value in flat.items() if not is_empty_value(value)]
    mapped: list[dict[str, Any]] = []

    for req in requirements:
        candidates: list[dict[str, Any]] = []

        for path, value in non_empty_items:
            score, matched_terms, reason = base_evidence_score(req, section_name, path, value)

            if score >= min_score:
                candidates.append({
                    "payload_path": path,
                    "payload_root": root_of_path(path),
                    "value_preview": value_preview(value),
                    "value_type": type(value).__name__,
                    "match_score": score,
                    "matched_keywords": matched_terms,
                    "mapping_reason": reason,
                })

        candidates = sorted(
            candidates,
            key=lambda item: (
                item["match_score"],
                len(item.get("matched_keywords", [])),
            ),
            reverse=True,
        )[:top_k]

        mapped.append({
            "requirement_id": req["requirement_id"],
            "section_name": section_name,
            "requirement_text": req.get("requirement_text", ""),
            "mandatory": req.get("mandatory", True),
            "evidence_candidates": candidates,
            "mapping_method": "deterministic_payload_aware",
        })

    return mapped


def targeted_candidate_paths(req: dict[str, Any], flat_payload: dict[str, Any]) -> list[str]:
    rid = str(req.get("requirement_id", ""))

    if rid not in REQUIREMENT_ID_ROUTE_HINTS:
        return []

    roots, hints = REQUIREMENT_ID_ROUTE_HINTS[rid]
    out: list[str] = []

    for path, value in flat_payload.items():
        if root_of_path(path) not in roots:
            continue

        if is_missing_like_value(value):
            continue

        path_lower = path.lower()

        if any(hint.lower() in path_lower for hint in hints):
            out.append(path)

    return out[:80]


def clean_and_enrich_evidence_map(
    section_name: str,
    requirements: list[dict[str, Any]],
    payload: dict[str, Any],
    evidence_map: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    reqs_by_id = {req["requirement_id"]: req for req in requirements}
    flat = flatten_json(payload)
    cleaned_map: list[dict[str, Any]] = []

    for row in evidence_map:
        req = reqs_by_id[row["requirement_id"]]
        by_path: dict[str, dict[str, Any]] = {}

        # Re-score base candidates under strict notebook rules.
        for candidate in row.get("evidence_candidates", []):
            path = candidate.get("payload_path")
            value = get_by_path(payload, path)

            if path is None:
                continue

            strict_candidate = make_strict_candidate(req, section_name, path, value)

            if strict_candidate:
                by_path[str(path)] = strict_candidate

        # Targeted enrichment only for notebook's narrow requirement ID hints.
        for path in targeted_candidate_paths(req, flat):
            if path in by_path:
                continue

            strict_candidate = make_strict_candidate(req, section_name, path, flat[path])

            if strict_candidate:
                by_path[path] = strict_candidate

        candidates = sorted(
            by_path.values(),
            key=lambda item: (
                2 if item.get("evidence_strength") == "strong"
                else 1 if item.get("evidence_strength") == "medium"
                else 0,
                item["match_score"],
                len(item.get("matched_keywords", [])),
                not item.get("generic_context_field", False),
            ),
            reverse=True,
        )[:8]

        cleaned_row = dict(row)
        cleaned_row["evidence_candidates"] = candidates
        cleaned_row["mapping_method"] = "deterministic_payload_aware_strict_writer_safe_postprocessed"
        cleaned_map.append(cleaned_row)

    return cleaned_map


def summarize_evidence_map(section_name: str, evidence_map: list[dict[str, Any]]) -> dict[str, Any]:
    roots = Counter()
    candidate_counts: list[int] = []
    strength_counts = Counter()

    for row in evidence_map:
        candidates = row.get("evidence_candidates", []) or []
        candidate_counts.append(len(candidates))

        for candidate in candidates:
            roots[candidate.get("payload_root") or root_of_path(candidate.get("payload_path", ""))] += 1
            strength_counts[candidate.get("evidence_strength", "unknown")] += 1

    covered = sum(1 for count in candidate_counts if count > 0)

    return {
        "section_name": section_name,
        "requirements_total": len(evidence_map),
        "requirements_with_candidates": covered,
        "requirements_without_candidates": len(evidence_map) - covered,
        "candidate_root_distribution": dict(roots.most_common()),
        "evidence_strength_distribution": dict(strength_counts),
    }


def _normalise_requirement(raw: dict[str, Any], fallback_section_key: Optional[str] = None) -> Optional[dict[str, Any]]:
    requirement_id = (
        raw.get("requirement_id")
        or raw.get("id")
        or raw.get("requirementId")
    )

    requirement_text = (
        raw.get("requirement_text")
        or raw.get("text")
        or raw.get("requirement")
        or raw.get("description")
    )

    if not requirement_id or not requirement_text:
        return None

    section_key = (
        normalize_section_key(raw.get("report_section"))
        or normalize_section_key(raw.get("section_name"))
        or normalize_section_key(raw.get("section"))
        or fallback_section_key
    )

    if not section_key:
        section_key = _infer_section_key_from_requirement_id(str(requirement_id))

    if not section_key:
        return None

    return {
        **raw,
        "requirement_id": str(requirement_id),
        "requirement_text": str(requirement_text),
        "mandatory": raw.get("mandatory", True),
        "_section_key": section_key,
    }


def _infer_section_key_from_requirement_id(requirement_id: str) -> Optional[str]:
    # Keep conservative. Prefer actual section metadata whenever available.
    rid = requirement_id.upper()

    if "_27_" in rid or "_GOV" in rid:
        return "governance"

    if "_29_" in rid or "_30_" in rid or "_31_" in rid or "_32_" in rid or "_33_" in rid:
        return "strategy"

    if "_44_" in rid:
        return "risk_management"

    if any(token in rid for token in ["_46_", "_47_", "_48_", "_49_", "_50_", "_51_", "_52_", "_53_", "_54_", "_55_", "_56_"]):
        return "metrics_targets"

    return "general_requirements"


def _walk_requirements(value: Any, fallback_section_key: Optional[str] = None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    if isinstance(value, list):
        for item in value:
            out.extend(_walk_requirements(item, fallback_section_key))
        return out

    if isinstance(value, dict):
        maybe_req = _normalise_requirement(value, fallback_section_key)

        if maybe_req:
            out.append(maybe_req)
            return out

        for key, child in value.items():
            child_section_key = normalize_section_key(key) or fallback_section_key
            out.extend(_walk_requirements(child, child_section_key))

    return out


def _requirements_by_section(requirements_data: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {key: [] for key in SECTION_ORDER}

    for top_key, value in requirements_data.items():
        fallback_section_key = normalize_section_key(top_key)
        for requirement in _walk_requirements(value, fallback_section_key):
            section_key = requirement.get("_section_key")
            if section_key in grouped:
                grouped[section_key].append(requirement)

    # De-duplicate while preserving order.
    for section_key, items in grouped.items():
        seen: set[str] = set()
        unique: list[dict[str, Any]] = []

        for item in items:
            rid = item["requirement_id"]
            if rid in seen:
                continue

            seen.add(rid)
            unique.append(item)

        grouped[section_key] = unique

    return grouped


def _deep_merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)

    for key, value in override.items():
        if (
            key in merged
            and isinstance(merged[key], dict)
            and isinstance(value, dict)
        ):
            merged[key] = _deep_merge_dicts(merged[key], value)
        else:
            merged[key] = value

    return merged


def _payload_by_section(payload_data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    payloads: dict[str, dict[str, Any]] = {}

    # Potential common/full payload keys. These are optional.
    common_payload: dict[str, Any] = {}
    for key, value in payload_data.items():
        normalised = str(key).lower()
        if normalised in {"combined", "full", "payload", "payload_bank01", "base"} and isinstance(value, dict):
            common_payload = _deep_merge_dicts(common_payload, value)

    for section_key, meta in SECTION_META.items():
        section_payload: Optional[dict[str, Any]] = None

        for key, value in payload_data.items():
            if not isinstance(value, dict):
                continue

            possible_section_key = normalize_section_key(key)
            if possible_section_key == section_key:
                section_payload = value
                break

            lowered = str(key).lower()
            if meta["slug"] in lowered or section_key in lowered:
                section_payload = value
                break

        if section_payload is None:
            # Fallback: use all payload data as one payload object.
            section_payload = payload_data

        # Notebook parity rule:
        # Use the section payload as-is. Do NOT blindly merge the full/common
        # BANK payload into every section, because that leaks unrelated metadata
        # such as PCAF notes into Risk Management or Metrics mappings.
        #
        # Only fall back to the common/full payload when no section-specific
        # payload exists.
        payloads[section_key] = section_payload

    return payloads


def _clear_caches() -> None:
    _REQUIREMENT_TEXT_BLOB_CACHE.clear()
    _REQUIREMENT_KEYWORDS_CACHE.clear()
    _FIELD_KEYWORDS_CACHE.clear()


def build_evidence_maps(*, payload_result: Any, requirements_result: Any) -> EvidenceMapResult:
    """
    Build notebook-parity requirement-centered evidence maps.

    Output shape is intentionally compatible with the existing Django pipeline:
    evidence_result.evidence_maps["maps"][section_key]
    evidence_result.evidence_maps["summaries"][section_key]
    evidence_result.evidence_maps["file_slugs"][section_key]
    """

    _clear_caches()

    warnings: list[GenerationWarningData] = []

    requirements_by_section = _requirements_by_section(requirements_result.data)
    payloads_by_section = _payload_by_section(payload_result.data)

    maps: dict[str, list[dict[str, Any]]] = {}
    summaries: dict[str, dict[str, Any]] = {}
    file_slugs: dict[str, str] = {}

    for section_key in SECTION_ORDER:
        section_name = SECTION_META[section_key]["title"]
        file_slug = SECTION_META[section_key]["slug"]

        requirements = requirements_by_section.get(section_key, [])
        payload = payloads_by_section.get(section_key, {})

        if not requirements:
            warnings.append(
                GenerationWarningData(
                    stage="build_evidence_maps",
                    warning_type="missing_section_requirements",
                    message=f"No requirements found for section: {section_name}",
                    details={"section_key": section_key},
                )
            )

        if not payload:
            warnings.append(
                GenerationWarningData(
                    stage="build_evidence_maps",
                    warning_type="missing_section_payload",
                    message=f"No payload found for section: {section_name}",
                    details={"section_key": section_key},
                )
            )

        base_map = build_base_evidence_map_for_section(
            section_name=section_name,
            requirements=requirements,
            payload=payload,
        )

        strict_map = clean_and_enrich_evidence_map(
            section_name=section_name,
            requirements=requirements,
            payload=payload,
            evidence_map=base_map,
        )

        maps[section_key] = strict_map
        summaries[section_key] = summarize_evidence_map(section_name, strict_map)
        file_slugs[section_key] = file_slug

    overall = {
        "mapping_method": "deterministic_payload_aware_strict_writer_safe_postprocessed",
        "sections_total": len(SECTION_ORDER),
        "requirements_total": sum(summary["requirements_total"] for summary in summaries.values()),
        "requirements_with_candidates": sum(summary["requirements_with_candidates"] for summary in summaries.values()),
        "requirements_without_candidates": sum(summary["requirements_without_candidates"] for summary in summaries.values()),
        "sections": summaries,
        "notebook_parity_notes": {
            "uses_cell_7_payload_aware_mapper": True,
            "uses_cell_9b_strict_postprocessor": True,
            "manual_requirement_routes_are_narrow": True,
            "missing_data_policy": "warning_only_and_not_report_content",
        },
    }

    return EvidenceMapResult(
        evidence_maps={
            "maps": maps,
            "summaries": summaries,
            "file_slugs": file_slugs,
        },
        summary=overall,
        warnings=warnings,
    )
