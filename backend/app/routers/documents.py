"""Document indexing and tree-based retrieval endpoints (powered by PageIndex).

Provides:
- POST /documents/upload      — Upload and index a PDF or Markdown file
- POST /documents/retrieve    — Tree-based reasoning retrieval
- GET  /documents             — List all indexed documents
- GET  /documents/{id}        — Get document with full tree structure
- GET  /documents/{id}/toc    — Get document table of contents
- DELETE /documents/{id}      — Delete a document index
- POST /documents/search      — Search document metadata
- GET  /documents/stats       — Document index statistics
"""

import logging
import os
import tempfile
import uuid

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from typing import Any

from app.services.pageindex_service import pageindex_service

logger = logging.getLogger(__name__)

router = APIRouter()


# --- Request/Response Models ---

class DocumentRetrieveRequest(BaseModel):
    query: str = Field(description="Question or search query")
    doc_id: str | None = Field(default=None, description="Specific document ID, or None for all")
    collection: str | None = Field(default=None, description="Collection filter")
    max_sections: int = Field(default=5, ge=1, le=20)


class DocumentSearchRequest(BaseModel):
    query: str = Field(description="Search query for document names/descriptions")
    collection: str | None = None
    limit: int = Field(default=10, ge=1, le=50)


class DocumentRetrieveResponse(BaseModel):
    query: str
    sections: list[dict[str, Any]]
    total: int


# --- Endpoints ---

@router.post("/documents/upload")
async def upload_and_index(
    file: UploadFile = File(...),
    collection: str = Form(default="documents"),
    name: str | None = Form(default=None),
):
    """Upload a PDF or Markdown file and index it using PageIndex.

    The document is analyzed into a hierarchical tree structure that enables
    intelligent, reasoning-based retrieval. No vector embeddings needed.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in (".pdf", ".md", ".markdown"):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {ext}. Supported: .pdf, .md, .markdown",
        )

    doc_name = name or file.filename

    # Save to temp file
    content = await file.read()
    suffix = ext
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        if ext == ".pdf":
            result = await pageindex_service.index_pdf(
                pdf_path=tmp_path,
                name=doc_name,
                collection=collection,
                metadata={"original_filename": file.filename, "size_bytes": len(content)},
                add_summaries=True,
                add_text=True,
            )
        else:
            result = await pageindex_service.index_markdown(
                md_path=tmp_path,
                name=doc_name,
                collection=collection,
                metadata={"original_filename": file.filename, "size_bytes": len(content)},
                add_summaries=False,
                add_text=True,
            )

        return {
            "id": result["id"],
            "name": result["name"],
            "doc_type": result["doc_type"],
            "page_count": result["page_count"],
            "node_count": result["node_count"],
            "collection": result["collection"],
            "message": f"Document indexed successfully with {result['node_count']} nodes",
        }

    except Exception as e:
        logger.exception("Failed to index document: %s", file.filename)
        raise HTTPException(status_code=500, detail=f"Indexing failed: {str(e)}")

    finally:
        os.unlink(tmp_path)


@router.post("/documents/retrieve", response_model=DocumentRetrieveResponse)
async def retrieve_from_documents(request: DocumentRetrieveRequest):
    """Retrieve relevant sections using tree-based reasoning.

    Unlike vector search which matches by similarity, this endpoint uses
    LLM reasoning to navigate the document's hierarchical structure —
    like how a human expert reads a table of contents to find information.

    Returns complete, coherent sections with exact page/section references.
    """
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    sections = await pageindex_service.retrieve(
        query=request.query,
        doc_id=request.doc_id,
        collection=request.collection,
        max_sections=request.max_sections,
    )

    return DocumentRetrieveResponse(
        query=request.query,
        sections=sections,
        total=len(sections),
    )


@router.get("/documents")
async def list_documents(
    collection: str | None = None,
    limit: int = 50,
):
    """List all indexed documents (without tree structure for brevity)."""
    docs = await pageindex_service.list_documents(
        collection=collection, limit=limit
    )
    return {"documents": docs, "total": len(docs)}


@router.get("/documents/stats")
async def document_stats():
    """Get statistics about the document index."""
    stats = await pageindex_service.get_stats()
    return stats


@router.get("/documents/{doc_id}")
async def get_document(doc_id: str):
    """Get a document index including the full tree structure."""
    doc = await pageindex_service.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.get("/documents/{doc_id}/toc")
async def get_document_toc(doc_id: str):
    """Get the document's table of contents (tree structure without text)."""
    doc = await pageindex_service.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    def strip_text(tree):
        """Remove text from tree nodes for a compact TOC view."""
        if isinstance(tree, dict):
            result = {k: v for k, v in tree.items() if k != "text"}
            if "nodes" in result:
                result["nodes"] = strip_text(result["nodes"])
            return result
        elif isinstance(tree, list):
            return [strip_text(item) for item in tree]
        return tree

    toc = strip_text(doc["tree_structure"])
    return {
        "id": doc["id"],
        "name": doc["name"],
        "toc": toc,
    }


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str):
    """Delete a document index."""
    deleted = await pageindex_service.delete_document(doc_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"deleted": True, "id": doc_id}


@router.post("/documents/search")
async def search_documents(request: DocumentSearchRequest):
    """Search documents by name and description (keyword search on metadata)."""
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    results = await pageindex_service.search_documents(
        query=request.query,
        collection=request.collection,
        limit=request.limit,
    )

    return {"results": results, "total": len(results), "query": request.query}
