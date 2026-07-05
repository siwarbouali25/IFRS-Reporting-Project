import os
from dataclasses import dataclass
from typing import Any

import requests


class AzureLLMError(Exception):
    pass


@dataclass
class AzureLLMResponse:
    content: str
    raw_response: dict[str, Any]
    model_role: str


class AzureURLLLMClient:
    """
    Minimal Azure OpenAI URL-based client.

    It supports your current setup where the full Azure deployment URL is stored
    in the .env file.

    Environment variables expected:
    - AZURE_OPENAI_API_KEY
    - AZURE_OPENAI_GPT52_DEPLOYMENT_URL
    - AZURE_OPENAI_FAST_DEPLOYMENT_URL
    """

    def __init__(
        self,
        *,
        writer_url: str | None = None,
        fast_url: str | None = None,
        api_key: str | None = None,
        timeout: int = 120,
        max_retries: int = 2,
    ) -> None:
        self.writer_url = writer_url or os.getenv("AZURE_OPENAI_GPT52_DEPLOYMENT_URL")
        self.fast_url = fast_url or os.getenv("AZURE_OPENAI_FAST_DEPLOYMENT_URL")
        self.api_key = api_key or os.getenv("AZURE_OPENAI_API_KEY")
        self.timeout = timeout
        self.max_retries = max_retries

        if not self.api_key:
            raise AzureLLMError("Missing AZURE_OPENAI_API_KEY.")

        if not self.writer_url:
            raise AzureLLMError("Missing AZURE_OPENAI_GPT52_DEPLOYMENT_URL.")

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "api-key": self.api_key,
        }

    def _extract_content_from_message(self, message: dict[str, Any]) -> str | None:
        content = message.get("content")

        if isinstance(content, str):
            return content.strip()

        if isinstance(content, list):
            parts: list[str] = []

            for item in content:
                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str):
                        parts.append(text)

                elif isinstance(item, str):
                    parts.append(item)

            joined = "\n".join(parts).strip()

            if joined:
                return joined

        return None

    def _extract_content(self, response_json: dict[str, Any]) -> str:
        """
        Supports common Azure/OpenAI chat response shapes.
        """

        choices = response_json.get("choices")

        if isinstance(choices, list) and choices:
            first_choice = choices[0]

            message = first_choice.get("message")
            if isinstance(message, dict):
                content = self._extract_content_from_message(message)
                if content:
                    return content

            text = first_choice.get("text")
            if isinstance(text, str):
                return text.strip()

        output_text = response_json.get("output_text")
        if isinstance(output_text, str):
            return output_text.strip()

        output = response_json.get("output")
        if isinstance(output, list):
            parts: list[str] = []

            for item in output:
                if not isinstance(item, dict):
                    continue

                content_items = item.get("content")

                if isinstance(content_items, list):
                    for content_item in content_items:
                        if not isinstance(content_item, dict):
                            continue

                        text = content_item.get("text")
                        if isinstance(text, str):
                            parts.append(text)

                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)

            joined = "\n".join(parts).strip()

            if joined:
                return joined

        raise AzureLLMError(
            "Could not extract text content from Azure LLM response. "
            f"Response keys: {list(response_json.keys())}"
        )

    def _build_payload_variants(
        self,
        *,
        messages: list[dict[str, str]],
        max_tokens: int,
    ) -> list[dict[str, Any]]:
        """
        Azure deployments can differ depending on model/API version.

        Some accept:
        - max_completion_tokens

        Older deployments accept:
        - max_tokens

        Some reasoning deployments reject temperature, so we omit temperature.
        """

        return [
            {
                "messages": messages,
                "max_completion_tokens": max_tokens,
            },
            {
                "messages": messages,
                "max_tokens": max_tokens,
            },
            {
                "messages": messages,
            },
        ]

    def _post_chat_completion(
        self,
        *,
        url: str,
        messages: list[dict[str, str]],
        max_tokens: int,
        model_role: str,
    ) -> AzureLLMResponse:
        payload_variants = self._build_payload_variants(
            messages=messages,
            max_tokens=max_tokens,
        )

        errors: list[str] = []

        for payload_index, payload in enumerate(payload_variants, start=1):
            for attempt in range(self.max_retries + 1):
                try:
                    response = requests.post(
                        url,
                        headers=self._headers(),
                        json=payload,
                        timeout=self.timeout,
                    )

                    if response.status_code >= 400:
                        errors.append(
                            f"payload_variant={payload_index}, "
                            f"attempt={attempt + 1}, "
                            f"status={response.status_code}, "
                            f"body={response.text[:2000]}"
                        )
                        break

                    response_json = response.json()
                    content = self._extract_content(response_json)

                    return AzureLLMResponse(
                        content=content,
                        raw_response=response_json,
                        model_role=model_role,
                    )

                except Exception as exc:
                    errors.append(
                        f"payload_variant={payload_index}, "
                        f"attempt={attempt + 1}, "
                        f"error={str(exc)}"
                    )

                    if attempt >= self.max_retries:
                        break

        raise AzureLLMError(
            "Azure LLM request failed for all payload variants:\n"
            + "\n\n".join(errors)
        )

    def generate_writer_text(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 2500,
    ) -> AzureLLMResponse:
        """
        Generate text with the writer deployment.

        temperature is kept in the function signature for later, but it is not
        sent in the request because some Azure reasoning deployments reject it.
        """

        return self._post_chat_completion(
            url=self.writer_url,
            messages=[
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],
            max_tokens=max_tokens,
            model_role="writer",
        )

    def generate_fast_text(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 1200,
    ) -> AzureLLMResponse:
        """
        Generate text with the fast deployment.

        If no fast URL is configured, it falls back to the writer URL.
        """

        url = self.fast_url or self.writer_url

        return self._post_chat_completion(
            url=url,
            messages=[
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],
            max_tokens=max_tokens,
            model_role="fast",
        )