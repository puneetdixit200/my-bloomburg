from __future__ import annotations

import hashlib
import math
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import requests

from internet_radar.brain.local_llm import OllamaClient


HttpPost = Callable[..., Any]

@dataclass(frozen=True)
class EmbeddingChoice:
    provider: str
    model: str
    reason: str


class DeterministicEmbedder:
    def __init__(self, dimensions: int = 64) -> None:
        self.dimensions = dimensions

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in _tokens(text):
            digest = hashlib.sha1(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        return _normalize(vector)


class OllamaEmbedder:
    def __init__(self, model: str = "nomic-embed-text", host: str | None = None, timeout: float = 10.0) -> None:
        self.model = model
        self.host = (host or os.getenv("OLLAMA_HOST") or "http://localhost:11434").rstrip("/")
        self.timeout = timeout

    def embed(self, text: str) -> list[float]:
        response = requests.post(
            f"{self.host}/api/embeddings",
            json={"model": self.model, "prompt": text[:8000]},
            timeout=self.timeout,
        )
        response.raise_for_status()
        embedding = response.json().get("embedding", [])
        if not isinstance(embedding, list):
            return []
        return _normalize([float(value) for value in embedding])


class CohereEmbedder:
    def __init__(
        self,
        model: str = "embed-english-light-v3.0",
        api_key: str | None = None,
        timeout: float = 10.0,
        http_post: HttpPost = requests.post,
    ) -> None:
        self.model = model
        self.api_key = api_key or os.getenv("COHERE_API_KEY", "")
        self.timeout = timeout
        self.http_post = http_post

    def embed(self, text: str) -> list[float]:
        if not self.api_key:
            return []
        response = self.http_post(
            "https://api.cohere.com/v1/embed",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json={"texts": [text[:8000]], "model": self.model, "input_type": "search_document"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        embeddings = response.json().get("embeddings", [])
        if not embeddings or not isinstance(embeddings[0], list):
            return []
        return _normalize([float(value) for value in embeddings[0]])


class GeminiEmbedder:
    def __init__(
        self,
        model: str = "gemini-embedding-2",
        api_key: str | None = None,
        timeout: float = 10.0,
        http_post: HttpPost = requests.post,
    ) -> None:
        self.model = model
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self.timeout = timeout
        self.http_post = http_post

    def embed(self, text: str) -> list[float]:
        if not self.api_key:
            return []
        response = self.http_post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:embedContent",
            headers={"x-goog-api-key": self.api_key, "Content-Type": "application/json"},
            json={
                "model": f"models/{self.model}",
                "content": {"parts": [{"text": text[:8000]}]},
                "output_dimensionality": 768,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        return _normalize(_embedding_values(response.json()))


class EmbeddingRouter:
    def __init__(
        self,
        available_models: list[str] | None = None,
        cohere_api_key: str | None = None,
        ollama_client: OllamaClient | None = None,
    ) -> None:
        self._available_models = available_models
        self.cohere_api_key = cohere_api_key if cohere_api_key is not None else os.getenv("COHERE_API_KEY", "")
        self.ollama_client = ollama_client or OllamaClient()

    @property
    def available_models(self) -> list[str]:
        if self._available_models is None:
            self._available_models = self.ollama_client.available_models()
        return self._available_models

    def route(self) -> EmbeddingChoice:
        if "nomic-embed-text" in self.available_models:
            return EmbeddingChoice(provider="ollama", model="nomic-embed-text", reason="local embedding model")
        if os.getenv("GEMINI_API_KEY", ""):
            return EmbeddingChoice(provider="gemini", model="gemini-embedding-2", reason="Gemini embedding free-tier key")
        if self.cohere_api_key:
            return EmbeddingChoice(provider="cohere", model="embed-english-light-v3.0", reason="online free-tier embedding fallback")
        return EmbeddingChoice(provider="deterministic", model="hashed-bow", reason="space-conscious local fallback")

    def embedder(self) -> DeterministicEmbedder | OllamaEmbedder | CohereEmbedder | GeminiEmbedder:
        choice = self.route()
        if choice.provider == "ollama":
            return OllamaEmbedder(model=choice.model)
        if choice.provider == "gemini":
            return GeminiEmbedder(model=choice.model)
        if choice.provider == "cohere":
            return CohereEmbedder(model=choice.model, api_key=self.cohere_api_key)
        return DeterministicEmbedder()


def cosine_similarity(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=False))


def _tokens(text: str) -> list[str]:
    normalized = text.lower().replace("builders", "resume").replace("builder", "resume").replace("automation", "agent")
    tokens = re.findall(r"[a-z0-9][a-z0-9.+#-]*", normalized)
    return [_stem_token(token) for token in tokens]


def _stem_token(token: str) -> str:
    if token in {"agents", "automate", "automates", "automating"}:
        return "agent"
    if token.endswith("s") and len(token) > 4:
        return token[:-1]
    return token


def _normalize(vector: list[float]) -> list[float]:
    magnitude = math.sqrt(sum(value * value for value in vector))
    if not magnitude:
        return vector
    return [value / magnitude for value in vector]


def _embedding_values(payload: dict[str, Any]) -> list[float]:
    embedding = payload.get("embedding")
    if isinstance(embedding, dict) and isinstance(embedding.get("values"), list):
        return [float(value) for value in embedding["values"]]
    embeddings = payload.get("embeddings")
    if isinstance(embeddings, list) and embeddings:
        first = embeddings[0]
        if isinstance(first, dict) and isinstance(first.get("values"), list):
            return [float(value) for value in first["values"]]
    return []
