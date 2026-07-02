import time

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from .models import (
    GenerationWarning,
    ReportGenerationJob,
    ReportVersion,
)

from report_artifacts.models import ReportArtifact
from report_artifacts.storage import (
    save_json_artifact,
    save_text_artifact,
)


@shared_task(bind=True)
def run_fake_report_generation_job(self, job_id):
    """
    Temporary fake async task.

    This proves:
    - Django can create a job
    - Celery can pick it up
    - the worker can update progress
    - warnings can be stored
    - final status can become completed_with_warnings

    Later, this task will be replaced by the real LangGraph workflow.
    """

    job = ReportGenerationJob.objects.select_related("bank").get(id=job_id)

    job.status = ReportGenerationJob.Status.RUNNING
    job.current_stage = "starting"
    job.progress_percent = 5
    job.started_at = timezone.now()
    job.save(
        update_fields=[
            "status",
            "current_stage",
            "progress_percent",
            "started_at",
        ]
    )

    stages = [
        ("load_payloads", 15),
        ("load_ifrs_requirements", 25),
        ("load_style_assets", 35),
        ("build_evidence_maps", 45),
        ("create_disclosure_plans", 55),
        ("generate_sections", 65),
        ("run_validation_checks", 75),
        ("revise_failed_sections", 82),
        ("assemble_markdown", 90),
        ("store_artifacts", 95),
    ]

    for stage, progress in stages:
        job.current_stage = stage
        job.progress_percent = progress
        job.save(update_fields=["current_stage", "progress_percent"])

        time.sleep(1)

    with transaction.atomic():
        GenerationWarning.objects.create(
            job=job,
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

        latest_version_number = (
            ReportVersion.objects.filter(
                bank=job.bank,
                reporting_year=job.reporting_year,
            ).count()
            + 1
        )

        report_version = ReportVersion.objects.create(
            job=job,
            bank=job.bank,
            reporting_year=job.reporting_year,
            version_number=latest_version_number,
            status=ReportVersion.Status.DRAFT,
            created_by=job.created_by,
        )

        fake_markdown = f"""# IFRS S1/S2 Sustainability-Related Financial Report

## Entity

{job.bank.name}

## Reporting Year

{job.reporting_year}

## Prototype Notice

This is a fake generated report artifact created by the Celery prototype task.

The real notebook/LangGraph workflow will replace this content later.

## Status

Completed with warnings.
"""

        save_text_artifact(
            job=job,
            report_version=report_version,
            artifact_type=ReportArtifact.ArtifactType.FINAL_MARKDOWN,
            object_key=f"jobs/{job.id}/final/approved_report_markdown.md",
            text=fake_markdown,
            content_type="text/markdown",
        )

        warning_summary = {
            "job_id": str(job.id),
            "status": "completed_with_warnings",
            "warning_count": 1,
            "warnings": [
                {
                    "stage": "connectivity_judge",
                    "warning_type": "final_connectivity_warning",
                    "approved": False,
                    "score": 6,
                    "message": (
                        "Final validation issue treated as warning in prototype mode."
                    ),
                }
            ],
        }

        save_json_artifact(
            job=job,
            report_version=report_version,
            artifact_type=ReportArtifact.ArtifactType.WARNING_SUMMARY,
            object_key=f"jobs/{job.id}/warnings/warning_summary.json",
            data=warning_summary,
        )

        job.status = ReportGenerationJob.Status.COMPLETED_WITH_WARNINGS
        job.current_stage = "completed"
        job.progress_percent = 100
        job.warning_count = 1
        job.completed_at = timezone.now()
        job.final_summary = {
            "message": "Fake report generation completed with warnings.",
            "markdown_available": False,
            "pdf_available": False,
            "final_failures_as_warnings": True,
        }

        job.save(
            update_fields=[
                "status",
                "current_stage",
                "progress_percent",
                "warning_count",
                "completed_at",
                "final_summary",
            ]
        )

    return {
        "job_id": str(job.id),
        "status": job.status,
        "warning_count": job.warning_count,
    }