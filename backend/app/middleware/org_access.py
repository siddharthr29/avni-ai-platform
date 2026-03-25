"""Org-scoped access control helper.

Enforces multi-tenant data isolation:
- platform_admin: full access to everything
- org_admin: full access within own org
- implementor / ngo_user: own data only
"""

import logging

from fastapi import HTTPException, Request

from app import db

logger = logging.getLogger(__name__)


async def check_org_access(
    request: Request,
    target_user_id: str | None = None,
    target_org_id: str | None = None,
) -> bool:
    """Check if the authenticated user has access to the target resource.

    Args:
        request: FastAPI request (must have JWT payload set by auth middleware).
        target_user_id: The user ID being accessed (for user-level checks).
        target_org_id: The org ID being accessed (for org-level checks).

    Returns:
        True if access is granted.

    Raises:
        HTTPException(403) if access is denied.
        HTTPException(401) if user is not authenticated.
    """
    # Extract user info from request state or JWT payload
    user = getattr(request.state, "user", None)
    if not user:
        # Fall back to reading from Authorization header
        from app.routers.auth import decode_token

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing authorization header")
        token = auth_header[7:]
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user = {
            "id": payload.get("sub"),
            "role": payload.get("role", "ngo_user"),
            "org_id": payload.get("org_id", ""),
        }

    role = user.get("role", "ngo_user")
    user_id = user.get("id") or user.get("sub")
    user_org_id = user.get("org_id", "")

    # platform_admin: unrestricted access
    if role == "platform_admin":
        return True

    # org_admin: access within own org
    if role == "org_admin":
        # If checking a specific org, it must match
        if target_org_id and target_org_id != user_org_id:
            logger.warning(
                "org_admin %s (org=%s) denied access to org %s",
                user_id, user_org_id, target_org_id,
            )
            raise HTTPException(
                status_code=403,
                detail="Access denied: you can only manage resources within your own organisation.",
            )
        # If checking a specific user, they must be in the same org
        if target_user_id:
            target_user = await db.get_user(target_user_id)
            if not target_user:
                raise HTTPException(status_code=404, detail="Target user not found")
            if target_user.get("org_id", "") != user_org_id:
                logger.warning(
                    "org_admin %s (org=%s) denied access to user %s (org=%s)",
                    user_id, user_org_id, target_user_id, target_user.get("org_id"),
                )
                raise HTTPException(
                    status_code=403,
                    detail="Access denied: target user is not in your organisation.",
                )
        return True

    # implementor / ngo_user: own data only
    if target_user_id and target_user_id != user_id:
        logger.warning(
            "%s user %s denied access to user %s data",
            role, user_id, target_user_id,
        )
        raise HTTPException(
            status_code=403,
            detail="Access denied: you can only access your own data.",
        )

    if target_org_id and target_org_id != user_org_id:
        logger.warning(
            "%s user %s (org=%s) denied access to org %s",
            role, user_id, user_org_id, target_org_id,
        )
        raise HTTPException(
            status_code=403,
            detail="Access denied: you can only access your own organisation's data.",
        )

    return True


async def require_org_admin_or_above(request: Request) -> dict:
    """Require the user to be org_admin or platform_admin. Returns user info dict.

    Raises HTTPException(403) if the user's role is insufficient.
    """
    from app.routers.auth import decode_token

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization header")

    token = auth_header[7:]
    payload = decode_token(token)
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")

    role = payload.get("role", "ngo_user")
    if role not in ("org_admin", "platform_admin"):
        raise HTTPException(
            status_code=403,
            detail="Access denied: org_admin or platform_admin role required.",
        )

    return {
        "id": payload.get("sub"),
        "email": payload.get("email", ""),
        "role": role,
        "org_id": payload.get("org_id", ""),
    }


async def require_platform_admin(request: Request) -> dict:
    """Require the user to be platform_admin. Returns user info dict.

    Raises HTTPException(403) if the user's role is insufficient.
    """
    from app.routers.auth import decode_token

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization header")

    token = auth_header[7:]
    payload = decode_token(token)
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")

    role = payload.get("role", "ngo_user")
    if role != "platform_admin":
        raise HTTPException(
            status_code=403,
            detail="Access denied: platform_admin role required.",
        )

    return {
        "id": payload.get("sub"),
        "email": payload.get("email", ""),
        "role": role,
        "org_id": payload.get("org_id", ""),
    }
