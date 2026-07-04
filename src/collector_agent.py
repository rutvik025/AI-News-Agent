"""Collector Agent — deterministic RSS pipeline (no LLM).

Fetches news from 50+ RSS sources, extracts structured article data,
cleans HTML, fetches full content when needed, and generates embeddings.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import aiohttp
import feedparser

from src.schemas import CollectionResult, NewsArticle, RSSSource
from src.utils.embeddings import EMBEDDING_DIM, EmbeddingGenerator
from src.utils.http_client import USER_AGENT
from src.utils.logger import get_logger
from src.utils.paths import resolve_path
from src.utils.source_prioritizer import SourcePrioritizer

logger = get_logger(__name__)

MAX_CONCURRENT = int(os.getenv("MAX_CONCURRENT_REQUESTS", "10"))
RATE_LIMIT_SECONDS = float(os.getenv("RATE_LIMIT_SECONDS", "0.5"))
REDDIT_RATE_LIMIT_SECONDS = float(os.getenv("REDDIT_RATE_LIMIT_SECONDS", "2.5"))
REDDIT_DOMAINS = ("reddit.com", "redd.it")
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT_SECONDS", "10"))
MAX_ARTICLES_PER_SOURCE = int(os.getenv("MAX_ARTICLES_PER_SOURCE", "50"))
MIN_SUMMARY_LENGTH = 100
MAX_SUMMARY_LENGTH = 1000


class CollectorAgent:
    """Fetches RSS feeds concurrently, parses articles, and generates embeddings.

    Pure Python data pipeline — no LLM involved.
    """

    def __init__(
        self,
        sources_config: str | Path | None = None,
        embedding_generator: EmbeddingGenerator | None = None,
        source_prioritizer: SourcePrioritizer | None = None,
    ) -> None:
        self.sources_config = resolve_path(
            sources_config or os.getenv("RSS_SOURCES_CONFIG", "config/rss_sources.yaml")
        )
        self.embedding_generator = embedding_generator or EmbeddingGenerator()
        self._prioritizer = source_prioritizer or SourcePrioritizer(self.sources_config)
        self._failed_sources: list[str] = []
        self._last_sources_count: int = 0

    # ------------------------------------------------------------------
    # Source loading & filtering
    # ------------------------------------------------------------------

    def _load_sources(self) -> list[RSSSource]:
        return self._prioritizer.load_sources()

    def _filter_active_sources(self, sources: list[RSSSource]) -> list[RSSSource]:
        return self._prioritizer.filter_active_sources(sources)

    def _sort_by_priority(self, sources: list[RSSSource]) -> list[RSSSource]:
        return self._prioritizer.sort_by_priority(sources)

    @staticmethod
    def _is_reddit_source(source: RSSSource) -> bool:
        url = source.url.lower()
        return any(domain in url for domain in REDDIT_DOMAINS)

    @staticmethod
    def _looks_like_feed(content: str) -> bool:
        """Return True when response body appears to be RSS/Atom XML."""
        if not content:
            return False
        stripped = content.lstrip()
        if stripped.startswith(("<?xml", "<rss", "<feed", "<RDF")):
            return True
        head = stripped[:200].lower()
        return "<rss" in head or "<feed" in head

    @staticmethod
    def _split_sources_by_domain(
        sources: list[RSSSource],
    ) -> tuple[list[RSSSource], list[RSSSource]]:
        reddit: list[RSSSource] = []
        other: list[RSSSource] = []
        for source in sources:
            if CollectorAgent._is_reddit_source(source):
                reddit.append(source)
            else:
                other.append(source)
        return other, reddit

    @staticmethod
    def _create_batches(
        sources: list[RSSSource],
        batch_size: int = MAX_CONCURRENT,
    ) -> list[list[RSSSource]]:
        return [sources[i : i + batch_size] for i in range(0, len(sources), batch_size)]

    # ------------------------------------------------------------------
    # HTML cleaning & content extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _clean_html(html_text: str) -> str:
        """Clean HTML using readability-lxml (not BeautifulSoup)."""
        if not html_text:
            return ""

        stripped = re.sub(
            r"<(script|style|nav|header|footer)[^>]*>.*?</\1>",
            "",
            html_text,
            flags=re.DOTALL | re.IGNORECASE,
        )

        try:
            from readability import Document

            doc = Document(stripped)
            text = doc.summary()
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text).strip()
            return text
        except Exception as e:
            logger.warning("collector.html_clean_failed", error=str(e))
            return re.sub(r"<[^>]+>", " ", stripped).strip()

    @staticmethod
    def _parse_timestamp(entry: dict[str, Any]) -> str:
        """Parse RSS entry timestamp to ISO format."""
        for field in ("published_parsed", "updated_parsed"):
            parsed = entry.get(field)
            if parsed:
                try:
                    dt = datetime(*parsed[:6], tzinfo=timezone.utc)
                    return dt.isoformat()
                except (TypeError, ValueError):
                    continue

        for field in ("published", "updated"):
            raw = entry.get(field)
            if raw:
                try:
                    dt = parsedate_to_datetime(raw).astimezone(timezone.utc)
                    return dt.isoformat()
                except (TypeError, ValueError):
                    continue

        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _generate_id(link: str, title: str) -> str:
        return hashlib.sha256(f"{link}:{title}".encode()).hexdigest()[:16]

    def _extract_rss_content(self, entry: dict[str, Any]) -> str:
        """Extract and clean content from an RSS entry with fallbacks."""
        try:
            if entry.get("content"):
                for item in entry["content"]:
                    if item.get("value"):
                        return self._clean_html(item["value"])

            for field in ("summary", "description"):
                if entry.get(field):
                    return self._clean_html(entry[field])
        except Exception as e:
            logger.warning("collector.content_extract_failed", error=str(e))

        return ""

    def _extract_full_content_sync(self, url: str) -> str:
        """Fetch full article text using newspaper3k (synchronous)."""
        try:
            from newspaper import Article

            article = Article(url)
            article.download()
            article.parse()
            return article.text or ""
        except Exception as e:
            logger.warning("collector.full_article_failed", url=url, error=str(e))
            return ""

    async def _extract_full_content(self, url: str) -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._extract_full_content_sync, url)

    async def _extract_article(self, entry: dict[str, Any], source: RSSSource) -> NewsArticle | None:
        """Extract a single NewsArticle from an RSS entry."""
        title = entry.get("title", "").strip()
        link = entry.get("link", "").strip()
        if not title or not link:
            return None

        try:
            cleaned = self._extract_rss_content(entry)
            timestamp = self._parse_timestamp(entry)

            summary = cleaned[:MAX_SUMMARY_LENGTH] if cleaned else ""
            content = cleaned

            if len(summary) < MIN_SUMMARY_LENGTH:
                full_text = await self._extract_full_content(link)
                if full_text:
                    content = full_text
                    summary = full_text[:MAX_SUMMARY_LENGTH]

            return NewsArticle(
                id=self._generate_id(link, title),
                title=title,
                link=link,
                summary=summary,
                content=content,
                timestamp=timestamp,
                source=source.name,
                category=source.category,
                credibility=source.credibility,
            )
        except Exception as e:
            logger.warning(
                "collector.article_extract_failed",
                source=source.name,
                title=title[:80],
                error=str(e),
            )
            return None

    # ------------------------------------------------------------------
    # Feed fetching & parsing
    # ------------------------------------------------------------------

    def _parse_feed_entries(
        self,
        content: str,
        source: RSSSource,
    ) -> list[dict[str, Any]]:
        """Parse RSS XML and return raw entries, handling feedparser bozo flag."""
        if not self._looks_like_feed(content):
            preview = re.sub(r"\s+", " ", content[:160]).strip()
            logger.error(
                "collector.feed_not_xml",
                source=source.name,
                url=source.url,
                preview=preview,
                hint="feed_url_returned_html_or_plain_text_not_rss",
            )
            return []

        feed = feedparser.parse(content)

        if feed.bozo:
            exc = feed.bozo_exception
            if not feed.entries:
                logger.error(
                    "collector.feed_parse_failed",
                    source=source.name,
                    url=source.url,
                    error=str(exc),
                )
                return []
            logger.warning(
                "collector.feed_bozo",
                source=source.name,
                error=str(exc),
                entries=len(feed.entries),
            )

        return list(feed.entries[:MAX_ARTICLES_PER_SOURCE])

    @staticmethod
    def _retry_after_seconds(header_value: str | None, attempt: int) -> float:
        if header_value:
            try:
                return max(float(header_value), 1.0)
            except ValueError:
                pass
        return min(2 ** attempt, 30.0)

    async def _fetch_feed_content(self, session: aiohttp.ClientSession, url: str) -> str:
        last_error: Exception | None = None
        for attempt in range(MAX_RETRIES):
            try:
                async with session.get(url) as response:
                    if response.status == 429:
                        wait = self._retry_after_seconds(
                            response.headers.get("Retry-After"),
                            attempt,
                        )
                        logger.warning(
                            "collector.rate_limited",
                            url=url,
                            wait_seconds=wait,
                            attempt=attempt + 1,
                        )
                        await asyncio.sleep(wait)
                        continue

                    response.raise_for_status()
                    return await response.text()
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                last_error = exc
                if attempt < MAX_RETRIES - 1:
                    wait = min(2 ** attempt, 10.0)
                    logger.warning(
                        "collector.fetch_retry",
                        url=url,
                        attempt=attempt + 1,
                        wait_seconds=wait,
                        error=str(exc),
                    )
                    await asyncio.sleep(wait)
                    continue
                raise

        if last_error:
            raise last_error
        raise RuntimeError(f"Rate limited after {MAX_RETRIES} retries: {url}")

    async def fetch_source(
        self,
        session: aiohttp.ClientSession,
        source: RSSSource,
    ) -> list[NewsArticle]:
        """Fetch and parse a single RSS source with retry logic."""
        try:
            content = await self._fetch_feed_content(session, source.url)
            entries = self._parse_feed_entries(content, source)

            articles: list[NewsArticle] = []
            for entry in entries:
                article = await self._extract_article(entry, source)
                if article:
                    articles.append(article)

            logger.info(
                "collector.source_fetched",
                source=source.name,
                articles=len(articles),
            )
            return articles

        except Exception as e:
            self._failed_sources.append(source.name)
            logger.error(
                "collector.source_failed",
                source=source.name,
                url=source.url,
                error=str(e),
            )
            return []

    async def _generate_embeddings(self, articles: list[NewsArticle]) -> None:
        """Generate embeddings in batches (async, non-blocking)."""
        if not articles:
            return

        texts = [a.text_for_embedding for a in articles]
        embeddings = await self.embedding_generator.generate_async(texts)

        for article, embedding in zip(articles, embeddings):
            article.embedding = embedding if embedding else self.embedding_generator.zero_embedding()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def collect_all_news(self) -> list[NewsArticle]:
        """Fetch news from all active RSS sources and return articles with embeddings.

        Returns 200-500 articles depending on feed availability.
        """
        start = time.monotonic()
        self._failed_sources = []

        sources = self._load_sources()
        active = self._filter_active_sources(sources)
        sorted_sources = self._sort_by_priority(active)
        other_sources, reddit_sources = self._split_sources_by_domain(sorted_sources)
        batches = self._create_batches(other_sources)
        self._last_sources_count = len(sorted_sources)

        logger.info(
            "collector.start",
            total_sources=len(sources),
            active_sources=len(active),
            batches=len(batches),
            reddit_sources=len(reddit_sources),
        )

        all_articles: list[NewsArticle] = []
        timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT)

        async with aiohttp.ClientSession(
            timeout=timeout,
            headers={"User-Agent": USER_AGENT},
        ) as session:
            for batch_idx, batch in enumerate(batches):
                logger.info(
                    "collector.batch_start",
                    batch=batch_idx + 1,
                    size=len(batch),
                )
                results = await asyncio.gather(
                    *[self.fetch_source(session, source) for source in batch],
                    return_exceptions=True,
                )

                for source, result in zip(batch, results):
                    if isinstance(result, Exception):
                        self._failed_sources.append(source.name)
                        logger.error(
                            "collector.batch_item_failed",
                            source=source.name,
                            error=str(result),
                        )
                    elif isinstance(result, list):
                        all_articles.extend(result)

                if batch_idx < len(batches) - 1:
                    await asyncio.sleep(RATE_LIMIT_SECONDS)

            if reddit_sources:
                logger.info(
                    "collector.reddit_sequential_start",
                    count=len(reddit_sources),
                    delay_seconds=REDDIT_RATE_LIMIT_SECONDS,
                )
                for reddit_idx, source in enumerate(reddit_sources):
                    articles = await self.fetch_source(session, source)
                    all_articles.extend(articles)
                    if reddit_idx < len(reddit_sources) - 1:
                        await asyncio.sleep(REDDIT_RATE_LIMIT_SECONDS)

        await self._generate_embeddings(all_articles)

        duration = time.monotonic() - start
        success_rate = (
            (len(sorted_sources) - len(self._failed_sources)) / len(sorted_sources) * 100
            if sorted_sources
            else 0.0
        )

        logger.info(
            "collector.complete",
            articles=len(all_articles),
            sources_total=len(sorted_sources),
            sources_failed=len(self._failed_sources),
            failed_sources=self._failed_sources,
            duration_seconds=round(duration, 2),
            success_rate_pct=round(success_rate, 1),
        )

        return all_articles

    async def collect_news(self) -> list[NewsArticle]:
        """Fetch news from all active RSS sources (orchestrator entry point)."""
        return await self.collect_all_news()

    async def collect(self) -> CollectionResult:
        """Run collection and return structured result (used by orchestrator)."""
        start = time.monotonic()
        articles = await self.collect_all_news()
        duration = time.monotonic() - start

        return CollectionResult(
            articles=articles,
            sources_fetched=self._last_sources_count - len(self._failed_sources),
            sources_failed=len(self._failed_sources),
            duration_seconds=duration,
        )

    async def collect_from_sources(self, sources: list[RSSSource]) -> list[NewsArticle]:
        """Collect from a specific list of sources (useful for testing)."""
        self._failed_sources = []
        sorted_sources = self._sort_by_priority(sources)
        batches = self._create_batches(sorted_sources)
        all_articles: list[NewsArticle] = []

        timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT)
        async with aiohttp.ClientSession(
            timeout=timeout,
            headers={"User-Agent": USER_AGENT},
        ) as session:
            for batch_idx, batch in enumerate(batches):
                results = await asyncio.gather(
                    *[self.fetch_source(session, source) for source in batch],
                )
                for result in results:
                    all_articles.extend(result)
                if batch_idx < len(batches) - 1:
                    await asyncio.sleep(RATE_LIMIT_SECONDS)

        await self._generate_embeddings(all_articles)
        return all_articles

    @property
    def failed_sources(self) -> list[str]:
        return list(self._failed_sources)
