"""PageIndex service — vectorless, reasoning-based document RAG.

Provides:
1. PDF/Markdown indexing into hierarchical JSON tree structures
2. Tree-based reasoning retrieval (LLM navigates the tree to find relevant sections)
3. Storage and management of document indexes in PostgreSQL
4. Integration with the existing RAG pipeline as a complementary search layer

PageIndex creates intelligent "tables of contents" that LLMs can reason over,
instead of relying solely on vector similarity. This gives:
- Better context preservation (whole sections, not fragments)
- Traceable retrieval (exact page/section references)
- No chunking artifacts
- Human-like document navigation
"""

import asyncio
import json
import logging
import os
import uuid
from io import BytesIO
from typing import Any

import asyncpg

from app.config import settings

logger = logging.getLogger(__name__)


class PageIndexService:
    """Manages document indexing and tree-based retrieval via PageIndex."""

    def __init__(self) -> None:
        self._pool: asyncpg.Pool | None = None
        self._initialized = False

    async def initialize(self, pool: asyncpg.Pool | None = None) -> None:
        """Initialize the service: create DB table, patch LLM adapter."""
        if self._initialized:
            return

        # Patch PageIndex to use our LLM provider
        from app.services.pageindex.llm_adapter import patch_pageindex_llm
        patch_pageindex_llm()

        # Use provided pool or create new one
        if pool:
            self._pool = pool
        elif settings.DATABASE_URL:
            try:
                self._pool = await asyncpg.create_pool(
                    settings.DATABASE_URL, min_size=1, max_size=5
                )
            except Exception as e:
                logger.warning("PageIndex: Could not connect to DB: %s", e)

        if self._pool:
            await self._create_schema()

        self._initialized = True
        logger.info("PageIndexService initialized")

    async def _create_schema(self) -> None:
        """Create the document_indexes table for storing tree structures."""
        async with self._pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS document_indexes (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    name VARCHAR(500) NOT NULL,
                    doc_type VARCHAR(50) NOT NULL DEFAULT 'pdf',
                    description TEXT DEFAULT '',
                    tree_structure JSONB NOT NULL,
                    page_count INT DEFAULT 0,
                    node_count INT DEFAULT 0,
                    source_path VARCHAR(1000) DEFAULT '',
                    collection VARCHAR(100) DEFAULT 'documents',
                    metadata JSONB DEFAULT '{}'::jsonb,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_docidx_collection
                ON document_indexes (collection)
            """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_docidx_name
                ON document_indexes USING gin (to_tsvector('english', name))
            """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_docidx_metadata
                ON document_indexes USING gin (metadata jsonb_path_ops)
            """)

        logger.info("PageIndex: document_indexes table ready")

    # ------------------------------------------------------------------
    # Index Generation
    # ------------------------------------------------------------------

    async def index_pdf(
        self,
        pdf_path: str | BytesIO,
        name: str | None = None,
        collection: str = "documents",
        metadata: dict | None = None,
        toc_check_pages: int = 20,
        max_pages_per_node: int = 10,
        max_tokens_per_node: int = 20000,
        add_summaries: bool = True,
        add_text: bool = True,
    ) -> dict[str, Any]:
        """Index a PDF document into a hierarchical tree structure.

        Args:
            pdf_path: Path to PDF file or BytesIO stream.
            name: Document name (defaults to filename).
            collection: Collection for grouping documents.
            metadata: Additional metadata to store.
            toc_check_pages: Pages to scan for table of contents.
            max_pages_per_node: Max pages grouped per tree node.
            max_tokens_per_node: Max tokens per tree node.
            add_summaries: Generate LLM summaries for each node.
            add_text: Include full text in tree nodes.

        Returns:
            Document index dict with id, name, tree_structure, stats.
        """
        from app.services.pageindex.page_index import page_index_main
        from app.services.pageindex.utils import config, get_number_of_pages, get_pdf_name

        if name is None:
            name = get_pdf_name(pdf_path) if isinstance(pdf_path, str) else "Uploaded Document"

        logger.info("PageIndex: Indexing PDF '%s'...", name)

        opt = config(
            model="gpt-4o-2024-11-20",  # PageIndex ignores this — we patched the LLM calls
            toc_check_page_num=toc_check_pages,
            max_page_num_each_node=max_pages_per_node,
            max_token_num_each_node=max_tokens_per_node,
            if_add_node_id="yes",
            if_add_node_summary="yes" if add_summaries else "no",
            if_add_doc_description="no",
            if_add_node_text="yes" if add_text else "no",
        )

        tree_structure = page_index_main(pdf_path, opt)

        page_count = get_number_of_pages(pdf_path) if isinstance(pdf_path, str) else 0
        node_count = self._count_nodes(tree_structure)

        doc_id = str(uuid.uuid4())
        doc_index = {
            "id": doc_id,
            "name": name,
            "doc_type": "pdf",
            "description": "",
            "tree_structure": tree_structure,
            "page_count": page_count,
            "node_count": node_count,
            "source_path": pdf_path if isinstance(pdf_path, str) else "",
            "collection": collection,
            "metadata": metadata or {},
        }

        # Persist to DB
        if self._pool:
            await self._save_index(doc_index)

        logger.info(
            "PageIndex: Indexed '%s' — %d pages, %d nodes",
            name, page_count, node_count,
        )
        return doc_index

    async def index_markdown(
        self,
        md_path: str,
        name: str | None = None,
        collection: str = "documents",
        metadata: dict | None = None,
        add_summaries: bool = False,
        add_text: bool = True,
        thinning: bool = False,
        thinning_threshold: int = 5000,
    ) -> dict[str, Any]:
        """Index a Markdown document into a hierarchical tree structure.

        Args:
            md_path: Path to the markdown file.
            name: Document name (defaults to filename).
            collection: Collection for grouping documents.
            metadata: Additional metadata to store.
            add_summaries: Generate LLM summaries for each node.
            add_text: Include full text in tree nodes.
            thinning: Merge small nodes for cleaner tree.
            thinning_threshold: Min tokens for thinning.

        Returns:
            Document index dict with id, name, tree_structure, stats.
        """
        from app.services.pageindex.page_index_md import md_to_tree

        if name is None:
            name = os.path.splitext(os.path.basename(md_path))[0]

        logger.info("PageIndex: Indexing Markdown '%s'...", name)

        tree_result = await md_to_tree(
            md_path=md_path,
            if_thinning=thinning,
            min_token_threshold=thinning_threshold,
            if_add_node_summary="yes" if add_summaries else "no",
            summary_token_threshold=200,
            model="gpt-4o-2024-11-20",  # Ignored — patched
            if_add_doc_description="no",
            if_add_node_text="yes" if add_text else "no",
            if_add_node_id="yes",
        )

        tree_structure = tree_result.get("structure", tree_result)
        node_count = self._count_nodes(tree_structure)

        doc_id = str(uuid.uuid4())
        doc_index = {
            "id": doc_id,
            "name": name,
            "doc_type": "markdown",
            "description": tree_result.get("doc_description", ""),
            "tree_structure": tree_structure if isinstance(tree_structure, list) else [tree_structure],
            "page_count": 0,
            "node_count": node_count,
            "source_path": md_path,
            "collection": collection,
            "metadata": metadata or {},
        }

        if self._pool:
            await self._save_index(doc_index)

        logger.info("PageIndex: Indexed '%s' — %d nodes", name, node_count)
        return doc_index

    # ------------------------------------------------------------------
    # Tree-Based Retrieval (Reasoning Search)
    # ------------------------------------------------------------------

    async def retrieve(
        self,
        query: str,
        doc_id: str | None = None,
        collection: str | None = None,
        max_sections: int = 5,
    ) -> list[dict[str, Any]]:
        """Retrieve relevant sections by LLM reasoning over document trees.

        The LLM examines the tree structure (like reading a table of contents)
        and reasons about which sections contain relevant information.

        Args:
            query: User question or search query.
            doc_id: Specific document to search, or None for all.
            collection: Collection filter, or None for all.
            max_sections: Max sections to return.

        Returns:
            List of relevant sections with text, source, and reasoning.
        """
        documents = await self._load_indexes(doc_id=doc_id, collection=collection)
        if not documents:
            return []

        all_sections = []
        for doc in documents:
            sections = await self._reason_over_tree(
                query=query,
                doc_name=doc["name"],
                tree=doc["tree_structure"],
                max_sections=max_sections,
            )
            all_sections.extend(sections)

        # Sort by relevance score and return top results
        all_sections.sort(key=lambda s: s.get("relevance", 0), reverse=True)
        return all_sections[:max_sections]

    async def _reason_over_tree(
        self,
        query: str,
        doc_name: str,
        tree: list | dict,
        max_sections: int = 5,
    ) -> list[dict[str, Any]]:
        """Use LLM to reason over a document tree and find relevant sections."""
        from app.services.pageindex.llm_adapter import _get_async_openai_client, _get_model

        # Build a compact TOC view for the LLM to reason over
        toc_view = self._build_toc_view(tree)

        prompt = f"""You are an expert document analyst. You have a document's table of contents below.
Find the sections most relevant to the user's query.

DOCUMENT: {doc_name}

TABLE OF CONTENTS:
{toc_view}

USER QUERY: {query}

Return a JSON array of the most relevant sections (up to {max_sections}). For each section, provide:
- "node_id": the section's node_id from the TOC
- "title": the section title
- "relevance": a score from 0.0 to 1.0
- "reasoning": brief explanation of why this section is relevant

Return ONLY the JSON array, no other text.
Example: [{{"node_id": "0001", "title": "Introduction", "relevance": 0.9, "reasoning": "Contains overview of the topic"}}]"""

        client = _get_async_openai_client()
        model = _get_model()

        try:
            response = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
            )
            content = response.choices[0].message.content

            # Parse the JSON response
            from app.services.pageindex.utils import extract_json
            sections = extract_json(content)
            if isinstance(sections, dict):
                sections = [sections]
            if not isinstance(sections, list):
                sections = []

            # Enrich with actual text from the tree
            for section in sections:
                node_id = section.get("node_id")
                if node_id:
                    node_data = self._find_node_by_id(tree, node_id)
                    if node_data:
                        section["text"] = node_data.get("text", "")
                        section["start_index"] = node_data.get("start_index")
                        section["end_index"] = node_data.get("end_index")
                        section["summary"] = node_data.get("summary", "")
                section["document"] = doc_name

            return sections

        except Exception as e:
            logger.error("PageIndex tree retrieval failed: %s", e)
            return []

    # ------------------------------------------------------------------
    # Search Documents (metadata/keyword search across indexes)
    # ------------------------------------------------------------------

    async def search_documents(
        self,
        query: str,
        collection: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Search document index metadata (names, descriptions)."""
        if not self._pool:
            return []

        if collection:
            sql = """
                SELECT id, name, doc_type, description, page_count, node_count,
                       collection, metadata, created_at,
                       ts_rank(to_tsvector('english', name || ' ' || COALESCE(description, '')),
                               plainto_tsquery('english', $1)) AS rank
                FROM document_indexes
                WHERE collection = $2
                  AND to_tsvector('english', name || ' ' || COALESCE(description, ''))
                      @@ plainto_tsquery('english', $1)
                ORDER BY rank DESC
                LIMIT $3
            """
            params = [query, collection, limit]
        else:
            sql = """
                SELECT id, name, doc_type, description, page_count, node_count,
                       collection, metadata, created_at,
                       ts_rank(to_tsvector('english', name || ' ' || COALESCE(description, '')),
                               plainto_tsquery('english', $1)) AS rank
                FROM document_indexes
                WHERE to_tsvector('english', name || ' ' || COALESCE(description, ''))
                      @@ plainto_tsquery('english', $1)
                ORDER BY rank DESC
                LIMIT $2
            """
            params = [query, limit]

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)

        return [
            {
                "id": str(r["id"]),
                "name": r["name"],
                "doc_type": r["doc_type"],
                "description": r["description"],
                "page_count": r["page_count"],
                "node_count": r["node_count"],
                "collection": r["collection"],
                "metadata": r["metadata"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in rows
        ]

    # ------------------------------------------------------------------
    # CRUD Operations
    # ------------------------------------------------------------------

    async def list_documents(
        self,
        collection: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List all indexed documents."""
        if not self._pool:
            return []

        if collection:
            sql = """
                SELECT id, name, doc_type, description, page_count, node_count,
                       collection, metadata, created_at
                FROM document_indexes
                WHERE collection = $1
                ORDER BY created_at DESC
                LIMIT $2
            """
            params = [collection, limit]
        else:
            sql = """
                SELECT id, name, doc_type, description, page_count, node_count,
                       collection, metadata, created_at
                FROM document_indexes
                ORDER BY created_at DESC
                LIMIT $1
            """
            params = [limit]

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)

        return [
            {
                "id": str(r["id"]),
                "name": r["name"],
                "doc_type": r["doc_type"],
                "description": r["description"],
                "page_count": r["page_count"],
                "node_count": r["node_count"],
                "collection": r["collection"],
                "metadata": r["metadata"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in rows
        ]

    async def get_document(self, doc_id: str) -> dict[str, Any] | None:
        """Get a document index by ID, including the full tree structure."""
        if not self._pool:
            return None

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM document_indexes WHERE id = $1",
                uuid.UUID(doc_id),
            )

        if not row:
            return None

        return {
            "id": str(row["id"]),
            "name": row["name"],
            "doc_type": row["doc_type"],
            "description": row["description"],
            "tree_structure": row["tree_structure"],
            "page_count": row["page_count"],
            "node_count": row["node_count"],
            "source_path": row["source_path"],
            "collection": row["collection"],
            "metadata": row["metadata"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        }

    async def delete_document(self, doc_id: str) -> bool:
        """Delete a document index."""
        if not self._pool:
            return False

        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM document_indexes WHERE id = $1",
                uuid.UUID(doc_id),
            )

        deleted = int(result.split()[-1]) if result else 0
        return deleted > 0

    async def get_stats(self) -> dict[str, Any]:
        """Return statistics about indexed documents."""
        if not self._pool:
            return {"total_documents": 0, "collections": {}}

        async with self._pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT collection,
                       COUNT(*) AS doc_count,
                       SUM(page_count) AS total_pages,
                       SUM(node_count) AS total_nodes
                FROM document_indexes
                GROUP BY collection
                ORDER BY collection
            """)

        collections = {}
        total_docs = 0
        for r in rows:
            collections[r["collection"]] = {
                "documents": r["doc_count"],
                "pages": r["total_pages"] or 0,
                "nodes": r["total_nodes"] or 0,
            }
            total_docs += r["doc_count"]

        return {
            "total_documents": total_docs,
            "collections": collections,
        }

    async def close(self) -> None:
        """Close the DB connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None

    # ------------------------------------------------------------------
    # Internal Helpers
    # ------------------------------------------------------------------

    async def _save_index(self, doc_index: dict[str, Any]) -> None:
        """Persist a document index to the database."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO document_indexes
                    (id, name, doc_type, description, tree_structure,
                     page_count, node_count, source_path, collection, metadata)
                VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7, $8, $9, $10::jsonb)
                ON CONFLICT (id) DO UPDATE SET
                    tree_structure = EXCLUDED.tree_structure,
                    page_count = EXCLUDED.page_count,
                    node_count = EXCLUDED.node_count,
                    updated_at = NOW()
                """,
                uuid.UUID(doc_index["id"]),
                doc_index["name"],
                doc_index["doc_type"],
                doc_index["description"],
                json.dumps(doc_index["tree_structure"]),
                doc_index["page_count"],
                doc_index["node_count"],
                doc_index["source_path"],
                doc_index["collection"],
                json.dumps(doc_index["metadata"]),
            )

    async def _load_indexes(
        self,
        doc_id: str | None = None,
        collection: str | None = None,
    ) -> list[dict[str, Any]]:
        """Load document indexes from DB."""
        if not self._pool:
            return []

        if doc_id:
            rows = await self._pool.fetch(
                "SELECT id, name, tree_structure FROM document_indexes WHERE id = $1",
                uuid.UUID(doc_id),
            )
        elif collection:
            rows = await self._pool.fetch(
                "SELECT id, name, tree_structure FROM document_indexes WHERE collection = $1",
                collection,
            )
        else:
            rows = await self._pool.fetch(
                "SELECT id, name, tree_structure FROM document_indexes"
            )

        return [
            {
                "id": str(r["id"]),
                "name": r["name"],
                "tree_structure": r["tree_structure"],
            }
            for r in rows
        ]

    def _count_nodes(self, tree: Any) -> int:
        """Recursively count nodes in a tree structure."""
        if isinstance(tree, dict):
            count = 1
            for child in tree.get("nodes", []):
                count += self._count_nodes(child)
            return count
        elif isinstance(tree, list):
            return sum(self._count_nodes(item) for item in tree)
        return 0

    def _build_toc_view(self, tree: Any, indent: int = 0) -> str:
        """Build a compact text TOC view for LLM reasoning."""
        lines = []
        if isinstance(tree, list):
            for node in tree:
                lines.append(self._build_toc_view(node, indent))
        elif isinstance(tree, dict):
            node_id = tree.get("node_id", "?")
            title = tree.get("title", "Untitled")
            summary = tree.get("summary", tree.get("prefix_summary", ""))
            start = tree.get("start_index", "")
            end = tree.get("end_index", "")
            page_info = f" (pages {start}-{end})" if start and end else ""
            line_info = f" (line {tree.get('line_num', '')})" if tree.get("line_num") else ""

            prefix = "  " * indent
            line = f"{prefix}[{node_id}] {title}{page_info}{line_info}"
            if summary:
                line += f" — {summary[:150]}"
            lines.append(line)

            for child in tree.get("nodes", []):
                lines.append(self._build_toc_view(child, indent + 1))

        return "\n".join(lines)

    def _find_node_by_id(self, tree: Any, node_id: str) -> dict | None:
        """Find a node in the tree by its node_id."""
        if isinstance(tree, dict):
            if tree.get("node_id") == node_id:
                return tree
            for child in tree.get("nodes", []):
                result = self._find_node_by_id(child, node_id)
                if result:
                    return result
        elif isinstance(tree, list):
            for item in tree:
                result = self._find_node_by_id(item, node_id)
                if result:
                    return result
        return None


# Module-level singleton
pageindex_service = PageIndexService()
