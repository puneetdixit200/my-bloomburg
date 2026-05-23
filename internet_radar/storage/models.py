from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


Category = Literal[
    "code",
    "social",
    "news",
    "jobs",
    "hackathons",
    "research",
    "finance",
    "search",
    "app_stores",
    "alerts",
    "profile",
]


class SourceDefinition(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    category: Category
    kind: str
    url: str
    requires_auth: bool = False
    default_enabled: bool = False
    reliability: Literal["high", "medium", "experimental"] = "medium"
    notes: str = ""


class SignalRecord(BaseModel):
    id: str | None = None
    topic: str
    title: str
    source: str
    category: Category
    url: str = ""
    score: int = Field(default=0, ge=0, le=100)
    velocity: float = 0.0
    summary: str = ""
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("topic", "title", "source")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def add_stable_id(self) -> "SignalRecord":
        if not self.id:
            key = f"{self.source}|{self.category}|{self.topic.lower()}|{self.title.lower()}|{self.url}"
            self.id = hashlib.sha1(key.encode("utf-8")).hexdigest()[:20]
        return self

    def as_row(self) -> dict[str, Any]:
        data = self.model_dump()
        data["observed_at"] = self.observed_at.isoformat()
        return data


class ValidationResult(BaseModel):
    topic: str
    confidence: int
    phase: str
    sources_confirming: list[str]
    earliest_signal: str


class BriefingPayload(BaseModel):
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    active_sources: int
    signals_24h: int
    top_signals: list[SignalRecord]
    source_health: dict[str, str] = Field(default_factory=dict)
    llm_status: str = "deterministic fallback"


class PageDefinition(BaseModel):
    key: str
    title: str
    category: Category | Literal["all", "mixed"]
    description: str


class UserProfile(BaseModel):
    skills: list[str] = Field(default_factory=list)
    interests: list[str] = Field(default_factory=list)
    goals: list[str] = Field(default_factory=list)
    blocked_topics: list[str] = Field(default_factory=list)
    alert_threshold: int = Field(default=80, ge=0, le=100)
    notification_channels: list[str] = Field(default_factory=list)
    llm_preference: Literal["local", "online", "auto"] = "auto"

    @field_validator("skills", "interests", "goals", "blocked_topics", "notification_channels")
    @classmethod
    def normalize_terms(cls, values: list[str]) -> list[str]:
        return [value.strip().lower() for value in values if value and value.strip()]
