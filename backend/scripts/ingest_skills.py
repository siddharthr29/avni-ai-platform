#!/usr/bin/env python3
"""Ingest all 27 avni-skills SKILL.md files and key documentation into RAG.

Reads markdown files from the avni-skills directory, chunks them, and
stores them in the 'skills' and 'guides' collections in pgvector.

Usage:
    python scripts/ingest_skills.py \
        --skills-dir /Users/samanvay/Downloads/All/avni-ai/avni-skills \
        --database-url postgresql://samanvay@localhost:5432/avni_ai
"""

import argparse
import asyncio
import logging
import os
import re
import sys
import time
from typing import Any

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.dirname(_SCRIPT_DIR)
sys.path.insert(0, _BACKEND_DIR)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("ingest_skills")

CHUNK_SIZE = 800
CHUNK_OVERLAP = 150


def chunk_markdown(text: str, source: str, skill_name: str) -> list[dict[str, Any]]:
    """Split markdown into overlapping chunks with heading context."""
    chunks: list[dict[str, Any]] = []
    sections = re.split(r"(?=^#{1,4}\s)", text, flags=re.MULTILINE)

    current_heading = ""
    for section in sections:
        section = section.strip()
        if not section:
            continue

        heading_match = re.match(r"^(#{1,4}\s+.+?)$", section, re.MULTILINE)
        if heading_match:
            current_heading = heading_match.group(1).strip("# ").strip()

        if len(section) <= CHUNK_SIZE:
            chunks.append({
                "content": section,
                "heading": current_heading,
                "skill": skill_name,
                "source_file": source,
            })
        else:
            start = 0
            while start < len(section):
                end = start + CHUNK_SIZE
                chunk_text = section[start:end]
                chunks.append({
                    "content": chunk_text,
                    "heading": current_heading,
                    "skill": skill_name,
                    "source_file": source,
                })
                start = end - CHUNK_OVERLAP
                if start >= len(section):
                    break

    return chunks


def collect_skill_files(skills_dir: str) -> list[dict[str, Any]]:
    """Collect all SKILL.md files and key documentation from avni-skills."""
    items: list[dict[str, Any]] = []

    # 1. All SKILL.md files from each skill directory
    for entry in sorted(os.listdir(skills_dir)):
        skill_path = os.path.join(skills_dir, entry)
        if not os.path.isdir(skill_path):
            continue

        skill_md = os.path.join(skill_path, "SKILL.md")
        if os.path.exists(skill_md):
            with open(skill_md, "r", encoding="utf-8") as f:
                text = f.read()
            chunks = chunk_markdown(text, f"{entry}/SKILL.md", entry)
            items.extend(chunks)
            logger.info("  %s/SKILL.md → %d chunks", entry, len(chunks))

        # Also ingest any other .md files in the skill directory (not subdirs)
        for md_file in sorted(os.listdir(skill_path)):
            if md_file.endswith(".md") and md_file != "SKILL.md":
                md_path = os.path.join(skill_path, md_file)
                if os.path.isfile(md_path):
                    with open(md_path, "r", encoding="utf-8") as f:
                        text = f.read()
                    # Only ingest files under 50KB to avoid huge dumps
                    if len(text) > 50_000:
                        text = text[:50_000]
                    chunks = chunk_markdown(text, f"{entry}/{md_file}", entry)
                    items.extend(chunks)
                    logger.info("  %s/%s → %d chunks", entry, md_file, len(chunks))

    # 2. Top-level markdown files
    for md_file in sorted(os.listdir(skills_dir)):
        if md_file.endswith(".md") and os.path.isfile(os.path.join(skills_dir, md_file)):
            with open(os.path.join(skills_dir, md_file), "r", encoding="utf-8") as f:
                text = f.read()
            if len(text) > 50_000:
                text = text[:50_000]
            chunks = chunk_markdown(text, md_file, "top-level")
            items.extend(chunks)
            logger.info("  %s → %d chunks", md_file, len(chunks))

    return items


async def run_ingestion(skills_dir: str, database_url: str, batch_size: int) -> None:
    """Run the skills knowledge ingestion."""
    from app.services.rag.embeddings import EmbeddingClient
    from app.services.rag.vector_store import VectorStore
    from app.services.rag.contextual_retrieval import ContextualRetrieval

    if not os.path.isdir(skills_dir):
        logger.error("Skills directory does not exist: %s", skills_dir)
        sys.exit(1)

    logger.info("Skills directory: %s", skills_dir)
    logger.info("Collecting skill files...")

    items = collect_skill_files(skills_dir)
    logger.info("Collected %d chunks from avni-skills", len(items))

    if not items:
        logger.warning("No skill files found.")
        return

    # Initialize pipeline
    embedding_client = EmbeddingClient()
    vector_store = VectorStore(dsn=database_url, embedding_dimension=embedding_client.dimension)
    await vector_store.initialize()

    cr = ContextualRetrieval(
        claude_client=None,
        embedding_client=embedding_client,
        vector_store=vector_store,
    )

    start_time = time.time()

    count = await cr.ingest_collection(
        "skills", items, "content",
        source_file="avni-skills",
        batch_size=batch_size,
        use_context=False,
    )

    elapsed = time.time() - start_time

    print(f"\n=== Skills Ingestion Complete ===")
    print(f"Total chunks: {count}")
    print(f"Time elapsed: {elapsed:.1f}s")
    print(f"Throughput: {count / max(elapsed, 0.1):.0f} chunks/sec")

    await vector_store.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest avni-skills knowledge into RAG")
    parser.add_argument(
        "--skills-dir",
        default="/Users/samanvay/Downloads/All/avni-ai/avni-skills",
        help="Path to avni-skills directory",
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL", ""),
        help="PostgreSQL connection URL",
    )
    parser.add_argument("--batch-size", type=int, default=50)

    args = parser.parse_args()

    if not args.database_url:
        print("ERROR: No database URL. Set DATABASE_URL or use --database-url.", file=sys.stderr)
        sys.exit(1)

    asyncio.run(run_ingestion(args.skills_dir, args.database_url, args.batch_size))


if __name__ == "__main__":
    main()
