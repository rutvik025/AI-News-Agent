"""Pytest configuration and shared fixtures."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent
RSS_SOURCES_CONFIG = PROJECT_ROOT / "config" / "rss_sources.yaml"
TOPICS_CONFIG = PROJECT_ROOT / "config" / "topics_config.yaml"
sys.path.insert(0, str(PROJECT_ROOT))

from src.schemas import NewsArticle, RSSSource, UpdateFrequency


@pytest.fixture
def rss_sources_config() -> Path:
    return RSS_SOURCES_CONFIG


@pytest.fixture
def topics_config() -> Path:
    return TOPICS_CONFIG


@pytest.fixture
def sample_source() -> RSSSource:
    return RSSSource(
        name="Test Source",
        url="https://example.com/feed.xml",
        category="test",
        credibility=0.9,
        priority=1,
        update_frequency=UpdateFrequency.DAILY,
    )


@pytest.fixture
def sample_articles() -> list[NewsArticle]:
    now = datetime.now(timezone.utc)
    return [
        NewsArticle(
            id="article-1",
            title="OpenAI Releases GPT-5 with Multimodal Capabilities",
            link="https://example.com/gpt5",
            summary="OpenAI announced GPT-5 with advanced multimodal reasoning.",
            content="Full article about GPT-5 release and capabilities.",
            source="OpenAI Blog",
            category="industry",
            credibility=0.95,
            published_at=now,
            timestamp=now.isoformat(),
            embedding=[0.1] * 384,
        ),
        NewsArticle(
            id="article-2",
            title="GPT-5 Launch: OpenAI's New Multimodal Model",
            link="https://example.com/gpt5-launch",
            summary="Similar article about GPT-5 launch from different source.",
            content="Another article covering the same GPT-5 announcement.",
            source="TechCrunch",
            category="tech_news",
            credibility=0.85,
            published_at=now,
            timestamp=now.isoformat(),
            embedding=[0.11] * 384,
        ),
        NewsArticle(
            id="article-3",
            title="New Reinforcement Learning Breakthrough",
            link="https://example.com/rl-breakthrough",
            summary="Researchers achieve new state-of-the-art in RL.",
            content="Details about reinforcement learning advances.",
            source="ArXiv cs.LG",
            category="ai_research",
            credibility=1.0,
            published_at=now,
            timestamp=now.isoformat(),
            embedding=[0.9] * 384,
        ),
    ]


@pytest.fixture
def sample_rss_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
        <channel>
            <title>Test Feed</title>
            <item>
                <title>Test Article Title</title>
                <link>https://example.com/article-1</link>
                <description>Test article summary content here.</description>
                <pubDate>Mon, 01 Jan 2024 12:00:00 GMT</pubDate>
            </item>
        </channel>
    </rss>"""
