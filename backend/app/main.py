import asyncio
import importlib
import logging
import os
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import db
from app.config import settings
from app.middleware.metrics import MetricsMiddleware
from app.middleware.rate_limiter import RateLimitMiddleware, rate_limiter
from app.middleware.security import SecurityMiddleware
from app.middleware.permissions import PermissionMiddleware

# Tier 1: Core flow — always imported eagerly
from app.routers import auth, bundle, chat, users

# Tier 2: Common features — imported eagerly
from app.routers import feedback, knowledge, preferences, rules, workflow

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

# --- Sentry Error Tracking ---
if settings.SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.starlette import StarletteIntegration
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
        environment=settings.SENTRY_ENVIRONMENT,
        integrations=[
            StarletteIntegration(transaction_style="endpoint"),
            FastApiIntegration(transaction_style="endpoint"),
        ],
        send_default_pii=False,
    )
    logger.info("Sentry error tracking enabled (env=%s)", settings.SENTRY_ENVIRONMENT)

_startup_time = time.time()

app = FastAPI(
    title="Avni AI Platform",
    description=(
        "AI-powered orchestration layer for the Avni field data collection platform. "
        "Provides chat, bundle generation, voice mapping, image extraction, and "
        "knowledge search capabilities using Claude as the primary LLM."
    ),
    version="1.0.0",
)


# ---------------------------------------------------------------------------
# Middleware stack (FastAPI processes outermost-added first on request)
# Order: CORS -> Security/Auth -> Rate Limiting -> Permissions -> Metrics
# ---------------------------------------------------------------------------

# Metrics middleware — outermost: first to see request, last to see response
app.add_middleware(MetricsMiddleware)

# Permission middleware — checks role-based access after auth
app.add_middleware(PermissionMiddleware)

# Rate limit middleware — runs after auth so user_id is available
app.add_middleware(RateLimitMiddleware)

# Security middleware (auth, correlation IDs)
app.add_middleware(SecurityMiddleware)

# CORS middleware — innermost added = outermost processed (runs first)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Router registration
# ---------------------------------------------------------------------------

def _include_router_lazy(app_instance: FastAPI, module_name: str, **kwargs):
    """Register router with deferred import. Logs warning if module unavailable."""
    try:
        module = importlib.import_module(f"app.routers.{module_name}")
        app_instance.include_router(module.router, **kwargs)
    except ImportError as e:
        logger.warning("Router %s not loaded: %s", module_name, e)


# Tier 1: Core flow
app.include_router(auth.router, prefix="/api", tags=["Auth"])
app.include_router(users.router, prefix="/api", tags=["Users"])
app.include_router(chat.router, prefix="/api", tags=["Chat"])
app.include_router(bundle.router, prefix="/api", tags=["Bundle"])

# Tier 2: Common features
app.include_router(feedback.router, prefix="/api", tags=["Feedback & Review"])
app.include_router(knowledge.router, prefix="/api", tags=["Knowledge"])
app.include_router(rules.router, prefix="/api", tags=["Rules"])
app.include_router(workflow.router, prefix="/api", tags=["Workflow Engine"])
app.include_router(preferences.router, prefix="/api", tags=["User Preferences"])

# Tier 3: Lazy-loaded — rarely used, imported on registration
_tier3_routers = [
    ("admin", "Admin"),
    ("agent", "Agent"),
    ("audit", "Audit & Versioning"),
    ("avni_org", "Avni Organisation"),
    ("bundle_editor", "Bundle Editor (NL)"),
    ("bundle_regenerate", "Bundle Regeneration"),
    ("bundle_validate", "Bundle Validation"),
    ("document_extractor", "Document Extractor"),
    ("documents", "Documents (PageIndex)"),
    ("guardrails_admin", "Guardrails Admin"),
    ("image", "Image"),
    ("mcp", "MCP Integration"),
    ("srs_chat", "SRS Chat"),
    ("support", "Support"),
    ("support_chat", "NGO Support"),
    ("sync", "Avni Sync"),
    ("templates", "Templates"),
    ("usage", "Usage Tracking"),
    ("voice", "Voice"),
    ("admin_tool_calling", "Admin Tool Calling"),
    ("admin_feedback_analytics", "Admin Feedback Analytics"),
    ("byok_validate", "BYOK Validation"),
    ("bundle_review_wizard", "Bundle Review Wizard"),
]

for _module_name, _tag in _tier3_routers:
    _include_router_lazy(app, _module_name, prefix="/api", tags=[_tag])


# ---------------------------------------------------------------------------
# Startup / Shutdown
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup_event() -> None:
    """Application startup: create required directories, init DB, init RAG, log config."""
    start = time.monotonic()

    os.makedirs(settings.BUNDLE_OUTPUT_DIR, exist_ok=True)

    # Initialize rate limiter and cache (Redis if available, else in-memory)
    await rate_limiter.init()
    from app.services.cache import cache
    await cache.init()

    # Validate config and log warnings
    config_warnings = settings.validate()
    for warning in config_warnings:
        if "CRITICAL" in warning:
            logger.critical("CONFIG: %s", warning)
        else:
            logger.warning("CONFIG WARNING: %s", warning)

    logger.info("Avni AI Platform starting up")
    logger.info("  LLM_PROVIDER: %s", settings.LLM_PROVIDER)
    logger.info("  ACTIVE_MODEL: %s", settings.active_model)
    logger.info("  AVNI_BASE_URL: %s", settings.AVNI_BASE_URL)
    logger.info("  BUNDLE_OUTPUT_DIR: %s", settings.BUNDLE_OUTPUT_DIR)
    logger.info(
        "  API_KEY: %s",
        "configured" if settings.api_key_configured else "NOT SET",
    )
    logger.info(
        "  DATABASE_URL: %s",
        "configured" if settings.DATABASE_URL else "NOT SET (in-memory only)",
    )
    logger.info("  MCP_SERVER_URL: %s", settings.MCP_SERVER_URL)
    logger.info("  CORS origins: %s", settings.CORS_ORIGINS)

    # Initialize PostgreSQL (users, sessions, messages)
    await db.init_db()

    # Run V2 schema migrations (preferences, org_memory, audit, tokens, bundles)
    if db.is_connected():
        from app.db_migrations import run_migrations
        applied = await run_migrations(db._pool)
        for desc in applied:
            logger.info("  Migration applied: %s", desc)

    # Parallelized initialization — these are independent of each other
    from app.services.audit import init_audit_schema
    from app.services.bundle_versioning import init_bundle_version_schema
    from app.services.token_budget import init_token_budget_schema
    from app.services.ban_list import load_ban_lists, seed_default_ban_lists

    await asyncio.gather(
        init_audit_schema(),
        init_bundle_version_schema(),
        init_token_budget_schema(),
        seed_default_ban_lists(),
    )

    # Ban list loading depends on seeding being complete
    await load_ban_lists()
    logger.info("  AI guardrails: ban lists loaded, gender bias=%s, ban_list=%s",
                settings.GENDER_BIAS_CHECK_ENABLED, settings.BAN_LIST_ENABLED)

    # Parallelize RAG and PageIndex initialization — both are independent
    from app.services.rag.fallback import rag_service
    from app.services.pageindex_service import pageindex_service

    await asyncio.gather(
        rag_service.initialize(),
        pageindex_service.initialize(),
    )

    pi_stats = await pageindex_service.get_stats()
    logger.info(
        "PageIndex: %d documents indexed across %d collections",
        pi_stats["total_documents"], len(pi_stats["collections"]),
    )

    elapsed_ms = (time.monotonic() - start) * 1000
    logger.info("Startup completed in %.0fms", elapsed_ms)


@app.on_event("shutdown")
async def shutdown_event() -> None:
    """Application shutdown: close DB, RAG, and rate limiter connections."""
    await rate_limiter.close()
    from app.services.cache import cache
    await cache.close()
    await db.close_db()
    from app.services.rag.fallback import rag_service
    await rag_service.close()
    from app.services.pageindex_service import pageindex_service
    await pageindex_service.close()
    logger.info("Avni AI Platform shut down")


# ---------------------------------------------------------------------------
# Built-in endpoints
# ---------------------------------------------------------------------------

@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
    from starlette.responses import Response as StarletteResponse
    return StarletteResponse(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/health")
async def health_check() -> dict:
    return {
        "status": "healthy",
        "service": "avni-ai-platform",
        "version": "1.0.0",
    }


@app.get("/api/health")
async def api_health_check() -> dict:
    """Enhanced health check with dependency status."""
    health = {
        "status": "healthy",
        "service": "avni-ai-platform",
        "version": "1.0.0",
        "uptime_seconds": int(time.time() - _startup_time),
        "llm_provider": settings.LLM_PROVIDER,
        "model": settings.active_model,
        "api_key_configured": settings.api_key_configured,
        "database_connected": db.is_connected(),
    }

    # RAG status
    try:
        from app.services.rag.fallback import rag_service
        if rag_service._rag_available:
            health["rag_status"] = "connected"
            stats = await rag_service.get_stats()
            health["rag_chunks"] = stats.get("total_chunks", 0)
            health["rag_collections"] = len(stats.get("collections", []))
        else:
            health["rag_status"] = "fallback"
    except Exception:
        health["rag_status"] = "unavailable"

    # LLM status
    try:
        import httpx
        ollama_url = getattr(settings, "OLLAMA_BASE_URL", "http://localhost:11434")
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{ollama_url}/api/tags")
            if resp.status_code == 200:
                health["llm_status"] = "connected"
                models = resp.json().get("models", [])
                health["llm_models"] = [m.get("name", "") for m in models[:5]]
            else:
                health["llm_status"] = "error"
    except Exception:
        health["llm_status"] = "unavailable"

    # MCP server status
    try:
        from app.services.mcp_client import mcp_client
        health["mcp_available"] = await mcp_client.is_available()
    except Exception:
        health["mcp_available"] = False

    # Overall status
    if not health["database_connected"]:
        health["status"] = "degraded"
    if health.get("llm_status") == "unavailable":
        health["status"] = "degraded"

    return health
