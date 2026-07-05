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

    This is intentionally simple because your notebook already uses deployment
    URLs directly. We keep this wrapper isolated so the rest of the generation
    engine does not depend on notebook code.
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

    def _extract_content(self, response_json: dict[str, Any]) -> str:
        """
        Supports common Azure/OpenAI chat response shapes.
        """

        choices = response_json.get("choices")

        if isinstance(choices, list) and choices:
            first_choice = choices[0]

            message = first_choice.get("message")
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str):
                    return content.strip()

            text = first_choice.get("text")
            if isinstance(text, str):
                return text.strip()

        output_text = response_json.get("output_text")
        if isinstance(output_text, str):
            return output_text.strip()

        raise AzureLLMError(
            "Could not extract text content from Azure LLM response."
        )

    def _post_chat_completion(
        self,
        *,
        url: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        model_role: str,
    ) -> AzureLLMResponse:
        payload = {
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                response = requests.post(
                    url,
                    headers=self._headers(),
                    json=payload,
                    timeout=self.timeout,
                )

                if response.status_code >= 400:
                    raise AzureLLMError(
                        f"Azure LLM request failed with status "
                        f"{response.status_code}: {response.text[:1000]}"
                    )

                response_json = response.json()
                content = self._extract_content(response_json)

                return AzureLLMResponse(
                    content=content,
                    raw_response=response_json,
                    model_role=model_role,
                )

            except Exception as exc:
                last_error = exc

                if attempt >= self.max_retries:
                    break

        raise AzureLLMError(f"Azure LLM request failed: {last_error}")

    def generate_writer_text(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 2500,
    ) -> AzureLLMResponse:
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
            temperature=temperature,
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
            temperature=temperature,
            max_tokens=max_tokens,
            model_role="fast",
        )