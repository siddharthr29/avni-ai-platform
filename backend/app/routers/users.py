"""User profile and session management endpoints."""

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app import db
from app.services.encryption import encrypt, decrypt

logger = logging.getLogger(__name__)


def _get_auth(request: Request) -> tuple[str, str]:
    """Extract authenticated user_id and role from request state.
    Returns (user_id, role). Raises 401 if not authenticated."""
    user_id = getattr(request.state, "user_id", None)
    role = getattr(request.state, "user_role", "implementor")
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user_id, role


def _is_admin(role: str) -> bool:
    """Check if role has admin privileges."""
    return role in ("platform_admin", "org_admin")

router = APIRouter()


# ── Request / Response Models ─────────────────────────────────────────────────

class UserLoginRequest(BaseModel):
    id: str = Field(description="Client-generated user UUID")
    name: str
    org_name: str
    sector: str = ""
    org_context: str = ""


class SessionCreateRequest(BaseModel):
    id: str = Field(description="Client-generated session UUID")
    user_id: str
    title: str = "New Chat"


class SessionUpdateRequest(BaseModel):
    title: str


# ── User Endpoints ────────────────────────────────────────────────────────────

@router.post("/users/login")
async def login_or_register(request: UserLoginRequest) -> dict:
    """Create or update a user profile. Called on frontend login."""
    user = await db.upsert_user(
        user_id=request.id,
        name=request.name,
        org_name=request.org_name,
        sector=request.sector,
        org_context=request.org_context,
    )
    return {"user": user}


@router.get("/users/{user_id}")
async def get_user(user_id: str, request: Request) -> dict:
    auth_user_id, auth_role = _get_auth(request)
    # Only allow users to view their own profile, unless admin
    if auth_user_id != user_id and not _is_admin(auth_role):
        raise HTTPException(status_code=403, detail="Cannot access another user's profile")
    user = await db.get_user(user_id)
    if not user:
        return {"user": None}
    return {"user": user}


# ── Session Endpoints ─────────────────────────────────────────────────────────

@router.get("/users/{user_id}/sessions")
async def get_user_sessions(user_id: str, request: Request) -> dict:
    """Get all sessions for a user with message counts."""
    auth_user_id, auth_role = _get_auth(request)
    if auth_user_id != user_id and not _is_admin(auth_role):
        raise HTTPException(status_code=403, detail="Cannot access another user's sessions")
    sessions = await db.get_user_sessions(user_id)
    return {"sessions": sessions}


@router.post("/sessions")
async def create_session(request: SessionCreateRequest, http_request: Request) -> dict:
    auth_user_id, auth_role = _get_auth(http_request)
    # Ensure the session is created for the authenticated user
    if auth_user_id != request.user_id and not _is_admin(auth_role):
        raise HTTPException(status_code=403, detail="Cannot create sessions for another user")
    session = await db.create_session(
        session_id=request.id,
        user_id=request.user_id,
        title=request.title,
    )
    return {"session": session}


@router.patch("/sessions/{session_id}")
async def update_session(session_id: str, request: SessionUpdateRequest, http_request: Request) -> dict:
    auth_user_id, auth_role = _get_auth(http_request)
    if not _is_admin(auth_role):
        if not await db.verify_session_ownership(session_id, auth_user_id):
            raise HTTPException(status_code=403, detail="Session does not belong to you")
    await db.update_session_title(session_id, request.title)
    return {"ok": True}


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, request: Request) -> dict:
    auth_user_id, auth_role = _get_auth(request)
    if not _is_admin(auth_role):
        if not await db.verify_session_ownership(session_id, auth_user_id):
            raise HTTPException(status_code=403, detail="Session does not belong to you")
    await db.delete_session(session_id)
    return {"ok": True}


@router.get("/sessions/{session_id}/messages")
async def get_session_messages(session_id: str, request: Request) -> dict:
    """Get all messages for a session."""
    auth_user_id, auth_role = _get_auth(request)
    if not _is_admin(auth_role):
        if not await db.verify_session_ownership(session_id, auth_user_id):
            raise HTTPException(status_code=403, detail="Session does not belong to you")
    messages = await db.get_session_messages(session_id)
    return {"messages": messages}


# ── BYOK (Bring Your Own Key) Endpoints ──────────────────────────────────────

class BYOKSaveRequest(BaseModel):
    provider: str = Field(description="LLM provider: 'groq', 'anthropic', 'gemini', 'cerebras', 'openai'")
    api_key: str = Field(description="API key for the provider")


class BYOKDeleteRequest(BaseModel):
    provider: str = Field(description="LLM provider to remove key for")


SUPPORTED_BYOK_PROVIDERS = {"groq", "anthropic", "gemini", "cerebras", "openai"}


@router.post("/users/{user_id}/byok")
async def save_byok_key(user_id: str, request: BYOKSaveRequest, http_request: Request) -> dict:
    """Save or update a user's BYOK API key for a specific provider."""
    auth_user_id, auth_role = _get_auth(http_request)
    if auth_user_id != user_id and not _is_admin(auth_role):
        raise HTTPException(status_code=403, detail="Cannot modify another user's API keys")

    if request.provider not in SUPPORTED_BYOK_PROVIDERS:
        return {"error": f"Unsupported provider: {request.provider}. Supported: {SUPPORTED_BYOK_PROVIDERS}"}

    user = await db.get_user(user_id)
    if not user:
        return {"error": "User not found"}

    overrides = user.get("llm_provider_overrides") or {}
    # Encrypt the API key before storing
    overrides[request.provider] = encrypt(request.api_key)
    await db.update_user_byok(user_id, overrides)
    return {"ok": True, "provider": request.provider, "configured": True}


@router.delete("/users/{user_id}/byok/{provider}")
async def delete_byok_key(user_id: str, provider: str, request: Request) -> dict:
    """Remove a user's BYOK API key for a specific provider."""
    auth_user_id, auth_role = _get_auth(request)
    if auth_user_id != user_id and not _is_admin(auth_role):
        raise HTTPException(status_code=403, detail="Cannot modify another user's API keys")

    user = await db.get_user(user_id)
    if not user:
        return {"error": "User not found"}

    overrides = user.get("llm_provider_overrides") or {}
    if provider in overrides:
        del overrides[provider]
    await db.update_user_byok(user_id, overrides)
    return {"ok": True, "provider": provider, "configured": False}


@router.get("/users/{user_id}/byok")
async def get_byok_keys(user_id: str, request: Request) -> dict:
    """Get user's configured BYOK providers (keys masked for security)."""
    auth_user_id, auth_role = _get_auth(request)
    if auth_user_id != user_id and not _is_admin(auth_role):
        raise HTTPException(status_code=403, detail="Cannot access another user's API keys")

    user = await db.get_user(user_id)
    if not user:
        return {"providers": {}}

    overrides = user.get("llm_provider_overrides") or {}
    # Decrypt and mask keys for display: show only first 8 and last 4 chars
    masked = {}
    for provider, encrypted_key in overrides.items():
        key = decrypt(encrypted_key)
        if len(key) > 12:
            masked[provider] = key[:8] + "..." + key[-4:]
        else:
            masked[provider] = "***configured***"
    return {"providers": masked}
