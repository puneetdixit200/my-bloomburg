from __future__ import annotations

import re
from dataclasses import dataclass

from internet_radar.brain.local_llm import OllamaClient


@dataclass(frozen=True)
class LLMChoice:
    provider: str
    model: str
    reason: str


class LLMRouter:
    def __init__(self, available_models: list[str] | None = None, ollama_client: OllamaClient | None = None) -> None:
        self.ollama_client = ollama_client or OllamaClient()
        self._available_models = available_models

    @property
    def available_models(self) -> list[str]:
        if self._available_models is None:
            self._available_models = self.ollama_client.available_models()
        return self._available_models

    def route(self, task: str, content_length: int) -> LLMChoice:
        preferred = {
            "classify": ["phi3:mini", "qwen2.5:0.5b"],
            "sentiment": ["phi3:mini", "qwen2.5:0.5b"],
            "extract_keywords": ["phi3:mini", "qwen2.5:0.5b"],
            "summarize": ["llama3.2", "qwen2.5:0.5b"],
            "score": ["llama3.2", "qwen2.5:0.5b"],
            "filter": ["llama3.2", "qwen2.5:0.5b"],
            "gap_analysis": ["mistral", "llama3.2", "qwen2.5:0.5b"],
            "idea_generate": ["mistral", "llama3.2", "qwen2.5:0.5b"],
            "trend_predict": ["mistral", "llama3.2", "qwen2.5:0.5b"],
        }.get(task, ["qwen2.5:0.5b"])

        if content_length > 50_000:
            return LLMChoice(provider="online-fallback", model="gemini-1.5-flash", reason="huge context")

        for model in preferred:
            if model in self.available_models:
                return LLMChoice(provider="ollama", model=model, reason=f"local model for {task}")

        if self.available_models:
            return LLMChoice(provider="ollama", model=self.available_models[0], reason="installed local model")

        return LLMChoice(provider="deterministic", model="rules", reason="no local model available")

    def classify_signal(self, text: str, allow_network: bool = True) -> dict[str, object]:
        choice = self.route("classify", len(text))
        if allow_network and choice.provider == "ollama":
            client = self.ollama_client
            if isinstance(client, OllamaClient) and client.model != choice.model:
                client = OllamaClient(model=choice.model)
            prompt = (
                "Return JSON with keys topic, sentiment, confidence for this technology signal: "
                f"{text[:2000]}"
            )
            try:
                result = client.generate_json(prompt)
                if {"topic", "sentiment", "confidence"} <= set(result):
                    return normalize_classification(result, text)
            except Exception:
                pass
        return deterministic_classify(text)


def normalize_classification(result: dict[str, object], fallback_text: str) -> dict[str, object]:
    fallback = deterministic_classify(fallback_text)

    topic = str(result.get("topic") or fallback["topic"]).strip().lower()
    if not topic:
        topic = str(fallback["topic"])
    fallback_topic = str(fallback["topic"])
    if fallback["confidence"] >= 70 and fallback_topic != "technology trend" and fallback_topic in fallback_text.lower():
        topic = fallback_topic

    sentiment = str(result.get("sentiment") or "").strip().lower()
    if sentiment not in {"positive", "neutral", "negative"}:
        sentiment = "neutral"
    fallback_sentiment = str(fallback["sentiment"])
    if fallback["confidence"] >= 70 and fallback_sentiment != "neutral" and sentiment != fallback_sentiment:
        sentiment = fallback_sentiment

    raw_confidence = result.get("confidence", fallback["confidence"])
    try:
        confidence = float(str(raw_confidence).strip().rstrip("%"))
    except (TypeError, ValueError):
        confidence = float(fallback["confidence"])
    if 0 <= confidence <= 1:
        confidence *= 100
    confidence = int(round(max(0, min(confidence, 100))))

    return {"topic": topic, "sentiment": sentiment, "confidence": confidence}


def deterministic_classify(text: str) -> dict[str, object]:
    lower = text.lower()
    topic_patterns = [
        (r"browser agents?|browser automation", "browser agents"),
        (r"\bmcp\b|model context protocol", "mcp"),
        (r"ollama|local llm", "local llm"),
        (r"streamlit", "streamlit"),
        (r"hackathon", "hackathon"),
        (r"intern", "internships"),
    ]
    topic = "technology trend"
    for pattern, label in topic_patterns:
        if re.search(pattern, lower):
            topic = label
            break

    positive_terms = {"exploding", "growth", "growing", "hot", "fast", "funded", "spike"}
    negative_terms = {"pain", "complaint", "broken", "hate", "decline", "abandoned"}
    sentiment = "neutral"
    if any(term in lower for term in positive_terms):
        sentiment = "positive"
    if any(term in lower for term in negative_terms):
        sentiment = "negative"

    confidence = 70 if topic != "technology trend" else 45
    return {"topic": topic, "sentiment": sentiment, "confidence": confidence}
