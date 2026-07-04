"""Embedding generation using sentence-transformers."""

from __future__ import annotations

import asyncio
import os
from functools import lru_cache

import numpy as np
from sentence_transformers import SentenceTransformer

from src.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-ai/nomic-embed-text-v1")
DEFAULT_BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", "32"))
EMBEDDING_DIM = 768


@lru_cache(maxsize=1)
def _load_model(model_name: str) -> SentenceTransformer:
    logger.info("embeddings.model_loading", model=model_name)
    model = SentenceTransformer(model_name, trust_remote_code=True)
    logger.info("embeddings.model_loaded", model=model_name)
    return model


class EmbeddingGenerator:
    """Generate embeddings for article deduplication and similarity."""

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        batch_size: int = DEFAULT_BATCH_SIZE,
    ) -> None:
        self.model_name = model_name
        self.batch_size = batch_size
        self._model: SentenceTransformer | None = None

    @property
    def model(self) -> SentenceTransformer:
        if self._model is None:
            self._model = _load_model(self.model_name)
        return self._model

    def _encode_batch(self, texts: list[str]) -> list[list[float]]:
        prefixed = [f"search_document: {t}" for t in texts]
        embeddings = self.model.encode(
            prefixed,
            batch_size=self.batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return [emb.tolist() for emb in embeddings]

    def generate(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        logger.info("embeddings.generating", count=len(texts), batch_size=self.batch_size)
        try:
            return self._encode_batch(texts)
        except Exception as e:
            logger.error("embeddings.batch_failed", error=str(e))
            return [[0.0] * EMBEDDING_DIM for _ in texts]

    async def generate_async(self, texts: list[str]) -> list[list[float]]:
        """Run embedding generation in a thread pool to avoid blocking the event loop."""
        if not texts:
            return []

        logger.info("embeddings.generating_async", count=len(texts), batch_size=self.batch_size)
        loop = asyncio.get_running_loop()

        all_embeddings: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            try:
                batch_embeddings = await loop.run_in_executor(None, self._encode_batch, batch)
                all_embeddings.extend(batch_embeddings)
            except Exception as e:
                logger.error(
                    "embeddings.async_batch_failed",
                    batch_start=i,
                    error=str(e),
                )
                all_embeddings.extend([[0.0] * EMBEDDING_DIM for _ in batch])

        return all_embeddings

    def generate_single(self, text: str) -> list[float]:
        result = self.generate([text])
        return result[0] if result else [0.0] * EMBEDDING_DIM

    def zero_embedding(self) -> list[float]:
        return [0.0] * EMBEDDING_DIM

    @staticmethod
    def cosine_similarity(a: list[float], b: list[float]) -> float:
        vec_a = np.array(a)
        vec_b = np.array(b)
        norm_a = np.linalg.norm(vec_a)
        norm_b = np.linalg.norm(vec_b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(vec_a, vec_b) / (norm_a * norm_b))
