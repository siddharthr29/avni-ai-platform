"""Contextual Retrieval -- Anthropic's approach to reducing retrieval failures.

For each knowledge chunk, a short contextual prefix is generated using Claude
that explains what the chunk IS, where it comes FROM, and when it is RELEVANT.
This prefix is prepended to the content before embedding, so the vector
captures semantic meaning in context rather than in isolation.

Reference: https://www.anthropic.com/news/contextual-retrieval
Result: 67% fewer retrieval failures vs. naive chunking.

When ``use_context=False`` (fast mode), chunks are embedded without the
Claude-generated prefix. This is useful for development/testing where you
want fast ingestion without API costs.
"""

import logging
from typing import Any

from app.services.rag.embeddings import EmbeddingClient
from app.services.rag.vector_store import VectorStore

logger = logging.getLogger(__name__)

# Collection-specific context generation prompts
_CONTEXT_PROMPTS: dict[str, str] = {
    "concepts": (
        "You are generating a short contextual description for a knowledge chunk "
        "that will be used in a semantic search index for the Avni field data "
        "collection platform.\n\n"
        "This chunk describes a concept (field definition) used in Avni forms.\n\n"
        "Chunk content:\n{content}\n\n"
        "Write a 2-3 sentence description that explains:\n"
        "1. What this concept captures (its purpose in data collection)\n"
        "2. What data type it is and any constraints\n"
        "3. When a user might search for this (e.g., what kind of form or program "
        "would need this field)\n\n"
        "Be specific and use domain terminology. Output ONLY the description, "
        "no preamble."
    ),
    "forms": (
        "You are generating a short contextual description for a knowledge chunk "
        "about an Avni form pattern.\n\n"
        "Chunk content:\n{content}\n\n"
        "Write a 2-3 sentence description that explains:\n"
        "1. What type of form this is and what program it belongs to\n"
        "2. Its structure (number of groups, elements, what rules it uses)\n"
        "3. When this form pattern is relevant (e.g., designing similar forms "
        "for health, education, or nutrition programs)\n\n"
        "Output ONLY the description."
    ),
    "rules": (
        "You are generating a short contextual description for a knowledge chunk "
        "about an Avni JavaScript rule template.\n\n"
        "Chunk content:\n{content}\n\n"
        "Write a 2-3 sentence description that explains:\n"
        "1. What type of rule this is (skip logic, visit scheduling, decision, "
        "validation, etc.)\n"
        "2. What it does functionally\n"
        "3. When a user would need this pattern (e.g., implementing similar "
        "logic for their own program)\n\n"
        "Output ONLY the description."
    ),
    "transcripts": (
        "You are generating a short contextual description for a chunk from "
        "an Avni training video transcript.\n\n"
        "Chunk content:\n{content}\n\n"
        "Write a 2-3 sentence description that explains:\n"
        "1. What Avni topic this covers\n"
        "2. The key concepts or steps explained\n"
        "3. When this is relevant (e.g., what user question would this help answer)\n\n"
        "Output ONLY the description."
    ),
    "support": (
        "You are generating a short contextual description for a troubleshooting "
        "knowledge chunk from the Avni platform.\n\n"
        "Chunk content:\n{content}\n\n"
        "Write a 2-3 sentence description that explains:\n"
        "1. What issue or category this describes\n"
        "2. The symptoms or error conditions\n"
        "3. When a user would need this (e.g., what problem they are experiencing)\n\n"
        "Output ONLY the description."
    ),
    "srs_examples": (
        "You are generating a short contextual description for a chunk from "
        "an Avni SRS (Scoping & Requirement Specification) example.\n\n"
        "Chunk content:\n{content}\n\n"
        "Write a 2-3 sentence description that explains:\n"
        "1. What part of the SRS this covers\n"
        "2. The implementation patterns or data model elements involved\n"
        "3. When this is relevant for an implementer\n\n"
        "Output ONLY the description."
    ),
}

# Fallback prompt for unknown collections
_DEFAULT_CONTEXT_PROMPT = (
    "You are generating a short contextual description for a knowledge chunk "
    "in the Avni field data collection platform's search index.\n\n"
    "Chunk content:\n{content}\n\n"
    "Write a 2-3 sentence description that explains what this chunk is about, "
    "where it comes from, and when it would be relevant to a user's search.\n\n"
    "Output ONLY the description."
)


class ContextualRetrieval:
    """Implements Anthropic's Contextual Retrieval approach.

    For each chunk:
    1. (Optional) Generate a contextual prefix using Claude Haiku
    2. Embed the concatenation of prefix + content
    3. Store in pgvector with metadata

    Search:
    1. Embed the query
    2. Run hybrid search (semantic + keyword)
    3. Return fused results
    """

    def __init__(
        self,
        claude_client: Any,
        embedding_client: EmbeddingClient,
        vector_store: VectorStore,
    ) -> None:
        self.claude = claude_client
        self.embedder = embedding_client
        self.store = vector_store

    async def ingest_collection(
        self,
        collection: str,
        items: list[dict[str, Any]],
        content_key: str = "content",
        source_file: str = "",
        batch_size: int = 50,
        use_context: bool = True,
    ) -> int:
        """Ingest a collection of items with contextual embeddings.

        Args:
            collection: Collection name (concepts, forms, rules, etc.).
            items: List of dicts, each with at least a ``content_key`` field.
            content_key: Key in each item dict that holds the text content.
            source_file: Source file name for provenance tracking.
            batch_size: Number of items to process per batch.
            use_context: If True, generate contextual prefixes via Claude.
                         If False, embed raw content (faster, no API calls).

        Returns:
            Total number of chunks ingested.
        """
        total_ingested = 0

        # Clear existing data for this collection before re-ingestion
        await self.store.clear_collection(collection)

        # Process in batches
        for batch_start in range(0, len(items), batch_size):
            batch = items[batch_start : batch_start + batch_size]
            batch_num = (batch_start // batch_size) + 1
            total_batches = (len(items) + batch_size - 1) // batch_size

            logger.info(
                "Ingesting %s: batch %d/%d (%d items)",
                collection, batch_num, total_batches, len(batch),
            )

            # Step 1: Generate contextual prefixes (if enabled)
            prefixes: list[str] = []
            if use_context:
                for item in batch:
                    content = item.get(content_key, "")
                    try:
                        prefix = await self._generate_context(content, collection)
                        prefixes.append(prefix)
                    except Exception as e:
                        logger.warning(
                            "Context generation failed for item in %s: %s",
                            collection, e,
                        )
                        prefixes.append("")
            else:
                prefixes = [""] * len(batch)

            # Step 2: Build texts for embedding (prefix + content)
            texts_to_embed: list[str] = []
            for item, prefix in zip(batch, prefixes):
                content = item.get(content_key, "")
                if prefix:
                    combined = f"{prefix}\n\n{content}"
                else:
                    combined = content
                texts_to_embed.append(combined)

            # Step 3: Batch embed
            embeddings = self.embedder.embed_batch(texts_to_embed)

            # Step 4: Build chunks for storage
            chunks: list[dict[str, Any]] = []
            for item, prefix, embedding in zip(batch, prefixes, embeddings):
                content = item.get(content_key, "")
                metadata = {
                    k: v for k, v in item.items()
                    if k != content_key and k != "embedding"
                }
                chunks.append({
                    "collection": collection,
                    "content": content,
                    "context_prefix": prefix,
                    "embedding": embedding,
                    "metadata": metadata,
                    "source_file": item.get("source_file", source_file),
                })

            # Step 5: Store in pgvector
            inserted = await self.store.upsert_chunks(chunks)
            total_ingested += inserted

        logger.info(
            "Ingestion complete for '%s': %d chunks stored", collection, total_ingested
        )
        return total_ingested

    async def _generate_context(self, content: str, collection: str) -> str:
        """Use Claude to generate a contextual prefix for a chunk.

        Uses Claude Haiku for speed and cost efficiency. The prompt is
        collection-specific to produce the most relevant context.
        """
        prompt_template = _CONTEXT_PROMPTS.get(collection, _DEFAULT_CONTEXT_PROMPT)
        prompt = prompt_template.format(content=content[:2000])

        try:
            response = await self.claude.complete(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=(
                    "You are a concise technical writer generating search index "
                    "descriptions for the Avni field data collection platform. "
                    "Keep descriptions to 2-3 sentences. Be specific and use "
                    "domain terminology."
                ),
            )
            return response.strip()
        except Exception as e:
            logger.warning("Claude context generation failed: %s", e)
            return ""

    async def search(
        self,
        query: str,
        collection: str | None = None,
        top_k: int = 10,
        semantic_weight: float = 0.6,
    ) -> list[dict[str, Any]]:
        """Search with hybrid retrieval (semantic + keyword via RRF).

        Args:
            query: Natural language search query.
            collection: Optional collection filter.
            top_k: Number of results to return.
            semantic_weight: Weight for semantic search in RRF (keyword = 1 - semantic).

        Returns:
            List of result dicts with content, metadata, score, etc.
        """
        query_embedding = self.embedder.embed(query)
        keyword_weight = 1.0 - semantic_weight

        results = await self.store.hybrid_search(
            query_embedding=query_embedding,
            query_text=query,
            collection=collection,
            top_k=top_k,
            semantic_weight=semantic_weight,
            keyword_weight=keyword_weight,
        )

        return results
