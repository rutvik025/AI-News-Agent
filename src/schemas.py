"""Pydantic models for the AI News Aggregator."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class UpdateFrequency(str, Enum):
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"


class RSSSource(BaseModel):
    name: str
    url: str
    category: str
    credibility: float = Field(ge=0.0, le=1.0)
    priority: int = Field(ge=1, le=4)
    update_frequency: UpdateFrequency
    active: bool = True

    @field_validator("credibility")
    @classmethod
    def validate_credibility(cls, v: float) -> float:
        return round(v, 2)


class NewsArticle(BaseModel):
    id: str
    title: str
    link: str
    summary: str = ""
    content: str = ""
    timestamp: str = ""
    source: str
    category: str = ""
    credibility: float = 0.5
    published_at: datetime | None = None
    embedding: list[float] | None = None
    importance_score: float | None = None
    relevance_score: float | None = None
    freshness_score: float | None = None

    @property
    def text_for_embedding(self) -> str:
        return f"{self.title}\n{self.summary}\n{self.content[:500]}"

    @property
    def display_text(self) -> str:
        return self.content if len(self.content) > len(self.summary) else self.summary

    def model_post_init(self, __context: Any) -> None:
        if self.timestamp and self.published_at is None:
            try:
                self.published_at = datetime.fromisoformat(
                    self.timestamp.replace("Z", "+00:00")
                )
            except ValueError:
                pass
        elif self.published_at and not self.timestamp:
            self.timestamp = self.published_at.isoformat()


class OrchestratorState(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    topics: list[str] = Field(default_factory=list)
    collected_news: list[NewsArticle] = Field(default_factory=list)
    deduplicated_news: list[NewsArticle] = Field(default_factory=list)
    ranked_news: list[NewsArticle] = Field(default_factory=list)
    newsletter: str = ""
    delivery_status: dict[str, bool] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeliveryConfig(BaseModel):
    telegram_enabled: bool = True
    email_enabled: bool = True
    telegram_max_message_length: int = 4000
    newsletter_output_dir: str = "./outputs/newsletters"


class TopicsConfig(BaseModel):
    keywords: list[str] = Field(default_factory=list)
    themes: list[str] = Field(default_factory=list)
    min_keyword_density: float = 0.01


class CollectionResult(BaseModel):
    articles: list[NewsArticle]
    sources_fetched: int
    sources_failed: int
    duration_seconds: float


class DeduplicationResult(BaseModel):
    articles: list[NewsArticle]
    duplicates_removed: int
    duration_seconds: float


class RankingResult(BaseModel):
    articles: list[NewsArticle]
    duration_seconds: float
