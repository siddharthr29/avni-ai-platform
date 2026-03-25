"""BYOK key validation endpoint — test a user's API key before using it."""

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/byok", tags=["BYOK"])


class BYOKValidateRequest(BaseModel):
    provider: str = Field(description="Provider name: groq, openai, anthropic, gemini, cerebras")
    api_key: str = Field(min_length=5, description="API key to validate")


class BYOKValidateResponse(BaseModel):
    valid: bool
    provider: str
    model: str | None = None
    error: str | None = None


# Provider base URLs for validation
_PROVIDER_URLS = {
    "groq": "https://api.groq.com/openai/v1",
    "openai": "https://api.openai.com/v1",
    "cerebras": "https://api.cerebras.ai/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
}

_PROVIDER_MODELS = {
    "groq": "llama-3.3-70b-versatile",
    "openai": "gpt-4o-mini",
    "cerebras": "llama-3.3-70b",
    "gemini": "gemini-2.0-flash",
}


@router.post("/validate", response_model=BYOKValidateResponse)
async def validate_byok_key(body: BYOKValidateRequest):
    """Test a BYOK API key by making a minimal API call.

    Sends a tiny completion request (1 token) to verify the key works.
    """
    provider = body.provider.lower()

    if provider == "anthropic":
        return await _validate_anthropic(body.api_key)

    if provider not in _PROVIDER_URLS:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")

    return await _validate_openai_compatible(provider, body.api_key)


async def _validate_openai_compatible(provider: str, api_key: str) -> BYOKValidateResponse:
    """Validate an OpenAI-compatible API key."""
    import httpx
    base_url = _PROVIDER_URLS[provider]
    model = _PROVIDER_MODELS[provider]

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": "hi"}],
                    "max_tokens": 1,
                },
            )

            if resp.status_code == 200:
                return BYOKValidateResponse(valid=True, provider=provider, model=model)
            elif resp.status_code in (401, 403):
                return BYOKValidateResponse(
                    valid=False, provider=provider,
                    error="Invalid API key — authentication failed",
                )
            elif resp.status_code == 429:
                # Rate limited but key is valid
                return BYOKValidateResponse(valid=True, provider=provider, model=model)
            else:
                error_text = resp.text[:200]
                return BYOKValidateResponse(
                    valid=False, provider=provider,
                    error=f"API error ({resp.status_code}): {error_text}",
                )
    except httpx.TimeoutException:
        return BYOKValidateResponse(
            valid=False, provider=provider,
            error=f"Timeout connecting to {provider} API",
        )
    except Exception as e:
        return BYOKValidateResponse(
            valid=False, provider=provider,
            error=str(e),
        )


async def _validate_anthropic(api_key: str) -> BYOKValidateResponse:
    """Validate an Anthropic API key."""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 1,
                    "messages": [{"role": "user", "content": "hi"}],
                },
            )

            if resp.status_code == 200:
                return BYOKValidateResponse(valid=True, provider="anthropic", model="claude-haiku-4-5-20251001")
            elif resp.status_code in (401, 403):
                return BYOKValidateResponse(
                    valid=False, provider="anthropic",
                    error="Invalid API key — authentication failed",
                )
            elif resp.status_code == 429:
                return BYOKValidateResponse(valid=True, provider="anthropic", model="claude-haiku-4-5-20251001")
            else:
                return BYOKValidateResponse(
                    valid=False, provider="anthropic",
                    error=f"API error ({resp.status_code}): {resp.text[:200]}",
                )
    except Exception as e:
        return BYOKValidateResponse(valid=False, provider="anthropic", error=str(e))
