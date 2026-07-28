"""
Turn orchestration for the non-streaming LangGraph endpoint.
"""

from __future__ import annotations

from .graph import get_assistant_graph
from .models import Conversation, Message
from .system_prompt import SYSTEM_PROMPT

# Sequential tool use means one multi-part question can require several graph
# passes. Eight leaves room for multiple retrievals plus the final answer.
MAX_ITERATIONS = 8


def _history_to_messages(
    conversation: Conversation,
) -> list[dict]:
    """
    Replay stored user/assistant turns.

    Tool messages are intentionally not replayed across separate user turns;
    each new LangGraph execution retrieves fresh data through the tools.
    """

    messages: list[dict] = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        }
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
    """
    Run one non-streamed turn through the existing LangGraph StateGraph.
    """

    # Build history first. Saving the current turn before this call would make
    # the same user prompt appear twice in the model context.
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

    graph = get_assistant_graph()
    final_state = graph.invoke(
        {
            "messages": messages,
            "bank_scope": bank_scope,
            "iterations": 0,
            "max_iterations": (
                MAX_ITERATIONS
            ),
            "citations": [],
        }
    )

    assistant_message = Message.objects.create(
        conversation=conversation,
        role=Message.Role.ASSISTANT,
        content=final_state.get(
            "answer",
            "",
        ),
        citations=final_state.get(
            "citations",
            [],
        ),
        model_used=final_state.get(
            "model_used",
            "",
        ),
        is_fallback=final_state.get(
            "is_fallback",
            False,
        ),
    )

    conversation.save(
        update_fields=["updated_at"]
    )
    return assistant_message
