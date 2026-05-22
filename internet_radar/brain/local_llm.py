from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import requests


@dataclass(frozen=True)
class OllamaResponse:
    text: str
    raw: dict[str, Any]


class OllamaClient:
    def __init__(self, model: str = "qwen2.5:0.5b", host: str | None = None, timeout: float = 20.0) -> None:
        self.model = model
        self.host = (host or os.getenv("OLLAMA_HOST") or "http://localhost:11434").rstrip("/")
        self.timeout = timeout

    def available_models(self) -> list[str]:
        try:
            response = requests.get(f"{self.host}/api/tags", timeout=3)
            response.raise_for_status()
        except requests.RequestException:
            return []
        data = response.json()
        return [item.get("name", "") for item in data.get("models", []) if item.get("name")]

    def generate(self, prompt: str) -> OllamaResponse:
        response = requests.post(
            f"{self.host}/api/generate",
            json={"model": self.model, "prompt": prompt, "stream": False, "format": "json"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        return OllamaResponse(text=str(data.get("response", "")), raw=data)

    def generate_json(self, prompt: str) -> dict[str, Any]:
        result = self.generate(prompt)
        try:
            parsed = json.loads(result.text)
        except json.JSONDecodeError:
            return {"text": result.text}
        return parsed if isinstance(parsed, dict) else {"result": parsed}
