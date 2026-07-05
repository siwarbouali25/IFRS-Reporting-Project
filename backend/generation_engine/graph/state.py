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

    payload_result: Any
    requirements_result: Any
    style_result: Any

    evidence_result: Any
    coverage_result: Any
    missing_result: Any
    disclosure_plan_result: Any
    writer_context_result: Any

    section_draft_result: Any
    draft_report_result: Any
    deterministic_validation_result: Any

    final_markdown: str
    final_summary: dict[str, Any]
    warnings: list[Any]
    artifacts: dict[str, Any]