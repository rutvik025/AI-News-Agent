"""Tests for Collector Agent."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.collector_agent import CollectorAgent, MAX_SUMMARY_LENGTH
from src.schemas import NewsArticle, RSSSource, UpdateFrequency


@pytest.fixture
def collector() -> CollectorAgent:
    return CollectorAgent()


@pytest.fixture
def sample_source() -> RSSSource:
    return RSSSource(
        name="ArXiv AI",
        url="https://example.com/feed.xml",
        category="research",
        credibility=1.0,
        priority=1,
        update_frequency=UpdateFrequency.DAILY,
    )


@pytest.fixture
def sample_rss_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
        <channel>
            <title>Test Feed</title>
            <item>
                <title>Breakthrough in Large Language Models</title>
                <link>https://example.com/article-1</link>
                <description><![CDATA[<p>Researchers announce a new LLM architecture.</p>]]></description>
                <pubDate>Mon, 22 Jun 2025 10:30:00 GMT</pubDate>
            </item>
            <item>
                <title>Short</title>
                <link>https://example.com/article-2</link>
                <description>AI</description>
                <pubDate>Mon, 22 Jun 2025 11:00:00 GMT</pubDate>
            </item>
        </channel>
    </rss>"""


class TestCollectorAgent:
    def test_load_sources(self, collector: CollectorAgent) -> None:
        sources = collector._load_sources()
        assert len(sources) >= 50

    def test_filter_and_sort(self, collector: CollectorAgent) -> None:
        sources = collector._load_sources()
        active = collector._filter_active_sources(sources)
        sorted_sources = collector._sort_by_priority(active)
        assert sorted_sources[0].priority <= sorted_sources[-1].priority

    def test_create_batches(self, collector: CollectorAgent) -> None:
        sources = [MagicMock() for _ in range(25)]
        batches = collector._create_batches(sources, batch_size=10)
        assert len(batches) == 3
        assert len(batches[0]) == 10

    def test_looks_like_feed(self, collector: CollectorAgent) -> None:
        assert collector._looks_like_feed('<?xml version="1.0"?><rss><channel></channel></rss>')
        assert collector._looks_like_feed('<feed xmlns="http://www.w3.org/2005/Atom"></feed>')
        assert not collector._looks_like_feed("<!doctype html><html></html>")
        assert not collector._looks_like_feed("RSS feeds are disabled on this site.")

    def test_split_reddit_sources(self, collector: CollectorAgent, sample_source: RSSSource) -> None:
        reddit = RSSSource(
            name="Reddit r/test",
            url="https://www.reddit.com/r/test/.rss",
            category="community",
            credibility=0.65,
            priority=3,
            update_frequency=UpdateFrequency.DAILY,
        )
        other, reddit_sources = collector._split_sources_by_domain([sample_source, reddit])
        assert len(other) == 1
        assert len(reddit_sources) == 1
        assert reddit_sources[0].name == "Reddit r/test"

    def test_clean_html(self, collector: CollectorAgent) -> None:
        html = "<html><body><script>alert(1)</script><p>AI news content</p></body></html>"
        cleaned = collector._clean_html(html)
        assert "AI news content" in cleaned
        assert "alert" not in cleaned

    def test_parse_timestamp_iso(self, collector: CollectorAgent) -> None:
        entry = {"published_parsed": (2025, 6, 22, 10, 30, 0)}
        ts = collector._parse_timestamp(entry)
        assert "2025-06-22" in ts
        assert "T" in ts

    def test_parse_feed_entries(
        self,
        collector: CollectorAgent,
        sample_source: RSSSource,
        sample_rss_xml: str,
    ) -> None:
        entries = collector._parse_feed_entries(sample_rss_xml, sample_source)
        assert len(entries) == 2

    @pytest.mark.asyncio
    async def test_extract_article(
        self,
        collector: CollectorAgent,
        sample_source: RSSSource,
        sample_rss_xml: str,
    ) -> None:
        entries = collector._parse_feed_entries(sample_rss_xml, sample_source)
        with patch.object(collector, "_extract_full_content", return_value=""):
            article = await collector._extract_article(entries[0], sample_source)

        assert article is not None
        assert article.title == "Breakthrough in Large Language Models"
        assert article.source == "ArXiv AI"
        assert article.credibility == 1.0
        assert article.timestamp != ""
        assert len(article.summary) <= MAX_SUMMARY_LENGTH

    @pytest.mark.asyncio
    async def test_fetch_source(
        self,
        collector: CollectorAgent,
        sample_source: RSSSource,
        sample_rss_xml: str,
    ) -> None:
        mock_response = MagicMock()
        mock_response.text = AsyncMock(return_value=sample_rss_xml)
        mock_response.raise_for_status = MagicMock()

        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_response)
        mock_context.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.get.return_value = mock_context

        with patch.object(collector, "_extract_full_content", new=AsyncMock(return_value="")):
            articles = await collector.fetch_source(mock_session, sample_source)

        assert len(articles) == 2
        assert all(isinstance(a, NewsArticle) for a in articles)

    @pytest.mark.asyncio
    async def test_generate_embeddings(self, collector: CollectorAgent) -> None:
        articles = [
            NewsArticle(
                id="1",
                title="Test",
                link="https://example.com",
                summary="AI machine learning",
                source="Test",
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
        ]
        with patch.object(
            collector.embedding_generator,
            "generate_async",
            return_value=[[0.1] * 768],
        ):
            await collector._generate_embeddings(articles)

        assert articles[0].embedding is not None
        assert len(articles[0].embedding) == 768

    @pytest.mark.asyncio
    async def test_collect_all_news(
        self,
        collector: CollectorAgent,
        sample_source: RSSSource,
        sample_rss_xml: str,
    ) -> None:
        with patch.object(collector, "_load_sources", return_value=[sample_source]):
            with patch.object(collector, "_filter_active_sources", side_effect=lambda s: s):
                with patch.object(
                    collector,
                    "fetch_source",
                    return_value=[
                        NewsArticle(
                            id="1",
                            title="AI News",
                            link="https://example.com/1",
                            summary="Machine learning breakthrough " * 5,
                            source=sample_source.name,
                            category=sample_source.category,
                            credibility=sample_source.credibility,
                            timestamp=datetime.now(timezone.utc).isoformat(),
                        )
                    ],
                ):
                    with patch.object(
                        collector.embedding_generator,
                        "generate_async",
                        return_value=[[0.1] * 768],
                    ):
                        articles = await collector.collect_all_news()

        assert len(articles) == 1
        assert articles[0].embedding is not None

    @pytest.mark.asyncio
    async def test_collect_from_sources(
        self,
        collector: CollectorAgent,
        sample_source: RSSSource,
        sample_rss_xml: str,
    ) -> None:
        with patch.object(collector, "fetch_source") as mock_fetch:
            mock_fetch.return_value = [
                NewsArticle(
                    id="1",
                    title="Test Article",
                    link="https://example.com/article-1",
                    summary="AI content " * 20,
                    source=sample_source.name,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
            ]
            with patch.object(
                collector.embedding_generator,
                "generate_async",
                return_value=[[0.1] * 768],
            ):
                articles = await collector.collect_from_sources([sample_source])

        assert len(articles) == 1
        assert articles[0].embedding is not None

    @pytest.mark.asyncio
    async def test_fetch_source_retries_on_failure(
        self,
        collector: CollectorAgent,
        sample_source: RSSSource,
    ) -> None:
        import aiohttp

        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(
            side_effect=aiohttp.ClientError("connection failed")
        )
        mock_context.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.get.return_value = mock_context

        articles = await collector.fetch_source(mock_session, sample_source)
        assert articles == []
        assert sample_source.name in collector.failed_sources
