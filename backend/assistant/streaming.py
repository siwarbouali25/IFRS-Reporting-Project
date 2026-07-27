"""
Streaming turn orchestration for SSE.

Mirrors agent.run_turn but instead of running the compiled graph to completion,
it walks the ReAct loop manually so it can stream tokens as the model writes
them and emit status events while tools run. Grounding, tool dispatch, bank
scoping and citations are identical to the non-streaming path -- only delivery
differs. The full assistant Message is persisted at the end for audit.

Event shapes yielded (each becomes one SSE `data:` line):
    {"type": "status",    "text": "Looking up emissions..."}
    {"type": "token",     "text": "partial answer chunk"}
    {"type": "citations", "citations": [...]}
    {"type": "done",      "conversation_id": "...", "message_id": "...",
                           "model_used": "...", "is_fallback": false}
    {"type": "error",     "message": "..."}
"""

from __future__ import annotations

import json
import logging
from typing import Iterator

from .agent import MAX_ITERATIONS, _history_to_messages
from .llm import LLMUnavailable, get_client_and_model
from .models import Conversation, Message
from .repository import PayloadRepository
from .tools import TOOL_SCHEMAS, dispatch

logger = logging.getLogger(__name__)


_STATUS_LABELS = {
    "list_available_banks": "Listing available banks…",
    "get_kpi": "Reading reporting KPIs…",
    "get_emissions": "Looking up emissions…",
    "list_targets": "Fetching climate targets…",
    "get_financed_emissions_breakdown": "Aggregating financed emissions…",
    "get_governance": "Reading governance data…",
    "get_climate_risks": "Reviewing climate risks…",
    "get_data_gaps": "Checking declared data gaps…",
    "compare_banks": "Comparing banks…",
    "search_report_text": "Searching report narrative…",
}


def _status_for(name: str) -> str:
    return _STATUS_LABELS.get(name, "Retrieving data…")


def run_turn_streamed(
    conversation: Conversation, user_text: str
) -> Iterator[dict]:
    # Persist the user turn first (same as run_turn).
    Message.objects.create(
        conversation=conversation,
        role=Message.Role.USER,
        content=user_text,
    )

    messages = _history_to_messages(conversation)
    messages.append({"role": "user", "content": user_text})

    bank_scope = conversation.bank.code if conversation.bank_id else None
    repo = PayloadRepository()

    try:
        client, model = get_client_and_model()
    except LLMUnavailable as exc:
        yield from _fallback_stream(conversation, str(exc))
        return

    citations: list[dict] = []
    answer_parts: list[str] = []

    try:
        for _ in range(MAX_ITERATIONS):
            stream = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=TOOL_SCHEMAS,
                tool_choice="auto",
                temperature=0.1,
                stream=True,
            )

            content_buf: list[str] = []
            tool_acc: dict[int, dict] = {}

            for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta

                if getattr(delta, "content", None):
                    content_buf.append(delta.content)
                    answer_parts.append(delta.content)
                    yield {"type": "token", "text": delta.content}

                for tc in getattr(delta, "tool_calls", None) or []:
                    slot = tool_acc.setdefault(
                        tc.index, {"id": None, "name": "", "args": ""}
                    )
                    if tc.id:
                        slot["id"] = tc.id
                    if tc.function and tc.function.name:
                        slot["name"] = tc.function.name
                    if tc.function and tc.function.arguments:
                        slot["args"] += tc.function.arguments

            # No tool calls this pass -> the prose we streamed is the answer.
            if not tool_acc:
                break

            # Record the assistant tool-call turn, then execute the tools.
            messages.append(
                {
                    "role": "assistant",
                    "content": "".join(content_buf),
                    "tool_calls": [
                        {
                            "id": s["id"],
                            "type": "function",
                            "function": {
                                "name": s["name"],
                                "arguments": s["args"],
                            },
                        }
                        for s in tool_acc.values()
                    ],
                }
            )

            for s in tool_acc.values():
                yield {"type": "status", "text": _status_for(s["name"])}
                try:
                    args = json.loads(s["args"] or "{}")
                except json.JSONDecodeError:
                    args = {}
                result = dispatch(s["name"], args, repo, bank_scope=bank_scope)

                if result.get("ok") and result.get("provenance"):
                    citations.append(
                        {
                            "tool": s["name"],
                            "provenance": result["provenance"],
                            "data_gaps": result.get("data_gaps", []),
                        }
                    )

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": s["id"],
                        "content": json.dumps(result, default=str),
                    }
                )
            # loop continues: next pass streams the grounded prose

    except LLMUnavailable as exc:
        logger.warning("Streaming provider error: %s", exc)
        # If tools already produced data, keep it; otherwise fall back.
        if not answer_parts:
            yield from _fallback_stream(conversation, str(exc), citations)
            return
    except Exception as exc:  # defensive: never leak a raw 500 mid-stream
        logger.exception("Unexpected streaming error")
        yield {"type": "error", "message": "The assistant hit an error."}

    answer_text = "".join(answer_parts).strip()
    msg = Message.objects.create(
        conversation=conversation,
        role=Message.Role.ASSISTANT,
        content=answer_text,
        citations=citations,
        model_used=model,
        is_fallback=False,
    )
    conversation.save(update_fields=["updated_at"])

    if citations:
        yield {"type": "citations", "citations": citations}
    yield {
        "type": "done",
        "conversation_id": str(conversation.id),
        "message_id": str(msg.id),
        "model_used": model,
        "is_fallback": False,
    }


def _fallback_stream(
    conversation: Conversation,
    reason: str,
    citations: list[dict] | None = None,
) -> Iterator[dict]:
    """Provider unavailable at start: emit a plain notice, persist, close."""
    text = (
        "The assistant is temporarily unavailable. Please retry shortly."
    )
    yield {"type": "token", "text": text}
    msg = Message.objects.create(
        conversation=conversation,
        role=Message.Role.ASSISTANT,
        content=text,
        citations=citations or [],
        model_used="fallback",
        is_fallback=True,
    )
    conversation.save(update_fields=["updated_at"])
    yield {
        "type": "done",
        "conversation_id": str(conversation.id),
        "message_id": str(msg.id),
        "model_used": "fallback",
        "is_fallback": True,
    }
