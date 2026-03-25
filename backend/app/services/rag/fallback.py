"""Unified RAG service with graceful degradation.

If PostgreSQL with pgvector is configured and reachable, uses hybrid
vector + keyword search via the ContextualRetrieval engine. Otherwise,
falls back to the existing in-memory keyword search in knowledge_base.py.

This ensures the platform always works -- pgvector is an enhancement,
not a hard dependency.
"""

import logging
from typing import Any

from app.config import settings
from app.models.schemas import KnowledgeResult

logger = logging.getLogger(__name__)


class RAGService:
    """Unified search interface with graceful fallback.

    Usage:
        rag_service = RAGService()
        await rag_service.initialize()  # call once at startup
        results = await rag_service.search("malnutrition screening")
        await rag_service.close()       # call at shutdown
    """

    def __init__(self) -> None:
        self._rag_available = False
        self._contextual_retrieval = None
        self._vector_store = None
        self._fallback_kb = None

    @property
    def is_rag_available(self) -> bool:
        """Whether the pgvector RAG pipeline is active."""
        return self._rag_available

    async def initialize(self) -> None:
        """Try to connect to pgvector. If it fails, use the in-memory fallback.

        This method never raises -- it logs warnings and falls back gracefully.
        """
        # Always load the in-memory fallback
        from app.services.knowledge_base import knowledge_base
        self._fallback_kb = knowledge_base

        database_url = settings.DATABASE_URL
        if not database_url:
            logger.info(
                "RAG: No DATABASE_URL configured, using in-memory fallback"
            )
            return

        try:
            from app.services.rag.embeddings import EmbeddingClient
            from app.services.rag.vector_store import VectorStore
            from app.services.rag.contextual_retrieval import ContextualRetrieval
            from app.services.claude_client import claude_client

            # Initialize embedding client (lazy -- model loads on first embed call)
            embedding_client = EmbeddingClient(
                model_name=settings.EMBEDDING_MODEL
            )

            # Initialize vector store (connects to PostgreSQL)
            vector_store = VectorStore(
                dsn=database_url,
                embedding_dimension=embedding_client.dimension,
            )
            await vector_store.initialize()

            # Initialize contextual retrieval
            contextual_retrieval = ContextualRetrieval(
                claude_client=claude_client,
                embedding_client=embedding_client,
                vector_store=vector_store,
            )

            self._vector_store = vector_store
            self._contextual_retrieval = contextual_retrieval
            self._rag_available = True

            # Log stats if data exists
            stats = await vector_store.get_collection_stats()
            total = sum(stats.values())
            if total > 0:
                logger.info(
                    "RAG: pgvector connected, %d chunks across %d collections",
                    total, len(stats),
                )
                for coll, count in stats.items():
                    logger.info("  %s: %d chunks", coll, count)
            else:
                logger.info(
                    "RAG: pgvector connected but empty. "
                    "Run 'python scripts/ingest_knowledge.py' to populate."
                )

        except ImportError as e:
            logger.warning(
                "RAG: Required package not installed (%s), using in-memory fallback. "
                "Install with: pip install asyncpg sentence-transformers",
                e,
            )
        except Exception as e:
            logger.warning(
                "RAG: pgvector unavailable (%s), using in-memory fallback",
                e,
            )

    async def close(self) -> None:
        """Close the vector store connection pool."""
        if self._vector_store:
            await self._vector_store.close()
            self._vector_store = None
            self._contextual_retrieval = None
            self._rag_available = False

    # ------------------------------------------------------------------
    # Search methods
    # ------------------------------------------------------------------

    async def _safe_rag_search(
        self,
        query: str,
        collection: str | None,
        top_k: int,
    ) -> list[KnowledgeResult] | None:
        """Try RAG search; return None if pgvector is down (triggers fallback).

        This handles the case where pgvector goes down AFTER startup.
        Without this, queries would crash permanently until restart.
        """
        if not self._rag_available:
            return None
        try:
            return await self._rag_search(query, collection, top_k)
        except Exception as e:
            logger.warning(
                "RAG search failed at runtime, switching to fallback: %s", e
            )
            self._rag_available = False
            return None

    async def search(
        self,
        query: str,
        collection: str | None = None,
        top_k: int = 10,
    ) -> list[KnowledgeResult]:
        """Search across all or a specific knowledge collection.

        When RAG is available, uses hybrid vector + keyword search.
        Falls back to in-memory automatically if pgvector goes down at runtime.
        """
        result = await self._safe_rag_search(query, collection, top_k)
        if result is not None:
            return result
        return self._fallback_search(query, collection, top_k)

    async def search_concepts(
        self, query: str, limit: int = 10
    ) -> list[KnowledgeResult]:
        """Search concept-related knowledge."""
        result = await self._safe_rag_search(query, "concepts", limit)
        if result is not None:
            return result
        return self._fallback_kb.search_concepts(query, limit=limit)

    async def search_forms(
        self, query: str, limit: int = 10
    ) -> list[KnowledgeResult]:
        """Search form patterns."""
        result = await self._safe_rag_search(query, "forms", limit)
        if result is not None:
            return result
        return self._fallback_kb.search_forms(query, limit=limit)

    async def search_rules(
        self, query: str, rule_type: str | None = None, limit: int = 10
    ) -> list[KnowledgeResult]:
        """Search rule templates."""
        result = await self._safe_rag_search(query, "rules", limit)
        if result is not None:
            if rule_type:
                rule_type_lower = rule_type.lower()
                result = [
                    r for r in result
                    if rule_type_lower in str(r.metadata.get("ruleType", "")).lower()
                    or rule_type_lower in str(r.metadata.get("type", "")).lower()
                ]
            return result
        return self._fallback_kb.search_rules(query, rule_type=rule_type, limit=limit)

    async def search_tickets(
        self, query: str, limit: int = 10
    ) -> list[KnowledgeResult]:
        """Search support patterns and troubleshooting knowledge."""
        result = await self._safe_rag_search(query, "support", limit)
        if result is not None:
            return result
        return self._fallback_kb.search_tickets(query, limit=limit)

    async def search_knowledge(
        self, query: str, limit: int = 10
    ) -> list[KnowledgeResult]:
        """Search transcript and general Avni knowledge."""
        result_t = await self._safe_rag_search(query, "transcripts", limit)
        result_k = await self._safe_rag_search(query, "knowledge", limit)
        if result_t is not None and result_k is not None:
            combined = result_t + result_k
            combined.sort(key=lambda r: r.score, reverse=True)
            return combined[:limit]
        return self._fallback_kb.search_knowledge(query, limit=limit)

    async def search_all(
        self, query: str, limit: int = 10
    ) -> list[KnowledgeResult]:
        """Search across all knowledge categories."""
        result = await self._safe_rag_search(query, None, limit)
        if result is not None:
            return result
        return self._fallback_kb.search_all(query, limit=limit)

    def get_uuid(self, answer_name: str) -> str | None:
        """Look up a standard UUID from the registry."""
        return self._fallback_kb.get_uuid(answer_name)

    async def get_stats(self) -> dict[str, Any]:
        """Return status and statistics about the RAG pipeline."""
        if self._rag_available:
            stats = await self._vector_store.get_collection_stats()
            total = sum(stats.values())
            return {
                "mode": "pgvector_hybrid",
                "total_chunks": total,
                "collections": stats,
                "semantic_weight": settings.RAG_SEMANTIC_WEIGHT,
                "keyword_weight": settings.RAG_KEYWORD_WEIGHT,
                "embedding_model": settings.EMBEDDING_MODEL,
            }
        return {
            "mode": "in_memory_fallback",
            "total_chunks": 0,
            "collections": {},
            "note": "RAG not available, using in-memory keyword search",
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _rag_search(
        self,
        query: str,
        collection: str | None,
        top_k: int,
    ) -> list[KnowledgeResult]:
        """Perform RAG search and convert results to KnowledgeResult objects."""
        try:
            results = await self._contextual_retrieval.search(
                query=query,
                collection=collection,
                top_k=top_k,
                semantic_weight=settings.RAG_SEMANTIC_WEIGHT,
            )
            return [
                KnowledgeResult(
                    text=r.get("content", ""),
                    category=r.get("collection", "general"),
                    score=min(round(r.get("score", 0.0), 3), 1.0),
                    metadata=r.get("metadata", {}),
                )
                for r in results
            ]
        except Exception as e:
            logger.error("RAG search failed, falling back to in-memory: %s", e)
            return self._fallback_search(query, collection, top_k)

    def _fallback_search(
        self,
        query: str,
        collection: str | None,
        top_k: int,
    ) -> list[KnowledgeResult]:
        """Use the in-memory knowledge base as a fallback."""
        if collection == "concepts":
            return self._fallback_kb.search_concepts(query, limit=top_k)
        elif collection == "forms":
            return self._fallback_kb.search_forms(query, limit=top_k)
        elif collection in ("rules",):
            return self._fallback_kb.search_rules(query, limit=top_k)
        elif collection in ("support", "tickets"):
            return self._fallback_kb.search_tickets(query, limit=top_k)
        elif collection in ("transcripts", "knowledge"):
            return self._fallback_kb.search_knowledge(query, limit=top_k)
        else:
            return self._fallback_kb.search_all(query, limit=top_k)


# Module-level singleton
rag_service = RAGService()
