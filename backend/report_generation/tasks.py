from celery import shared_task

from generation_engine.graph.workflow import run_ifrs_report_graph
from report_artifacts.models import ReportArtifact
from report_artifacts.storage import save_json_artifact, save_text_artifact
from report_generation.models import GenerationWarning, ReportGenerationJob, ReportVersion


def _next_report_version_number(job: ReportGenerationJob) -> int:
    latest_version = (
        ReportVersion.objects
        .filter(bank=job.bank, reporting_year=job.reporting_year)
        .order_by("-version_number")
        .first()
    )

    if latest_version is None:
        return 1

    return latest_version.version_number + 1


@shared_task
def run_real_report_generation_job(job_id: str):
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

    job.mark_running()

    try:
        if job.ifrs_asset_bundle is None:
            raise ValueError("This report job has no IFRS asset bundle.")

        if job.style_asset_bundle is None:
            raise ValueError("This report job has no style asset bundle.")

        initial_state = {
            "job_id": str(job.id),
            "bank_code": job.bank.code,
            "bank_name": job.bank.name,
            "reporting_year": job.reporting_year,
            "input_root": "",
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
        warnings = final_state.get("warnings", [])

        version = ReportVersion.objects.create(
            job=job,
            bank=job.bank,
            reporting_year=job.reporting_year,
            version_number=_next_report_version_number(job),
            status=ReportVersion.Status.APPROVED,
            created_by=job.created_by,
        )

        base_key = f"reports/{job.bank.code}/{job.reporting_year}/{job.id}"

        markdown_artifact = save_text_artifact(
            job=job,
            report_version=version,
            artifact_type=ReportArtifact.ArtifactType.FINAL_MARKDOWN,
            object_key=f"{base_key}/approved_report_markdown.md",
            text=final_markdown,
            content_type="text/markdown",
        )

        save_json_artifact(
            job=job,
            report_version=version,
            artifact_type=ReportArtifact.ArtifactType.AUDIT_SUMMARY,
            object_key=f"{base_key}/audit_summary.json",
            data=audit_summary,
        )

        save_json_artifact(
            job=job,
            report_version=version,
            artifact_type=ReportArtifact.ArtifactType.LOG,
            object_key=f"{base_key}/handoff_manifest.json",
            data=handoff_manifest,
        )

        save_json_artifact(
            job=job,
            report_version=version,
            artifact_type=ReportArtifact.ArtifactType.WARNING_SUMMARY,
            object_key=f"{base_key}/final_summary.json",
            data=final_summary,
        )

        for warning in warnings:
            GenerationWarning.objects.create(
                job=job,
                stage=warning.get("stage", "generation") if isinstance(warning, dict) else "generation",
                warning_type=warning.get("warning_type", "warning") if isinstance(warning, dict) else "warning",
                message=warning.get("message", str(warning)) if isinstance(warning, dict) else str(warning),
                details=warning.get("details", {}) if isinstance(warning, dict) else {},
            )

        job.final_summary = final_summary
        job.save(update_fields=["final_summary"])

        job.mark_completed(warning_count=len(warnings))

        return {
            "status": "completed",
            "job_id": str(job.id),
            "report_version_id": str(version.id),
            "final_markdown_artifact_id": str(markdown_artifact.id),
            "final_summary": final_summary,
        }

    except Exception as exc:
        job.mark_failed(str(exc))
        raise