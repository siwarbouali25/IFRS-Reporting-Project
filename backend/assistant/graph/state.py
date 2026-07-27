from typing import Any, TypedDict


class AssistantGraphState(TypedDict, total=False):
    # OpenAI-format message list, seeded with system + history + new user turn.
    messages: list[dict[str, Any]]

    # Conversation scope. When bank_scope is set, tools are locked to it.
    bank_scope: str | None

    # Loop control.
    iterations: int
    max_iterations: int

    # Collected provenance from every successful tool call, surfaced to the
    # API as citations.
    citations: list[dict[str, Any]]

    # Final answer + bookkeeping.
    answer: str
    is_fallback: bool
    model_used: str
