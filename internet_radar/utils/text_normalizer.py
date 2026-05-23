from __future__ import annotations

import re
import unicodedata


def normalize_text(text: object) -> str:
    value = unicodedata.normalize("NFKC", str(text or "")).replace("\xa0", " ")
    value = value.lower().replace("&", " ")
    value = re.sub(r"['’]", "", value)
    value = re.sub(r"[^a-z0-9.+#-]+", " ", value)
    return " ".join(token.strip(".") for token in value.split() if token.strip("."))


def normalize_topic(topic: object, max_words: int = 6) -> str:
    normalized = normalize_text(topic)
    words = normalized.split()
    return " ".join(words[:max_words])


def tokenize_terms(text: object, min_length: int = 2) -> list[str]:
    return [token for token in normalize_text(text).split() if len(token) >= min_length]
