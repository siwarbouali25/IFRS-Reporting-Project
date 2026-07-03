import time

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from generation_engine.workflow.fake_pipeline import (
    get_fake_pipeline_stages,
    run_fake_pipeline,
)
from report_artifacts.models import ReportArtifact
from report_artifacts.storage import save_json_artifact, save_text_artifact

from .models import GenerationWarning, ReportGenerationJob, ReportVersion


@shared_task(bind=True)
def run_fake_report_generation_job(self, job_id):
    """
    Temporary async report generation task.

    Celery handles the background execution.
    The fake generation logic is now inside generation_engine.

    Later, this task will call the real LangGraph workflow instead of run_fake_pipeline().
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

    for stage in get_fake_pipeline_stages():
        job.current_stage = stage.name
        job.progress_percent = stage.progress
        job.save(update_fields=["current_stage", "progress_percent"])

        time.sleep(1)

    result = run_fake_pipeline(
        job_id=str(job.id),
        bank_name=job.bank.name,
        reporting_year=job.reporting_year,
    )

    with transaction.atomic():
        latest_version_number = (
            ReportVersion.objects
            .filter(bank=job.bank, reporting_year=job.reporting_year)
            .count()
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

        for warning in result.warnings:
            GenerationWarning.objects.create(
                job=job,
                stage=warning.stage,
                warning_type=warning.warning_type,
                message=warning.message,
                details=warning.details,
            )

        save_text_artifact(
            job=job,
            report_version=report_version,
            artifact_type=ReportArtifact.ArtifactType.FINAL_MARKDOWN,
            object_key=f"jobs/{job.id}/final/approved_report_markdown.md",
            text=result.final_markdown,
            content_type="text/markdown",
        )

        save_json_artifact(
            job=job,
            report_version=report_version,
            artifact_type=ReportArtifact.ArtifactType.WARNING_SUMMARY,
            object_key=f"jobs/{job.id}/warnings/warning_summary.json",
            data=result.warning_summary,
        )

        warning_count = len(result.warnings)

        job.status = (
            ReportGenerationJob.Status.COMPLETED_WITH_WARNINGS
            if warning_count > 0
            else ReportGenerationJob.Status.COMPLETED
        )
        job.current_stage = "completed"
        job.progress_percent = 100
        job.warning_count = warning_count
        job.completed_at = timezone.now()
        job.final_summary = result.final_summary

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