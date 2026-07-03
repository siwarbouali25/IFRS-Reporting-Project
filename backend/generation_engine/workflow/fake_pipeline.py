from dataclasses import dataclass
from typing import Any

from generation_engine.schemas import LoaderResult


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
    input_summary: dict[str, Any]


def get_fake_pipeline_stages() -> list[PipelineStage]:
    """
    Temporary stage list used by the fake Celery workflow.

    These stages mirror the future LangGraph workflow.
    """

    return [
        PipelineStage("load_payloads", 15),
        PipelineStage("load_ifrs_requirements", 25),
        PipelineStage("load_style_assets", 35),
        PipelineStage("summarize_loaded_inputs", 45),
        PipelineStage("build_evidence_maps", 55),
        PipelineStage("create_disclosure_plans", 65),
        PipelineStage("generate_sections", 75),
        PipelineStage("run_validation_checks", 82),
        PipelineStage("assemble_markdown", 90),
        PipelineStage("store_artifacts", 95),
    ]


def _convert_loader_warnings(loader_results: list[LoaderResult]) -> list[PipelineWarning]:
    warnings: list[PipelineWarning] = []

    for loader_result in loader_results:
        for warning in loader_result.warnings:
            warnings.append(
                PipelineWarning(
                    stage=warning.stage,
                    warning_type=warning.warning_type,
                    message=warning.message,
                    details=warning.details,
                )
            )

    return warnings


def run_fake_pipeline(
    *,
    job_id: str,
    bank_name: str,
    reporting_year: int,
    payload_result: LoaderResult,
    requirements_result: LoaderResult,
    style_result: LoaderResult,
) -> FakePipelineResult:
    """
    Temporary fake report generator.

    It now receives real loaded inputs from the loaders.
    The content is still fake, but the pipeline proves that input loading works.
    """

    loader_warnings = _convert_loader_warnings(
        [payload_result, requirements_result, style_result]
    )

    simulated_connectivity_warning = PipelineWarning(
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

    warnings = [*loader_warnings, simulated_connectivity_warning]

    input_summary = {
        "payloads": {
            "loaded_files": len(payload_result.loaded_files),
            "missing_files": len(payload_result.missing_files),
            "warnings": len(payload_result.warnings),
            "sections": list(payload_result.data.keys()),
        },
        "requirements": {
            "loaded_files": len(requirements_result.loaded_files),
            "missing_files": len(requirements_result.missing_files),
            "warnings": len(requirements_result.warnings),
            "files": requirements_result.loaded_files,
        },
        "style_assets": {
            "loaded_files": len(style_result.loaded_files),
            "missing_files": len(style_result.missing_files),
            "warnings": len(style_result.warnings),
            "available_keys": list(style_result.data.keys()),
        },
    }

    final_markdown = f"""# IFRS S1/S2 Sustainability-Related Financial Report

## Entity

{bank_name}

## Reporting Year

{reporting_year}

## Prototype Notice

This is a fake generated report artifact created by the temporary generation engine.

The real notebook/LangGraph workflow will replace this content later.

## Loaded Input Summary

### Payloads

Loaded payload files: {len(payload_result.loaded_files)}

Missing payload files: {len(payload_result.missing_files)}

### IFRS Requirements

Loaded IFRS requirement files: {len(requirements_result.loaded_files)}

### Style Assets

Loaded style-system files: {len(style_result.loaded_files)}

Missing style-system files: {len(style_result.missing_files)}

## Status

Completed with warnings.
"""

    warning_summary = {
        "job_id": job_id,
        "status": "completed_with_warnings" if warnings else "completed",
        "warning_count": len(warnings),
        "warnings": [
            {
                "stage": warning.stage,
                "warning_type": warning.warning_type,
                "message": warning.message,
                "details": warning.details,
            }
            for warning in warnings
        ],
    }

    final_summary = {
        "message": "Fake report generation completed after loading real inputs.",
        "markdown_available": True,
        "pdf_available": False,
        "final_failures_as_warnings": True,
        "input_summary": input_summary,
    }

    return FakePipelineResult(
        final_markdown=final_markdown,
        warning_summary=warning_summary,
        warnings=warnings,
        final_summary=final_summary,
        input_summary=input_summary,
    )