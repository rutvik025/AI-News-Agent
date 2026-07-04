"""Importance scoring formula for article ranking."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

import yaml

from src.schemas import NewsArticle, TopicsConfig
from src.utils.logger import get_logger
from src.utils.paths import resolve_path
from src.utils.timezone_utils import get_timezone

logger = get_logger(__name__)

FRESHNESS_WEIGHT = 0.4
CREDIBILITY_WEIGHT = 0.3
RELEVANCE_WEIGHT = 0.3


def load_topics_config(config_path: str | Path = "config/topics_config.yaml") -> TopicsConfig:
    path = resolve_path(config_path)
    logger.debug("scoring.load_topics_config", path=str(path))
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return TopicsConfig(**data)


def calculate_freshness(published_at: datetime | None) -> float:
    """Score from 1.0 (today) to 0.1 (month+ old)."""
    if published_at is None:
        return 0.5

    now = datetime.now(get_timezone())
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)

    published_local = published_at.astimezone(get_timezone())
    age_days = (now - published_local).total_seconds() / 86400

    if age_days <= 0:
        return 1.0
    if age_days <= 1:
        return 0.95
    if age_days <= 3:
        return 0.85
    if age_days <= 7:
        return 0.70
    if age_days <= 14:
        return 0.50
    if age_days <= 30:
        return 0.30
    return 0.10


def calculate_relevance(text: str, keywords: list[str]) -> float:
    """Calculate AI keyword density relevance score."""
    if not text or not keywords:
        return 0.0

    text_lower = text.lower()
    word_count = max(len(text_lower.split()), 1)
    matches = 0

    for keyword in keywords:
        pattern = re.escape(keyword.lower())
        matches += len(re.findall(pattern, text_lower))

    density = matches / word_count
    score = min(density * 10, 1.0)
    return round(score, 3)


def calculate_importance(
    article: NewsArticle,
    keywords: list[str],
) -> float:
    freshness = calculate_freshness(article.published_at)
    credibility = article.credibility
    text = f"{article.title} {article.summary} {article.content}"
    relevance = calculate_relevance(text, keywords)

    score = (
        FRESHNESS_WEIGHT * freshness
        + CREDIBILITY_WEIGHT * credibility
        + RELEVANCE_WEIGHT * relevance
    )
    return round(score, 4)


def rank_articles(
    articles: list[NewsArticle],
    keywords: list[str],
    top_n: int = 20,
) -> list[NewsArticle]:
    """Score and rank articles, returning top N."""
    for article in articles:
        article.freshness_score = calculate_freshness(article.published_at)
        text = f"{article.title} {article.summary} {article.content}"
        article.relevance_score = calculate_relevance(text, keywords)
        article.importance_score = calculate_importance(article, keywords)

    ranked = sorted(
        articles,
        key=lambda a: a.importance_score or 0.0,
        reverse=True,
    )
    result = ranked[:top_n]
    logger.info("scoring.ranked", input_count=len(articles), output_count=len(result))
    return result
