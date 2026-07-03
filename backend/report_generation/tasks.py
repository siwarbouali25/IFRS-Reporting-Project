import time

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from generation_engine.loaders.payload_loader import load_payloads_from_prefix
from generation_engine.loaders.requirements_loader import load_requirements_from_prefix
from generation_engine.loaders.style_loader import load_style_assets_from_prefix
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

    It now loads real inputs:
    - payloads
    - IFRS requirements
    - style-system assets

    Later, this will call the real LangGraph workflow.
    """

    job = (
        ReportGenerationJob.objects
        .select_related(
            "bank",
            "payload_manifest",
            "ifrs_asset_bundle",
            "style_asset_bundle",
            "created_by",
        )
        .get(id=job_id)
    )

    try:
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

        # Simulated progress stages.
        # The actual loading happens below, but this keeps the frontend progress visible.
        for stage in get_fake_pipeline_stages():
            job.current_stage = stage.name
            job.progress_percent = stage.progress
            job.save(update_fields=["current_stage", "progress_percent"])
            time.sleep(1)

        input_root = settings.GENERATION_INPUT_ROOT

        payload_result = load_payloads_from_prefix(
            input_root=input_root,
            minio_prefix=job.payload_manifest.minio_prefix,
            bank_code=job.bank.code,
        )

        if not job.ifrs_asset_bundle:
            raise ValueError("No IFRS asset bundle is attached to this job.")

        requirements_result = load_requirements_from_prefix(
            input_root=input_root,
            minio_prefix=job.ifrs_asset_bundle.minio_prefix,
        )

        if not job.style_asset_bundle:
            raise ValueError("No style asset bundle is attached to this job.")

        style_result = load_style_assets_from_prefix(
            input_root=input_root,
            minio_prefix=job.style_asset_bundle.minio_prefix,
        )

        result = run_fake_pipeline(
            job_id=str(job.id),
            bank_name=job.bank.name,
            reporting_year=job.reporting_year,
            payload_result=payload_result,
            requirements_result=requirements_result,
            style_result=style_result,
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

            save_json_artifact(
                job=job,
                report_version=report_version,
                artifact_type=ReportArtifact.ArtifactType.LOG,
                object_key=f"jobs/{job.id}/logs/input_summary.json",
                data=result.input_summary,
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

    except Exception as exc:
        job.status = ReportGenerationJob.Status.FAILED
        job.current_stage = "failed"
        job.error_message = str(exc)
        job.completed_at = timezone.now()
        job.save(
            update_fields=[
                "status",
                "current_stage",
                "error_message",
                "completed_at",
            ]
        )

        raise