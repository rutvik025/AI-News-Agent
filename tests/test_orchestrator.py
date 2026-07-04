"""Tests for LangGraph Orchestrator."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.orchestrator import Orchestrator, build_orchestrator_graph
from src.schemas import NewsArticle, OrchestratorState


class TestOrchestrator:
    @pytest.fixture
    def orchestrator(self, sample_articles: list[NewsArticle]) -> Orchestrator:
        mock_collector = MagicMock()
        mock_collector.collect_news = AsyncMock(return_value=sample_articles)
        mock_collector._last_sources_count = 3
        mock_collector.failed_sources = []

        mock_deduplicator = MagicMock()
        mock_deduplicator.deduplicate_news = MagicMock(return_value=sample_articles[:2])

        mock_ranker = MagicMock()
        mock_ranker.rank_news = MagicMock(return_value=sample_articles[:2])

        mock_writer = MagicMock()
        mock_writer.write_newsletter = MagicMock(
            return_value="# Test Newsletter\n\nContent here."
        )

        mock_delivery = MagicMock()
        mock_delivery.deliver_newsletter = AsyncMock(
            return_value={"telegram": True, "email": True}
        )

        return Orchestrator(
            collector=mock_collector,
            deduplicator=mock_deduplicator,
            ranker=mock_ranker,
            writer=mock_writer,
            delivery=mock_delivery,
        )

    @pytest.mark.asyncio
    async def test_full_pipeline(
        self,
        orchestrator: Orchestrator,
        sample_articles: list[NewsArticle],
    ) -> None:
        result = await orchestrator.arun(topics=["machine learning", "LLM"])

        assert isinstance(result, OrchestratorState)
        assert result.topics == ["machine learning", "LLM"]
        assert len(result.collected_news) == 3
        assert len(result.deduplicated_news) == 2
        assert len(result.ranked_news) == 2
        assert "Test Newsletter" in result.newsletter
        assert result.delivery_status["telegram"] is True
        assert result.delivery_status["email"] is True

        orchestrator.collector.collect_news.assert_awaited_once()
        orchestrator.deduplicator.deduplicate_news.assert_called_once()
        orchestrator.ranker.rank_news.assert_called_once()
        orchestrator.writer.write_newsletter.assert_called_once()
        orchestrator.delivery.deliver_newsletter.assert_awaited_once()

    def test_build_orchestrator_graph(self) -> None:
        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
            with patch("src.writer_agent.ChatGoogleGenerativeAI"):
                graph = build_orchestrator_graph()
                assert graph is not None

    def test_build_graph_exists(self) -> None:
        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
            with patch("src.writer_agent.ChatGoogleGenerativeAI"):
                orchestrator = Orchestrator()
                graph = orchestrator.build_orchestrator_graph()
                assert graph is not None

    def test_workflow_order(self) -> None:
        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
            with patch("src.writer_agent.ChatGoogleGenerativeAI"):
                orchestrator = Orchestrator()
                graph = orchestrator.build_orchestrator_graph()
                nodes = list(graph.get_graph().nodes)
                assert "collector" in nodes
                assert "deduplicator" in nodes
                assert "ranker" in nodes
                assert "writer" in nodes
                assert "delivery" in nodes
