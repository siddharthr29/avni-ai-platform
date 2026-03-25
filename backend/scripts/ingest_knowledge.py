#!/usr/bin/env python3
"""Standalone knowledge ingestion script for the Avni AI Platform RAG pipeline.

Loads all knowledge sources from the training data directory, generates
embeddings (and optionally contextual prefixes via Claude), and stores
them in pgvector for hybrid retrieval.

Usage:
    # Full ingestion with contextual embeddings (slower, production quality)
    python scripts/ingest_knowledge.py \\
        --data-dir app/knowledge/data/ \\
        --database-url postgresql://avni:avni_ai_dev@localhost:5432/avni_ai \\
        --contextual

    # Fast ingestion without contextual embeddings (for development)
    python scripts/ingest_knowledge.py \\
        --data-dir app/knowledge/data/ \\
        --database-url postgresql://avni:avni_ai_dev@localhost:5432/avni_ai \\
        --fast

    # Check ingestion status
    python scripts/ingest_knowledge.py \\
        --status \\
        --database-url postgresql://avni:avni_ai_dev@localhost:5432/avni_ai

    # Clear all data and re-ingest
    python scripts/ingest_knowledge.py \\
        --data-dir app/knowledge/data/ \\
        --database-url postgresql://avni:avni_ai_dev@localhost:5432/avni_ai \\
        --clear --fast
"""

import argparse
import asyncio
import logging
import os
import sys
import time

# Add the backend directory to sys.path so we can import app modules
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.dirname(_SCRIPT_DIR)
sys.path.insert(0, _BACKEND_DIR)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("ingest_knowledge")


async def check_status(database_url: str) -> None:
    """Print current ingestion status."""
    from app.services.rag.vector_store import VectorStore

    store = VectorStore(dsn=database_url)
    await store.initialize()

    stats = await store.get_collection_stats()
    total = await store.get_total_count()

    print("\n=== RAG Pipeline Status ===")
    print(f"Database: {database_url.split('@')[-1] if '@' in database_url else database_url}")
    print(f"Total chunks: {total}")
    print()

    if stats:
        print("Collections:")
        for coll, count in sorted(stats.items()):
            print(f"  {coll:20s} {count:6d} chunks")
    else:
        print("No data ingested yet.")
        print("Run with --fast or --contextual to populate.")

    print()
    await store.close()


async def clear_data(database_url: str) -> None:
    """Clear all ingested data."""
    from app.services.rag.vector_store import VectorStore

    store = VectorStore(dsn=database_url)
    await store.initialize()

    count = await store.clear_all()
    print(f"Cleared {count} chunks from all collections.")
    await store.close()


async def run_ingestion(
    data_dir: str,
    database_url: str,
    use_context: bool,
    batch_size: int,
) -> None:
    """Run the full ingestion pipeline."""
    from app.services.rag.embeddings import EmbeddingClient
    from app.services.rag.vector_store import VectorStore
    from app.services.rag.contextual_retrieval import ContextualRetrieval
    from app.services.rag.ingestion import KnowledgeIngestion

    # Resolve data directory
    if not os.path.isabs(data_dir):
        data_dir = os.path.join(_BACKEND_DIR, data_dir)

    if not os.path.isdir(data_dir):
        logger.error("Data directory does not exist: %s", data_dir)
        sys.exit(1)

    logger.info("Data directory: %s", data_dir)
    logger.info("Database URL: %s", database_url.split("@")[-1] if "@" in database_url else "***")
    logger.info("Contextual prefixes: %s", "ENABLED (using Claude)" if use_context else "DISABLED (fast mode)")
    logger.info("Batch size: %d", batch_size)

    # Initialize components
    embedding_client = EmbeddingClient()
    logger.info("Embedding model: %s (dimension=%d)", embedding_client.model_name, embedding_client.dimension)

    vector_store = VectorStore(dsn=database_url, embedding_dimension=embedding_client.dimension)
    await vector_store.initialize()

    # For contextual mode, we need the Claude client
    claude_client = None
    if use_context:
        try:
            from app.services.claude_client import claude_client as _cc
            if not os.getenv("ANTHROPIC_API_KEY"):
                logger.warning(
                    "ANTHROPIC_API_KEY not set. Contextual prefixes will be empty. "
                    "Set the key or use --fast mode."
                )
            claude_client = _cc
        except Exception as e:
            logger.warning("Claude client not available: %s. Falling back to fast mode.", e)
            use_context = False

    contextual_retrieval = ContextualRetrieval(
        claude_client=claude_client,
        embedding_client=embedding_client,
        vector_store=vector_store,
    )

    ingestion = KnowledgeIngestion(contextual_retrieval)

    # Run ingestion
    start_time = time.time()
    stats = await ingestion.ingest_all(
        data_dir=data_dir,
        use_context=use_context,
        batch_size=batch_size,
    )
    elapsed = time.time() - start_time

    # Print summary
    total = sum(stats.values())
    print(f"\n=== Ingestion Complete ===")
    print(f"Total chunks: {total}")
    print(f"Time elapsed: {elapsed:.1f}s")
    print(f"Throughput: {total / max(elapsed, 0.1):.0f} chunks/sec")
    print()
    print("Collections:")
    for coll, count in sorted(stats.items()):
        print(f"  {coll:20s} {count:6d} chunks")
    print()

    await vector_store.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Avni AI Platform - Knowledge Ingestion for RAG Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--data-dir",
        default="app/knowledge/data/",
        help="Path to the knowledge data directory (default: app/knowledge/data/)",
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL", ""),
        help="PostgreSQL connection URL (default: $DATABASE_URL env var)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Number of items to process per batch (default: 50)",
    )

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--contextual",
        action="store_true",
        help="Generate contextual prefixes using Claude (slower, better quality)",
    )
    mode_group.add_argument(
        "--fast",
        action="store_true",
        help="Skip contextual prefix generation (faster, for development)",
    )
    mode_group.add_argument(
        "--status",
        action="store_true",
        help="Check ingestion status without ingesting",
    )

    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear all existing data before ingesting",
    )

    args = parser.parse_args()

    # Validate database URL
    if not args.database_url:
        print(
            "ERROR: No database URL provided.\n"
            "Set DATABASE_URL environment variable or use --database-url.\n"
            "Example: --database-url postgresql://avni:avni_ai_dev@localhost:5432/avni_ai",
            file=sys.stderr,
        )
        sys.exit(1)

    # Run the appropriate action
    if args.status:
        asyncio.run(check_status(args.database_url))
    elif args.clear and not (args.contextual or args.fast):
        asyncio.run(clear_data(args.database_url))
    else:
        if args.clear:
            asyncio.run(clear_data(args.database_url))

        use_context = args.contextual  # False for --fast or default
        asyncio.run(
            run_ingestion(
                data_dir=args.data_dir,
                database_url=args.database_url,
                use_context=use_context,
                batch_size=args.batch_size,
            )
        )


if __name__ == "__main__":
    main()
