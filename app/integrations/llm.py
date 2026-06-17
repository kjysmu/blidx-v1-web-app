from abc import ABC, abstractmethod
from typing import Any

import httpx

from app.core.config import settings


class LLMProvider(ABC):
    @abstractmethod
    def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        raise NotImplementedError


class ClaudeProvider(LLMProvider):
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: float = 45.0,
    ) -> None:
        self.api_key = api_key or settings.ANTHROPIC_API_KEY
        self.model = model or settings.ANTHROPIC_MODEL
        self.timeout_seconds = timeout_seconds

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        if not self.api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not configured")

        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": settings.ANTHROPIC_MAX_TOKENS,
            "temperature": settings.ANTHROPIC_TEMPERATURE,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system_prompt:
            payload["system"] = system_prompt

        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        text_blocks = [
            block.get("text", "")
            for block in data.get("content", [])
            if block.get("type") == "text"
        ]
        content = "\n".join(text_blocks).strip()
        if not content:
            raise RuntimeError("Anthropic returned an empty response")
        return content


class OpenAIProvider(LLMProvider):
    def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        # TODO: connect OpenAI API
        return "OpenAI placeholder response"
