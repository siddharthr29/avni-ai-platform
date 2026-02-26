import logging

from fastapi import APIRouter, HTTPException

from app.models.schemas import KnowledgeSearchRequest, KnowledgeSearchResponse
from app.services.knowledge_base import knowledge_base

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/knowledge/search", response_model=KnowledgeSearchResponse)
async def knowledge_search(request: KnowledgeSearchRequest) -> KnowledgeSearchResponse:
    """Search the Avni knowledge base.

    Searches across concepts, rules, and support patterns using keyword
    and fuzzy matching. Optionally filter by category.
    """
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    category = request.category
    limit = request.limit

    if category == "concepts":
        results = knowledge_base.search_concepts(request.query, limit=limit)
    elif category == "rules":
        results = knowledge_base.search_rules(request.query, limit=limit)
    elif category == "tickets":
        results = knowledge_base.search_tickets(request.query, limit=limit)
    elif category is None:
        results = knowledge_base.search_all(request.query, limit=limit)
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown category: {category}. "
                   f"Valid categories: concepts, rules, tickets, or omit for all.",
        )

    return KnowledgeSearchResponse(
        results=results,
        total=len(results),
        query=request.query,
    )
