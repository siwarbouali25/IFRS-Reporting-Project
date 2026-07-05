from typing import Any

from generation_engine.config import DEFAULT_SECTION_KEYS
from generation_engine.schemas import (
    DisclosurePlanResult,
    GenerationWarningData,
    LoaderResult,
    WriterContextResult,
)


def _safe_get_style(style_result: LoaderResult, section_key: str) -> dict[str, Any]:
    return style_result.data.get("section_styles", {}).get(section_key, {})


def _safe_get_blueprint(style_result: LoaderResult, section_key: str) -> dict[str, Any]:
    return style_result.data.get("section_blueprints", {}).get(section_key, {})


def _build_requirement_context(requirement_plan: dict[str, Any]) -> dict[str, Any]:
    selected_candidates = requirement_plan.get("selected_evidence_candidates", [])

    evidence_notes = []

    for candidate in selected_candidates:
        evidence_notes.append(
            {
                "payload_path": candidate.get("payload_path"),
                "payload_root": candidate.get("payload_root"),
                "value_preview": candidate.get("value_preview"),
                "value_type": candidate.get("value_type"),
                "match_score": candidate.get("match_score"),
                "evidence_strength": candidate.get("evidence_strength"),
                "writer_safe": candidate.get("writer_safe"),
            }
        )

    return {
        "requirement_id": requirement_plan.get("requirement_id"),
        "requirement_text": requirement_plan.get("requirement_text"),
        "mandatory": requirement_plan.get("mandatory", True),
        "has_writer_safe_evidence": requirement_plan.get(
            "has_writer_safe_evidence",
            False,
        ),
        "evidence": evidence_notes,
        "writer_instruction": (
            "Address this requirement only using the listed writer-safe evidence. "
            "If evidence is unavailable, do not invent facts and do not mention missing data."
        ),
    }


def _build_section_context(
    *,
    section_key: str,
    disclosure_plan: dict[str, Any],
    style_result: LoaderResult,
) -> dict[str, Any]:
    requirement_contexts = [
        _build_requirement_context(requirement_plan)
        for requirement_plan in disclosure_plan.get("requirements", [])
    ]

    section_style = _safe_get_style(style_result, section_key)
    section_blueprint = _safe_get_blueprint(style_result, section_key)

    return {
        "section_key": section_key,
        "section_title": disclosure_plan.get("section_title"),
        "file_slug": disclosure_plan.get("file_slug"),
        "context_type": "section_writer_context",
        "section_style": section_style,
        "section_blueprint": section_blueprint,
        "global_style": style_result.data.get("global_style", {}),
        "layout_style_guide": style_result.data.get("layout_style_guide", {}),
        "table_patterns": style_result.data.get("table_patterns", {}),
        "forbidden_terms": style_result.data.get("forbidden_terms", {}),
        "no_copying_rules": style_result.data.get("no_copying_rules", ""),
        "requirements_total": disclosure_plan.get("requirements_total", 0),
        "requirements_with_writer_safe_evidence": disclosure_plan.get(
            "requirements_with_writer_safe_evidence",
            0,
        ),
        "requirements_without_writer_safe_evidence": disclosure_plan.get(
            "requirements_without_writer_safe_evidence",
            0,
        ),
        "unique_selected_evidence_paths": disclosure_plan.get(
            "unique_selected_evidence_paths",
            [],
        ),
        "requirements": requirement_contexts,
        "writer_rules": {
            "use_only_writer_safe_evidence": True,
            "do_not_invent_facts": True,
            "do_not_use_audit_only_evidence": True,
            "do_not_mention_missing_data": True,
            "do_not_reduce_score_for_missing_synthetic_data": True,
            "follow_section_blueprint": True,
            "follow_style_guides": True,
            "maintain_ifrs_s1_s2_professional_tone": True,
        },
        "missing_data_policy": {
            "report_policy": "do_not_mention_missing_data_in_generated_report",
            "scoring_policy": "do_not_reduce_section_score",
            "workflow_impact": "warning_only",
        },
    }


def build_writer_contexts(
    *,
    disclosure_plan_result: DisclosurePlanResult,
    style_result: LoaderResult,
) -> WriterContextResult:
    """
    Build clean writer context packages for each report section.

    These contexts are not the final report.
    They are the structured inputs that the future section writer will use.
    """

    contexts: dict[str, Any] = {}
    warnings: list[GenerationWarningData] = []

    total_requirements = 0
    total_with_evidence = 0
    total_without_evidence = 0

    for section_key in DEFAULT_SECTION_KEYS:
        disclosure_plan = disclosure_plan_result.plans.get(section_key)

        if not disclosure_plan:
            warnings.append(
                GenerationWarningData(
                    stage="build_writer_contexts",
                    warning_type="missing_disclosure_plan",
                    message=f"No disclosure plan found for section: {section_key}",
                    details={
                        "section_key": section_key,
                    },
                )
            )
            continue

        context = _build_section_context(
            section_key=section_key,
            disclosure_plan=disclosure_plan,
            style_result=style_result,
        )

        contexts[section_key] = context

        total_requirements += context["requirements_total"]
        total_with_evidence += context["requirements_with_writer_safe_evidence"]
        total_without_evidence += context["requirements_without_writer_safe_evidence"]

        if not context["section_style"]:
            warnings.append(
                GenerationWarningData(
                    stage="build_writer_contexts",
                    warning_type="missing_section_style_in_writer_context",
                    message=f"No section style loaded for section: {section_key}",
                    details={
                        "section_key": section_key,
                        "workflow_impact": "warning_only",
                    },
                )
            )

        if not context["section_blueprint"]:
            warnings.append(
                GenerationWarningData(
                    stage="build_writer_contexts",
                    warning_type="missing_section_blueprint_in_writer_context",
                    message=f"No section blueprint loaded for section: {section_key}",
                    details={
                        "section_key": section_key,
                        "workflow_impact": "warning_only",
                    },
                )
            )

    summary = {
        "context_type": "writer_context_summary",
        "sections_total": len(contexts),
        "requirements_total": total_requirements,
        "requirements_with_writer_safe_evidence": total_with_evidence,
        "requirements_without_writer_safe_evidence": total_without_evidence,
        "policy": {
            "report_policy": "do_not_mention_missing_data_in_generated_report",
            "scoring_policy": "do_not_reduce_section_score",
            "workflow_impact": "warning_only",
        },
        "sections": {
            section_key: {
                "section_title": context["section_title"],
                "requirements_total": context["requirements_total"],
                "requirements_with_writer_safe_evidence": context[
                    "requirements_with_writer_safe_evidence"
                ],
                "requirements_without_writer_safe_evidence": context[
                    "requirements_without_writer_safe_evidence"
                ],
                "unique_selected_evidence_paths_count": len(
                    context["unique_selected_evidence_paths"]
                ),
            }
            for section_key, context in contexts.items()
        },
    }

    return WriterContextResult(
        contexts=contexts,
        summary=summary,
        warnings=warnings,
    )