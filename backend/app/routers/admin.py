"""Super Admin user management endpoints.

Provides CRUD operations on users, role/status management, invite flow,
platform stats, and a one-time bootstrap endpoint for the first admin.
"""

import logging
import secrets
import uuid

import bcrypt
from fastapi import APIRouter, HTTPException, Request

from app import db
from app.middleware.permissions import get_current_user
from app.models.roles import UserRole
from app.models.schemas import (
    AdminBootstrapRequest,
    AdminStatsResponse,
    AdminUserCreateRequest,
    AdminUserInviteRequest,
    AdminUserRoleUpdateRequest,
    AdminUserStatusUpdateRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin"])

VALID_ROLES = {r.value for r in UserRole}


# ── Helpers ──────────────────────────────────────────────────────────────────

def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _require_admin(request: Request) -> tuple[str, str, str | None]:
    """Return (user_id, role, org_name) or raise 403.

    Only platform_admin and org_admin are allowed to call admin endpoints.
    """
    user = get_current_user(request)
    role = user.role.value
    if role not in ("platform_admin", "org_admin"):
        raise HTTPException(status_code=403, detail="Forbidden: admin role required")
    # Fetch org_name from request state if available (set by middleware/auth)
    org_name: str | None = getattr(request.state, "org_name", None)
    return user.user_id, role, org_name


async def _get_caller_org(user_id: str) -> str | None:
    """Fetch the org_name of the calling user from DB."""
    caller = await db.get_user(user_id)
    return caller.get("org_name") if caller else None


def _can_manage_role(caller_role: str, target_role: str) -> bool:
    """Check if caller_role is allowed to assign target_role."""
    if caller_role == "platform_admin":
        return target_role in VALID_ROLES
    if caller_role == "org_admin":
        return target_role in ("ngo_user", "implementor")
    return False


# ── 1. GET /api/admin/users — List all users ────────────────────────────────

@router.get("/users")
async def list_users(
    request: Request,
    role: str | None = None,
    org_name: str | None = None,
    is_active: bool | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """List all users with optional filters. org_admin sees only their org."""
    caller_id, caller_role, _ = _require_admin(request)

    # org_admin can only see users in their own org
    if caller_role == "org_admin":
        caller_org = await _get_caller_org(caller_id)
        org_name = caller_org  # force filter to own org

    if role and role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role filter: {role}")

    users = await db.list_users(
        role=role, org_name=org_name, is_active=is_active,
        search=search, limit=min(limit, 200), offset=offset,
    )
    return {"users": users, "count": len(users)}


# ── 2. POST /api/admin/users — Create a new user ────────────────────────────

@router.post("/users")
async def create_user(request: Request, body: AdminUserCreateRequest) -> dict:
    """Create a new user. platform_admin can create any role; org_admin can create ngo_user/implementor."""
    caller_id, caller_role, _ = _require_admin(request)

    if body.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role: {body.role}. Valid: {VALID_ROLES}")

    if not _can_manage_role(caller_role, body.role):
        raise HTTPException(
            status_code=403,
            detail=f"org_admin can only create ngo_user or implementor roles",
        )

    # org_admin can only create users in their own org
    if caller_role == "org_admin":
        caller_org = await _get_caller_org(caller_id)
        if caller_org and body.org_name != caller_org:
            raise HTTPException(status_code=403, detail="org_admin can only create users in their own org")

    # Check email uniqueness
    from app.routers.auth import get_user_by_email
    existing = await get_user_by_email(body.email)
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    user_id = str(uuid.uuid4())
    pw_hash = _hash_password(body.password)

    user = await db.create_user_admin(
        user_id=user_id,
        name=body.name,
        email=body.email,
        password_hash=pw_hash,
        org_name=body.org_name,
        sector=body.sector,
        role=body.role,
        org_context=body.org_context,
    )

    logger.info("Admin %s created user %s (%s) with role %s", caller_id, user_id, body.email, body.role)
    return {"user": user}


# ── 3. PATCH /api/admin/users/{user_id}/role — Change role ──────────────────

@router.patch("/users/{user_id}/role")
async def update_user_role(request: Request, user_id: str, body: AdminUserRoleUpdateRequest) -> dict:
    """Change a user's role with validation."""
    caller_id, caller_role, _ = _require_admin(request)

    if body.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role: {body.role}. Valid: {VALID_ROLES}")

    if not _can_manage_role(caller_role, body.role):
        raise HTTPException(status_code=403, detail="org_admin can only assign ngo_user or implementor roles")

    target = await db.get_user(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    # org_admin can only change roles within their org
    if caller_role == "org_admin":
        caller_org = await _get_caller_org(caller_id)
        if target.get("org_name") != caller_org:
            raise HTTPException(status_code=403, detail="Cannot change role of user outside your org")

    # Prevent demoting self if last platform_admin
    if caller_id == user_id and target.get("role") == "platform_admin" and body.role != "platform_admin":
        admin_count = await db.count_users_by_role("platform_admin")
        if admin_count <= 1:
            raise HTTPException(status_code=400, detail="Cannot demote the last platform_admin")

    ok = await db.update_user_role(user_id, body.role)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to update role")

    logger.info("Admin %s changed user %s role to %s", caller_id, user_id, body.role)
    return {"ok": True, "user_id": user_id, "role": body.role}


# ── 4. PATCH /api/admin/users/{user_id}/status — Activate/deactivate ────────

@router.patch("/users/{user_id}/status")
async def update_user_status(request: Request, user_id: str, body: AdminUserStatusUpdateRequest) -> dict:
    """Activate or deactivate a user."""
    caller_id, caller_role, _ = _require_admin(request)

    if caller_id == user_id and not body.is_active:
        raise HTTPException(status_code=400, detail="Cannot deactivate yourself")

    target = await db.get_user(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    # org_admin can only manage users in their org
    if caller_role == "org_admin":
        caller_org = await _get_caller_org(caller_id)
        if target.get("org_name") != caller_org:
            raise HTTPException(status_code=403, detail="Cannot change status of user outside your org")

    # Cannot deactivate last platform_admin
    if not body.is_active and target.get("role") == "platform_admin":
        admin_count = await db.count_users_by_role("platform_admin")
        if admin_count <= 1:
            raise HTTPException(status_code=400, detail="Cannot deactivate the last platform_admin")

    ok = await db.update_user_status(user_id, body.is_active)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to update status")

    logger.info("Admin %s set user %s is_active=%s", caller_id, user_id, body.is_active)
    return {"ok": True, "user_id": user_id, "is_active": body.is_active}


# ── 5. POST /api/admin/users/invite — Invite user ───────────────────────────

@router.post("/users/invite")
async def invite_user(request: Request, body: AdminUserInviteRequest) -> dict:
    """Invite a user by creating an account with a temporary password.

    Returns the temp password so the admin can share it manually.
    """
    caller_id, caller_role, _ = _require_admin(request)

    if body.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role: {body.role}. Valid: {VALID_ROLES}")

    if not _can_manage_role(caller_role, body.role):
        raise HTTPException(status_code=403, detail="org_admin can only invite ngo_user or implementor roles")

    # org_admin can only invite to their org
    if caller_role == "org_admin":
        caller_org = await _get_caller_org(caller_id)
        if caller_org and body.org_name != caller_org:
            raise HTTPException(status_code=403, detail="org_admin can only invite users to their own org")

    # Check email uniqueness
    from app.routers.auth import get_user_by_email
    existing = await get_user_by_email(body.email)
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    temp_password = secrets.token_urlsafe(12)  # 16-char random password
    user_id = str(uuid.uuid4())
    pw_hash = _hash_password(temp_password)

    user = await db.create_user_admin(
        user_id=user_id,
        name=body.name,
        email=body.email,
        password_hash=pw_hash,
        org_name=body.org_name,
        sector="",
        role=body.role,
        org_context="",
        force_password_change=True,
    )

    logger.info("Admin %s invited user %s (%s) with role %s", caller_id, user_id, body.email, body.role)
    return {"user": user, "temp_password": temp_password}


# ── 6. GET /api/admin/users/{user_id} — Get full user details ───────────────

@router.get("/users/{user_id}")
async def get_user_details(request: Request, user_id: str) -> dict:
    """Get full user details including session count and last activity."""
    caller_id, caller_role, _ = _require_admin(request)

    user = await db.get_user_details(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # org_admin can only view users in their org
    if caller_role == "org_admin":
        caller_org = await _get_caller_org(caller_id)
        if user.get("org_name") != caller_org:
            raise HTTPException(status_code=403, detail="Cannot view user outside your org")

    return {"user": user}


# ── 7. DELETE /api/admin/users/{user_id} — Soft delete ──────────────────────

@router.delete("/users/{user_id}")
async def delete_user(request: Request, user_id: str) -> dict:
    """Soft delete (deactivate) a user. platform_admin only."""
    caller_id, caller_role, _ = _require_admin(request)

    if caller_role != "platform_admin":
        raise HTTPException(status_code=403, detail="Only platform_admin can delete users")

    if caller_id == user_id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")

    target = await db.get_user(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    # Cannot delete last platform_admin
    if target.get("role") == "platform_admin":
        admin_count = await db.count_users_by_role("platform_admin")
        if admin_count <= 1:
            raise HTTPException(status_code=400, detail="Cannot delete the last platform_admin")

    ok = await db.update_user_status(user_id, False)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to deactivate user")

    logger.info("Admin %s soft-deleted user %s", caller_id, user_id)
    return {"ok": True, "user_id": user_id, "is_active": False}


# ── 8. GET /api/admin/stats — Platform overview ─────────────────────────────

@router.get("/stats")
async def get_platform_stats(request: Request) -> dict:
    """Platform overview stats. platform_admin only."""
    caller_id, caller_role, _ = _require_admin(request)

    if caller_role != "platform_admin":
        raise HTTPException(status_code=403, detail="Only platform_admin can view platform stats")

    stats = await db.get_platform_stats()
    return stats


# ── 9. POST /api/admin/bootstrap — First-user bootstrap ─────────────────────

@router.post("/bootstrap")
async def bootstrap_admin(body: AdminBootstrapRequest) -> dict:
    """Create the first platform_admin user. Only works when no admin exists.

    No authentication required — this is a one-time bootstrap endpoint.
    After the first admin is created, this endpoint returns 403.
    """
    if await db.has_platform_admin():
        raise HTTPException(
            status_code=403,
            detail="Bootstrap disabled: a platform_admin already exists. Use normal admin endpoints.",
        )

    # Check email uniqueness
    from app.routers.auth import get_user_by_email
    existing = await get_user_by_email(body.email)
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    user_id = str(uuid.uuid4())
    pw_hash = _hash_password(body.password)

    user = await db.create_user_admin(
        user_id=user_id,
        name=body.name,
        email=body.email,
        password_hash=pw_hash,
        org_name=body.org_name,
        sector=body.sector,
        role="platform_admin",
        org_context=body.org_context,
    )

    # Generate tokens so the admin can immediately start using the platform
    from app.routers.auth import create_access_token, create_refresh_token
    access_token = create_access_token(user_id, body.email, "platform_admin")
    refresh_token = create_refresh_token(user_id)

    logger.info("Bootstrap: created first platform_admin %s (%s)", user_id, body.email)
    return {
        "user": user,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "message": "First platform admin created successfully. Bootstrap endpoint is now disabled.",
    }
