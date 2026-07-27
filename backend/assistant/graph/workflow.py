from functools import lru_cache

from langgraph.graph import END, START, StateGraph

from .nodes import agent_node, should_continue, tools_node
from .state import AssistantGraphState


def build_assistant_graph():
    graph = StateGraph(AssistantGraphState)

    graph.add_node("agent", agent_node)
    graph.add_node("tools", tools_node)

    graph.add_edge(START, "agent")
    graph.add_conditional_edges(
        "agent",
        should_continue,
        {"tools": "tools", "end": END},
    )
    graph.add_edge("tools", "agent")

    return graph.compile()


@lru_cache(maxsize=1)
def get_assistant_graph():
    """Compiled graph is stateless across turns, so compile once."""
    return build_assistant_graph()
