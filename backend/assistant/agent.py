"""
Turn orchestration for the protected assistant.

User input is checked by deterministic scope and prompt-injection guardrails
before it is stored or sent to Azure. Blocked turns are recorded for audit but
are not replayed into later model context.
"""

from __future__ import annotations

from .graph import get_assistant_graph
from .guardrails import (
    conversation_has_project_context,
    evaluate_user_input,
    guardrail_metadata,
    history_message_is_safe,
    validate_assistant_output,
)
from .models import Conversation, Message
from .system_prompt import SYSTEM_PROMPT

MAX_ITERATIONS = 8


def _scoped_system_prompt(
    conversation: Conversation,
) -> str:
    if not conversation.bank_id:
        return SYSTEM_PROMPT

    bank = conversation.bank

    scope_instruction = f"""

ACTIVE CONVERSATION BANK SCOPE:
- The user selected the bank "{bank.name}" in the interface.
- Its internal lookup code is "{bank.code}".
- Treat "{bank.name}" as the bank for every bank-specific question unless the \
user explicitly requests a supported cross-bank comparison.
- Do not ask the user to provide or confirm the bank name.
- Use "{bank.code}" only as the internal argument for bank-specific tools.
- In user-facing prose, use "{bank.name}", never "{bank.code}".
"""

    return (
        SYSTEM_PROMPT.rstrip()
        + scope_instruction
    )


def _history_to_messages(
    conversation: Conversation,
) -> list[dict]:
    """
    Replay only safe, project-relevant turns.

    This also removes older injection attempts that were saved before the
    deterministic guardrail was introduced.
    """

    has_context = (
        conversation_has_project_context(
            conversation
        )
    )

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
        if (
            message.content
            and history_message_is_safe(
                message,
                has_project_context=has_context,
            )
        ):
            messages.append(
                {
                    "role": message.role,
                    "content": message.content,
                }
            )

    return messages


def _persist_guardrail_block(
    conversation: Conversation,
    user_text: str,
    decision,
) -> Message:
    marker = guardrail_metadata(
        decision
    )

    Message.objects.create(
        conversation=conversation,
        role=Message.Role.USER,
        content=user_text,
        tool_calls=marker,
    )

    assistant_message = Message.objects.create(
        conversation=conversation,
        role=Message.Role.ASSISTANT,
        content=decision.response,
        tool_calls=marker,
        citations=[],
        model_used="deterministic-guardrail",
        is_fallback=False,
    )

    conversation.save(
        update_fields=["updated_at"]
    )
    return assistant_message


def run_turn(
    conversation: Conversation,
    user_text: str,
) -> Message:
    has_context = (
        conversation_has_project_context(
            conversation
        )
    )
    input_decision = (
        evaluate_user_input(
            user_text,
            has_project_context=has_context,
        )
    )

    if not input_decision.allowed:
        return _persist_guardrail_block(
            conversation,
            user_text,
            input_decision,
        )

    # Build history before saving this turn so the current user message is not
    # duplicated in the model context.
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

    citations = final_state.get(
        "citations",
        [],
    )
    output_decision = (
        validate_assistant_output(
            final_state.get(
                "answer",
                "",
            ),
            citations=citations,
            input_decision=input_decision,
            bank_code=(
                conversation.bank.code
                if conversation.bank_id
                else None
            ),
            bank_name=(
                conversation.bank.name
                if conversation.bank_id
                else None
            ),
        )
    )

    if not output_decision.accepted:
        citations = []

    assistant_message = Message.objects.create(
        conversation=conversation,
        role=Message.Role.ASSISTANT,
        content=output_decision.text,
        citations=citations,
        model_used=(
            final_state.get(
                "model_used",
                "",
            )
            if output_decision.accepted
            else "deterministic-output-guardrail"
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
