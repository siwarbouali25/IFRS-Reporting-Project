"""
LangGraph-compatible ReAct orchestration with genuine Azure SSE forwarding.

The browser connection remains Django SSE. Each ReAct model pass is sent to
AZURE_OPENAI_FAST_DEPLOYMENT_URL using the raw full-URL REST client from
assistant.llm:

Azure SSE -> Django StreamingHttpResponse -> Angular fetch reader

The model may request one tool per pass. The tool result is appended to the
conversation, and another streamed model pass begins until the final grounded
answer is produced.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Iterator

from .agent import (
    MAX_ITERATIONS,
    _history_to_messages,
)
from .llm import (
    AssistantMessage,
    AzureStreamInterrupted,
    LLMUnavailable,
    chat_with_tools,
    get_azure_fast_config,
    stream_chat_with_tools,
)
from .models import Conversation, Message
from .repository import PayloadRepository
from .tools import TOOL_SCHEMAS, dispatch

logger = logging.getLogger(__name__)


_STATUS_LABELS = {
    "list_available_banks": "Listing available banks…",
    "get_kpi": "Reading reporting KPIs…",
    "get_emissions": "Looking up emissions…",
    "list_targets": "Fetching climate targets…",
    "get_financed_emissions_breakdown": (
        "Aggregating financed emissions…"
    ),
    "get_governance": "Reading governance data…",
    "get_climate_risks": "Reviewing climate risks…",
    "get_data_gaps": "Checking declared data gaps…",
    "compare_banks": "Comparing banks…",
    "search_report_text": "Searching report narrative…",
}


def _status_for(tool_name: str) -> str:
    return _STATUS_LABELS.get(
        tool_name,
        "Retrieving data…",
    )


def _text_chunks(
    text: str,
    target_size: int = 28,
) -> Iterator[str]:
    buffer = ""

    for token in re.findall(r"\S+\s*", text):
        buffer += token
        if len(buffer) >= target_size:
            yield buffer
            buffer = ""

    if buffer:
        yield buffer


def _assistant_message_dict(
    message: AssistantMessage,
) -> dict:
    return {
        "role": "assistant",
        "content": message.content or "",
        "tool_calls": [
            call.model_dump()
            for call in message.tool_calls
        ],
    }


def _fallback_provider_turn(
    messages: list[dict],
) -> AssistantMessage:
    """
    If an upstream SSE socket is interrupted, retry the current model pass as a
    normal REST completion. The outer Django response remains open.
    """

    return chat_with_tools(
        messages,
        TOOL_SCHEMAS,
    )


def run_turn_streamed(
    conversation: Conversation,
    user_text: str,
) -> Iterator[dict]:
    """
    Run one assistant turn and yield Angular-facing SSE event objects.
    """

    # Build history before saving the current user message. Saving first would
    # replay it from the database and then append it a second time.
    messages = _history_to_messages(
        conversation
    )
    messages.append(
        {
            "role": "user",
            "content": user_text,
        }
    )

    Message.objects.create(
        conversation=conversation,
        role=Message.Role.USER,
        content=user_text,
    )

    bank_scope = (
        conversation.bank.code
        if conversation.bank_id
        else None
    )
    repository = PayloadRepository()

    citations: list[dict] = []
    final_answer = ""
    model_used = (
        get_azure_fast_config().model_label
    )

    yield {
        "type": "status",
        "text": "Analyzing your question…",
    }

    try:
        for _iteration in range(
            MAX_ITERATIONS
        ):
            assistant_message: (
                AssistantMessage | None
            ) = None
            streamed_text = ""
            used_real_sse = False

            try:
                for event in stream_chat_with_tools(
                    messages,
                    TOOL_SCHEMAS,
                ):
                    if event["type"] == "content_delta":
                        text = event["text"]
                        streamed_text += text
                        yield {
                            "type": "token",
                            "text": text,
                        }

                    elif event["type"] == "complete":
                        assistant_message = event[
                            "message"
                        ]
                        used_real_sse = bool(
                            event.get("sse")
                        )

            except (
                AzureStreamInterrupted,
                LLMUnavailable,
            ) as exc:
                logger.warning(
                    "Azure SSE pass failed; retrying current "
                    "ReAct pass without upstream streaming: %s",
                    exc,
                )
                assistant_message = (
                    _fallback_provider_turn(
                        messages
                    )
                )

                # Do not duplicate a prefix that may already have reached the
                # browser before the stream disconnected.
                fallback_text = (
                    assistant_message.content or ""
                )
                if (
                    streamed_text
                    and fallback_text.startswith(
                        streamed_text
                    )
                ):
                    fallback_text = fallback_text[
                        len(streamed_text):
                    ]

                for chunk in _text_chunks(
                    fallback_text
                ):
                    yield {
                        "type": "token",
                        "text": chunk,
                    }
                    time.sleep(0.012)

            if assistant_message is None:
                raise LLMUnavailable(
                    "Azure returned no assistant message."
                )

            model_used = (
                assistant_message.model
                or model_used
            )

            tool_call = (
                assistant_message.tool_calls[0]
                if assistant_message.tool_calls
                else None
            )

            if tool_call is None:
                final_answer = (
                    assistant_message.content or ""
                ).strip()
                break

            # A streamed tool-use pass normally contains no prose. If the model
            # emitted a short preamble, it has already reached the browser, but
            # only the final grounded pass is persisted as the answer.
            messages.append(
                _assistant_message_dict(
                    assistant_message
                )
            )

            tool_name = (
                tool_call.function.name
            )

            yield {
                "type": "status",
                "text": _status_for(
                    tool_name
                ),
            }

            try:
                arguments = json.loads(
                    tool_call.function.arguments
                    or "{}"
                )
            except json.JSONDecodeError:
                arguments = {}

            result = dispatch(
                tool_name,
                arguments,
                repository,
                bank_scope=bank_scope,
            )

            if (
                result.get("ok")
                and result.get("provenance")
            ):
                citations.append(
                    {
                        "tool": tool_name,
                        "provenance": result[
                            "provenance"
                        ],
                        "data_gaps": result.get(
                            "data_gaps",
                            [],
                        ),
                    }
                )

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": (
                        tool_call.id
                    ),
                    "content": json.dumps(
                        result,
                        default=str,
                    ),
                }
            )

            yield {
                "type": "status",
                "text": "Preparing the grounded answer…",
            }

        else:
            final_answer = (
                "I could not complete the grounded tool workflow "
                "within the allowed number of steps."
            )
            for chunk in _text_chunks(
                final_answer
            ):
                yield {
                    "type": "token",
                    "text": chunk,
                }
                time.sleep(0.012)

    except Exception as exc:
        logger.exception(
            "Azure assistant turn failed"
        )
        yield from _fallback_stream(
            conversation,
            str(exc),
            citations=citations,
        )
        return

    if not final_answer:
        final_answer = (
            "The requested information is not available "
            "in the retrieved data."
        )
        for chunk in _text_chunks(
            final_answer
        ):
            yield {
                "type": "token",
                "text": chunk,
            }
            time.sleep(0.012)

    assistant_record = Message.objects.create(
        conversation=conversation,
        role=Message.Role.ASSISTANT,
        content=final_answer,
        citations=citations,
        model_used=model_used,
        is_fallback=False,
    )

    conversation.save(
        update_fields=["updated_at"]
    )

    if citations:
        yield {
            "type": "citations",
            "citations": citations,
        }

    yield {
        "type": "done",
        "conversation_id": str(
            conversation.id
        ),
        "message_id": str(
            assistant_record.id
        ),
        "model_used": model_used,
        "is_fallback": False,
    }


def _fallback_stream(
    conversation: Conversation,
    reason: str,
    citations: list[dict] | None = None,
) -> Iterator[dict]:
    logger.warning(
        "Assistant fallback used: %s",
        reason,
    )

    text = (
        "The assistant is temporarily unavailable because "
        "the Azure model connection failed. Please retry shortly."
    )

    for chunk in _text_chunks(text):
        yield {
            "type": "token",
            "text": chunk,
        }
        time.sleep(0.012)

    assistant_record = Message.objects.create(
        conversation=conversation,
        role=Message.Role.ASSISTANT,
        content=text,
        citations=citations or [],
        model_used="azure-fast-fallback",
        is_fallback=True,
    )

    conversation.save(
        update_fields=["updated_at"]
    )

    if citations:
        yield {
            "type": "citations",
            "citations": citations,
        }

    yield {
        "type": "done",
        "conversation_id": str(
            conversation.id
        ),
        "message_id": str(
            assistant_record.id
        ),
        "model_used": "azure-fast-fallback",
        "is_fallback": True,
    }
