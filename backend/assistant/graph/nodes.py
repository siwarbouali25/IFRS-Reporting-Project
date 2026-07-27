"""
Explicit ReAct loop as LangGraph nodes:

    START -> agent -> (tool_calls?) -> tools -> agent -> ... -> END

The agent node calls the model with the tool schemas. If the model asks for
tool calls, the tools node executes them against the payload repository and
appends the results; otherwise we finish. A deterministic fallback keeps the
turn useful if the provider is unavailable but tools already returned data.
"""

from __future__ import annotations

import json
import logging

from ..llm import LLMUnavailable, chat_with_tools, get_client_and_model
from ..repository import PayloadRepository
from ..tools import TOOL_SCHEMAS, dispatch
from .state import AssistantGraphState

logger = logging.getLogger(__name__)


def _message_to_dict(msg) -> dict:
    """Normalise an OpenAI SDK message object into a plain dict for state."""
    out: dict = {"role": "assistant", "content": msg.content or ""}
    if getattr(msg, "tool_calls", None):
        out["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.function.name, "arguments": tc.function.arguments},
            }
            for tc in msg.tool_calls
        ]
    return out


def agent_node(state: AssistantGraphState) -> dict:
    try:
        _, model = get_client_and_model()
    except LLMUnavailable:
        model = "unavailable"

    try:
        msg = chat_with_tools(state["messages"], TOOL_SCHEMAS)
    except LLMUnavailable as exc:
        logger.warning("LLM unavailable, using deterministic fallback: %s", exc)
        return _fallback(state)

    assistant_dict = _message_to_dict(msg)
    return {
        "messages": state["messages"] + [assistant_dict],
        "iterations": state.get("iterations", 0) + 1,
        "model_used": model,
        "answer": assistant_dict["content"],
    }


def tools_node(state: AssistantGraphState) -> dict:
    repo = PayloadRepository()
    bank_scope = state.get("bank_scope")
    last = state["messages"][-1]
    tool_messages = []
    citations = list(state.get("citations", []))

    for call in last.get("tool_calls", []):
        name = call["function"]["name"]
        try:
            args = json.loads(call["function"]["arguments"] or "{}")
        except json.JSONDecodeError:
            args = {}
        result = dispatch(name, args, repo, bank_scope=bank_scope)

        if result.get("ok") and result.get("provenance"):
            citations.append(
                {
                    "tool": name,
                    "provenance": result["provenance"],
                    "data_gaps": result.get("data_gaps", []),
                }
            )

        tool_messages.append(
            {
                "role": "tool",
                "tool_call_id": call["id"],
                "content": json.dumps(result, default=str),
            }
        )

    return {
        "messages": state["messages"] + tool_messages,
        "citations": citations,
    }


def should_continue(state: AssistantGraphState) -> str:
    last = state["messages"][-1]
    if state.get("iterations", 0) >= state.get("max_iterations", 5):
        return "end"
    if last.get("role") == "assistant" and last.get("tool_calls"):
        return "tools"
    return "end"


def _fallback(state: AssistantGraphState) -> dict:
    """
    Provider is down. If tools already produced data this turn, summarise it
    plainly instead of erroring, consistent with the platform's deterministic
    fallback philosophy.
    """
    facts = []
    for msg in state["messages"]:
        if msg.get("role") == "tool":
            try:
                payload = json.loads(msg["content"])
            except (json.JSONDecodeError, TypeError):
                continue
            if payload.get("ok"):
                facts.append(payload.get("data"))

    if facts:
        answer = (
            "The language model is temporarily unavailable, but here is the "
            "retrieved data:\n\n" + json.dumps(facts, indent=2, default=str)
        )
    else:
        answer = (
            "The assistant is temporarily unavailable. Please retry shortly."
        )
    return {"answer": answer, "is_fallback": True, "model_used": "fallback"}
