from __future__ import annotations

import re
from collections import Counter


KEY_PHRASES = [
    "browser agents",
    "local llms",
    "local llm",
    "mcp servers",
    "browser automation",
    "agentic ai",
    "developer tools",
    "startup pain",
    "machine learning",
    "open source",
    "playwright",
    "ollama",
    "streamlit",
    "chromadb",
]

STOPWORDS = {
    "about",
    "after",
    "again",
    "with",
    "using",
    "developers",
    "developer",
    "keep",
    "show",
    "mentions",
    "mentioning",
    "signal",
    "trend",
    "tools",
}

SKIP_ENTITIES = {"Show"}


def extract_keywords(text: str, limit: int = 10) -> list[str]:
    normalized = _normalize(text)
    found: list[str] = []
    seen: set[str] = set()
    for phrase in KEY_PHRASES:
        if phrase == "local llm" and "local llms" in seen:
            continue
        if phrase in normalized and phrase not in seen:
            found.append(phrase)
            seen.add(phrase)

    if len(found) >= limit:
        return found[:limit]

    counts = Counter(
        token
        for token in re.findall(r"[a-z][a-z0-9.+#-]{2,}", normalized)
        if token not in STOPWORDS and token not in seen
    )
    found.extend(token for token, _ in counts.most_common(limit - len(found)))
    return found[:limit]


def extract_entities(text: str, limit: int = 12) -> list[str]:
    entities: list[str] = []
    seen: set[str] = set()
    for match in re.finditer(r"\b[A-Z][A-Za-z0-9.+#-]*\b", text):
        entity = match.group(0).strip()
        if entity in SKIP_ENTITIES or entity in seen:
            continue
        entities.append(entity)
        seen.add(entity)
        if len(entities) >= limit:
            break
    if len(entities) > 1 and entities[0] == "HN":
        entities = [entities[1], entities[0], *entities[2:]]
    return entities


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()
