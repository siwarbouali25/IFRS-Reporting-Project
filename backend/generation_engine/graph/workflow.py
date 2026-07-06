from langgraph.graph import END, START, StateGraph

from generation_engine.graph.nodes import (
    assemble_report_node,
    build_disclosure_plans_node,
    build_writer_contexts_node,
    deterministic_validation_node,
    final_summary_node,
    generate_sections_node,
    load_inputs_node,
    run_notebook_evidence_node,
)
from generation_engine.graph.state import IFRSReportGraphState


def build_ifrs_report_graph():
    graph = StateGraph(IFRSReportGraphState)

    graph.add_node("load_inputs", load_inputs_node)

    # Real notebook evidence stage.
    # This replaces:
    # - build_evidence_maps_node
    # - build_coverage_and_missing_node
    graph.add_node("notebook_evidence", run_notebook_evidence_node)

    graph.add_node("build_disclosure_plans", build_disclosure_plans_node)
    graph.add_node("build_writer_contexts", build_writer_contexts_node)
    graph.add_node("generate_sections", generate_sections_node)
    graph.add_node("assemble_report", assemble_report_node)
    graph.add_node("deterministic_validation", deterministic_validation_node)
    graph.add_node("final_summary", final_summary_node)

    graph.add_edge(START, "load_inputs")
    graph.add_edge("load_inputs", "notebook_evidence")
    graph.add_edge("notebook_evidence", "build_disclosure_plans")
    graph.add_edge("build_disclosure_plans", "build_writer_contexts")
    graph.add_edge("build_writer_contexts", "generate_sections")
    graph.add_edge("generate_sections", "assemble_report")
    graph.add_edge("assemble_report", "deterministic_validation")
    graph.add_edge("deterministic_validation", "final_summary")
    graph.add_edge("final_summary", END)

    return graph.compile()


def run_ifrs_report_graph(initial_state: IFRSReportGraphState):
    app = build_ifrs_report_graph()
    return app.invoke(initial_state)