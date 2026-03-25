"""JWT authentication endpoints: register, login, refresh, me, logout."""

import hashlib
import logging
import time
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

from app import db
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# ── Login Rate Limiting ──────────────────────────────────────────────────────
# In-memory rate limiter: tracks login attempts per email
# Key: email (lowercase), Value: list of attempt timestamps
_login_attempts: dict[str, list[float]] = defaultdict(list)
_LOGIN_RATE_LIMIT = 5  # max attempts
_LOGIN_RATE_WINDOW = 60  # per 60 seconds


def _check_login_rate_limit(email: str) -> None:
    """Check if login attempts for this email exceed the rate limit.
    Raises HTTPException(429) if exceeded. Cleans up expired entries."""
    key = email.lower()
    now = time.time()
    cutoff = now - _LOGIN_RATE_WINDOW

    # Remove expired attempts
    _login_attempts[key] = [t for t in _login_attempts[key] if t > cutoff]

    if len(_login_attempts[key]) >= _LOGIN_RATE_LIMIT:
        logger.warning("Login rate limit exceeded for email: %s", key)
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts. Please try again in a minute.",
        )

    # Record this attempt
    _login_attempts[key].append(now)


def _cleanup_login_attempts() -> None:
    """Periodic cleanup of stale rate limit entries (called lazily)."""
    now = time.time()
    cutoff = now - _LOGIN_RATE_WINDOW
    stale_keys = [k for k, v in _login_attempts.items() if all(t <= cutoff for t in v)]
    for k in stale_keys:
        del _login_attempts[k]


# ── Request / Response Models ─────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=200)
    org_name: str = Field(min_length=1, max_length=200)
    sector: str = ""
    org_context: str = ""


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(min_length=8, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: dict
    force_password_change: bool = False
    pending_approval: bool = False


class RefreshRequest(BaseModel):
    refresh_token: str


# ── Password Hashing ─────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


# ── Password Strength Validation ────────────────────────────────────────────

def validate_password(password: str) -> list[str]:
    """Validate password strength. Returns a list of error messages (empty = valid)."""
    errors = []
    if len(password) < 8:
        errors.append("Password must be at least 8 characters")
    if not any(c.isupper() for c in password):
        errors.append("Password must contain at least one uppercase letter")
    if not any(c.islower() for c in password):
        errors.append("Password must contain at least one lowercase letter")
    if not any(c.isdigit() for c in password):
        errors.append("Password must contain at least one digit")
    return errors


# ── Token Hashing ───────────────────────────────────────────────────────────

def _hash_token(token: str) -> str:
    """SHA-256 hash of a refresh token for secure storage."""
    return hashlib.sha256(token.encode()).hexdigest()


# ── JWT Token Generation ─────────────────────────────────────────────────────

def create_access_token(user_id: str, email: str, role: str, org_id: str = "") -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "org_id": org_id,
        "type": "access",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "type": "refresh",
        "exp": datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and validate a JWT token. Raises HTTPException on failure."""
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


# ── DB Helpers ────────────────────────────────────────────────────────────────

async def get_user_by_email(email: str) -> dict | None:
    """Fetch a user by email address."""
    if not db._pool:
        return None
    async with db._pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT id, name, org_name, org_id, sector, org_context, email, password_hash,
                      role, is_active, pending_approval, force_password_change, created_at
               FROM users WHERE email = $1""",
            email,
        )
        return dict(row) if row else None


async def create_user_with_auth(
    user_id: str, email: str, password_hash: str,
    name: str, org_name: str, sector: str, org_context: str,
    role: str = "ngo_user", pending_approval: bool = False,
) -> dict:
    """Create a user with email and password hash. Derives org_id from org_name."""
    org_id = db._slugify_org(org_name)
    if not db._pool:
        return {"id": user_id, "name": name, "email": email, "org_name": org_name, "org_id": org_id, "role": role}
    async with db._pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO users (id, name, org_name, org_id, sector, org_context, email, password_hash,
                               role, pending_approval)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            RETURNING id, name, org_name, org_id, sector, org_context, email, role,
                      pending_approval, force_password_change, created_at
            """,
            user_id, name, org_name, org_id, sector, org_context, email, password_hash,
            role, pending_approval,
        )
        return dict(row)


def _safe_user(user: dict) -> dict:
    """Strip sensitive fields from user dict for API response."""
    return {k: v for k, v in user.items() if k not in ("password_hash",)}


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/register", response_model=TokenResponse)
async def register(request: RegisterRequest):
    """Register a new user with email and password."""
    # Password strength validation
    pw_errors = validate_password(request.password)
    if pw_errors:
        raise HTTPException(status_code=422, detail="; ".join(pw_errors))

    # Check if email already exists
    existing = await get_user_by_email(request.email)
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    user_id = str(uuid.uuid4())
    pw_hash = hash_password(request.password)

    # First user in the system becomes platform_admin (bootstrap)
    total_users = await db.count_all_users()
    if total_users == 0:
        role = "platform_admin"
        pending_approval = False
        logger.info("First user registration — assigning platform_admin role to %s", request.email)
    else:
        role = "ngo_user"  # Self-registration defaults to ngo_user
        pending_approval = True  # Requires admin approval

    user = await create_user_with_auth(
        user_id=user_id,
        email=request.email,
        password_hash=pw_hash,
        name=request.name,
        org_name=request.org_name,
        sector=request.sector,
        org_context=request.org_context,
        role=role,
        pending_approval=pending_approval,
    )

    access_token = create_access_token(user_id, request.email, role, user.get("org_id", ""))
    refresh_tok = create_refresh_token(user_id)

    # Store hashed refresh token for rotation
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    await db.store_refresh_token(_hash_token(refresh_tok), user_id, expires_at)

    logger.info("User registered: %s (%s) role=%s pending=%s", request.email, user_id, role, pending_approval)
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_tok,
        user=_safe_user(user),
        pending_approval=pending_approval,
    )


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest):
    """Login with email and password, returns JWT tokens."""
    # Rate limit check (before any DB lookup to prevent enumeration timing)
    _check_login_rate_limit(request.email)
    # Lazy cleanup of stale entries (~every request, cheap operation)
    _cleanup_login_attempts()

    user = await get_user_by_email(request.email)
    if not user or not user.get("password_hash"):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not verify_password(request.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Check if account is pending approval
    if user.get("pending_approval"):
        raise HTTPException(
            status_code=403,
            detail="Your account is pending approval. Please contact an administrator.",
        )

    # Check if account is deactivated
    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="Your account has been deactivated.")

    role = user.get("role", "ngo_user")
    org_id = user.get("org_id", "")
    access_token = create_access_token(user["id"], request.email, role, org_id)
    refresh_tok = create_refresh_token(user["id"])

    # Store hashed refresh token for rotation
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    await db.store_refresh_token(_hash_token(refresh_tok), user["id"], expires_at)

    # Update last_login
    if db._pool:
        async with db._pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET last_login = now() WHERE id = $1", user["id"]
            )

    force_pw = user.get("force_password_change", False)
    logger.info("User logged in: %s (force_pw=%s)", request.email, force_pw)
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_tok,
        user=_safe_user(user),
        force_password_change=force_pw,
        pending_approval=False,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token_endpoint(request: RefreshRequest):
    """Refresh an expired access token using a valid refresh token.

    Implements token rotation: the old refresh token is invalidated and a new one is issued.
    If the old token is not found in the DB (already used), all tokens for the user are revoked
    as a security measure (potential token theft).
    """
    payload = decode_token(request.refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type")

    user_id = payload["sub"]

    # Verify the refresh token exists in DB (token rotation check)
    old_hash = _hash_token(request.refresh_token)
    stored = await db.verify_refresh_token(old_hash)
    if not stored:
        # Token reuse detected — revoke ALL tokens for this user as a precaution
        logger.warning("Refresh token reuse detected for user %s — revoking all tokens", user_id)
        await db.revoke_all_user_tokens(user_id)
        raise HTTPException(status_code=401, detail="Invalid refresh token (revoked)")

    # Revoke the old refresh token
    await db.revoke_refresh_token(old_hash)

    user = await db.get_user(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    role = user.get("role", "implementor")
    email = user.get("email", "")
    org_id = user.get("org_id", "")
    access_token = create_access_token(user_id, email, role, org_id)
    new_refresh = create_refresh_token(user_id)

    # Store the new refresh token
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    await db.store_refresh_token(_hash_token(new_refresh), user_id, expires_at)

    # Lazily cleanup expired tokens (~1% of requests)
    if time.time() % 100 < 1:
        await db.cleanup_expired_tokens()

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh,
        user=_safe_user(user),
    )


@router.get("/me")
async def get_current_user(request: Request):
    """Get the current authenticated user from JWT token."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization header")

    token = auth_header[7:]
    payload = decode_token(token)
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")

    user = await db.get_user(payload["sub"])
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return {"user": _safe_user(user)}


@router.post("/logout")
async def logout(request: Request):
    """Logout: revoke all refresh tokens for the authenticated user."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization header")

    token = auth_header[7:]
    try:
        payload = decode_token(token)
    except HTTPException:
        # Even if the access token is expired, try to extract user_id for logout
        try:
            payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM], options={"verify_exp": False})
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="Invalid token")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    await db.revoke_all_user_tokens(user_id)
    logger.info("User logged out (all refresh tokens revoked): %s", user_id)
    return {"message": "Logged out"}


@router.post("/change-password")
async def change_password(request: Request):
    """Change password. Required on first login for invited users."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization header")

    token = auth_header[7:]
    payload = decode_token(token)
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")

    user_id = payload["sub"]
    user = await db.get_user(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    # Parse body
    body = await request.json()
    old_password = body.get("old_password", "")
    new_password = body.get("new_password", "")

    if not old_password or not new_password:
        raise HTTPException(status_code=422, detail="old_password and new_password are required")

    # Verify old password
    if not user.get("password_hash") or not verify_password(old_password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Current password is incorrect")

    # Validate new password strength
    pw_errors = validate_password(new_password)
    if pw_errors:
        raise HTTPException(status_code=422, detail="; ".join(pw_errors))

    if old_password == new_password:
        raise HTTPException(status_code=422, detail="New password must be different from current password")

    # Update password and clear force_password_change flag
    new_hash = hash_password(new_password)
    await db.update_user_password(user_id, new_hash)

    # Revoke all existing refresh tokens (force re-login with new password)
    await db.revoke_all_user_tokens(user_id)

    # Issue fresh tokens
    role = user.get("role", "ngo_user")
    org_id = user.get("org_id", "")
    access_token = create_access_token(user_id, user["email"], role, org_id)
    refresh_tok = create_refresh_token(user_id)

    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    await db.store_refresh_token(_hash_token(refresh_tok), user_id, expires_at)

    logger.info("Password changed for user: %s", user["email"])
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_tok,
        user=_safe_user(user),
        force_password_change=False,
    )
