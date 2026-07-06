from typing import Any, TypedDict


class IFRSReportGraphState(TypedDict, total=False):
    job_id: str
    bank_code: str
    bank_name: str
    reporting_year: int

    input_root: str
    payload_prefix: str
    ifrs_asset_prefix: str
    style_asset_prefix: str

    writer_mode: str

    # Loader / notebook input outputs
    payload_result: Any
    requirements_result: Any
    style_result: Any

    requirements_by_section: Any
    payloads_by_section: Any

    # Evidence outputs
    evidence_result: Any
    coverage_result: Any
    missing_result: Any

    evidence_maps_by_section: Any
    evidence_map_summaries: Any
    coverage_by_section: Any
    missing_registers_by_section: Any

    # Planning / writing outputs
    disclosure_plan_result: Any
    writer_context_result: Any
    section_draft_result: Any
    draft_report_result: Any

    plans_by_section: Any
    section_results: Any

    # QA / validation outputs
    deterministic_validation_result: Any
    quality_refinement_result: Any
    final_quality_result: Any
    final_editorial_result: Any
    connectivity_result: Any

    # Final report outputs
    final_markdown: str
    final_markdown_path: str
    handoff_manifest: Any
    audit_summary: Any

    # Final API-compatible fields
    final_summary: dict[str, Any]
    warnings: list[Any]
    artifacts: dict[str, Any]

    # Debug metadata
    notebook_full_output_dir: str
    notebook_full_executed_cells: list[str]
    notebook_full_executed_cells_count: int