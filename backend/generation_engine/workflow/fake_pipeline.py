from dataclasses import dataclass
from typing import Any


@dataclass
class PipelineStage:
    name: str
    progress: int


@dataclass
class PipelineWarning:
    stage: str
    warning_type: str
    message: str
    details: dict[str, Any]


@dataclass
class FakePipelineResult:
    final_markdown: str
    warning_summary: dict[str, Any]
    warnings: list[PipelineWarning]
    final_summary: dict[str, Any]


def get_fake_pipeline_stages() -> list[PipelineStage]:
    """
    Temporary stage list used by the fake Celery workflow.

    Later, LangGraph nodes will replace these stages.
    """

    return [
        PipelineStage("load_payloads", 15),
        PipelineStage("load_ifrs_requirements", 25),
        PipelineStage("load_style_assets", 35),
        PipelineStage("build_evidence_maps", 45),
        PipelineStage("create_disclosure_plans", 55),
        PipelineStage("generate_sections", 65),
        PipelineStage("run_validation_checks", 75),
        PipelineStage("revise_failed_sections", 82),
        PipelineStage("assemble_markdown", 90),
        PipelineStage("store_artifacts", 95),
    ]


def run_fake_pipeline(
    *,
    job_id: str,
    bank_name: str,
    reporting_year: int,
) -> FakePipelineResult:
    """
    Temporary fake report generator.

    This simulates the output of the real notebook/LangGraph workflow.
    Celery will call this function and then store the returned outputs.
    """

    final_markdown = f"""# IFRS S1/S2 Sustainability-Related Financial Report

## Entity

{bank_name}

## Reporting Year

{reporting_year}

## Prototype Notice

This is a fake generated report artifact created by the temporary generation engine.

The real notebook/LangGraph workflow will replace this content later.

## Status

Completed with warnings.
"""

    warning = PipelineWarning(
        stage="connectivity_judge",
        warning_type="final_connectivity_warning",
        message=(
            "Fake workflow completed with a simulated connectivity warning. "
            "In the current prototype, final validation failures are treated as warnings."
        ),
        details={
            "approved": False,
            "score": 6,
            "final_failures_as_warnings": True,
        },
    )

    warning_summary = {
        "job_id": job_id,
        "status": "completed_with_warnings",
        "warning_count": 1,
        "warnings": [
            {
                "stage": warning.stage,
                "warning_type": warning.warning_type,
                "approved": warning.details["approved"],
                "score": warning.details["score"],
                "message": warning.message,
            }
        ],
    }

    final_summary = {
        "message": "Fake report generation completed with warnings.",
        "markdown_available": True,
        "pdf_available": False,
        "final_failures_as_warnings": True,
    }

    return FakePipelineResult(
        final_markdown=final_markdown,
        warning_summary=warning_summary,
        warnings=[warning],
        final_summary=final_summary,
    )