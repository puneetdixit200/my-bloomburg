from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass

import requests


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
    def __init__(self, model: str = "nomic-embed-text", host: str = "http://localhost:11434", timeout: float = 10.0) -> None:
        self.model = model
        self.host = host.rstrip("/")
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


class EmbeddingRouter:
    def __init__(self, available_models: list[str] | None = None) -> None:
        self.available_models = available_models or []

    def route(self) -> EmbeddingChoice:
        if "nomic-embed-text" in self.available_models:
            return EmbeddingChoice(provider="ollama", model="nomic-embed-text", reason="local embedding model")
        return EmbeddingChoice(provider="deterministic", model="hashed-bow", reason="space-conscious local fallback")

    def embedder(self) -> DeterministicEmbedder | OllamaEmbedder:
        choice = self.route()
        if choice.provider == "ollama":
            return OllamaEmbedder(model=choice.model)
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
