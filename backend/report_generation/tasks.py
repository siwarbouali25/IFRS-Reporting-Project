from pathlib import Path

from celery import shared_task

from generation_engine.graph.workflow import run_ifrs_report_graph
from payloads.services import resolve_payload_directory
from report_artifacts.models import ReportArtifact
from report_artifacts.storage import (
    save_bytes_artifact,
    save_json_artifact,
    save_text_artifact,
    upload_output_directory,
)
from report_generation.models import (
    GenerationWarning,
    ReportGenerationJob,
    ReportVersion,
)
from report_generation.pdf_renderer import render_markdown_to_pdf_bytes


def _next_report_version_number(job: ReportGenerationJob) -> int:
    latest_version = (
        ReportVersion.objects.filter(
            bank=job.bank,
            reporting_year=job.reporting_year,
        )
        .order_by("-version_number")
        .first()
    )
    return 1 if latest_version is None else latest_version.version_number + 1


def _resolve_notebook_output_directory(
    final_state: dict,
    final_summary: dict,
) -> Path | None:
    candidate = (
        final_state.get("notebook_full_output_dir")
        or final_summary.get("output_dir")
        or final_state.get("artifacts", {}).get("output_dir")
    )
    if not candidate:
        return None
    output_directory = Path(candidate).resolve()
    return output_directory if output_directory.exists() else None


@shared_task
def run_real_report_generation_job(job_id: str):
    job = (
        ReportGenerationJob.objects.select_related(
            "bank",
            "payload_manifest",
            "payload_manifest__source_batch",
            "ifrs_asset_bundle",
            "style_asset_bundle",
            "created_by",
        ).get(id=job_id)
    )

    job.mark_running()

    try:
        if job.ifrs_asset_bundle is None:
            raise ValueError("This report job has no IFRS asset bundle.")
        if job.style_asset_bundle is None:
            raise ValueError("This report job has no style asset bundle.")

        payload_dir = resolve_payload_directory(job.payload_manifest)
        initial_state = {
            "job_id": str(job.id),
            "bank_code": job.bank.code,
            "bank_name": job.bank.name,
            "reporting_year": job.reporting_year,
            "payload_dir": str(payload_dir),
            "ifrs_asset_prefix": job.ifrs_asset_bundle.minio_prefix,
            "style_asset_prefix": job.style_asset_bundle.minio_prefix,
            "writer_mode": "llm",
        }

        final_state = run_ifrs_report_graph(initial_state)
        final_markdown = final_state.get("final_markdown", "")
        final_summary = dict(final_state.get("final_summary", {}))
        audit_summary = final_state.get("audit_summary", {})
        handoff_manifest = final_state.get("handoff_manifest", {})
        warnings = final_state.get("warnings", [])

        version_number = _next_report_version_number(job)
        version = ReportVersion.objects.create(
            job=job,
            bank=job.bank,
            reporting_year=job.reporting_year,
            version_number=version_number,
            status=ReportVersion.Status.DRAFT,
            created_by=job.created_by,
        )

        base_key = f"reports/{job.bank.code}/{job.reporting_year}/{job.id}"
        filename_base = (
            f"ifrs_s1_s2_report_{job.bank.code}_"
            f"{job.reporting_year}_v{version_number}"
        )

        markdown_artifact = save_text_artifact(
            job=job,
            report_version=version,
            artifact_type=ReportArtifact.ArtifactType.FINAL_MARKDOWN,
            object_key=f"{base_key}/final/{filename_base}.md",
            text=final_markdown,
            content_type="text/markdown",
        )

        output_formats = set(
            job.config.get("output_formats", ["markdown", "pdf"])
        )
        pdf_artifact = None

        if "pdf" in output_formats:
            pdf_bytes = render_markdown_to_pdf_bytes(
                final_markdown,
                title="IFRS S1/S2 Sustainability-Related Financial Disclosures",
                bank_name=job.bank.name,
                reporting_year=job.reporting_year,
                version_number=version_number,
            )
            pdf_artifact = save_bytes_artifact(
                job=job,
                report_version=version,
                artifact_type=ReportArtifact.ArtifactType.FINAL_PDF,
                object_key=f"{base_key}/final/{filename_base}.pdf",
                content=pdf_bytes,
                content_type="application/pdf",
            )

        save_json_artifact(
            job=job,
            report_version=version,
            artifact_type=ReportArtifact.ArtifactType.AUDIT_SUMMARY,
            object_key=f"{base_key}/audit/audit_summary.json",
            data=audit_summary,
        )
        save_json_artifact(
            job=job,
            report_version=version,
            artifact_type=ReportArtifact.ArtifactType.LOG,
            object_key=f"{base_key}/handoff/handoff_manifest.json",
            data=handoff_manifest,
        )

        output_directory = _resolve_notebook_output_directory(
            final_state,
            final_summary,
        )
        notebook_artifacts = []
        if output_directory is not None:
            notebook_artifacts = upload_output_directory(
                job=job,
                report_version=version,
                local_directory=output_directory,
                object_prefix=f"{base_key}/notebook-output",
            )

        final_summary.update(
            {
                "report_version_id": str(version.id),
                "report_version_number": version_number,
                "approval_status": version.status,
                "final_markdown_artifact_id": str(markdown_artifact.id),
                "final_pdf_artifact_id": (
                    str(pdf_artifact.id) if pdf_artifact else None
                ),
                "artifact_bucket": markdown_artifact.bucket,
                "artifact_prefix": base_key,
                "notebook_artifact_count": len(notebook_artifacts),
            }
        )

        save_json_artifact(
            job=job,
            report_version=version,
            artifact_type=ReportArtifact.ArtifactType.WARNING_SUMMARY,
            object_key=f"{base_key}/summary/final_summary.json",
            data=final_summary,
        )

        for warning in warnings:
            if isinstance(warning, dict):
                stage = warning.get("stage", "generation")
                warning_type = warning.get("warning_type", "warning")
                message = warning.get("message", str(warning))
                details = warning.get("details", {})
            else:
                stage = "generation"
                warning_type = "warning"
                message = str(warning)
                details = {}

            GenerationWarning.objects.create(
                job=job,
                stage=stage,
                warning_type=warning_type,
                message=message,
                details=details,
            )

        job.final_summary = final_summary
        job.save(update_fields=["final_summary"])
        job.mark_completed(warning_count=len(warnings))

        return {
            "status": "completed",
            "job_id": str(job.id),
            "report_version_id": str(version.id),
            "final_markdown_artifact_id": str(markdown_artifact.id),
            "final_pdf_artifact_id": (
                str(pdf_artifact.id) if pdf_artifact else None
            ),
            "notebook_artifact_count": len(notebook_artifacts),
            "final_summary": final_summary,
        }

    except Exception as exc:
        job.mark_failed(str(exc))
        raise