from typing import Any

from generation_engine.schemas import CoverageResult, EvidenceMapResult


def _writer_safe_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        candidate
        for candidate in candidates
        if candidate.get("writer_safe") is True
        and candidate.get("audit_only_evidence") is False
        and candidate.get("missing_like_value") is False
    ]


def build_coverage_summary(
    *,
    evidence_result: EvidenceMapResult,
) -> CoverageResult:
    """
    Build coverage statistics from notebook-style evidence maps.

    This is internal audit logic only.
    Missing evidence should not lower final report scoring in the current prototype.
    """

    evidence_maps = evidence_result.evidence_maps["maps"]

    section_summaries: dict[str, Any] = {}

    total_requirements = 0
    total_with_any_candidates = 0
    total_with_writer_safe_candidates = 0
    total_without_writer_safe_candidates = 0

    for section_key, section_map in evidence_maps.items():
        section_total = len(section_map)
        section_with_any = 0
        section_with_writer_safe = 0
        section_without_writer_safe = 0
        section_strong = 0
        section_medium = 0
        section_audit_only_candidates = 0
        section_missing_like_candidates = 0

        for requirement in section_map:
            candidates = requirement.get("evidence_candidates", [])
            safe_candidates = _writer_safe_candidates(candidates)

            if candidates:
                section_with_any += 1

            if safe_candidates:
                section_with_writer_safe += 1
            else:
                section_without_writer_safe += 1

            if any(candidate.get("evidence_strength") == "strong" for candidate in safe_candidates):
                section_strong += 1
            elif any(candidate.get("evidence_strength") == "medium" for candidate in safe_candidates):
                section_medium += 1

            section_audit_only_candidates += sum(
                1 for candidate in candidates if candidate.get("audit_only_evidence") is True
            )

            section_missing_like_candidates += sum(
                1 for candidate in candidates if candidate.get("missing_like_value") is True
            )

        writer_safe_coverage_ratio = (
            section_with_writer_safe / section_total if section_total else 0
        )

        any_candidate_coverage_ratio = (
            section_with_any / section_total if section_total else 0
        )

        section_summaries[section_key] = {
            "requirements_total": section_total,
            "requirements_with_any_candidates": section_with_any,
            "requirements_with_writer_safe_candidates": section_with_writer_safe,
            "requirements_without_writer_safe_candidates": section_without_writer_safe,
            "requirements_with_strong_evidence": section_strong,
            "requirements_with_medium_evidence_only": section_medium,
            "audit_only_candidate_count": section_audit_only_candidates,
            "missing_like_candidate_count": section_missing_like_candidates,
            "any_candidate_coverage_ratio": round(any_candidate_coverage_ratio, 4),
            "writer_safe_coverage_ratio": round(writer_safe_coverage_ratio, 4),
            "scoring_policy": "warning_only_missing_data_does_not_reduce_score",
        }

        total_requirements += section_total
        total_with_any_candidates += section_with_any
        total_with_writer_safe_candidates += section_with_writer_safe
        total_without_writer_safe_candidates += section_without_writer_safe

    overall = {
        "requirements_total": total_requirements,
        "requirements_with_any_candidates": total_with_any_candidates,
        "requirements_with_writer_safe_candidates": total_with_writer_safe_candidates,
        "requirements_without_writer_safe_candidates": total_without_writer_safe_candidates,
        "any_candidate_coverage_ratio": round(
            total_with_any_candidates / total_requirements, 4
        ) if total_requirements else 0,
        "writer_safe_coverage_ratio": round(
            total_with_writer_safe_candidates / total_requirements, 4
        ) if total_requirements else 0,
        "scoring_policy": "warning_only_missing_data_does_not_reduce_score",
        "report_policy": "do_not_mention_missing_data_in_generated_report",
    }

    return CoverageResult(
        coverage_summary={
            "overall": overall,
            "sections": section_summaries,
        }
    )