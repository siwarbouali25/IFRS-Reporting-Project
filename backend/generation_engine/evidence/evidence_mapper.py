import re
from collections import Counter
from typing import Any

from generation_engine.config import DEFAULT_SECTION_KEYS
from generation_engine.schemas import EvidenceMapResult, GenerationWarningData, LoaderResult


MAPPING_METHOD = "deterministic_payload_aware_strict_writer_safe_postprocessed"


SECTION_NAMES = {
    "general_requirements": "General Requirements",
    "governance": "Governance",
    "strategy": "Strategy",
    "risk_management": "Risk Management",
    "metrics_targets": "Metrics and Targets",
}


SECTION_FILE_SLUGS = {
    "general_requirements": "general_requirements",
    "governance": "governance",
    "strategy": "strategy",
    "risk_management": "risk_management",
    "metrics_targets": "metrics_and_targets",
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
    "an", "a", "of", "to", "in", "on", "by", "as", "is", "are", "be", "or",
}


SECTION_ROOTS = {
    "general_requirements": {
        "metadata",
        "bank",
        "financial_summary",
        "value_chain_map",
        "climate_risk_register",
        "physical_risk_exposures",
        "reporting_kpis",
        "climate_scenarios",
        "scope1",
        "scope2",
        "governance",
        "targets",
    },
    "governance": {
        "governance",
        "board_minutes",
        "reporting_kpis",
    },
    "strategy": {
        "climate_risk_register",
        "climate_opportunities",
        "value_chain_map",
        "climate_scenarios",
        "financial_summary",
        "reporting_kpis",
        "bank",
        "metadata",
    },
    "risk_management": {
        "climate_risk_register",
        "physical_risk_exposures",
        "metadata",
        "value_chain_map",
    },
    "metrics_targets": {
        "targets",
        "reporting_kpis",
        "financial_summary",
        "financed_emissions",
        "financed_emissions_sovereign",
        "financed_emissions_equity",
        "internal_carbon_price",
        "scope1",
        "scope2",
        "scope3_travel",
        "bank",
        "metadata",
    },
}


GENERIC_CONTEXT_LEAVES = {
    "reporting_year",
    "bank_id",
    "summary_id",
    "id",
    "country",
    "lei_code",
    "fiscal_year_end",
    "boundary_type",
    "reporting_currency",
    "established_year",
    "headcount",
    "in_scope_esg_flag",
    "regulatory_regime",
}


GENERIC_ALLOWED_TERMS = {
    "reporting period",
    "reporting year",
    "same reporting",
    "reporting entity",
    "financial statements",
    "presentation currency",
    "currency",
    "fiscal",
    "comparative",
    "preceding period",
    "prior period",
    "boundary",
    "general purpose financial reports",
    "same time",
    "period covered",
    "longer or shorter than 12 months",
}


AUDIT_ONLY_PATH_FRAGMENTS = {
    "data_gaps",
    "data_gap",
    "missing",
    "placeholder",
}


AUDIT_ONLY_LEAVES = {
    "reason",
    "gap_reason",
    "missing_reason",
}


MISSING_LIKE_STRINGS = {
    "",
    "nan",
    "none",
    "null",
    "na",
    "n/a",
    "not applicable",
    "not_applicable",
}


PHRASE_RULES = [
    ({"board", "committee", "oversight", "governance"}, {"governance", "board_minutes"}),
    ({"skill", "competence", "expertise", "training"}, {"governance", "board_minutes"}),
    ({"scenario", "analysis", "resilience"}, {"climate_scenarios", "climate_risk_register"}),
    ({"business", "model", "value", "chain"}, {"value_chain_map"}),
    ({"risk", "likelihood", "severity", "monitor"}, {"climate_risk_register"}),
    ({"physical", "exposure", "flood", "heat"}, {"physical_risk_exposures"}),
    ({"metric", "target", "baseline", "progress"}, {"targets", "reporting_kpis"}),
    ({"emissions", "scope", "ghg", "tco2e", "financed"}, {
        "scope1",
        "scope2",
        "scope3_travel",
        "financed_emissions",
        "financed_emissions_sovereign",
        "financed_emissions_equity",
        "reporting_kpis",
    }),
    ({"capital", "revenue", "profit", "cash", "financial"}, {"financial_summary"}),
    ({"carbon", "price"}, {"internal_carbon_price"}),
]


REQUIREMENT_ID_ROUTE_HINTS = {
    "IFRS_S1_27": {"governance", "board_minutes", "reporting_kpis"},
    "IFRS_S1_29": {"climate_risk_register", "value_chain_map", "climate_scenarios", "financial_summary"},
    "IFRS_S1_30": {"climate_risk_register", "climate_opportunities", "climate_scenarios"},
    "IFRS_S1_32": {"value_chain_map"},
    "IFRS_S1_33": {"climate_opportunities", "climate_risk_register"},
    "IFRS_S1_34": {"financial_summary"},
    "IFRS_S1_41": {"climate_scenarios"},
    "IFRS_S1_44": {"climate_risk_register", "physical_risk_exposures", "metadata", "value_chain_map"},
    "IFRS_S1_46": {"targets", "reporting_kpis"},
    "IFRS_S1_51": {"targets"},
    "IFRS_S2_29": {"scope1", "scope2", "scope3_travel", "reporting_kpis", "financed_emissions"},
    "IFRS_S2_B61": {"financed_emissions_sovereign", "financed_emissions_equity", "financed_emissions"},
    "IFRS_S2_B62": {"financed_emissions_sovereign", "financed_emissions_equity", "financed_emissions"},
    "IFRS_S2_B63": {"financed_emissions_sovereign", "financed_emissions_equity", "financed_emissions"},
}


def _tokenize(text: Any) -> set[str]:
    text = str(text or "").lower()
    tokens = re.findall(r"[a-z0-9_]+", text)

    expanded: list[str] = []
    for token in tokens:
        expanded.append(token)
        expanded.extend(token.split("_"))

    return {
        token
        for token in expanded
        if token and token not in STOPWORDS and len(token) > 1
    }


def _root_of_path(path: str) -> str:
    return str(path).split(".")[0].split("[")[0]


def _path_leaf(path: str) -> str:
    last = str(path).split(".")[-1]
    return last.split("[")[0]


def _value_preview(value: Any, max_chars: int = 240) -> str:
    if isinstance(value, (dict, list)):
        text = str(value)
    else:
        text = str(value)

    if len(text) > max_chars:
        return text[:max_chars] + "..."

    return text


def _is_missing_like_value(value: Any) -> bool:
    if value is None:
        return True

    if isinstance(value, str):
        return value.strip().lower() in MISSING_LIKE_STRINGS

    return False


def _is_audit_only_path(path: str) -> bool:
    lowered = path.lower()
    leaf = _path_leaf(path).lower()

    return any(fragment in lowered for fragment in AUDIT_ONLY_PATH_FRAGMENTS) or leaf in AUDIT_ONLY_LEAVES


def _requirement_allows_generic_context(requirement_text: str) -> bool:
    lowered = requirement_text.lower()
    return any(term in lowered for term in GENERIC_ALLOWED_TERMS)


def _flatten_json(data: Any, prefix: str = "") -> dict[str, Any]:
    flat: dict[str, Any] = {}

    if isinstance(data, dict):
        for key, value in data.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            flat.update(_flatten_json(value, path))
        return flat

    if isinstance(data, list):
        for index, value in enumerate(data):
            path = f"{prefix}[{index}]" if prefix else f"[{index}]"
            flat.update(_flatten_json(value, path))
        return flat

    flat[prefix or "root"] = data
    return flat


def _merge_payloads(payloads: dict[str, Any]) -> dict[str, Any]:
    """
    Build one root-level payload catalog.

    The notebook maps requirements against rich section payloads containing roots
    like climate_risk_register, governance, targets, financial_summary, etc.
    This merge keeps first occurrence of each top-level root to avoid duplicated
    candidates when the same root appears in several payload files.
    """

    merged: dict[str, Any] = {}

    for payload_key in ["entity", *DEFAULT_SECTION_KEYS]:
        payload = payloads.get(payload_key, {})
        if not isinstance(payload, dict):
            continue

        for root, value in payload.items():
            if root not in merged:
                merged[root] = value

    return merged


def _infer_section_key(value: Any, fallback: str | None = None) -> str | None:
    text = str(value or fallback or "").lower()

    if "general" in text:
        return "general_requirements"
    if "governance" in text:
        return "governance"
    if "strategy" in text:
        return "strategy"
    if "risk management" in text or "risk_management" in text:
        return "risk_management"
    if "metrics" in text or "targets" in text or "metrics_and_targets" in text:
        return "metrics_targets"

    return None


def _extract_requirement_text(raw: dict[str, Any]) -> str:
    for key in ["requirement_text", "text", "requirement", "description", "content"]:
        if raw.get(key):
            return str(raw[key])

    return ""


def _extract_requirements_recursive(
    data: Any,
    *,
    fallback_section_key: str | None = None,
) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []

    if isinstance(data, dict):
        if "requirement_id" in data:
            requirement_text = _extract_requirement_text(data)

            if requirement_text:
                section_key = _infer_section_key(
                    data.get("section_name") or data.get("section"),
                    fallback_section_key,
                )

                if section_key:
                    found.append(
                        {
                            "requirement_id": str(data["requirement_id"]),
                            "section_key": section_key,
                            "section_name": SECTION_NAMES[section_key],
                            "requirement_text": requirement_text,
                            "mandatory": bool(data.get("mandatory", True)),
                            "raw": data,
                        }
                    )

        for value in data.values():
            found.extend(
                _extract_requirements_recursive(
                    value,
                    fallback_section_key=fallback_section_key,
                )
            )

    elif isinstance(data, list):
        for item in data:
            found.extend(
                _extract_requirements_recursive(
                    item,
                    fallback_section_key=fallback_section_key,
                )
            )

    return found


def _requirements_by_section(requirements_result: LoaderResult) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {
        section_key: [] for section_key in DEFAULT_SECTION_KEYS
    }

    for file_key, data in requirements_result.data.items():
        fallback_section_key = _infer_section_key(file_key)
        requirements = _extract_requirements_recursive(
            data,
            fallback_section_key=fallback_section_key,
        )

        for requirement in requirements:
            grouped[requirement["section_key"]].append(requirement)

    seen: set[str] = set()
    deduped: dict[str, list[dict[str, Any]]] = {
        section_key: [] for section_key in DEFAULT_SECTION_KEYS
    }

    for section_key, requirements in grouped.items():
        for requirement in requirements:
            requirement_id = requirement["requirement_id"]
            if requirement_id in seen:
                continue
            seen.add(requirement_id)
            deduped[section_key].append(requirement)

    return deduped


def _manual_route_bonus(requirement_id: str, payload_root: str) -> tuple[int, bool]:
    for prefix, roots in REQUIREMENT_ID_ROUTE_HINTS.items():
        if requirement_id.startswith(prefix) and payload_root in roots:
            return 6, True

    return 0, False


def _phrase_boost(requirement_keywords: set[str], payload_root: str, path_keywords: set[str]) -> int:
    boost = 0

    for phrase_keywords, roots in PHRASE_RULES:
        if payload_root in roots and requirement_keywords.intersection(phrase_keywords):
            boost += 3

        if path_keywords.intersection(phrase_keywords) and requirement_keywords.intersection(phrase_keywords):
            boost += 2

    return boost


def _score_candidate(
    *,
    requirement_id: str,
    requirement_text: str,
    payload_path: str,
    payload_value: Any,
    section_key: str,
) -> dict[str, Any] | None:
    payload_root = _root_of_path(payload_path)

    if payload_root not in SECTION_ROOTS[section_key]:
        return None

    if _is_missing_like_value(payload_value):
        missing_like = True
    else:
        missing_like = False

    requirement_keywords = _tokenize(requirement_text)
    path_keywords = _tokenize(payload_path)
    value_keywords = _tokenize(payload_value)

    matched_keywords = sorted(requirement_keywords.intersection(path_keywords.union(value_keywords)))

    if not matched_keywords:
        return None

    leaf = _path_leaf(payload_path)
    generic_context = leaf in GENERIC_CONTEXT_LEAVES

    if generic_context and not _requirement_allows_generic_context(requirement_text):
        return None

    audit_only = _is_audit_only_path(payload_path)

    score = 0
    reasons: list[str] = []

    if payload_root in SECTION_ROOTS[section_key]:
        score += 5
        reasons.append("payload_root_routing")

    manual_bonus, manual_route = _manual_route_bonus(requirement_id, payload_root)
    if manual_bonus:
        score += manual_bonus
        reasons.insert(0, "manual_requirement_route")

    phrase = _phrase_boost(requirement_keywords, payload_root, path_keywords)
    if phrase:
        score += phrase
        reasons.append("phrase_boost")

    score += min(len(matched_keywords), 5)
    reasons.append("lexical")

    if audit_only:
        score -= 3

    if missing_like:
        score -= 4

    if score < 6:
        return None

    writer_safe = not audit_only and not missing_like

    if score >= 10:
        evidence_strength = "strong"
    else:
        evidence_strength = "medium"

    return {
        "payload_path": payload_path,
        "payload_root": payload_root,
        "value_preview": _value_preview(payload_value),
        "value_type": type(payload_value).__name__,
        "match_score": int(score),
        "matched_keywords": matched_keywords[:8],
        "mapping_reason": "+".join(dict.fromkeys(reasons)),
        "generic_context_field": generic_context,
        "audit_only_evidence": audit_only,
        "writer_safe": writer_safe,
        "missing_like_value": missing_like,
        "evidence_strength": evidence_strength,
    }


def _build_map_for_section(
    *,
    section_key: str,
    requirements: list[dict[str, Any]],
    flat_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    section_map: list[dict[str, Any]] = []

    for requirement in requirements:
        candidates: list[dict[str, Any]] = []

        for payload_path, payload_value in flat_payload.items():
            candidate = _score_candidate(
                requirement_id=requirement["requirement_id"],
                requirement_text=requirement["requirement_text"],
                payload_path=payload_path,
                payload_value=payload_value,
                section_key=section_key,
            )

            if candidate:
                candidates.append(candidate)

        candidates = sorted(
            candidates,
            key=lambda item: (
                item["writer_safe"],
                item["match_score"],
                item["evidence_strength"] == "strong",
            ),
            reverse=True,
        )[:8]

        section_map.append(
            {
                "requirement_id": requirement["requirement_id"],
                "section_name": requirement["section_name"],
                "requirement_text": requirement["requirement_text"],
                "mandatory": requirement["mandatory"],
                "evidence_candidates": candidates,
                "mapping_method": MAPPING_METHOD,
            }
        )

    return section_map


def _summarize_section_map(section_name: str, section_map: list[dict[str, Any]]) -> dict[str, Any]:
    root_counter: Counter[str] = Counter()

    requirements_with_candidates = 0

    for item in section_map:
        candidates = item.get("evidence_candidates", [])

        if candidates:
            requirements_with_candidates += 1

        for candidate in candidates:
            root_counter[candidate["payload_root"]] += 1

    requirements_total = len(section_map)

    return {
        "section_name": section_name,
        "requirements_total": requirements_total,
        "requirements_with_candidates": requirements_with_candidates,
        "requirements_without_candidates": requirements_total - requirements_with_candidates,
        "candidate_root_distribution": dict(root_counter.most_common()),
    }


def build_evidence_maps(
    *,
    payload_result: LoaderResult,
    requirements_result: LoaderResult,
) -> EvidenceMapResult:
    """
    Build notebook-style evidence maps.

    Output shape:
    {
      "maps": {
        "governance": [requirement mapping rows...]
      },
      "summaries": {
        "governance": {...}
      },
      "file_slugs": {
        "metrics_targets": "metrics_and_targets"
      }
    }
    """

    merged_payload = _merge_payloads(payload_result.data)
    flat_payload = _flatten_json(merged_payload)

    requirements_grouped = _requirements_by_section(requirements_result)

    maps: dict[str, Any] = {}
    summaries: dict[str, Any] = {}
    warnings: list[GenerationWarningData] = []

    for section_key in DEFAULT_SECTION_KEYS:
        requirements = requirements_grouped.get(section_key, [])

        if not requirements:
            warnings.append(
                GenerationWarningData(
                    stage="build_evidence_maps",
                    warning_type="no_requirements_for_section",
                    message=f"No requirements found for section: {SECTION_NAMES[section_key]}",
                    details={"section": section_key},
                )
            )

        section_map = _build_map_for_section(
            section_key=section_key,
            requirements=requirements,
            flat_payload=flat_payload,
        )

        maps[section_key] = section_map
        summaries[section_key] = _summarize_section_map(
            SECTION_NAMES[section_key],
            section_map,
        )

    overall_summary = {
        "sections": summaries,
        "total_requirements": sum(item["requirements_total"] for item in summaries.values()),
        "total_requirements_with_candidates": sum(
            item["requirements_with_candidates"] for item in summaries.values()
        ),
        "total_requirements_without_candidates": sum(
            item["requirements_without_candidates"] for item in summaries.values()
        ),
    }

    return EvidenceMapResult(
        evidence_maps={
            "maps": maps,
            "summaries": summaries,
            "file_slugs": SECTION_FILE_SLUGS,
        },
        summary=overall_summary,
        warnings=warnings,
    )