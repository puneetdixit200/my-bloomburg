from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Callable

import requests


PostFunction = Callable[..., Any]


@dataclass(frozen=True)
class OnlineLLMResponse:
    text: str
    raw: dict[str, Any]


class OnlineLLMClient:
    endpoint: str = ""
    env_key: str = ""
    model: str = ""

    def __init__(self, model: str | None = None, api_key: str | None = None, post: PostFunction | None = None, timeout: float = 30.0) -> None:
        self.model = model or self.model
        self.api_key = api_key if api_key is not None else os.getenv(self.env_key, "")
        self.post = post or requests.post
        self.timeout = timeout

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def generate(self, prompt: str) -> OnlineLLMResponse:
        if not self.available:
            raise RuntimeError(f"{self.env_key} is not configured")

        response = self.post(
            self.endpoint,
            headers=self._headers(),
            json=self._payload(prompt),
            timeout=self.timeout,
        )
        response.raise_for_status()
        raw = response.json()
        return OnlineLLMResponse(text=self._extract_text(raw), raw=raw)

    def generate_json(self, prompt: str) -> dict[str, Any]:
        result = self.generate(prompt)
        try:
            parsed = json.loads(result.text)
        except json.JSONDecodeError:
            return {"text": result.text}
        return parsed if isinstance(parsed, dict) else {"result": parsed}

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def _payload(self, prompt: str) -> dict[str, object]:
        return {"model": self.model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.2}

    def _extract_text(self, raw: dict[str, Any]) -> str:
        choices = raw.get("choices", [])
        if choices and isinstance(choices[0], dict):
            message = choices[0].get("message", {})
            if isinstance(message, dict):
                return str(message.get("content", ""))
        return str(raw.get("text", ""))


class GroqClient(OnlineLLMClient):
    endpoint = "https://api.groq.com/openai/v1/chat/completions"
    env_key = "GROQ_API_KEY"
    model = "llama-3.3-70b-versatile"


class GeminiClient(OnlineLLMClient):
    endpoint = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    env_key = "GEMINI_API_KEY"
    model = "gemini-1.5-flash"


class OpenRouterClient(OnlineLLMClient):
    endpoint = "https://openrouter.ai/api/v1/chat/completions"
    env_key = "OPENROUTER_API_KEY"
    model = "meta-llama/llama-3.2-3b-instruct:free"
