"""Security middleware: API key auth, rate limiting, input guardrails, correlation IDs."""

import logging
import re
import time
import uuid
from typing import Callable

from fastapi import HTTPException, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings

logger = logging.getLogger(__name__)

# ── Input Guard: PII + Prompt Injection Detection ──────────────────────────

PII_PATTERNS = {
    "email": r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z]{2,}",
    "phone_in": r"\b(\+91[\-\s]?)?[6-9]\d{9}\b",
    "api_key": r"(sk-|ghp_|xox[baprs]-|AIza)[a-zA-Z0-9\-_]{20,}",
    "aadhaar": r"\b[2-9]{1}\d{3}\s?\d{4}\s?\d{4}\b",
    "credit_card": r"\b(?:\d[ -]?){13,16}\b",
}

PROMPT_INJECTION_PATTERNS = re.compile(
    r"(?i)("
    r"ignore\s+(previous|all|above|prior|system)\s+(instructions?|prompts?|rules?)|"
    r"you\s+are\s+now\s+|"
    r"forget\s+(your|all|previous)\s+instructions?|"
    r"jailbreak|DAN\s+mode|"
    r"act\s+as\s+if\s+you\s+have\s+no\s+restrictions|"
    r"pretend\s+you\s+are\s+|"
    r"disregard\s+(your|all|previous)|"
    r"what\s+is\s+your\s+system\s+prompt|"
    r"reveal\s+(your|the)\s+(system|internal)\s+(prompt|instructions?)|"
    r"output\s+your\s+(initial|system)\s+(prompt|instructions?)"
    r")"
)

def check_input_safety(text: str) -> dict:
    """Check for PII and prompt injection. Returns {is_safe, triggered_rules}."""
    triggered = []
    for name, pattern in PII_PATTERNS.items():
        if re.search(pattern, text):
            triggered.append(name)
    if PROMPT_INJECTION_PATTERNS.search(text):
        triggered.append("prompt_injection")
    return {
        "is_safe": len(triggered) == 0,
        "triggered_rules": triggered,
    }

def sanitize_output(text: str) -> str:
    """Redact PII from LLM output."""
    sanitized = text
    for name, pattern in PII_PATTERNS.items():
        sanitized = re.sub(pattern, f"[{name.upper()}_REDACTED]", sanitized)
    return sanitized

# ── Request Size Limits ────────────────────────────────────────────────────

MAX_MESSAGE_LENGTH = 10_000  # characters
MAX_BODY_SIZE = 50 * 1024 * 1024  # 50 MB


def _add_security_headers(response: Response) -> None:
    """Add security response headers (OWASP best practices)."""
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if not settings.AVNI_DEV_MODE:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; "
            "connect-src 'self' ws: wss:; "
            "font-src 'self'; "
            "frame-ancestors 'none'"
        )

# ── Auth: API Key Verification ─────────────────────────────────────────────

# Public endpoints that don't require auth
PUBLIC_PATHS = {"/health", "/api/health", "/metrics", "/docs", "/openapi.json", "/redoc", "/api/auth/login", "/api/auth/register", "/api/auth/refresh", "/api/admin/bootstrap", "/api/byok/validate"}

def _is_public(path: str) -> bool:
    return path in PUBLIC_PATHS or path.startswith("/docs") or path.startswith("/redoc")

# ── Security Middleware ────────────────────────────────────────────────────

class SecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Add correlation ID
        request_id = str(uuid.uuid4())[:8]
        request.state.request_id = request_id

        path = request.url.path

        # Skip auth for public endpoints and OPTIONS
        if request.method == "OPTIONS" or _is_public(path):
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            _add_security_headers(response)
            return response

        # Auth — return JSONResponse directly instead of raising HTTPException
        # (BaseHTTPMiddleware converts HTTPException to 500)
        from starlette.responses import JSONResponse

        # JWT Bearer token auth
        auth_header = request.headers.get("Authorization", "")
        bearer_token_provided = auth_header.startswith("Bearer ")
        if bearer_token_provided:
            token = auth_header[7:]
            try:
                import jwt as pyjwt
                payload = pyjwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
                if payload.get("type") == "access":
                    request.state.user_id = payload.get("sub")
                    request.state.user_role = payload.get("role", "implementor")
                    request.state.org_id = payload.get("org_id")
                else:
                    return JSONResponse(
                        status_code=401,
                        content={"detail": "Invalid token type — access token required"},
                        headers={"X-Request-ID": request_id},
                    )
            except Exception as e:
                logger.warning("JWT decode failed: %s", e)
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid or expired Bearer token"},
                    headers={"X-Request-ID": request_id},
                )

        # API Key auth (only if no Bearer token was provided)
        if not bearer_token_provided:
            api_keys = getattr(settings, "API_KEYS", "")
            if api_keys:
                valid_keys = {k.strip() for k in api_keys.split(",") if k.strip()}
                provided_key = request.headers.get("X-API-Key", "")
                if provided_key in valid_keys:
                    request.state.user_role = "platform_admin"
                    request.state.user_id = "api_key_user"
                else:
                    return JSONResponse(
                        status_code=401,
                        content={"detail": "Invalid or missing API key"},
                        headers={"X-Request-ID": request_id},
                    )
            elif settings.AVNI_DEV_MODE:
                request.state.user_role = "platform_admin"
                request.state.user_id = "dev_user"
            else:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Authentication required"},
                    headers={"X-Request-ID": request_id},
                )

        # Prompt injection detection on chat/message endpoints (Donald Lobo: responsible AI)
        if request.method == "POST" and any(
            path.startswith(p) for p in ("/api/chat", "/api/srs/")
        ):
            try:
                body = await request.body()
                text = body.decode("utf-8", errors="ignore")
                safety = check_input_safety(text)
                if not safety["is_safe"]:
                    triggered = safety["triggered_rules"]
                    if "prompt_injection" in triggered:
                        logger.warning(
                            "Prompt injection detected",
                            extra={"request_id": request_id, "path": path},
                        )
                        from starlette.responses import JSONResponse
                        return JSONResponse(
                            status_code=400,
                            content={"detail": "Request blocked: potentially unsafe input detected."},
                            headers={"X-Request-ID": request_id},
                        )
                    # PII detected — log warning but allow through (data may be field worker input)
                    if any(r != "prompt_injection" for r in triggered):
                        logger.info(
                            "PII patterns detected in input: %s",
                            [r for r in triggered if r != "prompt_injection"],
                            extra={"request_id": request_id},
                        )
            except Exception as e:
                logger.debug("Input safety check skipped: %s", e)

        # Log request
        logger.info(
            "request_start",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": path,
            },
        )

        start = time.time()
        response = await call_next(request)
        duration_ms = int((time.time() - start) * 1000)

        response.headers["X-Request-ID"] = request_id
        _add_security_headers(response)
        logger.info(
            "request_end",
            extra={
                "request_id": request_id,
                "status": response.status_code,
                "duration_ms": duration_ms,
            },
        )

        return response
