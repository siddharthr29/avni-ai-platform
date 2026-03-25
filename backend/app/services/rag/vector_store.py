"""pgvector-backed vector store with hybrid search.

Provides semantic search (cosine similarity via HNSW index), BM25 keyword
search (via PostgreSQL tsvector/GIN), and hybrid search that fuses both
result sets using Reciprocal Rank Fusion (RRF).

Schema:
    ai_knowledge_chunks -- single table holding all embedded knowledge
    Indexes: HNSW (vector), GIN (tsvector), B-tree (collection), GIN (metadata)
"""

import json
import logging
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)


def reciprocal_rank_fusion(
    result_lists: list[list[dict[str, Any]]],
    weights: list[float],
    k: int = 60,
) -> list[dict[str, Any]]:
    """Reciprocal Rank Fusion across multiple ranked result lists.

    For each document appearing in any result list:
        score = sum(weight_i / (k + rank_i + 1))  for each list containing it

    Args:
        result_lists: List of ranked result lists. Each result must have an "id" key.
        weights: Corresponding weight for each result list.
        k: RRF constant (default 60, per the original RRF paper).

    Returns:
        Fused results sorted by descending RRF score.
    """
    scores: dict[int, dict[str, Any]] = {}

    for results, weight in zip(result_lists, weights):
        for rank, result in enumerate(results):
            doc_id = result["id"]
            if doc_id not in scores:
                scores[doc_id] = {"score": 0.0, **result}
            scores[doc_id]["score"] += weight / (k + rank + 1)

    fused = sorted(scores.values(), key=lambda x: x["score"], reverse=True)
    return fused


class VectorStore:
    """pgvector-backed vector store with hybrid search capabilities.

    Manages a single ``ai_knowledge_chunks`` table partitioned by
    ``collection`` (concepts, forms, rules, transcripts, support, srs_examples).
    """

    def __init__(self, dsn: str, embedding_dimension: int = 384) -> None:
        self.dsn = dsn
        self.embedding_dimension = embedding_dimension
        self._pool: asyncpg.Pool | None = None

    async def initialize(self) -> None:
        """Create connection pool and ensure schema + indexes exist."""
        logger.info("VectorStore: connecting to %s", self._safe_dsn())
        from app.config import settings
        self._pool = await asyncpg.create_pool(
            self.dsn,
            min_size=settings.DB_POOL_MIN,
            max_size=settings.DB_POOL_MAX,
        )
        await self._create_schema()
        logger.info("VectorStore: initialized successfully")

    def _safe_dsn(self) -> str:
        """Return DSN with password masked for logging."""
        parts = self.dsn.split("@")
        if len(parts) > 1:
            return "***@" + parts[-1]
        return self.dsn[:30] + "..."

    async def _create_schema(self) -> None:
        """Create the table and all indexes if they do not exist."""
        async with self._pool.acquire() as conn:
            # Enable pgvector extension
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")

            # Main knowledge chunks table
            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS ai_knowledge_chunks (
                    id SERIAL PRIMARY KEY,
                    collection VARCHAR(50) NOT NULL,
                    content TEXT NOT NULL,
                    context_prefix TEXT DEFAULT '',
                    embedding vector({self.embedding_dimension}),
                    metadata JSONB DEFAULT '{{}}'::jsonb,
                    source_file VARCHAR(500) DEFAULT '',
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)

            # HNSW index for fast approximate nearest neighbor search
            await conn.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_chunks_embedding
                ON ai_knowledge_chunks
                USING hnsw (embedding vector_cosine_ops)
                WITH (m = 16, ef_construction = 64)
            """)

            # GIN index for BM25-style keyword search via tsvector
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_chunks_fts
                ON ai_knowledge_chunks
                USING gin (to_tsvector('english', content))
            """)

            # B-tree index for collection filtering
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_chunks_collection
                ON ai_knowledge_chunks (collection)
            """)

            # GIN index on JSONB metadata for filtered queries
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_chunks_metadata
                ON ai_knowledge_chunks
                USING gin (metadata jsonb_path_ops)
            """)

            logger.info("VectorStore: schema and indexes verified")

    async def upsert_chunks(self, chunks: list[dict[str, Any]]) -> int:
        """Batch insert knowledge chunks.

        Each chunk dict should contain:
            collection (str), content (str), embedding (list[float]),
            and optionally context_prefix (str), metadata (dict), source_file (str).

        Returns the number of rows inserted.
        """
        if not chunks:
            return 0

        rows = []
        for c in chunks:
            embedding_str = "[" + ",".join(str(v) for v in c["embedding"]) + "]"
            metadata_str = json.dumps(c.get("metadata", {}))
            rows.append((
                c["collection"],
                c["content"],
                c.get("context_prefix", ""),
                embedding_str,
                metadata_str,
                c.get("source_file", ""),
            ))

        async with self._pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO ai_knowledge_chunks
                    (collection, content, context_prefix, embedding, metadata, source_file)
                VALUES
                    ($1, $2, $3, $4::vector, $5::jsonb, $6)
                """,
                rows,
            )

        return len(rows)

    async def semantic_search(
        self,
        query_embedding: list[float],
        collection: str | None = None,
        top_k: int = 20,
    ) -> list[dict[str, Any]]:
        """Pure vector similarity search using cosine distance.

        Returns up to ``top_k`` results sorted by descending cosine similarity.
        """
        embedding_str = "[" + ",".join(str(v) for v in query_embedding) + "]"

        if collection:
            query = """
                SELECT id, collection, content, context_prefix, metadata,
                       source_file, 1 - (embedding <=> $1::vector) AS similarity
                FROM ai_knowledge_chunks
                WHERE collection = $2
                ORDER BY embedding <=> $1::vector
                LIMIT $3
            """
            params = [embedding_str, collection, top_k]
        else:
            query = """
                SELECT id, collection, content, context_prefix, metadata,
                       source_file, 1 - (embedding <=> $1::vector) AS similarity
                FROM ai_knowledge_chunks
                ORDER BY embedding <=> $1::vector
                LIMIT $2
            """
            params = [embedding_str, top_k]

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, *params)

        return [self._row_to_dict(row) for row in rows]

    async def keyword_search(
        self,
        query_text: str,
        collection: str | None = None,
        top_k: int = 20,
    ) -> list[dict[str, Any]]:
        """BM25-style keyword search using PostgreSQL full-text search.

        Uses plainto_tsquery for robust query parsing (handles arbitrary user input).
        Results are ranked by ts_rank_cd (cover density ranking).
        """
        if collection:
            query = """
                SELECT id, collection, content, context_prefix, metadata,
                       source_file,
                       ts_rank_cd(
                           to_tsvector('english', content),
                           plainto_tsquery('english', $1)
                       ) AS rank
                FROM ai_knowledge_chunks
                WHERE collection = $2
                  AND to_tsvector('english', content) @@ plainto_tsquery('english', $1)
                ORDER BY rank DESC
                LIMIT $3
            """
            params = [query_text, collection, top_k]
        else:
            query = """
                SELECT id, collection, content, context_prefix, metadata,
                       source_file,
                       ts_rank_cd(
                           to_tsvector('english', content),
                           plainto_tsquery('english', $1)
                       ) AS rank
                FROM ai_knowledge_chunks
                WHERE to_tsvector('english', content) @@ plainto_tsquery('english', $1)
                ORDER BY rank DESC
                LIMIT $2
            """
            params = [query_text, top_k]

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, *params)

        return [self._row_to_dict(row) for row in rows]

    async def hybrid_search(
        self,
        query_embedding: list[float],
        query_text: str,
        collection: str | None = None,
        top_k: int = 10,
        semantic_weight: float = 0.6,
        keyword_weight: float = 0.4,
    ) -> list[dict[str, Any]]:
        """Hybrid search: semantic (pgvector) + BM25 (tsvector), fused via RRF.

        Runs both searches in parallel, then merges results using Reciprocal
        Rank Fusion. This is the primary search method.

        Args:
            query_embedding: Pre-computed query embedding vector.
            query_text: Raw query text for keyword search.
            collection: Optional collection filter.
            top_k: Number of final results to return.
            semantic_weight: RRF weight for semantic results.
            keyword_weight: RRF weight for keyword results.

        Returns:
            Fused results sorted by RRF score, with up to ``top_k`` entries.
        """
        # Fetch more candidates than needed for better fusion quality
        candidate_k = min(top_k * 3, 100)

        # Run both searches
        semantic_results = await self.semantic_search(
            query_embedding, collection=collection, top_k=candidate_k
        )
        keyword_results = await self.keyword_search(
            query_text, collection=collection, top_k=candidate_k
        )

        # Fuse with RRF
        fused = reciprocal_rank_fusion(
            result_lists=[semantic_results, keyword_results],
            weights=[semantic_weight, keyword_weight],
        )

        return fused[:top_k]

    async def get_collection_stats(self) -> dict[str, int]:
        """Return the row count per collection."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT collection, COUNT(*) AS cnt
                FROM ai_knowledge_chunks
                GROUP BY collection
                ORDER BY collection
            """)
        return {row["collection"]: row["cnt"] for row in rows}

    async def get_total_count(self) -> int:
        """Return total number of chunks across all collections."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT COUNT(*) AS cnt FROM ai_knowledge_chunks"
            )
        return row["cnt"] if row else 0

    async def clear_collection(self, collection: str) -> int:
        """Remove all chunks in a collection. Returns number of rows deleted."""
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM ai_knowledge_chunks WHERE collection = $1",
                collection,
            )
        # result is like "DELETE 42"
        count = int(result.split()[-1]) if result else 0
        logger.info("VectorStore: cleared %d chunks from collection '%s'", count, collection)
        return count

    async def clear_all(self) -> int:
        """Remove all chunks from all collections. Returns number of rows deleted."""
        async with self._pool.acquire() as conn:
            result = await conn.execute("DELETE FROM ai_knowledge_chunks")
        count = int(result.split()[-1]) if result else 0
        logger.info("VectorStore: cleared all %d chunks", count)
        return count

    async def close(self) -> None:
        """Close the connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None
            logger.info("VectorStore: connection pool closed")

    @staticmethod
    def _row_to_dict(row: asyncpg.Record) -> dict[str, Any]:
        """Convert an asyncpg Record to a plain dict for RRF and API consumption."""
        metadata = row["metadata"]
        if isinstance(metadata, str):
            metadata = json.loads(metadata)

        return {
            "id": row["id"],
            "collection": row["collection"],
            "content": row["content"],
            "context_prefix": row.get("context_prefix", ""),
            "metadata": metadata,
            "source_file": row.get("source_file", ""),
            "score": float(row.get("similarity", 0.0) or row.get("rank", 0.0)),
        }
