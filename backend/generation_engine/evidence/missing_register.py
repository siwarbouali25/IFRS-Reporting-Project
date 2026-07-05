from typing import Any

from generation_engine.schemas import EvidenceMapResult, MissingRequirementsResult


def _writer_safe_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        candidate
        for candidate in candidates
        if candidate.get("writer_safe") is True
        and candidate.get("audit_only_evidence") is False
        and candidate.get("missing_like_value") is False
    ]


def build_missing_requirements_register(
    *,
    evidence_result: EvidenceMapResult,
) -> MissingRequirementsResult:
    """
    Build an internal missing requirements register.

    This artifact is for audit/debugging only.
    It must not be inserted into the generated report.
    """

    evidence_maps = evidence_result.evidence_maps["maps"]

    register_items: list[dict[str, Any]] = []

    for section_key, section_map in evidence_maps.items():
        for requirement in section_map:
            candidates = requirement.get("evidence_candidates", [])
            safe_candidates = _writer_safe_candidates(candidates)

            if safe_candidates:
                continue

            if candidates:
                missing_reason = "candidates_exist_but_none_writer_safe"
            else:
                missing_reason = "no_evidence_candidates"

            register_items.append(
                {
                    "section_key": section_key,
                    "section_name": requirement.get("section_name"),
                    "requirement_id": requirement.get("requirement_id"),
                    "requirement_text": requirement.get("requirement_text"),
                    "mandatory": requirement.get("mandatory", True),
                    "missing_reason": missing_reason,
                    "candidate_count": len(candidates),
                    "writer_safe_candidate_count": len(safe_candidates),
                    "audit_only_candidate_count": sum(
                        1 for candidate in candidates if candidate.get("audit_only_evidence") is True
                    ),
                    "missing_like_candidate_count": sum(
                        1 for candidate in candidates if candidate.get("missing_like_value") is True
                    ),
                    "report_policy": "do_not_mention_in_generated_report",
                    "scoring_policy": "do_not_reduce_section_score",
                    "workflow_impact": "warning_only",
                }
            )

    by_section: dict[str, int] = {}

    for item in register_items:
        section_key = item["section_key"]
        by_section[section_key] = by_section.get(section_key, 0) + 1

    missing_register = {
        "policy": {
            "purpose": "internal_audit_only",
            "report_policy": "do_not_mention_missing_data_in_generated_report",
            "scoring_policy": "do_not_reduce_section_score",
            "workflow_impact": "warning_only",
        },
        "summary": {
            "total_missing_requirements": len(register_items),
            "missing_by_section": by_section,
        },
        "items": register_items,
    }

    return MissingRequirementsResult(
        missing_register=missing_register
    )