"""
Reliable SSE delivery for the assistant.

The upstream LLM call is intentionally non-streaming because some OpenAI-
compatible providers can reset long-lived streaming connections on Windows
(httpx.ReadError / WinError 10054), especially during tool-calling turns.

The browser still receives a real SSE response:
- an immediate status event opens the connection;
- tool status events are sent between ReAct steps;
- the final grounded answer is emitted in small token-like chunks;
- citations and the done event are emitted at the end.

This keeps the UI responsive without depending on upstream token streaming.
"""

from __future__ import annotations

import json
import logging
import re
import time
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


def _text_chunks(text: str, target_size: int = 28) -> Iterator[str]:
    """Split text into small whitespace-preserving chunks."""
    buffer = ""

    for token in re.findall(r"\S+\s*", text):
        buffer += token
        if len(buffer) >= target_size:
            yield buffer
            buffer = ""

    if buffer:
        yield buffer


def _serialise_tool_calls(tool_calls) -> list[dict]:
    serialised = []

    for call in tool_calls or []:
        serialised.append(
            {
                "id": call.id,
                "type": "function",
                "function": {
                    "name": call.function.name,
                    "arguments": call.function.arguments or "{}",
                },
            }
        )

    return serialised


def run_turn_streamed(
    conversation: Conversation,
    user_text: str,
) -> Iterator[dict]:
    # Build history before persisting the new user turn. Otherwise the newest
    # user message is included by _history_to_messages and appended twice.
    messages = _history_to_messages(conversation)
    messages.append({"role": "user", "content": user_text})

    Message.objects.create(
        conversation=conversation,
        role=Message.Role.USER,
        content=user_text,
    )

    bank_scope = conversation.bank.code if conversation.bank_id else None
    repo = PayloadRepository()

    yield {
        "type": "status",
        "text": "Analyzing your question…",
    }

    try:
        client, model = get_client_and_model()
    except LLMUnavailable as exc:
        yield from _fallback_stream(conversation, str(exc))
        return

    citations: list[dict] = []
    answer_text = ""

    try:
        for _ in range(MAX_ITERATIONS):
            # Non-streaming upstream avoids provider-side socket resets while
            # preserving SSE streaming to the browser.
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=TOOL_SCHEMAS,
                tool_choice="auto",
                temperature=0.1,
                stream=False,
            )

            assistant = response.choices[0].message
            tool_calls = assistant.tool_calls or []

            if not tool_calls:
                answer_text = (assistant.content or "").strip()
                break

            messages.append(
                {
                    "role": "assistant",
                    "content": assistant.content or "",
                    "tool_calls": _serialise_tool_calls(tool_calls),
                }
            )

            for call in tool_calls:
                tool_name = call.function.name
                yield {
                    "type": "status",
                    "text": _status_for(tool_name),
                }

                try:
                    arguments = json.loads(
                        call.function.arguments or "{}"
                    )
                except json.JSONDecodeError:
                    arguments = {}

                result = dispatch(
                    tool_name,
                    arguments,
                    repo,
                    bank_scope=bank_scope,
                )

                if result.get("ok") and result.get("provenance"):
                    citations.append(
                        {
                            "tool": tool_name,
                            "provenance": result["provenance"],
                            "data_gaps": result.get("data_gaps", []),
                        }
                    )

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(result, default=str),
                    }
                )
        else:
            answer_text = (
                "I could not complete the grounded tool workflow within "
                "the allowed number of steps."
            )

    except Exception as exc:
        logger.exception("Assistant provider/tool error")
        yield from _fallback_stream(
            conversation,
            str(exc),
            citations=citations,
        )
        return

    if not answer_text:
        answer_text = (
            "The requested information is not available in the retrieved data."
        )

    # Emit token-like SSE chunks. The short delay prevents WSGI/browser layers
    # from coalescing the entire answer into one visible update.
    for chunk in _text_chunks(answer_text):
        yield {"type": "token", "text": chunk}
        time.sleep(0.015)

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
        yield {
            "type": "citations",
            "citations": citations,
        }

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
    logger.warning("Assistant fallback used: %s", reason)

    text = (
        "The assistant is temporarily unavailable because the model provider "
        "connection failed. Please retry shortly."
    )

    for chunk in _text_chunks(text):
        yield {"type": "token", "text": chunk}
        time.sleep(0.015)

    msg = Message.objects.create(
        conversation=conversation,
        role=Message.Role.ASSISTANT,
        content=text,
        citations=citations or [],
        model_used="fallback",
        is_fallback=True,
    )
    conversation.save(update_fields=["updated_at"])

    if citations:
        yield {
            "type": "citations",
            "citations": citations,
        }

    yield {
        "type": "done",
        "conversation_id": str(conversation.id),
        "message_id": str(msg.id),
        "model_used": "fallback",
        "is_fallback": True,
    }
