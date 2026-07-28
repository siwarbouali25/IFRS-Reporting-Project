"""Turn orchestration for the non-streaming assistant endpoint."""

from __future__ import annotations

from .graph import get_assistant_graph
from .models import Conversation, Message
from .system_prompt import SYSTEM_PROMPT

MAX_ITERATIONS = 5


def _history_to_messages(conversation: Conversation) -> list[dict]:
    """Replay stored user/assistant turns; tool turns are not replayed."""
    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT}
    ]

    for message in conversation.messages.filter(
        role__in=[
            Message.Role.USER,
            Message.Role.ASSISTANT,
        ]
    ).order_by("created_at"):
        if message.content:
            messages.append(
                {
                    "role": message.role,
                    "content": message.content,
                }
            )

    return messages


def run_turn(
    conversation: Conversation,
    user_text: str,
) -> Message:
    # Build history before saving the current user turn. The previous version
    # saved first and then appended user_text again, duplicating the prompt.
    messages = _history_to_messages(conversation)
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

    graph = get_assistant_graph()
    final_state = graph.invoke(
        {
            "messages": messages,
            "bank_scope": bank_scope,
            "iterations": 0,
            "max_iterations": MAX_ITERATIONS,
            "citations": [],
        }
    )

    assistant_msg = Message.objects.create(
        conversation=conversation,
        role=Message.Role.ASSISTANT,
        content=final_state.get("answer", ""),
        citations=final_state.get("citations", []),
        model_used=final_state.get("model_used", ""),
        is_fallback=final_state.get(
            "is_fallback",
            False,
        ),
    )

    conversation.save(update_fields=["updated_at"])
    return assistant_msg
