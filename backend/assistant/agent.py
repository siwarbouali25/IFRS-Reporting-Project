"""
Turn orchestration for the assistant.

The selected bank is stored on Conversation and injected into the system
message before Azure chooses a tool. This prevents the model from asking the
user to name a bank when the page already has an active bank scope.
"""

from __future__ import annotations

from .graph import get_assistant_graph
from .models import Conversation, Message
from .system_prompt import SYSTEM_PROMPT

# Sequential tool use can require several model/tool passes.
MAX_ITERATIONS = 8


def _scoped_system_prompt(
    conversation: Conversation,
) -> str:
    """
    Build the system prompt with the active UI-selected bank scope.

    The bank code remains available for internal tool lookup, while the model
    is instructed to use the real name in user-facing prose.
    """

    if not conversation.bank_id:
        return SYSTEM_PROMPT

    bank = conversation.bank

    scope_instruction = f"""

ACTIVE CONVERSATION BANK SCOPE:
- The user selected the bank "{bank.name}" in the interface.
- Its internal lookup code is "{bank.code}".
- Treat "{bank.name}" as the bank for every bank-specific question in this
  conversation unless the user explicitly asks for a cross-bank comparison.
- Do not ask the user to provide or confirm the bank name.
- When calling a bank-specific tool, use "{bank.code}" as its bank argument.
- In the final answer, refer to the bank as "{bank.name}", not "{bank.code}".
"""

    return SYSTEM_PROMPT.rstrip() + scope_instruction


def _history_to_messages(
    conversation: Conversation,
) -> list[dict]:
    """
    Replay stored user and assistant turns with the active bank scope included
    in the first system message.

    Tool messages are not replayed across separate user turns. Each turn
    retrieves fresh structured data.
    """

    messages: list[dict] = [
        {
            "role": "system",
            "content": _scoped_system_prompt(
                conversation
            ),
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

    # Build history before persisting the current user message, otherwise that
    # message would be included twice.
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
            "max_iterations": MAX_ITERATIONS,
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
