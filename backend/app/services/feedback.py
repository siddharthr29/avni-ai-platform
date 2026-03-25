"""Feedback and bundle editing service.

Handles:
1. Message-level feedback (thumbs up/down, corrections)
2. Bundle edit requests (modify generated bundle before applying)
3. Feedback-driven learning (store corrections for RAG retrieval)
"""

import json
import logging
import uuid
from typing import Any

from app import db
from app.services.rag.fallback import rag_service

logger = logging.getLogger(__name__)

# In-memory store for generated bundles awaiting review
_pending_bundles: dict[str, dict[str, Any]] = {}


class FeedbackService:
    """Manages user feedback on AI responses and generated bundles."""

    async def save_feedback(
        self,
        session_id: str,
        message_id: str,
        rating: str,  # "up", "down", "correction"
        correction: str | None = None,
        metadata: dict | None = None,
    ) -> dict:
        """Save feedback on an AI response.

        When rating is "down" with a correction, the correction is stored
        as a training signal for future RAG retrieval.
        """
        feedback_id = str(uuid.uuid4())

        # Save to DB
        if db.is_connected():
            await db.add_feedback(
                feedback_id=feedback_id,
                session_id=session_id,
                message_id=message_id,
                rating=rating,
                correction=correction,
                metadata=metadata or {},
            )

        # If user provided a correction, index it for future retrieval
        if rating in ("down", "correction") and correction:
            await self._index_correction(session_id, message_id, correction, metadata)

        return {"feedback_id": feedback_id, "status": "saved"}

    async def _index_correction(
        self,
        session_id: str,
        message_id: str,
        correction: str,
        metadata: dict | None = None,
    ) -> None:
        """Index a user correction into the RAG knowledge base.

        Corrections become part of the 'corrections' collection and are
        retrieved alongside other knowledge to prevent the same mistake.
        """
        try:
            if not rag_service.is_rag_available:
                return

            from app.services.rag.embeddings import EmbeddingClient

            emb = EmbeddingClient()
            embedding = emb.embed_batch([correction])[0]

            await rag_service._vector_store.upsert_chunks([{
                "collection": "corrections",
                "content": correction,
                "context_prefix": "",
                "embedding": embedding,
                "metadata": {
                    "session_id": session_id,
                    "message_id": message_id,
                    **(metadata or {}),
                },
                "source_file": f"feedback/{session_id}",
            }])
            logger.info("Indexed correction from session %s", session_id)
        except Exception:
            logger.exception("Failed to index correction")

    def store_pending_bundle(
        self,
        bundle_id: str,
        srs_data: dict,
        generated_files: dict[str, Any],
    ) -> None:
        """Store a generated bundle for user review before applying."""
        _pending_bundles[bundle_id] = {
            "srs_data": srs_data,
            "files": generated_files,
            "edits": [],
            "status": "pending_review",
        }

    def get_pending_bundle(self, bundle_id: str) -> dict | None:
        """Get a pending bundle for review."""
        return _pending_bundles.get(bundle_id)

    def edit_bundle_file(
        self,
        bundle_id: str,
        file_name: str,
        content: Any,
    ) -> dict:
        """Edit a specific file in a pending bundle.

        Users can modify concepts, forms, rules etc before the bundle
        is finalized and uploaded to Avni.
        """
        bundle = _pending_bundles.get(bundle_id)
        if not bundle:
            return {"error": "Bundle not found"}

        if file_name not in bundle["files"]:
            return {"error": f"File '{file_name}' not found in bundle"}

        # Track the edit
        bundle["edits"].append({
            "file": file_name,
            "original": bundle["files"][file_name],
            "modified": content,
        })
        bundle["files"][file_name] = content

        return {"status": "updated", "file": file_name}

    def approve_bundle(self, bundle_id: str) -> dict | None:
        """Mark a bundle as approved and ready for upload."""
        bundle = _pending_bundles.get(bundle_id)
        if bundle:
            bundle["status"] = "approved"
        return bundle

    def list_pending_bundles(self) -> list[dict]:
        """List all bundles pending review."""
        return [
            {"bundle_id": bid, "status": b["status"], "edit_count": len(b["edits"])}
            for bid, b in _pending_bundles.items()
        ]


feedback_service = FeedbackService()
