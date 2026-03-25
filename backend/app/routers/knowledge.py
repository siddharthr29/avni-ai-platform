import logging

from fastapi import APIRouter, HTTPException

from app.models.schemas import KnowledgeSearchRequest, KnowledgeSearchResponse
from app.services.rag.fallback import rag_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/knowledge/search", response_model=KnowledgeSearchResponse)
async def knowledge_search(request: KnowledgeSearchRequest) -> KnowledgeSearchResponse:
    """Search the Avni knowledge base.

    Uses hybrid vector + keyword search (RAG) when pgvector is available,
    or falls back to in-memory keyword + fuzzy matching. Optionally filter
    by category.
    """
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    category = request.category
    limit = request.limit

    if category == "concepts":
        results = await rag_service.search_concepts(request.query, limit=limit)
    elif category == "forms":
        results = await rag_service.search_forms(request.query, limit=limit)
    elif category == "rules":
        results = await rag_service.search_rules(request.query, limit=limit)
    elif category == "tickets":
        results = await rag_service.search_tickets(request.query, limit=limit)
    elif category == "knowledge":
        results = await rag_service.search_knowledge(request.query, limit=limit)
    elif category is None:
        results = await rag_service.search_all(request.query, limit=limit)
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown category: {category}. "
                   f"Valid categories: concepts, forms, rules, tickets, knowledge, or omit for all.",
        )

    return KnowledgeSearchResponse(
        results=results,
        total=len(results),
        query=request.query,
    )


@router.get("/knowledge/status")
async def knowledge_status() -> dict:
    """Return the status and statistics of the knowledge/RAG pipeline."""
    stats = await rag_service.get_stats()

    # Include PageIndex stats
    try:
        from app.services.pageindex_service import pageindex_service
        pi_stats = await pageindex_service.get_stats()
        stats["pageindex"] = pi_stats
    except Exception:
        stats["pageindex"] = {"total_documents": 0, "collections": {}}

    return stats
