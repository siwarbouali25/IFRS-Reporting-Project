import json
from pathlib import Path

from celery import shared_task
from django.conf import settings

from generation_engine.graph.workflow import run_ifrs_report_graph
from ifrs_assets.models import IFRSAssetBundle, StyleAssetBundle
from payloads.models import PayloadManifest
from report_artifacts.models import ReportArtifact
from report_artifacts.storage import save_json_artifact, save_text_artifact
from report_generation.models import ReportGenerationJob, ReportVersion


@shared_task
def run_real_report_generation_job(job_id: str):
    job = ReportGenerationJob.objects.select_related(
        "bank",
        "payload_manifest",
        "ifrs_asset_bundle",
        "style_asset_bundle",
    ).get(id=job_id)

    job.mark_running()

    try:
        initial_state = {
            "job_id": str(job.id),
            "bank_code": job.bank.code,
            "bank_name": job.bank.name,
            "reporting_year": job.reporting_year,
            "input_root": str(settings.GENERATION_INPUT_ROOT),
            "payload_prefix": job.payload_manifest.minio_prefix,
            "ifrs_asset_prefix": job.ifrs_asset_bundle.minio_prefix,
            "style_asset_prefix": job.style_asset_bundle.minio_prefix,
            "writer_mode": "llm",
        }

        final_state = run_ifrs_report_graph(initial_state)

        final_markdown = final_state.get("final_markdown", "")
        final_summary = final_state.get("final_summary", {})
        audit_summary = final_state.get("audit_summary", {})
        handoff_manifest = final_state.get("handoff_manifest", {})

        # Save final markdown
        markdown_storage_path = save_text_artifact(
            relative_path=f"reports/{job.bank.code}/{job.reporting_year}/{job.id}/approved_report_markdown.md",
            content=final_markdown,
        )

        markdown_artifact = ReportArtifact.objects.create(
            job=job,
            artifact_type=ReportArtifact.ArtifactType.FINAL_MARKDOWN,
            name="Approved report markdown",
            storage_path=markdown_storage_path,
            mime_type="text/markdown",
        )

        # Save audit summary
        audit_storage_path = save_json_artifact(
            relative_path=f"reports/{job.bank.code}/{job.reporting_year}/{job.id}/audit_summary.json",
            content=audit_summary,
        )

        ReportArtifact.objects.create(
            job=job,
            artifact_type=ReportArtifact.ArtifactType.AUDIT_SUMMARY,
            name="Audit summary",
            storage_path=audit_storage_path,
            mime_type="application/json",
        )

        # Save handoff manifest
        manifest_storage_path = save_json_artifact(
            relative_path=f"reports/{job.bank.code}/{job.reporting_year}/{job.id}/handoff_manifest.json",
            content=handoff_manifest,
        )

        ReportArtifact.objects.create(
            job=job,
            artifact_type=ReportArtifact.ArtifactType.LOG,
            name="PDF handoff manifest",
            storage_path=manifest_storage_path,
            mime_type="application/json",
        )

        # Save final summary
        summary_storage_path = save_json_artifact(
            relative_path=f"reports/{job.bank.code}/{job.reporting_year}/{job.id}/final_summary.json",
            content=final_summary,
        )

        ReportArtifact.objects.create(
            job=job,
            artifact_type=ReportArtifact.ArtifactType.WARNING_SUMMARY,
            name="Final generation summary",
            storage_path=summary_storage_path,
            mime_type="application/json",
        )

        ReportVersion.objects.create(
            job=job,
            version_number=1,
            markdown_artifact=markdown_artifact,
            status="approved",
        )

        job.mark_completed(warning_count=0)

        return {
            "status": "completed",
            "job_id": str(job.id),
            "final_markdown_artifact_id": str(markdown_artifact.id),
            "final_summary": final_summary,
        }

    except Exception as exc:
        job.mark_failed(str(exc))
        raise