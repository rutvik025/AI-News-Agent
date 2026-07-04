"""Integration tests for the full workflow."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.schemas import NewsArticle, RSSSource, UpdateFrequency
from src.utils.embeddings import EMBEDDING_DIM, EmbeddingGenerator
from src.utils.scoring import rank_articles
from src.utils.source_prioritizer import filter_active_sources, load_rss_sources


class TestIntegration:
    def test_load_rss_sources(self, rss_sources_config: Path) -> None:
        sources = load_rss_sources(rss_sources_config)
        assert len(sources) >= 50
        assert all(isinstance(s, RSSSource) for s in sources)

    def test_filter_active_sources(self, rss_sources_config: Path) -> None:
        sources = load_rss_sources(rss_sources_config)
        active = filter_active_sources(sources)
        assert len(active) > 0
        assert active[0].priority <= active[-1].priority

    def test_embedding_cosine_similarity(self) -> None:
        a = [1.0, 0.0, 0.0]
        b = [1.0, 0.0, 0.0]
        c = [0.0, 1.0, 0.0]
        assert EmbeddingGenerator.cosine_similarity(a, b) == pytest.approx(1.0)
        assert EmbeddingGenerator.cosine_similarity(a, c) == pytest.approx(0.0)

    def test_end_to_end_scoring_pipeline(self, sample_articles: list[NewsArticle]) -> None:
        keywords = ["GPT", "AI", "machine learning", "reinforcement learning"]
        ranked = rank_articles(sample_articles, keywords, top_n=2)
        assert len(ranked) == 2
        assert ranked[0].importance_score >= ranked[1].importance_score

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_collector_with_mock_http(self, sample_rss_xml: str) -> None:
        from src.collector_agent import CollectorAgent

        source = RSSSource(
            name="Test",
            url="https://example.com/feed",
            category="test",
            credibility=0.9,
            priority=1,
            update_frequency=UpdateFrequency.DAILY,
        )

        agent = CollectorAgent()

        mock_response = MagicMock()
        mock_response.text = AsyncMock(return_value=sample_rss_xml)
        mock_response.raise_for_status = MagicMock()

        mock_get_context = MagicMock()
        mock_get_context.__aenter__ = AsyncMock(return_value=mock_response)
        mock_get_context.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.get.return_value = mock_get_context
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("src.collector_agent.aiohttp.ClientSession", return_value=mock_session):
            with patch.object(
                agent,
                "_extract_full_content",
                new=AsyncMock(return_value=""),
            ):
                with patch.object(
                    agent.embedding_generator,
                    "generate_async",
                    return_value=[[0.1] * EMBEDDING_DIM],
                ):
                    articles = await agent.collect_from_sources([source])

        assert len(articles) >= 1
