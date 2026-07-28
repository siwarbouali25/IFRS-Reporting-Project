from pathlib import Path

from django.conf import settings

from generation_engine.notebook_port.evidence_bridge import (
    run_notebook_full_generation_stage,
)


def load_inputs_node(state: dict) -> dict:
    """
    Validate the routing information required by the
    notebook bridge.
    """

    required_keys = [
        "job_id",
        "bank_code",
        "reporting_year",
        "payload_dir",
        "ifrs_asset_prefix",
        "style_asset_prefix",
    ]

    missing = [
        key
        for key in required_keys
        if not state.get(key)
    ]

    if missing:
        raise ValueError(
            "Missing required LangGraph initial state "
            "keys: "
            + ", ".join(missing)
        )

    payload_dir = Path(state["payload_dir"]).resolve()

    if not payload_dir.exists():
        raise FileNotFoundError(
            f"Payload directory not found: {payload_dir}"
        )

    return {
        **state,
        "payload_dir": str(payload_dir),
        "load_inputs_status": "validated",
    }


def run_full_notebook_generation_node(
    state: dict,
) -> dict:
    """
    Run the complete notebook generation pipeline using
    the payload directory produced by data preparation.
    """

    bank_code = state["bank_code"]
    reporting_year = state["reporting_year"]
    job_id = state["job_id"]

    output_dir = (
        Path(settings.BASE_DIR)
        / "debug_outputs"
        / "langgraph_full_notebook"
        / bank_code
        / str(reporting_year)
        / str(job_id)
    )

    result = run_notebook_full_generation_stage(
        notebook_path=Path(
            settings.IFRS_NOTEBOOK_PATH
        ),
        input_root=Path(
            settings.GENERATION_INPUT_ROOT
        ),
        payload_dir=Path(state["payload_dir"]),
        ifrs_asset_prefix=state[
            "ifrs_asset_prefix"
        ],
        style_asset_prefix=state[
            "style_asset_prefix"
        ],
        output_dir=output_dir,
        job_id=str(job_id),
    )

    final_summary = {
        "status": (
            "completed_with_notebook_bridge"
        ),
        "job_id": str(job_id),
        "bank_code": bank_code,
        "reporting_year": reporting_year,
        "payload_dir": str(
            Path(state["payload_dir"]).resolve()
        ),
        "output_dir": result["output_dir"],
        "final_markdown_path": result[
            "final_markdown_path"
        ],
        "executed_cells_count": result[
            "executed_cells_count"
        ],
        "stop_marker": result["stop_marker"],
    }

    return {
        **state,

        "requirements_by_section": result[
            "requirements_by_section"
        ],
        "payloads_by_section": result[
            "payloads_by_section"
        ],
        "evidence_maps_by_section": result[
            "evidence_maps_by_section"
        ],
        "evidence_map_summaries": result[
            "evidence_map_summaries"
        ],
        "coverage_by_section": result[
            "coverage_by_section"
        ],
        "missing_registers_by_section": result[
            "missing_registers_by_section"
        ],
        "plans_by_section": result[
            "plans_by_section"
        ],

        "section_results": result["section_results"],
        "quality_refinement_result": result[
            "quality_refinement_result"
        ],
        "final_quality_result": result[
            "final_quality_result"
        ],
        "final_editorial_result": result[
            "final_editorial_result"
        ],
        "connectivity_result": result[
            "connectivity_result"
        ],

        "final_markdown": result["final_markdown"],
        "final_markdown_path": result[
            "final_markdown_path"
        ],
        "handoff_manifest": result[
            "handoff_manifest"
        ],
        "audit_summary": result["audit_summary"],

        "final_summary": final_summary,
        "warnings": [],
        "artifacts": {
            "output_dir": result["output_dir"],
            "final_markdown_path": result[
                "final_markdown_path"
            ],
            "handoff_manifest": result[
                "handoff_manifest"
            ],
            "audit_summary": result[
                "audit_summary"
            ],
        },

        "notebook_full_output_dir": result[
            "output_dir"
        ],
        "notebook_full_executed_cells": result[
            "executed_cells"
        ],
        "notebook_full_executed_cells_count": result[
            "executed_cells_count"
        ],
    }