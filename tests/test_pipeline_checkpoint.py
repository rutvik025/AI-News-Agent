"""Tests for pipeline checkpoint helpers."""

from __future__ import annotations

import json

from src.schemas import NewsArticle
from src.utils.pipeline_checkpoint import (
    articles_from_dicts,
    articles_to_dicts,
    load_snapshot_for_resume,
    save_node_snapshot,
)


class TestPipelineCheckpoint:
    def test_article_roundtrip(self, sample_articles: list[NewsArticle]) -> None:
        payload = articles_to_dicts(sample_articles)
        restored = articles_from_dicts(payload)
        assert len(restored) == len(sample_articles)
        assert restored[0].title == sample_articles[0].title

    def test_save_and_load_writer_snapshot(
        self,
        sample_articles: list[NewsArticle],
        tmp_path,
        monkeypatch,
    ) -> None:
        monkeypatch.setenv("PIPELINE_SNAPSHOT_DIR", str(tmp_path))
        thread_id = "test-thread"
        state = {
            "ranked_news": articles_to_dicts(sample_articles[:2]),
            "metadata": {"ranking": {"top_n": 2}},
        }
        save_node_snapshot(thread_id, "ranker", state)

        loaded = load_snapshot_for_resume(thread_id, "writer")
        assert loaded is not None
        assert loaded["resume_from"] == "writer"
        assert len(loaded["ranked_news"]) == 2

    def test_snapshot_file_written(
        self,
        sample_articles: list[NewsArticle],
        tmp_path,
        monkeypatch,
    ) -> None:
        monkeypatch.setenv("PIPELINE_SNAPSHOT_DIR", str(tmp_path))
        save_node_snapshot("t1", "collector", {"collected_news": articles_to_dicts(sample_articles)})
        path = tmp_path / "t1" / "collector.json"
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["last_completed_node"] == "collector"
