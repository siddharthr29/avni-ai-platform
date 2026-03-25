"""Local embedding client using sentence-transformers.

Uses all-MiniLM-L6-v2 (384 dimensions, ~80MB) by default. The model is
lazily loaded on first use so it never blocks application startup.

No external API key required -- everything runs locally.
"""

import asyncio
import hashlib
import logging
from collections import OrderedDict
from typing import Any

logger = logging.getLogger(__name__)

# LRU cache for embedding results — avoids recomputing identical queries.
_CACHE_MAX_SIZE = 10_000


class _EmbeddingCache:
    """Thread-safe LRU cache for embedding vectors."""

    def __init__(self, max_size: int = _CACHE_MAX_SIZE) -> None:
        self._cache: OrderedDict[str, list[float]] = OrderedDict()
        self._max_size = max_size
        self.hits = 0
        self.misses = 0

    def _key(self, text: str) -> str:
        return hashlib.md5(text.encode()).hexdigest()

    def get(self, text: str) -> list[float] | None:
        k = self._key(text)
        if k in self._cache:
            self._cache.move_to_end(k)
            self.hits += 1
            return self._cache[k]
        self.misses += 1
        return None

    def put(self, text: str, vector: list[float]) -> None:
        k = self._key(text)
        self._cache[k] = vector
        self._cache.move_to_end(k)
        if len(self._cache) > self._max_size:
            self._cache.popitem(last=False)


class EmbeddingClient:
    """Local embedding model backed by sentence-transformers.

    The model is lazily loaded on first call to ``embed`` or ``embed_batch``.
    This keeps startup instant even when sentence-transformers is installed.

    Includes an LRU cache (10K entries) to avoid recomputing identical queries.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self._model: Any = None
        self.model_name = model_name
        self.dimension = 384  # all-MiniLM-L6-v2 output dimension
        self._cache = _EmbeddingCache()

    @property
    def model(self) -> Any:
        """Lazy-load the SentenceTransformer model on first access."""
        if self._model is None:
            logger.info("Loading embedding model '%s' ...", self.model_name)
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self.model_name)
                logger.info(
                    "Embedding model '%s' loaded (dimension=%d)",
                    self.model_name,
                    self.dimension,
                )
            except ImportError:
                raise ImportError(
                    "sentence-transformers is required for the RAG pipeline. "
                    "Install it with: pip install sentence-transformers>=3.0.0"
                )
        return self._model

    def embed(self, text: str) -> list[float]:
        """Embed a single text string into a normalized vector (cached, sync)."""
        cached = self._cache.get(text)
        if cached is not None:
            return cached
        vector = self.model.encode(text, normalize_embeddings=True).tolist()
        self._cache.put(text, vector)
        return vector

    async def embed_async(self, text: str) -> list[float]:
        """Async-safe embed — runs model.encode() in a thread to avoid blocking the event loop."""
        cached = self._cache.get(text)
        if cached is not None:
            return cached
        vector = await asyncio.to_thread(
            lambda: self.model.encode(text, normalize_embeddings=True).tolist()
        )
        self._cache.put(text, vector)
        return vector

    def embed_batch(
        self, texts: list[str], batch_size: int = 64
    ) -> list[list[float]]:
        """Embed a batch of texts, returning a list of normalized vectors (sync).

        Uses ``batch_size`` to control memory usage for large batches.
        Cached entries are returned from cache; only uncached texts hit the model.
        """
        if not texts:
            return []

        results: list[list[float] | None] = [None] * len(texts)
        uncached_indices: list[int] = []
        uncached_texts: list[str] = []

        for i, text in enumerate(texts):
            cached = self._cache.get(text)
            if cached is not None:
                results[i] = cached
            else:
                uncached_indices.append(i)
                uncached_texts.append(text)

        if uncached_texts:
            vectors = self.model.encode(
                uncached_texts, normalize_embeddings=True, batch_size=batch_size
            ).tolist()
            for idx, vec in zip(uncached_indices, vectors):
                results[idx] = vec
                self._cache.put(texts[idx], vec)

        return results  # type: ignore[return-value]

    async def embed_batch_async(
        self, texts: list[str], batch_size: int = 64
    ) -> list[list[float]]:
        """Async-safe batch embed — runs model.encode() in a thread."""
        if not texts:
            return []

        results: list[list[float] | None] = [None] * len(texts)
        uncached_indices: list[int] = []
        uncached_texts: list[str] = []

        for i, text in enumerate(texts):
            cached = self._cache.get(text)
            if cached is not None:
                results[i] = cached
            else:
                uncached_indices.append(i)
                uncached_texts.append(text)

        if uncached_texts:
            vectors = await asyncio.to_thread(
                lambda: self.model.encode(
                    uncached_texts, normalize_embeddings=True, batch_size=batch_size
                ).tolist()
            )
            for idx, vec in zip(uncached_indices, vectors):
                results[idx] = vec
                self._cache.put(texts[idx], vec)

        return results  # type: ignore[return-value]
