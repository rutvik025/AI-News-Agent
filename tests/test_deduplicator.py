"""Tests for Deduplicator Agent."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.deduplicator_agent import DeduplicatorAgent
from src.schemas import NewsArticle


class TestDeduplicatorAgent:
    def test_deduplicate_removes_similar_articles(self, sample_articles: list[NewsArticle]) -> None:
        agent = DeduplicatorAgent(similarity_threshold=0.85, chromadb_path="./outputs/test_chroma")

        with patch.object(agent, "_get_collection") as mock_get_collection:
            mock_collection = MagicMock()
            mock_collection.count.return_value = 0
            mock_get_collection.return_value = mock_collection

            with patch.object(agent.embedding_generator, "cosine_similarity", return_value=0.95):
                result = agent.deduplicate(sample_articles)

        assert result.duplicates_removed >= 1
        assert len(result.articles) < len(sample_articles)

    def test_deduplicate_keeps_unique_articles(self, sample_articles: list[NewsArticle]) -> None:
        agent = DeduplicatorAgent(similarity_threshold=0.99, chromadb_path="./outputs/test_chroma")

        with patch.object(agent, "_get_collection") as mock_get_collection:
            mock_collection = MagicMock()
            mock_collection.count.return_value = 0
            mock_get_collection.return_value = mock_collection

            with patch.object(agent.embedding_generator, "cosine_similarity", return_value=0.5):
                result = agent.deduplicate(sample_articles)

        assert len(result.articles) == len(sample_articles)
