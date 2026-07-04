"""Tests for Ranker Agent."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.ranker_agent import RankerAgent
from src.schemas import NewsArticle
from src.utils.scoring import calculate_freshness, calculate_importance, calculate_relevance


class TestRankerAgent:
    def test_calculate_freshness_today(self) -> None:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        score = calculate_freshness(now)
        assert score >= 0.95

    def test_calculate_freshness_old(self) -> None:
        from datetime import datetime, timedelta, timezone
        old = datetime.now(timezone.utc) - timedelta(days=60)
        score = calculate_freshness(old)
        assert score <= 0.30

    def test_calculate_relevance_with_keywords(self) -> None:
        text = "Large language model GPT transformer neural network AI machine learning"
        keywords = ["language model", "GPT", "AI", "machine learning"]
        score = calculate_relevance(text, keywords)
        assert score > 0.0

    def test_rank_returns_top_n(
        self,
        sample_articles: list[NewsArticle],
        topics_config: Path,
    ) -> None:
        agent = RankerAgent(topics_config=topics_config, top_n=2)
        result = agent.rank(sample_articles)
        assert len(result.articles) == 2
        assert all(a.importance_score is not None for a in result.articles)
        scores = [a.importance_score for a in result.articles]
        assert scores == sorted(scores, reverse=True)
