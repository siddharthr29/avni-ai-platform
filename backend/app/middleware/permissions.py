"""Permission middleware and decorators for route-level access control.

Usage:
    @router.post("/bundle/upload")
    @require_permission(Permission.BUNDLE_UPLOAD)
    async def upload_bundle(request: Request, ...):
        ...

Or via middleware (auto-checks based on ROUTE_PERMISSIONS mapping).
"""

import functools
import logging
from dataclasses import dataclass
from typing import Any, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.models.roles import (
    ROLE_PERMISSIONS,
    ROUTE_PERMISSIONS,
    Permission,
    UserRole,
    has_permission,
)

logger = logging.getLogger(__name__)

# Public paths that skip permission checks entirely (matches security.py)
_PUBLIC_PATHS = frozenset({"/health", "/api/health", "/metrics", "/docs", "/openapi.json", "/redoc", "/api/auth/login", "/api/auth/register", "/api/auth/refresh", "/api/admin/bootstrap"})


def _is_public(path: str) -> bool:
    """Return True if the path is public and requires no permission check."""
    return path in _PUBLIC_PATHS or path.startswith("/docs") or path.startswith("/redoc")


# ---------------------------------------------------------------------------
# User context helper
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CurrentUser:
    """Lightweight user context extracted from request state."""
    user_id: str | None
    role: UserRole
    org_id: str | None

    @property
    def permissions(self) -> set[Permission]:
        """Return the full set of permissions for this user's role."""
        return ROLE_PERMISSIONS.get(self.role, set())


def get_current_user(request: Request) -> CurrentUser:
    """Extract the current user context from request.state.

    SecurityMiddleware (or an upstream auth layer) is expected to populate:
        request.state.user_id   — the authenticated user id (str or None)
        request.state.user_role — a UserRole enum value or its string name
        request.state.org_id    — the organisation id (str or None)

    If *user_role* is missing or unrecognisable the function falls back to
    ``platform_admin`` **only when no API keys are configured** (dev mode).
    Otherwise it defaults to the most restricted role (``ngo_user``).
    """
    user_id: str | None = getattr(request.state, "user_id", None)
    org_id: str | None = getattr(request.state, "org_id", None)
    raw_role: Any = getattr(request.state, "user_role", None)

    role = _resolve_role(raw_role, _is_dev_mode(request))
    return CurrentUser(user_id=user_id, role=role, org_id=org_id)


def _resolve_role(raw_role: Any, dev_mode: bool) -> UserRole:
    """Normalise a raw role value into a UserRole enum member."""
    if isinstance(raw_role, UserRole):
        return raw_role

    if isinstance(raw_role, str):
        try:
            return UserRole(raw_role)
        except ValueError:
            pass

    # No valid role found — use dev fallback or least-privilege default
    return UserRole.PLATFORM_ADMIN if dev_mode else UserRole.NGO_USER


def _is_dev_mode(request: Request) -> bool:
    """Return True when DEV_MODE=true or no API keys are configured.

    When no API_KEYS are set, the SecurityMiddleware already grants
    platform_admin role. This must match so the PermissionMiddleware
    resolves the same role instead of falling back to ngo_user.
    """
    import os
    if os.getenv("DEV_MODE", "").lower() == "true":
        return True
    try:
        from app.config import settings
        api_keys = getattr(settings, "API_KEYS", "")
        return not bool(api_keys and api_keys.strip())
    except Exception:
        return False


# ---------------------------------------------------------------------------
# JSON 403 response builder
# ---------------------------------------------------------------------------

def _forbidden_response(
    permission: Permission,
    request_id: str,
    path: str,
) -> JSONResponse:
    """Build a consistent 403 JSON response."""
    return JSONResponse(
        status_code=403,
        content={
            "detail": "Forbidden",
            "permission_required": permission.value,
            "path": path,
            "request_id": request_id,
        },
    )


# ---------------------------------------------------------------------------
# Decorator: @require_permission(Permission.X)
# ---------------------------------------------------------------------------

def require_permission(permission: Permission) -> Callable:
    """Decorator that enforces a specific permission on a route handler.

    The decorated handler **must** accept a ``request: Request`` parameter
    (which FastAPI route handlers normally do).

    Example::

        @router.post("/bundle/upload")
        @require_permission(Permission.BUNDLE_UPLOAD)
        async def upload_bundle(request: Request):
            ...
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Locate the Request object in args/kwargs
            request: Request | None = kwargs.get("request")
            if request is None:
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break

            if request is None:
                logger.error(
                    "require_permission decorator could not find Request object "
                    "in handler '%s'. Denying access.",
                    func.__name__,
                )
                return JSONResponse(
                    status_code=500,
                    content={"detail": "Internal server error: missing request context"},
                )

            request_id: str = getattr(request.state, "request_id", "unknown")
            user = get_current_user(request)

            if not has_permission(user.role, permission):
                logger.warning(
                    "permission_denied",
                    extra={
                        "request_id": request_id,
                        "user_id": user.user_id,
                        "role": user.role.value,
                        "permission_required": permission.value,
                        "path": str(request.url.path),
                    },
                )
                return _forbidden_response(permission, request_id, request.url.path)

            return await func(*args, **kwargs)

        return wrapper

    return decorator


# ---------------------------------------------------------------------------
# Middleware: automatic route prefix -> permission check
# ---------------------------------------------------------------------------

class PermissionMiddleware(BaseHTTPMiddleware):
    """Starlette middleware that auto-checks permissions using ROUTE_PERMISSIONS.

    For every non-public request the middleware:
    1. Finds the longest matching route prefix in ``ROUTE_PERMISSIONS``.
    2. Resolves the user role from ``request.state.user_role`` (set by
       SecurityMiddleware or an auth layer upstream).
    3. Returns 403 if the role lacks the required permission.

    Routes with no matching prefix in ROUTE_PERMISSIONS are allowed through
    (they can still use the ``@require_permission`` decorator for fine-grained
    control).
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path

        # Skip public paths and pre-flight requests
        if request.method == "OPTIONS" or _is_public(path):
            return await call_next(request)

        # Find the required permission for this route (longest prefix match)
        required = self._match_permission(path)
        if required is None:
            # No permission mapping — allow through (decorator may still guard)
            return await call_next(request)

        request_id: str = getattr(request.state, "request_id", "unknown")
        user = get_current_user(request)

        if not has_permission(user.role, required):
            logger.warning(
                "permission_denied_middleware",
                extra={
                    "request_id": request_id,
                    "user_id": user.user_id,
                    "role": user.role.value,
                    "permission_required": required.value,
                    "path": path,
                },
            )
            return _forbidden_response(required, request_id, path)

        return await call_next(request)

    @staticmethod
    def _match_permission(path: str) -> Permission | None:
        """Return the permission for the longest matching route prefix, or None."""
        best_match: str | None = None
        best_permission: Permission | None = None

        for prefix, permission in ROUTE_PERMISSIONS.items():
            if path.startswith(prefix):
                if best_match is None or len(prefix) > len(best_match):
                    best_match = prefix
                    best_permission = permission

        return best_permission
