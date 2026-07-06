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

    # Existing loader results
    payload_result: Any
    requirements_result: Any
    style_result: Any

    # Existing pipeline result fields
    evidence_result: Any
    coverage_result: Any
    missing_result: Any
    disclosure_plan_result: Any
    writer_context_result: Any

    section_draft_result: Any
    draft_report_result: Any
    deterministic_validation_result: Any

    # Notebook evidence bridge outputs
    requirements_by_section: Any
    payloads_by_section: Any
    evidence_maps_by_section: Any
    evidence_map_summaries: Any
    coverage_by_section: Any
    missing_registers_by_section: Any
    section_slugs: Any

    notebook_evidence_output_dir: str
    notebook_evidence_executed_cells: list[str]
    notebook_evidence_executed_cells_count: int
    evidence_stage_status: str

    final_markdown: str
    final_summary: dict[str, Any]
    warnings: list[Any]
    artifacts: dict[str, Any]