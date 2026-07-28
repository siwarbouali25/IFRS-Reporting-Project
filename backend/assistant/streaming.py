"""
Reliable SSE orchestration for an OpenAI-compatible model that supports only
one tool call per assistant turn.

The browser still receives SSE status/token/citation/done events. The upstream
provider call is non-streaming to avoid provider-side socket resets.
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
    """Split a completed answer into small whitespace-preserving SSE chunks."""
    buffer = ""

    for token in re.findall(r"\S+\s*", text):
        buffer += token
        if len(buffer) >= target_size:
            yield buffer
            buffer = ""

    if buffer:
        yield buffer


def _single_tool_call_message(call, content: str = "") -> dict:
    """Create an OpenAI assistant message containing exactly one tool call."""
    return {
        "role": "assistant",
        "content": content,
        "tool_calls": [
            {
                "id": call.id,
                "type": "function",
                "function": {
                    "name": call.function.name,
                    "arguments": call.function.arguments or "{}",
                },
            }
        ],
    }


def run_turn_streamed(
    conversation: Conversation,
    user_text: str,
) -> Iterator[dict]:
    # Build model history before saving this user message; otherwise the current
    # message is replayed by _history_to_messages and then appended a second time.
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
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=TOOL_SCHEMAS,
                tool_choice="auto",
                parallel_tool_calls=False,
                temperature=0.1,
                stream=False,
            )

            assistant = response.choices[0].message
            returned_tool_calls = list(assistant.tool_calls or [])

            if not returned_tool_calls:
                answer_text = (assistant.content or "").strip()
                break

            # The selected NIM model accepts only one tool call in each assistant
            # message. Even if the provider ignores parallel_tool_calls=False,
            # keep only the first call and let the next ReAct iteration request
            # another tool if needed.
            if len(returned_tool_calls) > 1:
                logger.warning(
                    "Provider returned %s tool calls; executing only the first "
                    "because the model supports one tool call per turn.",
                    len(returned_tool_calls),
                )

            call = returned_tool_calls[0]
            tool_name = call.function.name

            messages.append(
                _single_tool_call_message(
                    call,
                    assistant.content or "",
                )
            )

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
        "request failed. Please retry shortly."
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
