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


def load_inputs_node(state):
    payload_result = load_payloads_from_prefix(
        input_root=state["input_root"],
        minio_prefix=state["payload_prefix"],
        bank_code=state["bank_code"],
    )

    requirements_result = load_requirements_from_prefix(
        input_root=state["input_root"],
        minio_prefix=state["ifrs_asset_prefix"],
    )

    style_result = load_style_assets_from_prefix(
        input_root=state["input_root"],
        minio_prefix=state["style_asset_prefix"],
    )

    return {
        "payload_result": payload_result,
        "requirements_result": requirements_result,
        "style_result": style_result,
    }


def build_evidence_maps_node(state):
    evidence_result = build_evidence_maps(
        payload_result=state["payload_result"],
        requirements_result=state["requirements_result"],
    )

    return {
        "evidence_result": evidence_result,
    }


def build_coverage_and_missing_node(state):
    coverage_result = build_coverage_summary(
        evidence_result=state["evidence_result"],
    )

    missing_result = build_missing_requirements_register(
        evidence_result=state["evidence_result"],
    )

    return {
        "coverage_result": coverage_result,
        "missing_result": missing_result,
    }


def build_disclosure_plans_node(state):
    disclosure_plan_result = build_disclosure_plans(
        evidence_result=state["evidence_result"],
    )

    return {
        "disclosure_plan_result": disclosure_plan_result,
    }


def build_writer_contexts_node(state):
    writer_context_result = build_writer_contexts(
        disclosure_plan_result=state["disclosure_plan_result"],
        style_result=state["style_result"],
    )

    return {
        "writer_context_result": writer_context_result,
    }


def generate_sections_node(state):
    section_draft_result = build_section_drafts(
        writer_context_result=state["writer_context_result"],
    )

    return {
        "section_draft_result": section_draft_result,
    }


def assemble_report_node(state):
    draft_report_result = assemble_draft_report(
        section_draft_result=state["section_draft_result"],
        bank_name=state["bank_name"],
        reporting_year=state["reporting_year"],
    )

    return {
        "draft_report_result": draft_report_result,
        "final_markdown": draft_report_result.markdown,
    }


def deterministic_validation_node(state):
    deterministic_validation_result = run_deterministic_validation_gates(
        markdown=state["final_markdown"],
    )

    return {
        "deterministic_validation_result": deterministic_validation_result,
    }


def final_summary_node(state):
    warnings = []

    for key in [
        "coverage_result",
        "missing_result",
        "disclosure_plan_result",
        "writer_context_result",
        "section_draft_result",
        "draft_report_result",
        "deterministic_validation_result",
    ]:
        result = state.get(key)
        if result and hasattr(result, "warnings"):
            warnings.extend(result.warnings)

    final_summary = {
        "bank_code": state["bank_code"],
        "bank_name": state["bank_name"],
        "reporting_year": state["reporting_year"],
        "writer_mode": state.get("writer_mode", "deterministic"),
        "coverage_summary": state["coverage_result"].coverage_summary["overall"],
        "missing_requirements_summary": state["missing_result"].missing_register[
            "summary"
        ],
        "disclosure_plan_summary": state["disclosure_plan_result"].summary,
        "writer_context_summary": state["writer_context_result"].summary,
        "section_draft_summary": state["section_draft_result"].summary,
        "draft_report_summary": state["draft_report_result"].summary,
        "deterministic_validation_summary": state[
            "deterministic_validation_result"
        ].summary,
        "missing_data_policy": {
            "report_policy": "do_not_mention_missing_data_in_generated_report",
            "scoring_policy": "do_not_reduce_section_score",
            "workflow_impact": "warning_only",
        },
    }

    return {
        "warnings": warnings,
        "final_summary": final_summary,
    }