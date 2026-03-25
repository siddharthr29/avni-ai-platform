#!/usr/bin/env python3
"""Ingest YouTube video transcripts into pgvector RAG.

Fetches auto-generated or manual captions from YouTube videos
and indexes them into the 'transcripts' collection.

Usage:
    # Single video
    python scripts/ingest_youtube.py https://www.youtube.com/watch?v=VIDEO_ID

    # Multiple videos
    python scripts/ingest_youtube.py VIDEO_ID1 VIDEO_ID2 VIDEO_ID3

    # From a file (one URL/ID per line)
    python scripts/ingest_youtube.py --file video_list.txt

    # Avni YouTube channel (known training videos)
    python scripts/ingest_youtube.py --avni-channel
"""

import asyncio
import logging
import os
import re
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.dirname(_SCRIPT_DIR)
sys.path.insert(0, _BACKEND_DIR)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("ingest_youtube")

DATABASE_URL = "postgresql://samanvay@localhost:5432/avni_ai"
COLLECTION = "transcripts"

# Known Avni training video IDs (from YouTube channel)
AVNI_TRAINING_VIDEOS = [
    # Add known Avni video IDs here
    # These can be found from the Avni YouTube channel
]


def chunk_text(text: str, max_chars: int = 1500, overlap: int = 200) -> list[str]:
    """Split text into overlapping chunks."""
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


def extract_video_id(url_or_id: str) -> str:
    """Extract YouTube video ID from URL or return as-is if already an ID."""
    patterns = [
        r"(?:v=|\/v\/|youtu\.be\/|\/embed\/)([a-zA-Z0-9_-]{11})",
        r"^([a-zA-Z0-9_-]{11})$",
    ]
    for pattern in patterns:
        match = re.search(pattern, url_or_id)
        if match:
            return match.group(1)
    return url_or_id


def fetch_transcript(video_id: str) -> tuple[str, str]:
    """Fetch transcript for a YouTube video.

    Returns: (transcript_text, video_title)
    """
    from youtube_transcript_api import YouTubeTranscriptApi

    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

        # Prefer manual transcripts, fall back to auto-generated
        transcript = None
        for t in transcript_list:
            if not t.is_generated:
                transcript = t
                break
        if transcript is None:
            # Use first available (auto-generated)
            transcript = next(iter(transcript_list))

        entries = transcript.fetch()

        # Group entries into paragraphs by timestamp gaps
        paragraphs = []
        current_para = []
        last_end = 0

        for entry in entries:
            start = entry.get("start", 0) if isinstance(entry, dict) else getattr(entry, "start", 0)
            text = entry.get("text", "") if isinstance(entry, dict) else getattr(entry, "text", "")
            duration = entry.get("duration", 0) if isinstance(entry, dict) else getattr(entry, "duration", 0)

            # New paragraph if gap > 3 seconds
            if start - last_end > 3 and current_para:
                paragraphs.append(" ".join(current_para))
                current_para = []

            current_para.append(text.strip())
            last_end = start + duration

        if current_para:
            paragraphs.append(" ".join(current_para))

        full_text = "\n\n".join(paragraphs)

        # Try to get video title from transcript metadata
        title = f"YouTube Video {video_id}"
        try:
            lang = transcript.language
            title = f"YouTube Video {video_id} ({lang})"
        except Exception:
            pass

        return full_text, title

    except Exception as e:
        logger.warning("Failed to fetch transcript for %s: %s", video_id, e)
        return "", f"YouTube Video {video_id}"


def load_video_ids(args: list[str]) -> list[str]:
    """Parse command line args into video IDs."""
    video_ids = []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--avni-channel":
            video_ids.extend(AVNI_TRAINING_VIDEOS)
        elif arg == "--file":
            i += 1
            if i < len(args):
                filepath = args[i]
                with open(filepath, "r") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            video_ids.append(extract_video_id(line))
        else:
            video_ids.append(extract_video_id(arg))
        i += 1

    return video_ids


def process_videos(video_ids: list[str]) -> list[dict]:
    """Fetch and chunk transcripts for all videos."""
    all_chunks = []

    for vid in video_ids:
        logger.info("Fetching transcript for %s...", vid)
        text, title = fetch_transcript(vid)

        if not text or len(text) < 50:
            logger.warning("Skipping %s (no transcript or too short)", vid)
            continue

        logger.info("  %s: %d chars", title, len(text))

        for i, chunk in enumerate(chunk_text(text, 1500)):
            all_chunks.append({
                "content": chunk,
                "collection": COLLECTION,
                "context_prefix": f"YouTube Training Video: {title}",
                "metadata": {
                    "video_id": vid,
                    "title": title,
                    "chunk": i,
                    "type": "youtube_transcript",
                    "url": f"https://www.youtube.com/watch?v={vid}",
                },
                "source_file": f"youtube:{vid}",
            })

    logger.info("Total: %d chunks from %d videos", len(all_chunks), len(video_ids))
    return all_chunks


async def ingest(all_chunks: list[dict]):
    """Embed and insert chunks into pgvector."""
    from app.services.rag.embeddings import EmbeddingClient
    from app.services.rag.vector_store import VectorStore

    emb = EmbeddingClient()
    vs = VectorStore(dsn=DATABASE_URL)
    await vs.initialize()

    logger.info("Clearing existing '%s' collection...", COLLECTION)
    await vs.clear_collection(COLLECTION)

    total = 0
    batch_size = 64
    for i in range(0, len(all_chunks), batch_size):
        batch = all_chunks[i : i + batch_size]
        texts = [c["content"] for c in batch]
        embeddings = emb.embed_batch(texts)
        db_chunks = [
            {
                "collection": COLLECTION,
                "content": c["content"],
                "context_prefix": c.get("context_prefix", ""),
                "embedding": e,
                "metadata": c.get("metadata", {}),
                "source_file": c.get("source_file", ""),
            }
            for c, e in zip(batch, embeddings)
        ]
        await vs.upsert_chunks(db_chunks)
        total += len(db_chunks)
        logger.info("  Ingested %d / %d", total, len(all_chunks))

    stats = await vs.get_collection_stats()
    logger.info("=" * 60)
    logger.info("DONE: %d transcript chunks ingested", total)
    for c, n in sorted(stats.items()):
        logger.info("  %s: %d", c, n)
    logger.info("=" * 60)
    await vs.close()


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    video_ids = load_video_ids(sys.argv[1:])
    if not video_ids:
        logger.error("No video IDs provided")
        sys.exit(1)

    logger.info("Processing %d video(s)...", len(video_ids))
    chunks = process_videos(video_ids)

    if not chunks:
        logger.error("No transcripts extracted")
        sys.exit(1)

    asyncio.run(ingest(chunks))


if __name__ == "__main__":
    main()
