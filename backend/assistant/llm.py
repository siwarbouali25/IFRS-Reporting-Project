"""
Azure fast-deployment client for the assistant.

This module deliberately follows the working notebook's REST pattern:

- AZURE_OPENAI_FAST_DEPLOYMENT_URL is the complete chat-completions URL.
- AZURE_OPENAI_API_KEY is sent through the ``api-key`` header.
- The URL is never rebuilt from an endpoint, deployment name, or API version.
- ``max_completion_tokens`` is tried before ``max_tokens``.
- 429, transient server failures, timeouts, resets, and remote disconnects
  are retried without exposing the API key.
- Both normal and genuine SSE chat-completion requests are supported.
- Tool calling is sequential: at most one tool call is returned per turn.
"""

from __future__ import annotations

import http.client
import json
import logging
import os
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional

logger = logging.getLogger(__name__)

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    # Django settings normally load the project .env. The optional call above
    # also makes this module convenient to test directly.
    pass


class LLMUnavailable(RuntimeError):
    """Raised when the configured Azure deployment cannot complete a request."""


class AzureStreamInterrupted(LLMUnavailable):
    """Raised when an Azure SSE response disconnects before completion."""


@dataclass
class ToolFunctionCall:
    name: str
    arguments: str = "{}"

    def model_dump(self) -> dict:
        return {
            "name": self.name,
            "arguments": self.arguments,
        }

    def to_dict(self) -> dict:
        return self.model_dump()


@dataclass
class ToolCall:
    id: str
    function: ToolFunctionCall
    type: str = "function"

    def model_dump(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "function": self.function.model_dump(),
        }

    def to_dict(self) -> dict:
        return self.model_dump()


@dataclass
class AssistantMessage:
    """
    Small OpenAI-message-compatible object used by the existing LangGraph nodes.

    It exposes the same attributes those nodes already use:
    ``content``, ``tool_calls``, and ``model_dump()``.
    """

    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    model: str = "azure-fast"

    def model_dump(self) -> dict:
        return {
            "role": "assistant",
            "content": self.content,
            "tool_calls": [
                call.model_dump()
                for call in self.tool_calls
            ],
        }

    def to_dict(self) -> dict:
        return self.model_dump()

    def model_copy(
        self,
        *,
        update: Optional[dict] = None,
    ) -> "AssistantMessage":
        values = {
            "content": self.content,
            "tool_calls": list(self.tool_calls),
            "model": self.model,
        }
        values.update(update or {})
        return AssistantMessage(**values)


@dataclass(frozen=True)
class AzureFastConfig:
    api_key: str
    url: str
    model_label: str
    timeout: int
    max_attempts: int
    max_output_tokens: int
    temperature: Optional[float]


def _django_setting(name: str) -> Any:
    try:
        from django.conf import settings

        if settings.configured:
            return getattr(settings, name, None)
    except Exception:
        return None
    return None


def _clean_url(value: Optional[str]) -> Optional[str]:
    """
    Clean copied full deployment URLs without changing their route or query.
    """

    if not value:
        return None

    value = (
        str(value)
        .strip()
        .strip('"')
        .strip("'")
        .strip()
    )

    markdown_match = re.search(
        r"\]\((https://[^)\s]+)\)",
        value,
    )
    if markdown_match:
        value = markdown_match.group(1).strip()

    positions = [
        match.start()
        for match in re.finditer(
            r"https://",
            value,
        )
    ]
    if positions:
        value = value[positions[-1]:]

    return (
        value
        .strip()
        .strip("[]")
        .strip()
        .rstrip(").,;")
    )


def _mask_url_for_display(
    url: Optional[str],
) -> str:
    if not url:
        return "NOT CONFIGURED"

    try:
        parsed = urllib.parse.urlparse(url)
        host = parsed.netloc
        host_parts = host.split(".")

        if host_parts and len(host_parts[0]) > 6:
            host_parts[0] = (
                host_parts[0][:3]
                + "***"
                + host_parts[0][-2:]
            )
        masked_host = ".".join(host_parts)

        path = re.sub(
            r"(/deployments/)([^/]+)(/chat/completions)",
            lambda match: (
                match.group(1)
                + match.group(2)[:2]
                + "***"
                + match.group(3)
            ),
            parsed.path,
        )

        query = "..." if parsed.query else ""

        return urllib.parse.urlunparse(
            (
                parsed.scheme,
                masked_host,
                path,
                "",
                query,
                "",
            )
        )
    except Exception:
        return "<configured Azure URL>"


def _deployment_label(url: str) -> str:
    match = re.search(
        r"/deployments/([^/]+)/chat/completions",
        url,
        flags=re.IGNORECASE,
    )
    if match:
        return f"azure-fast:{match.group(1)}"
    return "azure-fast"


def _optional_float(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def get_azure_fast_config() -> AzureFastConfig:
    api_key = (
        os.getenv("AZURE_OPENAI_API_KEY")
        or _django_setting("AZURE_OPENAI_API_KEY")
    )
    url = _clean_url(
        os.getenv(
            "AZURE_OPENAI_FAST_DEPLOYMENT_URL"
        )
        or _django_setting(
            "AZURE_OPENAI_FAST_DEPLOYMENT_URL"
        )
    )

    if not api_key:
        raise LLMUnavailable(
            "AZURE_OPENAI_API_KEY is not configured."
        )

    if not url:
        raise LLMUnavailable(
            "AZURE_OPENAI_FAST_DEPLOYMENT_URL is not configured."
        )

    if not url.startswith("https://"):
        raise LLMUnavailable(
            "AZURE_OPENAI_FAST_DEPLOYMENT_URL must be a full HTTPS URL."
        )

    if "/chat/completions" not in url:
        raise LLMUnavailable(
            "AZURE_OPENAI_FAST_DEPLOYMENT_URL must be a complete "
            "chat-completions deployment URL."
        )

    timeout = int(
        os.getenv(
            "ASSISTANT_AZURE_TIMEOUT",
            str(
                _django_setting(
                    "ASSISTANT_AZURE_TIMEOUT"
                )
                or 240
            ),
        )
    )
    max_attempts = int(
        os.getenv(
            "ASSISTANT_AZURE_MAX_ATTEMPTS",
            str(
                _django_setting(
                    "ASSISTANT_AZURE_MAX_ATTEMPTS"
                )
                or 6
            ),
        )
    )
    max_output_tokens = int(
        os.getenv(
            "ASSISTANT_AZURE_MAX_TOKENS",
            str(
                _django_setting(
                    "ASSISTANT_AZURE_MAX_TOKENS"
                )
                or 2500
            ),
        )
    )
    temperature = _optional_float(
        os.getenv(
            "ASSISTANT_AZURE_TEMPERATURE",
            _django_setting(
                "ASSISTANT_AZURE_TEMPERATURE"
            ),
        )
    )

    return AzureFastConfig(
        api_key=str(api_key),
        url=url,
        model_label=_deployment_label(url),
        timeout=timeout,
        max_attempts=max_attempts,
        max_output_tokens=max_output_tokens,
        temperature=temperature,
    )


def get_client_and_model():
    """
    Backward-compatible configuration accessor.

    The assistant no longer uses the OpenAI SDK. The first returned value is
    the AzureFastConfig object, and the second is an audit-safe model label.
    """

    config = get_azure_fast_config()
    return config, config.model_label


def _build_payload(
    *,
    messages: list[dict],
    tools: Optional[list[dict]],
    token_field: str,
    max_output_tokens: int,
    temperature: Optional[float],
    stream: bool,
    include_parallel_setting: bool = True,
) -> dict:
    payload: dict[str, Any] = {
        "messages": messages,
        token_field: max_output_tokens,
        "stream": stream,
    }

    if temperature is not None:
        payload["temperature"] = temperature

    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

        if include_parallel_setting:
            payload["parallel_tool_calls"] = False

    return payload


def _retry_wait(
    attempt: int,
    *,
    cap: float = 12,
) -> float:
    return min(
        2 ** (attempt - 1) + random.random(),
        cap,
    )


def _error_message(
    *,
    label: str,
    code: int,
    url: str,
    token_field: str,
    body: str,
) -> str:
    return (
        f"{label} HTTP error {code}.\n"
        f"Endpoint: {_mask_url_for_display(url)}\n"
        f"Token field used: {token_field}\n"
        f"Response: {body[:3000]}"
    )


def _request_json(
    *,
    messages: list[dict],
    tools: Optional[list[dict]],
    max_output_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
    request_label: str = "Azure assistant",
) -> dict:
    """
    Run a normal Azure chat-completions request using the notebook's resilient
    full-URL logic.
    """

    config = get_azure_fast_config()
    output_tokens = (
        max_output_tokens
        if max_output_tokens is not None
        else config.max_output_tokens
    )
    request_temperature = (
        temperature
        if temperature is not None
        else config.temperature
    )

    last_error: Optional[Exception] = None

    for token_field in (
        "max_completion_tokens",
        "max_tokens",
    ):
        include_parallel = True
        include_temperature = (
            request_temperature is not None
        )

        while True:
            payload = _build_payload(
                messages=messages,
                tools=tools,
                token_field=token_field,
                max_output_tokens=output_tokens,
                temperature=(
                    request_temperature
                    if include_temperature
                    else None
                ),
                stream=False,
                include_parallel_setting=include_parallel,
            )

            compatibility_retry = False

            for attempt in range(
                1,
                config.max_attempts + 1,
            ):
                request = urllib.request.Request(
                    config.url,
                    data=json.dumps(payload).encode(
                        "utf-8"
                    ),
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                        "api-key": config.api_key,
                    },
                    method="POST",
                )

                try:
                    with urllib.request.urlopen(
                        request,
                        timeout=config.timeout,
                    ) as response:
                        raw = response.read().decode(
                            "utf-8"
                        )
                        return json.loads(raw)

                except urllib.error.HTTPError as exc:
                    body = exc.read().decode(
                        errors="replace"
                    )
                    body_lower = body.lower()
                    last_error = LLMUnavailable(
                        _error_message(
                            label=request_label,
                            code=exc.code,
                            url=config.url,
                            token_field=token_field,
                            body=body,
                        )
                    )

                    if (
                        exc.code == 429
                        and attempt < config.max_attempts
                    ):
                        retry_after = None
                        try:
                            value = (
                                exc.headers.get(
                                    "Retry-After"
                                )
                                if exc.headers
                                else None
                            )
                            if value is not None:
                                retry_after = float(
                                    str(value).strip()
                                )
                        except (
                            TypeError,
                            ValueError,
                        ):
                            retry_after = None

                        wait = (
                            retry_after
                            if retry_after is not None
                            else min(
                                (2 ** attempt) * 2
                                + random.random(),
                                90,
                            )
                        )
                        logger.warning(
                            "%s rate limited; retrying in %.1fs",
                            request_label,
                            wait,
                        )
                        time.sleep(wait)
                        continue

                    if (
                        exc.code in {500, 502, 503, 504}
                        and attempt < config.max_attempts
                    ):
                        wait = _retry_wait(attempt)
                        logger.warning(
                            "%s server error %s; retrying in %.1fs",
                            request_label,
                            exc.code,
                            wait,
                        )
                        time.sleep(wait)
                        continue

                    if (
                        include_temperature
                        and "temperature" in body_lower
                        and exc.code in {400, 422}
                    ):
                        include_temperature = False
                        compatibility_retry = True
                        logger.warning(
                            "%s endpoint rejected temperature; retrying without it.",
                            request_label,
                        )
                        break

                    if (
                        include_parallel
                        and "parallel_tool_calls"
                        in body_lower
                        and exc.code in {400, 422, 500}
                    ):
                        include_parallel = False
                        compatibility_retry = True
                        logger.warning(
                            "%s endpoint rejected parallel_tool_calls; "
                            "retrying without that field.",
                            request_label,
                        )
                        break

                    if (
                        token_field
                        == "max_completion_tokens"
                        and exc.code in {400, 422, 500}
                    ):
                        compatibility_retry = False
                        logger.warning(
                            "%s endpoint may not support "
                            "max_completion_tokens; trying max_tokens.",
                            request_label,
                        )
                        break

                    if exc.code == 404:
                        raise LLMUnavailable(
                            f"{request_label} returned HTTP 404.\n"
                            f"Endpoint: "
                            f"{_mask_url_for_display(config.url)}\n"
                            "The configured full fast-deployment URL was "
                            "sent unchanged. Check the URL and API key."
                        ) from exc

                    raise last_error from exc

                except urllib.error.URLError as exc:
                    last_error = LLMUnavailable(
                        f"{request_label} connection error.\n"
                        f"Endpoint: "
                        f"{_mask_url_for_display(config.url)}\n"
                        f"Error: {exc}"
                    )
                    if attempt < config.max_attempts:
                        wait = _retry_wait(attempt)
                        logger.warning(
                            "%s connection issue; retrying in %.1fs",
                            request_label,
                            wait,
                        )
                        time.sleep(wait)
                        continue
                    raise last_error from exc

                except (
                    ConnectionError,
                    TimeoutError,
                    OSError,
                    http.client.RemoteDisconnected,
                ) as exc:
                    last_error = LLMUnavailable(
                        f"{request_label} connection reset/timeout.\n"
                        f"Endpoint: "
                        f"{_mask_url_for_display(config.url)}\n"
                        f"Error: {type(exc).__name__}: {exc}"
                    )
                    if attempt < config.max_attempts:
                        wait = _retry_wait(attempt)
                        logger.warning(
                            "%s connection reset/timeout; retrying in %.1fs",
                            request_label,
                            wait,
                        )
                        time.sleep(wait)
                        continue
                    raise last_error from exc

                except json.JSONDecodeError as exc:
                    raise LLMUnavailable(
                        f"{request_label} returned invalid JSON."
                    ) from exc

            if compatibility_retry:
                continue
            break

    raise last_error or LLMUnavailable(
        f"{request_label} failed."
    )


def _open_sse_response(
    *,
    messages: list[dict],
    tools: Optional[list[dict]],
    max_output_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
    request_label: str = "Azure assistant stream",
):
    """
    Open the Azure SSE response. Retries apply while opening the response.
    Mid-stream disconnects are reported by ``stream_chat_with_tools``.
    """

    config = get_azure_fast_config()
    output_tokens = (
        max_output_tokens
        if max_output_tokens is not None
        else config.max_output_tokens
    )
    request_temperature = (
        temperature
        if temperature is not None
        else config.temperature
    )

    last_error: Optional[Exception] = None

    for token_field in (
        "max_completion_tokens",
        "max_tokens",
    ):
        include_parallel = True
        include_temperature = (
            request_temperature is not None
        )

        while True:
            payload = _build_payload(
                messages=messages,
                tools=tools,
                token_field=token_field,
                max_output_tokens=output_tokens,
                temperature=(
                    request_temperature
                    if include_temperature
                    else None
                ),
                stream=True,
                include_parallel_setting=include_parallel,
            )

            compatibility_retry = False

            for attempt in range(
                1,
                config.max_attempts + 1,
            ):
                request = urllib.request.Request(
                    config.url,
                    data=json.dumps(payload).encode(
                        "utf-8"
                    ),
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "text/event-stream",
                        "Cache-Control": "no-cache",
                        "api-key": config.api_key,
                    },
                    method="POST",
                )

                try:
                    return urllib.request.urlopen(
                        request,
                        timeout=config.timeout,
                    )

                except urllib.error.HTTPError as exc:
                    body = exc.read().decode(
                        errors="replace"
                    )
                    body_lower = body.lower()
                    last_error = LLMUnavailable(
                        _error_message(
                            label=request_label,
                            code=exc.code,
                            url=config.url,
                            token_field=token_field,
                            body=body,
                        )
                    )

                    if (
                        exc.code == 429
                        and attempt < config.max_attempts
                    ):
                        retry_after = None
                        try:
                            value = (
                                exc.headers.get(
                                    "Retry-After"
                                )
                                if exc.headers
                                else None
                            )
                            if value is not None:
                                retry_after = float(
                                    str(value).strip()
                                )
                        except (
                            TypeError,
                            ValueError,
                        ):
                            retry_after = None

                        wait = (
                            retry_after
                            if retry_after is not None
                            else min(
                                (2 ** attempt) * 2
                                + random.random(),
                                90,
                            )
                        )
                        logger.warning(
                            "%s rate limited; retrying in %.1fs",
                            request_label,
                            wait,
                        )
                        time.sleep(wait)
                        continue

                    if (
                        exc.code in {500, 502, 503, 504}
                        and attempt < config.max_attempts
                    ):
                        wait = _retry_wait(attempt)
                        logger.warning(
                            "%s server error %s; retrying in %.1fs",
                            request_label,
                            exc.code,
                            wait,
                        )
                        time.sleep(wait)
                        continue

                    if (
                        include_temperature
                        and "temperature" in body_lower
                        and exc.code in {400, 422}
                    ):
                        include_temperature = False
                        compatibility_retry = True
                        break

                    if (
                        include_parallel
                        and "parallel_tool_calls"
                        in body_lower
                        and exc.code in {400, 422, 500}
                    ):
                        include_parallel = False
                        compatibility_retry = True
                        break

                    if (
                        token_field
                        == "max_completion_tokens"
                        and exc.code in {400, 422, 500}
                    ):
                        compatibility_retry = False
                        break

                    raise last_error from exc

                except urllib.error.URLError as exc:
                    last_error = LLMUnavailable(
                        f"{request_label} connection error: {exc}"
                    )
                    if attempt < config.max_attempts:
                        wait = _retry_wait(attempt)
                        time.sleep(wait)
                        continue
                    raise last_error from exc

                except (
                    ConnectionError,
                    TimeoutError,
                    OSError,
                    http.client.RemoteDisconnected,
                ) as exc:
                    last_error = LLMUnavailable(
                        f"{request_label} connection reset/timeout: "
                        f"{type(exc).__name__}: {exc}"
                    )
                    if attempt < config.max_attempts:
                        wait = _retry_wait(attempt)
                        time.sleep(wait)
                        continue
                    raise last_error from exc

            if compatibility_retry:
                continue
            break

    raise last_error or LLMUnavailable(
        f"{request_label} failed."
    )


def _normalise_tool_calls(
    raw_calls: Any,
) -> list[ToolCall]:
    calls: list[ToolCall] = []

    for raw_call in raw_calls or []:
        if not isinstance(raw_call, dict):
            continue

        function = raw_call.get("function") or {}
        name = str(
            function.get("name") or ""
        ).strip()

        if not name:
            continue

        calls.append(
            ToolCall(
                id=str(
                    raw_call.get("id")
                    or f"call_{uuid.uuid4().hex}"
                ),
                type=str(
                    raw_call.get("type")
                    or "function"
                ),
                function=ToolFunctionCall(
                    name=name,
                    arguments=str(
                        function.get("arguments")
                        or "{}"
                    ),
                ),
            )
        )

    if len(calls) > 1:
        logger.warning(
            "Azure returned %s tool calls; keeping only the first: %s",
            len(calls),
            calls[0].function.name,
        )
        calls = calls[:1]

    return calls


def _message_from_response(
    data: dict,
) -> AssistantMessage:
    try:
        message = data["choices"][0]["message"]
    except (
        KeyError,
        IndexError,
        TypeError,
    ) as exc:
        raise LLMUnavailable(
            "Unexpected Azure chat-completions response structure."
        ) from exc

    content = message.get("content")
    if content is None:
        content = ""

    return AssistantMessage(
        content=str(content),
        tool_calls=_normalise_tool_calls(
            message.get("tool_calls")
        ),
        model=str(
            data.get("model")
            or get_azure_fast_config().model_label
        ),
    )


def chat_with_tools(
    messages: list[dict],
    tools: list[dict],
) -> AssistantMessage:
    """
    One normal Azure assistant turn for the existing LangGraph agent node.
    """

    data = _request_json(
        messages=messages,
        tools=tools,
        request_label="Azure fast assistant",
    )
    return _message_from_response(data)


def _delta_text(delta: dict) -> str:
    content = delta.get("content")

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)

    return ""


def stream_chat_with_tools(
    messages: list[dict],
    tools: list[dict],
) -> Iterator[dict]:
    """
    Stream one Azure chat-completions turn.

    Yields:
      {"type": "content_delta", "text": "..."}
      {"type": "complete", "message": AssistantMessage(...), "sse": True}

    Tool-call argument fragments are accumulated internally and returned in the
    final AssistantMessage. Only the first tool call is kept.
    """

    config = get_azure_fast_config()
    response = _open_sse_response(
        messages=messages,
        tools=tools,
    )

    content_parts: list[str] = []
    tool_slots: dict[int, dict[str, str]] = {}
    model_name = config.model_label
    saw_sse = False
    raw_non_sse: list[str] = []

    try:
        with response:
            for raw_line in response:
                line = raw_line.decode(
                    "utf-8",
                    errors="replace",
                ).strip()

                if not line:
                    continue

                if not line.startswith("data:"):
                    raw_non_sse.append(line)
                    continue

                saw_sse = True
                payload_text = line[5:].strip()

                if not payload_text:
                    continue

                if payload_text == "[DONE]":
                    break

                try:
                    event = json.loads(payload_text)
                except json.JSONDecodeError:
                    logger.debug(
                        "Ignoring malformed Azure SSE frame."
                    )
                    continue

                if event.get("model"):
                    model_name = str(event["model"])

                choices = event.get("choices") or []
                if not choices:
                    continue

                delta = choices[0].get("delta") or {}

                text = _delta_text(delta)
                if text:
                    content_parts.append(text)
                    yield {
                        "type": "content_delta",
                        "text": text,
                    }

                for fragment in (
                    delta.get("tool_calls") or []
                ):
                    index = int(
                        fragment.get("index", 0)
                    )
                    slot = tool_slots.setdefault(
                        index,
                        {
                            "id": "",
                            "name": "",
                            "arguments": "",
                            "type": "function",
                        },
                    )

                    if fragment.get("id"):
                        slot["id"] = str(
                            fragment["id"]
                        )

                    if fragment.get("type"):
                        slot["type"] = str(
                            fragment["type"]
                        )

                    function = (
                        fragment.get("function")
                        or {}
                    )
                    if function.get("name"):
                        slot["name"] += str(
                            function["name"]
                        )
                    if function.get("arguments"):
                        slot["arguments"] += str(
                            function["arguments"]
                        )

    except (
        urllib.error.URLError,
        ConnectionError,
        TimeoutError,
        OSError,
        http.client.RemoteDisconnected,
    ) as exc:
        raise AzureStreamInterrupted(
            "Azure fast-deployment SSE connection was interrupted: "
            f"{type(exc).__name__}: {exc}"
        ) from exc

    if not saw_sse and raw_non_sse:
        # Some enterprise gateways ignore stream=true and return normal JSON.
        # Preserve compatibility instead of failing silently.
        try:
            data = json.loads(
                "\n".join(raw_non_sse)
            )
        except json.JSONDecodeError as exc:
            raise LLMUnavailable(
                "Azure returned neither valid SSE nor valid JSON."
            ) from exc

        message = _message_from_response(data)
        if message.content:
            yield {
                "type": "content_delta",
                "text": message.content,
            }
        yield {
            "type": "complete",
            "message": message,
            "sse": False,
        }
        return

    raw_calls = []
    for index in sorted(tool_slots):
        slot = tool_slots[index]
        if not slot["name"]:
            continue
        raw_calls.append(
            {
                "id": (
                    slot["id"]
                    or f"call_{uuid.uuid4().hex}"
                ),
                "type": slot["type"],
                "function": {
                    "name": slot["name"],
                    "arguments": (
                        slot["arguments"] or "{}"
                    ),
                },
            }
        )

    message = AssistantMessage(
        content="".join(content_parts),
        tool_calls=_normalise_tool_calls(
            raw_calls
        ),
        model=model_name,
    )

    yield {
        "type": "complete",
        "message": message,
        "sse": True,
    }
