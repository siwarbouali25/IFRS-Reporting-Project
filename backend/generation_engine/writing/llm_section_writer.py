import json
from typing import Any

from generation_engine.config import DEFAULT_SECTION_KEYS
from generation_engine.llm.azure_client import AzureURLLLMClient
from generation_engine.schemas import (
    GenerationWarningData,
    SectionDraftResult,
    WriterContextResult,
)


MAX_REQUIREMENTS_PER_SECTION = 25
MAX_EVIDENCE_PER_REQUIREMENT = 3
MAX_PREVIEW_CHARS = 700


def _clean_llm_markdown(markdown: str) -> str:
    text = markdown.strip()

    if text.startswith("```markdown"):
        text = text.removeprefix("```markdown").strip()

    if text.startswith("```"):
        text = text.removeprefix("```").strip()

    if text.endswith("```"):
        text = text.removesuffix("```").strip()

    return text.strip() + "\n"


def _truncate_text(value: Any, max_chars: int = MAX_PREVIEW_CHARS) -> str:
    if value is None:
        return ""

    text = str(value)
    text = text.replace("\n", " ")
    text = " ".join(text.split()).strip()

    if len(text) > max_chars:
        text = text[:max_chars].rstrip() + "..."

    return text


def _compact_requirement(requirement_context: dict[str, Any]) -> dict[str, Any]:
    evidence_items = []

    for evidence in requirement_context.get("evidence", [])[:MAX_EVIDENCE_PER_REQUIREMENT]:
        evidence_items.append(
            {
                "value_preview": _truncate_text(evidence.get("value_preview")),
                "value_type": evidence.get("value_type"),
                "evidence_strength": evidence.get("evidence_strength"),
            }
        )

    return {
        "requirement_id": requirement_context.get("requirement_id"),
        "requirement_text": _truncate_text(
            requirement_context.get("requirement_text"),
            max_chars=900,
        ),
        "mandatory": requirement_context.get("mandatory", True),
        "evidence": evidence_items,
    }


def _compact_section_context(section_context: dict[str, Any]) -> dict[str, Any]:
    requirements = []

    for requirement in section_context.get("requirements", [])[
        :MAX_REQUIREMENTS_PER_SECTION
    ]:
        compact_requirement = _compact_requirement(requirement)

        if compact_requirement["evidence"]:
            requirements.append(compact_requirement)

    return {
        "section_key": section_context.get("section_key"),
        "section_title": section_context.get("section_title"),
        "requirements_total": section_context.get("requirements_total"),
        "requirements_with_writer_safe_evidence": section_context.get(
            "requirements_with_writer_safe_evidence"
        ),
        "requirements_used_for_generation": len(requirements),
        "style_instructions": {
            "tone": "professional audit-ready sustainability reporting tone",
            "format": "Markdown",
            "audience": "audit and sustainability reporting teams",
        },
        "requirements": requirements,
    }


def _build_system_prompt(section_title: str) -> str:
    return f"""
You are an expert IFRS S1 and IFRS S2 sustainability reporting writer.

Write the "{section_title}" section of an IFRS S1/S2-aligned sustainability-related financial disclosure report.

Strict rules:
- Use only the evidence provided in the user prompt.
- Do not invent facts, numbers, entities, policies, dates, committees, targets, or scenarios.
- Do not mention missing data, data gaps, unavailable information, or synthetic data.
- Do not expose payload paths, JSON keys, internal field names, evidence IDs, or technical pipeline details.
- Do not write "the available reporting evidence indicates".
- Do not write a list of raw disclosures.
- Do not mention that you are an AI or that this is generated.
- Do not include markdown code fences.
- Use polished report language.
- Use clear paragraphs and useful subheadings.
- Keep the section coherent and readable.
""".strip()


def _build_user_prompt(section_context: dict[str, Any]) -> str:
    compact_context = _compact_section_context(section_context)

    return f"""
Generate a polished Markdown report section using this compact writer context.

Return only the Markdown section.

Compact writer context:
{json.dumps(compact_context, ensure_ascii=False, indent=2)}
""".strip()


def generate_llm_section_draft(
    *,
    section_context: dict[str, Any],
    llm_client: AzureURLLLMClient,
    max_tokens: int = 3500,
) -> dict[str, Any]:
    section_key = section_context.get("section_key")
    section_title = section_context.get("section_title", section_key)
    file_slug = section_context.get("file_slug", section_key)

    response = llm_client.generate_writer_text(
        system_prompt=_build_system_prompt(section_title),
        user_prompt=_build_user_prompt(section_context),
        max_tokens=max_tokens,
    )

    markdown = _clean_llm_markdown(response.content)

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
        "draft_type": "llm_section_draft",
        "llm_used": True,
        "model_role": response.model_role,
        "writer_rules_applied": {
            "used_only_writer_safe_evidence": True,
            "did_not_invent_facts_instruction": True,
            "did_not_mention_missing_data_instruction": True,
            "did_not_expose_payload_paths_instruction": True,
        },
    }


def build_llm_section_drafts(
    *,
    writer_context_result: WriterContextResult,
    sections: list[str] | None = None,
    llm_client: AzureURLLLMClient | None = None,
) -> SectionDraftResult:
    """
    Generate LLM-based section drafts from writer contexts.

    For now, use this in a test command first.
    Later, we will connect it to the Celery task.
    """

    client = llm_client or AzureURLLLMClient()
    selected_sections = sections or DEFAULT_SECTION_KEYS

    drafts: dict[str, Any] = {}
    warnings: list[GenerationWarningData] = []

    total_sections = 0
    total_requirements = 0
    total_requirements_with_evidence = 0

    for section_key in selected_sections:
        section_context = writer_context_result.contexts.get(section_key)

        if not section_context:
            warnings.append(
                GenerationWarningData(
                    stage="llm_section_writer",
                    warning_type="missing_writer_context",
                    message=f"No writer context found for section: {section_key}",
                    details={
                        "section_key": section_key,
                        "workflow_impact": "warning_only",
                    },
                )
            )
            continue

        try:
            draft = generate_llm_section_draft(
                section_context=section_context,
                llm_client=client,
            )

            drafts[section_key] = draft

            total_sections += 1
            total_requirements += draft["requirements_total"]
            total_requirements_with_evidence += draft[
                "requirements_with_writer_safe_evidence"
            ]

        except Exception as exc:
            warnings.append(
                GenerationWarningData(
                    stage="llm_section_writer",
                    warning_type="llm_section_generation_failed",
                    message=f"LLM generation failed for section: {section_key}",
                    details={
                        "section_key": section_key,
                        "error": str(exc),
                        "workflow_impact": "warning_only_for_now",
                    },
                )
            )

    summary = {
        "draft_type": "llm_section_drafts_summary",
        "sections_requested": selected_sections,
        "sections_generated": total_sections,
        "requirements_total": total_requirements,
        "requirements_with_writer_safe_evidence": total_requirements_with_evidence,
        "drafting_mode": "azure_llm_section_writer",
        "llm_used": True,
        "policy": {
            "use_only_writer_safe_evidence": True,
            "do_not_invent_facts": True,
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
        "warning_count": len(warnings),
    }

    return SectionDraftResult(
        drafts=drafts,
        summary=summary,
        warnings=warnings,
    )