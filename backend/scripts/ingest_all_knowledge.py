#!/usr/bin/env python3
"""Master ingestion: load ALL Avni knowledge into pgvector RAG.

Sources:
1. Avni skills (27 SKILL.md + guides from avni-skills/)
2. Implementation bundles (concepts summaries, rules from orgs-bundle/)
3. Knowledge base (rule_templates, bundle_guide, videos from app/knowledge/data/)
4. SRS chunks (pre-extracted from Implementations directories)

Usage:
    python scripts/ingest_all_knowledge.py
"""

import asyncio
import glob
import json
import logging
import os
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.dirname(_SCRIPT_DIR)
sys.path.insert(0, _BACKEND_DIR)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("ingest_all")

# Paths
SKILLS_DIR = os.path.expanduser("~/Downloads/All/avni-ai/avni-skills/")
BUNDLES_DIR = os.path.expanduser("~/Downloads/All/avni-ai/orgs-bundle/")
KNOWLEDGE_DIR = os.path.join(_BACKEND_DIR, "app/knowledge/data/")
SRS_CHUNKS = os.path.join(_BACKEND_DIR, "training_data/srs_chunks.json")
DB_EXPORT = "/tmp/avni_db_knowledge/"
DATABASE_URL = "postgresql://samanvay@localhost:5432/avni_ai"


def chunk_text(text: str, max_chars: int = 1500, overlap: int = 200) -> list[str]:
    """Split text into overlapping chunks at paragraph boundaries."""
    if len(text) <= max_chars:
        return [text]
    chunks = []
    paragraphs = text.split("\n\n")
    current = ""
    for para in paragraphs:
        if len(current) + len(para) + 2 > max_chars and current:
            chunks.append(current.strip())
            lines = current.split("\n")
            overlap_text = "\n".join(lines[-3:]) if len(lines) > 3 else current[-overlap:]
            current = overlap_text + "\n\n" + para
        else:
            current = current + "\n\n" + para if current else para
    if current.strip():
        chunks.append(current.strip())
    return chunks


def load_skills() -> list[dict]:
    """Load all SKILL.md and markdown files from avni-skills."""
    chunks = []
    if not os.path.isdir(SKILLS_DIR):
        return chunks
    for md_file in glob.glob(os.path.join(SKILLS_DIR, "**/*.md"), recursive=True):
        rel_path = os.path.relpath(md_file, SKILLS_DIR)
        skill_name = rel_path.split(os.sep)[0]
        try:
            with open(md_file, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            continue
        if len(content) < 50:
            continue
        for i, chunk in enumerate(chunk_text(content, 2000)):
            chunks.append({
                "content": chunk,
                "collection": "skills",
                "metadata": {"skill": skill_name, "file": rel_path, "chunk": i},
                "source_file": rel_path,
            })
    logger.info("Skills: %d chunks from %d files", len(chunks),
                len(glob.glob(os.path.join(SKILLS_DIR, "**/*.md"), recursive=True)))
    return chunks


def load_bundles() -> list[dict]:
    """Load concept summaries and rules from implementation bundles."""
    chunks = []
    if not os.path.isdir(BUNDLES_DIR):
        return chunks
    for org_dir in sorted(os.listdir(BUNDLES_DIR)):
        org_path = os.path.join(BUNDLES_DIR, org_dir)
        if not os.path.isdir(org_path):
            continue

        # Concept summary
        concepts_file = os.path.join(org_path, "concepts.json")
        if os.path.isfile(concepts_file):
            try:
                with open(concepts_file) as f:
                    concepts = json.load(f)
                if isinstance(concepts, list):
                    by_type = {}
                    for c in concepts:
                        dt = c.get("dataType", "?")
                        by_type.setdefault(dt, []).append(c.get("name", ""))
                    summary = f"Org: {org_dir} | {len(concepts)} concepts\n"
                    for dt, names in sorted(by_type.items()):
                        summary += f"{dt} ({len(names)}): {', '.join(names[:25])}\n"
                    chunks.append({
                        "content": summary[:2000],
                        "collection": "concepts",
                        "metadata": {"org": org_dir},
                        "source_file": f"{org_dir}/concepts.json",
                    })
            except Exception:
                pass

        # Rules from forms
        forms_dir = os.path.join(org_path, "forms")
        if os.path.isdir(forms_dir):
            for form_file in glob.glob(os.path.join(forms_dir, "*.json")):
                try:
                    with open(form_file) as f:
                        form = json.load(f)
                except Exception:
                    continue
                if not isinstance(form, dict):
                    continue
                for group in form.get("formElementGroups", []):
                    for fe in group.get("formElements", []):
                        rule = fe.get("rule")
                        if rule and len(str(rule)) > 30:
                            chunks.append({
                                "content": (
                                    f"Rule from {org_dir} | Form: {form.get('name','')} "
                                    f"({form.get('formType','')})\n"
                                    f"Element: {fe.get('concept',{}).get('name','')}\n"
                                    f"Rule:\n{str(rule)[:1500]}"
                                ),
                                "collection": "rules",
                                "metadata": {
                                    "org": org_dir,
                                    "form_type": form.get("formType", ""),
                                },
                                "source_file": f"{org_dir}/forms/{os.path.basename(form_file)}",
                            })

    logger.info("Bundles: %d chunks", len(chunks))
    return chunks


def load_knowledge() -> list[dict]:
    """Load knowledge base files."""
    chunks = []
    if not os.path.isdir(KNOWLEDGE_DIR):
        return chunks
    for f in os.listdir(KNOWLEDGE_DIR):
        path = os.path.join(KNOWLEDGE_DIR, f)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r") as fh:
                content = fh.read()
        except Exception:
            continue
        if len(content) < 50:
            continue
        for i, chunk in enumerate(chunk_text(content, 2000)):
            chunks.append({
                "content": chunk,
                "collection": "knowledge",
                "metadata": {"file": f, "chunk": i},
                "source_file": f,
            })
    # Also load DB export
    kb_file = os.path.join(DB_EXPORT, "COMPLETE_KNOWLEDGE_BASE.md")
    if os.path.isfile(kb_file):
        with open(kb_file) as f:
            content = f.read()
        for i, chunk in enumerate(chunk_text(content, 2000)):
            chunks.append({
                "content": chunk,
                "collection": "knowledge",
                "metadata": {"file": "COMPLETE_KNOWLEDGE_BASE.md", "chunk": i},
                "source_file": "COMPLETE_KNOWLEDGE_BASE.md",
            })
    logger.info("Knowledge: %d chunks", len(chunks))
    return chunks


def load_srs() -> list[dict]:
    """Load pre-extracted SRS chunks."""
    if not os.path.isfile(SRS_CHUNKS):
        return []
    with open(SRS_CHUNKS) as f:
        raw = json.load(f)
    chunks = [{
        "content": c.get("content", ""),
        "collection": "srs_examples",
        "metadata": c.get("metadata", {}),
        "source_file": c.get("metadata", {}).get("source_file", ""),
    } for c in raw if c.get("content")]
    logger.info("SRS: %d chunks", len(chunks))
    return chunks


async def ingest(all_chunks: list[dict]):
    """Embed and insert all chunks into pgvector."""
    from app.services.rag.embeddings import EmbeddingClient
    from app.services.rag.vector_store import VectorStore

    emb = EmbeddingClient()
    vs = VectorStore(dsn=DATABASE_URL)
    await vs.initialize()

    by_coll = {}
    for c in all_chunks:
        by_coll.setdefault(c["collection"], []).append(c)

    total = 0
    for coll, coll_chunks in sorted(by_coll.items()):
        logger.info("Ingesting %s: %d chunks...", coll, len(coll_chunks))
        await vs.clear_collection(coll)

        batch_size = 64
        for i in range(0, len(coll_chunks), batch_size):
            batch = coll_chunks[i:i+batch_size]
            texts = [c["content"] for c in batch]
            embeddings = emb.embed_batch(texts)
            db_chunks = [{
                "collection": coll,
                "content": c["content"],
                "context_prefix": "",
                "embedding": e,
                "metadata": c.get("metadata", {}),
                "source_file": c.get("source_file", ""),
            } for c, e in zip(batch, embeddings)]
            await vs.upsert_chunks(db_chunks)
            total += len(db_chunks)

    stats = await vs.get_collection_stats()
    logger.info("=" * 60)
    logger.info("DONE: %d total chunks ingested", total)
    for c, n in sorted(stats.items()):
        logger.info("  %s: %d", c, n)
    logger.info("=" * 60)
    await vs.close()


def main():
    all_chunks = []
    all_chunks.extend(load_skills())
    all_chunks.extend(load_bundles())
    all_chunks.extend(load_knowledge())
    all_chunks.extend(load_srs())
    logger.info("Total: %d chunks to ingest", len(all_chunks))
    asyncio.run(ingest(all_chunks))


if __name__ == "__main__":
    main()
