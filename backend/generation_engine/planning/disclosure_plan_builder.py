from typing import Any

from generation_engine.config import DEFAULT_SECTION_KEYS, SECTION_TITLES
from generation_engine.schemas import DisclosurePlanResult, EvidenceMapResult, GenerationWarningData


FILE_SLUGS = {
    "general_requirements": "general_requirements",
    "governance": "governance",
    "strategy": "strategy",
    "risk_management": "risk_management",
    "metrics_targets": "metrics_and_targets",
}


def _writer_safe_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        candidate
        for candidate in candidates
        if candidate.get("writer_safe") is True
        and candidate.get("audit_only_evidence") is False
        and candidate.get("missing_like_value") is False
    ]


def _select_top_candidates(
    candidates: list[dict[str, Any]],
    *,
    max_candidates: int = 5,
) -> list[dict[str, Any]]:
    safe_candidates = _writer_safe_candidates(candidates)

    sorted_candidates = sorted(
        safe_candidates,
        key=lambda item: (
            item.get("match_score", 0),
            item.get("evidence_strength") == "strong",
        ),
        reverse=True,
    )

    return sorted_candidates[:max_candidates]


def _build_requirement_plan(requirement: dict[str, Any]) -> dict[str, Any]:
    candidates = requirement.get("evidence_candidates", [])
    selected_candidates = _select_top_candidates(candidates)

    evidence_paths = [
        candidate.get("payload_path")
        for candidate in selected_candidates
        if candidate.get("payload_path")
    ]

    has_writer_safe_evidence = len(selected_candidates) > 0

    return {
        "requirement_id": requirement.get("requirement_id"),
        "section_name": requirement.get("section_name"),
        "requirement_text": requirement.get("requirement_text"),
        "mandatory": requirement.get("mandatory", True),
        "has_writer_safe_evidence": has_writer_safe_evidence,
        "selected_evidence_count": len(selected_candidates),
        "selected_evidence_paths": evidence_paths,
        "selected_evidence_candidates": selected_candidates,
        "writing_instruction": (
            "Use only the selected writer-safe evidence candidates. "
            "Do not mention missing evidence or data gaps in the generated report."
        ),
        "missing_data_policy": {
            "report_policy": "do_not_mention_missing_data_in_generated_report",
            "scoring_policy": "do_not_reduce_section_score",
            "workflow_impact": "warning_only",
        },
    }


def _build_section_plan(
    *,
    section_key: str,
    section_map: list[dict[str, Any]],
) -> dict[str, Any]:
    requirement_plans = [
        _build_requirement_plan(requirement)
        for requirement in section_map
    ]

    total_requirements = len(requirement_plans)
    requirements_with_evidence = sum(
        1 for item in requirement_plans if item["has_writer_safe_evidence"]
    )

    requirements_without_evidence = total_requirements - requirements_with_evidence

    evidence_paths: list[str] = []

    for item in requirement_plans:
        evidence_paths.extend(item["selected_evidence_paths"])

    unique_evidence_paths = sorted(set(evidence_paths))

    return {
        "section_key": section_key,
        "section_title": SECTION_TITLES.get(section_key, section_key),
        "file_slug": FILE_SLUGS[section_key],
        "plan_type": "requirement_evidence_disclosure_plan",
        "requirements_total": total_requirements,
        "requirements_with_writer_safe_evidence": requirements_with_evidence,
        "requirements_without_writer_safe_evidence": requirements_without_evidence,
        "unique_selected_evidence_paths_count": len(unique_evidence_paths),
        "unique_selected_evidence_paths": unique_evidence_paths,
        "requirements": requirement_plans,
        "writer_rules": {
            "use_only_selected_evidence": True,
            "do_not_invent_facts": True,
            "do_not_mention_missing_data": True,
            "do_not_penalize_missing_synthetic_data": True,
            "maintain_ifrs_s1_s2_tone": True,
        },
    }


def build_disclosure_plans(
    *,
    evidence_result: EvidenceMapResult,
) -> DisclosurePlanResult:
    """
    Build section-level disclosure plans from notebook-style evidence maps.

    These plans will later be used by the section writer.
    They are internal generation inputs, not final report content.
    """

    evidence_maps = evidence_result.evidence_maps["maps"]

    plans: dict[str, Any] = {}
    warnings: list[GenerationWarningData] = []

    total_requirements = 0
    total_with_evidence = 0
    total_without_evidence = 0

    for section_key in DEFAULT_SECTION_KEYS:
        section_map = evidence_maps.get(section_key, [])

        section_plan = _build_section_plan(
            section_key=section_key,
            section_map=section_map,
        )

        plans[section_key] = section_plan

        total_requirements += section_plan["requirements_total"]
        total_with_evidence += section_plan["requirements_with_writer_safe_evidence"]
        total_without_evidence += section_plan["requirements_without_writer_safe_evidence"]

        if section_plan["requirements_without_writer_safe_evidence"] > 0:
            warnings.append(
                GenerationWarningData(
                    stage="build_disclosure_plans",
                    warning_type="requirements_without_writer_safe_evidence",
                    message=(
                        f"{section_plan['section_title']} has "
                        f"{section_plan['requirements_without_writer_safe_evidence']} "
                        "requirements without writer-safe evidence. "
                        "This is warning-only and must not be mentioned in the generated report."
                    ),
                    details={
                        "section_key": section_key,
                        "section_title": section_plan["section_title"],
                        "requirements_without_writer_safe_evidence": section_plan[
                            "requirements_without_writer_safe_evidence"
                        ],
                        "report_policy": "do_not_mention_missing_data_in_generated_report",
                        "scoring_policy": "do_not_reduce_section_score",
                    },
                )
            )

    summary = {
        "plan_type": "disclosure_plan_summary",
        "sections_total": len(plans),
        "requirements_total": total_requirements,
        "requirements_with_writer_safe_evidence": total_with_evidence,
        "requirements_without_writer_safe_evidence": total_without_evidence,
        "sections": {
            section_key: {
                "section_title": plan["section_title"],
                "requirements_total": plan["requirements_total"],
                "requirements_with_writer_safe_evidence": plan[
                    "requirements_with_writer_safe_evidence"
                ],
                "requirements_without_writer_safe_evidence": plan[
                    "requirements_without_writer_safe_evidence"
                ],
                "unique_selected_evidence_paths_count": plan[
                    "unique_selected_evidence_paths_count"
                ],
            }
            for section_key, plan in plans.items()
        },
        "policy": {
            "report_policy": "do_not_mention_missing_data_in_generated_report",
            "scoring_policy": "do_not_reduce_section_score",
            "workflow_impact": "warning_only",
        },
    }

    return DisclosurePlanResult(
        plans=plans,
        summary=summary,
        warnings=warnings,
    )