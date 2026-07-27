"""
Chat-with-tools call against the same OpenAI-compatible provider the rest of
the platform uses (NVIDIA NIM by default, Azure/OpenAI via RISK_LLM_* settings).
Reuses risk_analysis._provider_config so provider config lives in one place.
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
        raise LLMUnavailable("No LLM API key configured (RISK_LLM_API_KEY / NVIDIA_API_KEY).")
    return OpenAI(api_key=api_key, base_url=base_url), model


def chat_with_tools(messages: list[dict], tools: list[dict]):
    """One turn of the model. Returns the assistant message object."""
    client, model = get_client_and_model()
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=0.1,
        )
    except Exception as exc:  # network / provider errors
        raise LLMUnavailable(str(exc)) from exc
    return resp.choices[0].message
