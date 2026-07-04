"""Ranker Agent — importance scoring and top-N selection."""

from __future__ import annotations

import os
import time
from pathlib import Path

from src.schemas import NewsArticle, RankingResult
from src.utils.logger import get_logger
from src.utils.paths import resolve_path
from src.utils.scoring import load_topics_config, rank_articles

logger = get_logger(__name__)

DEFAULT_TOP_N = int(os.getenv("TOP_ARTICLES_COUNT", "20"))


class RankerAgent:
    """Score articles by importance and return top N."""

    def __init__(
        self,
        topics_config: str | Path = "config/topics_config.yaml",
        top_n: int = DEFAULT_TOP_N,
    ) -> None:
        self.topics_config = resolve_path(topics_config)
        self.top_n = top_n
        self._keywords: list[str] | None = None

    @property
    def keywords(self) -> list[str]:
        if self._keywords is None:
            config = load_topics_config(self.topics_config)
            self._keywords = config.keywords
        return self._keywords

    def rank(self, articles: list[NewsArticle]) -> RankingResult:
        start = time.monotonic()
        ranked = rank_articles(articles, self.keywords, self.top_n)
        duration = time.monotonic() - start

        logger.info(
            "ranker.complete",
            input_count=len(articles),
            output_count=len(ranked),
            top_score=ranked[0].importance_score if ranked else 0,
            duration=round(duration, 2),
        )

        return RankingResult(articles=ranked, duration_seconds=duration)

    def rank_news(
        self,
        articles: list[NewsArticle],
        topics: list[str] | None = None,
    ) -> list[NewsArticle]:
        """Score and rank articles, returning top N (orchestrator entry point)."""
        from src.utils.scoring import rank_articles

        start = time.monotonic()
        keywords = topics if topics else self.keywords
        ranked = rank_articles(articles, keywords, self.top_n)
        duration = time.monotonic() - start

        logger.info(
            "ranker.complete",
            input_count=len(articles),
            output_count=len(ranked),
            top_score=ranked[0].importance_score if ranked else 0,
            duration=round(duration, 2),
        )
        return ranked
