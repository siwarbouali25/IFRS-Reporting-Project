"""
OpenAI-compatible provider helper for the LangGraph assistant.
"""

from __future__ import annotations

import logging

from openai import OpenAI

from risk_analysis.llm import _provider_config

logger = logging.getLogger(__name__)


class LLMUnavailable(Exception):
    pass


def get_client_and_model() -> tuple[OpenAI, str]:
    api_key, base_url, model = _provider_config()

    if not api_key:
        raise LLMUnavailable(
            "No LLM API key configured "
            "(RISK_LLM_API_KEY / NVIDIA_API_KEY)."
        )

    return OpenAI(
        api_key=api_key,
        base_url=base_url,
    ), model


def chat_with_tools(
    messages: list[dict],
    tools: list[dict],
):
    """
    One non-streaming provider turn.

    parallel_tool_calls=False is required by the configured NIM model because
    its prompt template supports only one tool call per assistant turn.
    """
    client, model = get_client_and_model()

    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            parallel_tool_calls=False,
            temperature=0.1,
        )
    except Exception as exc:
        raise LLMUnavailable(str(exc)) from exc

    message = response.choices[0].message

    # Defensive normalization for providers that ignore
    # parallel_tool_calls=False. The LangGraph tools node should receive one
    # call and then loop back to the agent for any additional retrieval.
    if message.tool_calls and len(message.tool_calls) > 1:
        logger.warning(
            "Provider returned %s tool calls; keeping the first only.",
            len(message.tool_calls),
        )
        message.tool_calls = message.tool_calls[:1]

    return message
