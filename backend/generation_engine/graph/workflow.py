from langgraph.graph import END, START, StateGraph

from generation_engine.graph.nodes import (
    load_inputs_node,
    run_full_notebook_generation_node,
)
from generation_engine.graph.state import IFRSReportGraphState


def build_ifrs_report_graph():
    graph = StateGraph(IFRSReportGraphState)

    graph.add_node("load_inputs", load_inputs_node)
    graph.add_node("full_notebook_generation", run_full_notebook_generation_node)

    graph.add_edge(START, "load_inputs")
    graph.add_edge("load_inputs", "full_notebook_generation")
    graph.add_edge("full_notebook_generation", END)

    return graph.compile()


def run_ifrs_report_graph(initial_state: IFRSReportGraphState):
    app = build_ifrs_report_graph()
    return app.invoke(initial_state)