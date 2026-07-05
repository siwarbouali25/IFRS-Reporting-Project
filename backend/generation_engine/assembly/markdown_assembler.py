from generation_engine.config import DEFAULT_SECTION_KEYS
from generation_engine.schemas import (
    DraftReportResult,
    GenerationWarningData,
    SectionDraftResult,
)


def assemble_draft_report(
    *,
    section_draft_result: SectionDraftResult,
    bank_name: str,
    reporting_year: int,
) -> DraftReportResult:
    """
    Assemble section drafts into one report Markdown.

    This function creates the main report body shown to the reviewer.
    Internal pipeline details stay in audit artifacts, not in the report text.
    """

    warnings: list[GenerationWarningData] = []

    markdown_parts: list[str] = [
        "# IFRS S1/S2 Sustainability-Related Financial Report",
        "",
        f"**Entity:** {bank_name}",
        "",
        f"**Reporting year:** {reporting_year}",
        "",
        "This report presents sustainability-related financial disclosures "
        "prepared for the reporting period.",
        "",
        "---",
        "",
    ]

    sections_included = 0

    for section_key in DEFAULT_SECTION_KEYS:
        draft = section_draft_result.drafts.get(section_key)

        if not draft:
            warnings.append(
                GenerationWarningData(
                    stage="assemble_draft_report",
                    warning_type="missing_section_draft",
                    message=f"No draft section found for section: {section_key}",
                    details={
                        "section_key": section_key,
                        "workflow_impact": "warning_only",
                    },
                )
            )
            continue

        markdown_parts.append(draft["markdown"].strip())
        markdown_parts.append("")
        markdown_parts.append("---")
        markdown_parts.append("")

        sections_included += 1

    markdown = "\n".join(markdown_parts).strip() + "\n"

    summary = {
        "artifact_type": "assembled_report_markdown",
        "sections_expected": len(DEFAULT_SECTION_KEYS),
        "sections_included": sections_included,
        "markdown_length": len(markdown),
        "llm_used": False,
        "drafting_mode": "deterministic_report_safe_writer",
        "status": "draft",
    }

    return DraftReportResult(
        markdown=markdown,
        summary=summary,
        warnings=warnings,
    )