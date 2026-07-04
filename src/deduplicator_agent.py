"""Deduplicator Agent — semantic similarity deduplication with ChromaDB."""

from __future__ import annotations

import os
import time

import chromadb
from chromadb.config import Settings

from src.schemas import DeduplicationResult, NewsArticle
from src.utils.embeddings import EmbeddingGenerator
from src.utils.logger import get_logger
from src.utils.paths import resolve_env_path
from src.utils.timezone_utils import now_local

logger = get_logger(__name__)

DEFAULT_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", "0.85"))
DEFAULT_CHROMADB_PATH = str(resolve_env_path("CHROMADB_PATH", "outputs/chroma_db"))


class DeduplicatorAgent:
    """Remove duplicate articles using cosine similarity and ChromaDB storage."""

    def __init__(
        self,
        similarity_threshold: float = DEFAULT_THRESHOLD,
        chromadb_path: str = DEFAULT_CHROMADB_PATH,
        embedding_generator: EmbeddingGenerator | None = None,
    ) -> None:
        self.similarity_threshold = similarity_threshold
        self.chromadb_path = chromadb_path
        self.embedding_generator = embedding_generator or EmbeddingGenerator()
        self._client: chromadb.ClientAPI | None = None
        self._collection: chromadb.Collection | None = None

    def _get_collection(self) -> chromadb.Collection:
        if self._collection is None:
            self._client = chromadb.PersistentClient(
                path=self.chromadb_path,
                settings=Settings(anonymized_telemetry=False),
            )
            self._collection = self._client.get_or_create_collection(
                name="news_articles",
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    def _is_duplicate(self, embedding: list[float], collection: chromadb.Collection) -> bool:
        if collection.count() == 0:
            return False

        results = collection.query(
            query_embeddings=[embedding],
            n_results=1,
            include=["distances"],
        )
        distances = results.get("distances", [[]])[0]
        if not distances:
            return False

        similarity = 1.0 - distances[0]
        return similarity >= self.similarity_threshold

    def _store_article(self, article: NewsArticle, collection: chromadb.Collection) -> None:
        if not article.embedding:
            return
        collection.add(
            ids=[article.id],
            embeddings=[article.embedding],
            metadatas=[{
                "title": article.title[:200],
                "source": article.source,
                "link": article.link,
                "stored_at": now_local().isoformat(),
            }],
            documents=[article.text_for_embedding[:1000]],
        )

    def deduplicate(self, articles: list[NewsArticle]) -> DeduplicationResult:
        start = time.monotonic()
        collection = self._get_collection()
        unique: list[NewsArticle] = []
        duplicates_removed = 0
        seen_in_batch: list[list[float]] = []

        for article in articles:
            if not article.embedding:
                article.embedding = self.embedding_generator.generate_single(
                    article.text_for_embedding
                )

            is_dup_external = self._is_duplicate(article.embedding, collection)
            is_dup_internal = any(
                self.embedding_generator.cosine_similarity(article.embedding, emb)
                >= self.similarity_threshold
                for emb in seen_in_batch
            )

            if is_dup_external or is_dup_internal:
                duplicates_removed += 1
                continue

            unique.append(article)
            seen_in_batch.append(article.embedding)
            self._store_article(article, collection)

        duration = time.monotonic() - start
        logger.info(
            "deduplicator.complete",
            input_count=len(articles),
            unique_count=len(unique),
            duplicates_removed=duplicates_removed,
            duration=round(duration, 2),
        )

        return DeduplicationResult(
            articles=unique,
            duplicates_removed=duplicates_removed,
            duration_seconds=duration,
        )

    def deduplicate_news(self, articles: list[NewsArticle]) -> list[NewsArticle]:
        """Remove duplicate articles (orchestrator entry point)."""
        return self.deduplicate(articles).articles

    def clear_storage(self) -> None:
        """Clear ChromaDB collection (for testing)."""
        if self._client:
            self._client.delete_collection("news_articles")
            self._collection = None
