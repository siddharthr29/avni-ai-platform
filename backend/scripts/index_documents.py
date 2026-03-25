#!/usr/bin/env python3
"""Bulk document indexing using PageIndex.

Indexes PDF and Markdown files into hierarchical tree structures for
reasoning-based retrieval. Works alongside the existing vector RAG.

Usage:
    # Index a single PDF
    python scripts/index_documents.py --file /path/to/document.pdf

    # Index a single Markdown file
    python scripts/index_documents.py --file /path/to/document.md

    # Index all PDFs and MDs in a directory
    python scripts/index_documents.py --dir /path/to/docs/

    # Index with specific collection name
    python scripts/index_documents.py --dir /path/to/docs/ --collection srs_documents

    # Index Avni skills documentation
    python scripts/index_documents.py --skills /path/to/avni-skills/

    # List all indexed documents
    python scripts/index_documents.py --list

    # Show stats
    python scripts/index_documents.py --stats
"""

import argparse
import asyncio
import glob
import logging
import os
import sys

# Add parent dir to path so we can import app modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def index_file(service, file_path: str, collection: str, metadata: dict | None = None):
    """Index a single file."""
    ext = os.path.splitext(file_path)[1].lower()
    name = os.path.basename(file_path)

    if ext == ".pdf":
        result = await service.index_pdf(
            pdf_path=file_path,
            name=name,
            collection=collection,
            metadata=metadata or {},
            add_summaries=True,
            add_text=True,
        )
    elif ext in (".md", ".markdown"):
        result = await service.index_markdown(
            md_path=file_path,
            name=name,
            collection=collection,
            metadata=metadata or {},
            add_summaries=False,
            add_text=True,
        )
    else:
        logger.warning("Skipping unsupported file: %s", file_path)
        return None

    return result


async def index_directory(service, dir_path: str, collection: str):
    """Index all PDF and Markdown files in a directory."""
    patterns = ["**/*.pdf", "**/*.md", "**/*.markdown"]
    files = []
    for pattern in patterns:
        files.extend(glob.glob(os.path.join(dir_path, pattern), recursive=True))

    files = sorted(set(files))
    logger.info("Found %d files to index in %s", len(files), dir_path)

    indexed = 0
    failed = 0
    for i, fp in enumerate(files):
        try:
            rel_path = os.path.relpath(fp, dir_path)
            logger.info("[%d/%d] Indexing: %s", i + 1, len(files), rel_path)
            result = await index_file(
                service, fp, collection,
                metadata={"relative_path": rel_path, "source_dir": dir_path},
            )
            if result:
                indexed += 1
                logger.info("  -> %d nodes", result["node_count"])
        except Exception as e:
            logger.error("  -> FAILED: %s", e)
            failed += 1

    logger.info("Done: %d indexed, %d failed out of %d files", indexed, failed, len(files))


async def index_skills(service, skills_dir: str):
    """Index avni-skills SKILL.md files and other documentation."""
    skill_dirs = sorted(glob.glob(os.path.join(skills_dir, "*")))

    indexed = 0
    for sd in skill_dirs:
        if not os.path.isdir(sd):
            continue

        skill_name = os.path.basename(sd)
        skill_md = os.path.join(sd, "SKILL.md")

        if os.path.exists(skill_md):
            try:
                logger.info("Indexing skill: %s", skill_name)
                result = await service.index_markdown(
                    md_path=skill_md,
                    name=f"Skill: {skill_name}",
                    collection="skills",
                    metadata={"skill_name": skill_name, "type": "skill_documentation"},
                    add_text=True,
                )
                indexed += 1
                logger.info("  -> %d nodes", result["node_count"])
            except Exception as e:
                logger.error("  -> FAILED: %s", e)

        # Also index other .md files in the skill directory
        for md_file in glob.glob(os.path.join(sd, "*.md")):
            if md_file == skill_md:
                continue
            md_name = os.path.basename(md_file)
            try:
                result = await service.index_markdown(
                    md_path=md_file,
                    name=f"{skill_name}/{md_name}",
                    collection="skills",
                    metadata={"skill_name": skill_name, "type": "skill_guide"},
                    add_text=True,
                )
                indexed += 1
            except Exception as e:
                logger.error("  -> FAILED to index %s: %s", md_name, e)

    logger.info("Done: %d skill documents indexed", indexed)


async def main():
    parser = argparse.ArgumentParser(description="Bulk document indexing with PageIndex")
    parser.add_argument("--file", type=str, help="Path to a single file to index")
    parser.add_argument("--dir", type=str, help="Directory to scan for PDF/MD files")
    parser.add_argument("--skills", type=str, help="Path to avni-skills directory")
    parser.add_argument("--collection", type=str, default="documents", help="Collection name")
    parser.add_argument("--list", action="store_true", help="List all indexed documents")
    parser.add_argument("--stats", action="store_true", help="Show index statistics")
    args = parser.parse_args()

    if not any([args.file, args.dir, args.skills, args.list, args.stats]):
        parser.print_help()
        return

    # Initialize service
    from app.services.pageindex_service import pageindex_service
    await pageindex_service.initialize()

    try:
        if args.stats:
            stats = await pageindex_service.get_stats()
            print(f"\nPageIndex Statistics:")
            print(f"  Total documents: {stats['total_documents']}")
            for coll, info in stats.get("collections", {}).items():
                print(f"  [{coll}] {info['documents']} docs, {info['pages']} pages, {info['nodes']} nodes")

        elif args.list:
            docs = await pageindex_service.list_documents(limit=100)
            print(f"\nIndexed Documents ({len(docs)}):")
            for d in docs:
                print(f"  [{d['collection']}] {d['name']} — {d['node_count']} nodes, {d['page_count']} pages ({d['doc_type']})")

        elif args.file:
            if not os.path.exists(args.file):
                print(f"File not found: {args.file}")
                return
            result = await index_file(pageindex_service, args.file, args.collection)
            if result:
                print(f"\nIndexed: {result['name']}")
                print(f"  ID: {result['id']}")
                print(f"  Nodes: {result['node_count']}")
                print(f"  Pages: {result['page_count']}")

        elif args.dir:
            if not os.path.isdir(args.dir):
                print(f"Directory not found: {args.dir}")
                return
            await index_directory(pageindex_service, args.dir, args.collection)

        elif args.skills:
            if not os.path.isdir(args.skills):
                print(f"Skills directory not found: {args.skills}")
                return
            await index_skills(pageindex_service, args.skills)

    finally:
        await pageindex_service.close()


if __name__ == "__main__":
    asyncio.run(main())
