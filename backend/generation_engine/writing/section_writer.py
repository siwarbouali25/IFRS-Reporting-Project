from typing import Any

from generation_engine.config import DEFAULT_SECTION_KEYS
from generation_engine.schemas import (
    GenerationWarningData,
    SectionDraftResult,
    WriterContextResult,
)


NON_REPORTABLE_TERMS = [
    "missing",
    "missing data",
    "data gap",
    "not available",
    "n/a",
    "none",
    "null",
    "unknown",
]


def _clean_preview(value: Any, max_length: int = 420) -> str:
    """
    Convert evidence preview into report-safe text.

    Important:
    - Do not expose payload paths.
    - Do not mention missing data.
    - Do not use developer/prototype language.
    """

    if value is None:
        return ""

    text = str(value)
    text = text.replace("`", "")
    text = text.replace("\n", " ")
    text = " ".join(text.split()).strip()

    if not text:
        return ""

    lowered = text.lower()

    if any(term in lowered for term in NON_REPORTABLE_TERMS):
        return ""

    if len(text) > max_length:
        text = text[:max_length].rstrip() + "..."

    return text


def _build_requirement_paragraph(
    *,
    requirement_context: dict[str, Any],
    disclosure_number: int,
) -> str:
    evidence_items = requirement_context.get("evidence", [])

    cleaned_previews: list[str] = []

    for evidence_item in evidence_items:
        preview = _clean_preview(evidence_item.get("value_preview"))

        if preview:
            cleaned_previews.append(preview)

        if len(cleaned_previews) >= 3:
            break

    if not cleaned_previews:
        return ""

    if len(cleaned_previews) == 1:
        evidence_sentence = cleaned_previews[0]
    else:
        evidence_sentence = " ".join(
            f"{index + 1}) {preview}"
            for index, preview in enumerate(cleaned_previews)
        )

    return f"""### Disclosure {disclosure_number}

The available reporting evidence indicates that {evidence_sentence}
"""


def _build_section_intro(section_title: str) -> str:
    intro_by_title = {
        "General Requirements": (
            "This section presents the general basis for the entity's "
            "sustainability-related financial disclosures, including the "
            "reporting context, scope and preparation basis."
        ),
        "Governance": (
            "This section describes the governance arrangements used to oversee "
            "sustainability-related risks and opportunities."
        ),
        "Strategy": (
            "This section describes the sustainability-related risks and "
            "opportunities that may affect the entity's strategy, business model "
            "and value chain."
        ),
        "Risk Management": (
            "This section describes the processes used to identify, assess, "
            "prioritise and monitor sustainability-related risks."
        ),
        "Metrics and Targets": (
            "This section presents the metrics and targets used to monitor and "
            "manage sustainability-related risks and opportunities."
        ),
    }

    return intro_by_title.get(
        section_title,
        "This section presents sustainability-related financial disclosures.",
    )


def _build_section_draft(section_context: dict[str, Any]) -> dict[str, Any]:
    section_key = section_context.get("section_key")
    section_title = section_context.get("section_title", section_key)
    file_slug = section_context.get("file_slug", section_key)

    requirement_blocks: list[str] = []
    disclosure_number = 1

    for requirement_context in section_context.get("requirements", []):
        block = _build_requirement_paragraph(
            requirement_context=requirement_context,
            disclosure_number=disclosure_number,
        )

        if block:
            requirement_blocks.append(block)
            disclosure_number += 1

    body = "\n\n".join(requirement_blocks).strip()

    if not body:
        body = (
            "The entity presents sustainability-related financial disclosures "
            "based on the available reporting package for the period."
        )

    section_intro = _build_section_intro(section_title)

    markdown = f"""# {section_title}

{section_intro}

{body}
"""

    return {
        "section_key": section_key,
        "section_title": section_title,
        "file_slug": file_slug,
        "markdown": markdown,
        "requirements_total": section_context.get("requirements_total", 0),
        "requirements_with_writer_safe_evidence": section_context.get(
            "requirements_with_writer_safe_evidence",
            0,
        ),
        "requirements_without_writer_safe_evidence": section_context.get(
            "requirements_without_writer_safe_evidence",
            0,
        ),
        "draft_type": "deterministic_report_safe_section_draft",
        "writer_rules_applied": {
            "used_only_writer_safe_evidence": True,
            "did_not_invent_facts": True,
            "did_not_use_audit_only_evidence": True,
            "did_not_mention_missing_data": True,
            "did_not_expose_payload_paths": True,
            "removed_prototype_language": True,
        },
    }


def build_section_drafts(
    *,
    writer_context_result: WriterContextResult,
) -> SectionDraftResult:
    """
    Build report-safe deterministic section drafts from writer contexts.

    This still does not use the LLM writer, but the produced Markdown is now
    cleaner and closer to what a reviewer should see.
    """

    drafts: dict[str, Any] = {}
    warnings: list[GenerationWarningData] = []

    total_sections = 0
    total_requirements = 0
    total_requirements_with_evidence = 0

    for section_key in DEFAULT_SECTION_KEYS:
        section_context = writer_context_result.contexts.get(section_key)

        if not section_context:
            warnings.append(
                GenerationWarningData(
                    stage="build_section_drafts",
                    warning_type="missing_writer_context",
                    message=f"No writer context found for section: {section_key}",
                    details={
                        "section_key": section_key,
                        "workflow_impact": "warning_only",
                    },
                )
            )
            continue

        draft = _build_section_draft(section_context)
        drafts[section_key] = draft

        total_sections += 1
        total_requirements += draft["requirements_total"]
        total_requirements_with_evidence += draft[
            "requirements_with_writer_safe_evidence"
        ]

    summary = {
        "draft_type": "section_drafts_summary",
        "sections_total": total_sections,
        "requirements_total": total_requirements,
        "requirements_with_writer_safe_evidence": total_requirements_with_evidence,
        "drafting_mode": "deterministic_report_safe_writer",
        "llm_used": False,
        "policy": {
            "use_only_writer_safe_evidence": True,
            "do_not_invent_facts": True,
            "do_not_use_audit_only_evidence": True,
            "do_not_mention_missing_data": True,
            "do_not_expose_payload_paths": True,
        },
        "sections": {
            section_key: {
                "section_title": draft["section_title"],
                "file_slug": draft["file_slug"],
                "requirements_total": draft["requirements_total"],
                "requirements_with_writer_safe_evidence": draft[
                    "requirements_with_writer_safe_evidence"
                ],
                "markdown_length": len(draft["markdown"]),
            }
            for section_key, draft in drafts.items()
        },
    }

    return SectionDraftResult(
        drafts=drafts,
        summary=summary,
        warnings=warnings,
    )