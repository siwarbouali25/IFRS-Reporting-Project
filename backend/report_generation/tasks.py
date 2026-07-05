from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from generation_engine.assembly.markdown_assembler import assemble_draft_report
from generation_engine.evidence.coverage import build_coverage_summary
from generation_engine.evidence.evidence_mapper import build_evidence_maps
from generation_engine.evidence.missing_register import build_missing_requirements_register
from generation_engine.loaders.payload_loader import load_payloads_from_prefix
from generation_engine.loaders.requirements_loader import load_requirements_from_prefix
from generation_engine.loaders.style_loader import load_style_assets_from_prefix
from generation_engine.planning.disclosure_plan_builder import build_disclosure_plans
from generation_engine.validation.deterministic_gates import (
    run_deterministic_validation_gates,
)
from generation_engine.writing.section_writer import build_section_drafts
from generation_engine.writing.writer_context import build_writer_contexts
from generation_engine.workflow.fake_pipeline import run_fake_pipeline

from report_artifacts.models import ReportArtifact
from report_artifacts.storage import (
    save_json_artifact,
    save_text_artifact,
)

from .models import (
    GenerationWarning,
    ReportGenerationJob,
    ReportVersion,
)


@shared_task(bind=True)
def run_fake_report_generation_job(self, job_id):
    """
    Temporary async report generation task.

    Current flow:
    - load real payloads
    - load IFRS requirements
    - load style-system assets
    - build evidence maps
    - build coverage summary
    - build missing requirements register
    - build disclosure plans
    - build writer contexts
    - build deterministic section drafts
    - assemble full draft report markdown
    - run deterministic validation gates
    - use assembled draft as the primary report markdown

    Later, this task will call the real LangGraph workflow.
    """

    job = (
        ReportGenerationJob.objects.select_related(
            "bank",
            "payload_manifest",
            "ifrs_asset_bundle",
            "style_asset_bundle",
            "created_by",
        ).get(id=job_id)
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

        input_root = settings.GENERATION_INPUT_ROOT

        job.current_stage = "load_payloads"
        job.progress_percent = 15
        job.save(update_fields=["current_stage", "progress_percent"])

        payload_result = load_payloads_from_prefix(
            input_root=input_root,
            minio_prefix=job.payload_manifest.minio_prefix,
            bank_code=job.bank.code,
        )

        if not job.ifrs_asset_bundle:
            raise ValueError("No IFRS asset bundle is attached to this job.")

        job.current_stage = "load_ifrs_requirements"
        job.progress_percent = 25
        job.save(update_fields=["current_stage", "progress_percent"])

        requirements_result = load_requirements_from_prefix(
            input_root=input_root,
            minio_prefix=job.ifrs_asset_bundle.minio_prefix,
        )

        if not job.style_asset_bundle:
            raise ValueError("No style asset bundle is attached to this job.")

        job.current_stage = "load_style_assets"
        job.progress_percent = 35
        job.save(update_fields=["current_stage", "progress_percent"])

        style_result = load_style_assets_from_prefix(
            input_root=input_root,
            minio_prefix=job.style_asset_bundle.minio_prefix,
        )

        job.current_stage = "build_evidence_maps"
        job.progress_percent = 55
        job.save(update_fields=["current_stage", "progress_percent"])

        evidence_result = build_evidence_maps(
            payload_result=payload_result,
            requirements_result=requirements_result,
        )

        job.current_stage = "build_coverage_and_missing_register"
        job.progress_percent = 62
        job.save(update_fields=["current_stage", "progress_percent"])

        coverage_result = build_coverage_summary(
            evidence_result=evidence_result,
        )

        missing_result = build_missing_requirements_register(
            evidence_result=evidence_result,
        )

        job.current_stage = "build_disclosure_plans"
        job.progress_percent = 68
        job.save(update_fields=["current_stage", "progress_percent"])

        disclosure_plan_result = build_disclosure_plans(
            evidence_result=evidence_result,
        )

        job.current_stage = "build_writer_contexts"
        job.progress_percent = 72
        job.save(update_fields=["current_stage", "progress_percent"])

        writer_context_result = build_writer_contexts(
            disclosure_plan_result=disclosure_plan_result,
            style_result=style_result,
        )

        job.current_stage = "build_section_drafts"
        job.progress_percent = 78
        job.save(update_fields=["current_stage", "progress_percent"])

        section_draft_result = build_section_drafts(
            writer_context_result=writer_context_result,
        )

        job.current_stage = "assemble_draft_report"
        job.progress_percent = 84
        job.save(update_fields=["current_stage", "progress_percent"])

        draft_report_result = assemble_draft_report(
            section_draft_result=section_draft_result,
            bank_name=job.bank.name,
            reporting_year=job.reporting_year,
        )

        job.current_stage = "run_deterministic_validation"
        job.progress_percent = 86
        job.save(update_fields=["current_stage", "progress_percent"])

        deterministic_validation_result = run_deterministic_validation_gates(
            markdown=draft_report_result.markdown,
        )

        job.current_stage = "run_fake_pipeline"
        job.progress_percent = 90
        job.save(update_fields=["current_stage", "progress_percent"])

        result = run_fake_pipeline(
            job_id=str(job.id),
            bank_name=job.bank.name,
            reporting_year=job.reporting_year,
            payload_result=payload_result,
            requirements_result=requirements_result,
            style_result=style_result,
            evidence_result=evidence_result,
        )

        primary_report_markdown = draft_report_result.markdown

        result.final_summary["coverage_summary"] = coverage_result.coverage_summary[
            "overall"
        ]

        result.final_summary["missing_requirements_summary"] = (
            missing_result.missing_register["summary"]
        )

        result.final_summary["disclosure_plan_summary"] = (
            disclosure_plan_result.summary
        )

        result.final_summary["writer_context_summary"] = (
            writer_context_result.summary
        )

        result.final_summary["section_draft_summary"] = (
            section_draft_result.summary
        )

        result.final_summary["draft_report_summary"] = (
            draft_report_result.summary
        )

        result.final_summary["deterministic_validation_summary"] = (
            deterministic_validation_result.summary
        )

        result.final_summary["primary_report_source"] = {
            "source": "assembled_draft_report",
            "llm_used": False,
            "status": "draft",
            "note": (
                "The main downloadable Markdown report is currently assembled from "
                "deterministic section drafts. It will later be replaced by the "
                "LLM-generated validated report."
            ),
        }

        result.final_summary["missing_data_policy"] = {
            "report_policy": "do_not_mention_missing_data_in_generated_report",
            "scoring_policy": "do_not_reduce_section_score",
            "workflow_impact": "warning_only",
        }

        with transaction.atomic():
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

            all_warnings = [
                *result.warnings,
                *coverage_result.warnings,
                *missing_result.warnings,
                *disclosure_plan_result.warnings,
                *writer_context_result.warnings,
                *section_draft_result.warnings,
                *draft_report_result.warnings,
                *deterministic_validation_result.warnings,
            ]

            warning_count = len(all_warnings)

            result.warning_summary = {
                "job_id": str(job.id),
                "status": (
                    "completed_with_warnings"
                    if warning_count > 0
                    else "completed"
                ),
                "warning_count": warning_count,
                "warnings": [
                    {
                        "stage": warning.stage,
                        "warning_type": warning.warning_type,
                        "message": warning.message,
                        "details": warning.details,
                    }
                    for warning in all_warnings
                ],
            }

            for warning in all_warnings:
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
                object_key=f"jobs/{job.id}/final/report_markdown.md",
                text=primary_report_markdown,
                content_type="text/markdown",
            )

            save_json_artifact(
                job=job,
                report_version=report_version,
                artifact_type=ReportArtifact.ArtifactType.WARNING_SUMMARY,
                object_key=f"jobs/{job.id}/warnings/warning_summary.json",
                data=result.warning_summary,
            )

            evidence_maps = evidence_result.evidence_maps["maps"]
            evidence_summaries = evidence_result.evidence_maps["summaries"]
            file_slugs = evidence_result.evidence_maps["file_slugs"]

            for section_key, section_map in evidence_maps.items():
                file_slug = file_slugs[section_key]

                save_json_artifact(
                    job=job,
                    report_version=report_version,
                    artifact_type=ReportArtifact.ArtifactType.EVIDENCE_MAP,
                    object_key=(
                        f"jobs/{job.id}/evidence_maps/"
                        f"evidence_map_{file_slug}.json"
                    ),
                    data=section_map,
                )

                save_json_artifact(
                    job=job,
                    report_version=report_version,
                    artifact_type=ReportArtifact.ArtifactType.LOG,
                    object_key=(
                        f"jobs/{job.id}/evidence_maps/"
                        f"evidence_map_summary_{file_slug}.json"
                    ),
                    data=evidence_summaries[section_key],
                )

            save_json_artifact(
                job=job,
                report_version=report_version,
                artifact_type=ReportArtifact.ArtifactType.LOG,
                object_key=f"jobs/{job.id}/logs/evidence_summary.json",
                data=evidence_result.summary,
            )

            save_json_artifact(
                job=job,
                report_version=report_version,
                artifact_type=ReportArtifact.ArtifactType.COVERAGE,
                object_key=f"jobs/{job.id}/coverage/coverage_summary.json",
                data=coverage_result.coverage_summary,
            )

            save_json_artifact(
                job=job,
                report_version=report_version,
                artifact_type=ReportArtifact.ArtifactType.MISSING_REQUIREMENTS,
                object_key=f"jobs/{job.id}/missing/missing_requirements_register.json",
                data=missing_result.missing_register,
            )

            for section_key, plan in disclosure_plan_result.plans.items():
                file_slug = plan["file_slug"]

                save_json_artifact(
                    job=job,
                    report_version=report_version,
                    artifact_type=ReportArtifact.ArtifactType.DISCLOSURE_PLAN,
                    object_key=(
                        f"jobs/{job.id}/disclosure_plans/"
                        f"disclosure_plan_{file_slug}.json"
                    ),
                    data=plan,
                )

            save_json_artifact(
                job=job,
                report_version=report_version,
                artifact_type=ReportArtifact.ArtifactType.LOG,
                object_key=(
                    f"jobs/{job.id}/disclosure_plans/"
                    "disclosure_plan_summary.json"
                ),
                data=disclosure_plan_result.summary,
            )

            for section_key, context in writer_context_result.contexts.items():
                file_slug = context["file_slug"]

                save_json_artifact(
                    job=job,
                    report_version=report_version,
                    artifact_type=ReportArtifact.ArtifactType.LOG,
                    object_key=(
                        f"jobs/{job.id}/writer_contexts/"
                        f"writer_context_{file_slug}.json"
                    ),
                    data=context,
                )

            save_json_artifact(
                job=job,
                report_version=report_version,
                artifact_type=ReportArtifact.ArtifactType.LOG,
                object_key=(
                    f"jobs/{job.id}/writer_contexts/"
                    "writer_context_summary.json"
                ),
                data=writer_context_result.summary,
            )

            for section_key, draft in section_draft_result.drafts.items():
                file_slug = draft["file_slug"]

                save_text_artifact(
                    job=job,
                    report_version=report_version,
                    artifact_type=ReportArtifact.ArtifactType.DRAFT_SECTION,
                    object_key=(
                        f"jobs/{job.id}/draft_sections/"
                        f"draft_{file_slug}.md"
                    ),
                    text=draft["markdown"],
                    content_type="text/markdown",
                )

            save_json_artifact(
                job=job,
                report_version=report_version,
                artifact_type=ReportArtifact.ArtifactType.LOG,
                object_key=(
                    f"jobs/{job.id}/draft_sections/"
                    "draft_sections_summary.json"
                ),
                data=section_draft_result.summary,
            )

            save_text_artifact(
                job=job,
                report_version=report_version,
                artifact_type=ReportArtifact.ArtifactType.LOG,
                object_key=f"jobs/{job.id}/draft_report/full_draft_report.md",
                text=draft_report_result.markdown,
                content_type="text/markdown",
            )

            save_json_artifact(
                job=job,
                report_version=report_version,
                artifact_type=ReportArtifact.ArtifactType.LOG,
                object_key=f"jobs/{job.id}/draft_report/full_draft_report_summary.json",
                data=draft_report_result.summary,
            )

            save_json_artifact(
                job=job,
                report_version=report_version,
                artifact_type=ReportArtifact.ArtifactType.VALIDATION_RESULT,
                object_key=(
                    f"jobs/{job.id}/validation/"
                    "deterministic_validation_result.json"
                ),
                data={
                    "summary": deterministic_validation_result.summary,
                    "checks": deterministic_validation_result.checks,
                },
            )

            save_json_artifact(
                job=job,
                report_version=report_version,
                artifact_type=ReportArtifact.ArtifactType.LOG,
                object_key=f"jobs/{job.id}/logs/input_summary.json",
                data=result.input_summary,
            )

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