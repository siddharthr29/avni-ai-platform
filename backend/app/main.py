import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import bundle, chat, image, knowledge, rules, support, sync, voice

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Avni AI Platform",
    description=(
        "AI-powered orchestration layer for the Avni field data collection platform. "
        "Provides chat, bundle generation, voice mapping, image extraction, and "
        "knowledge search capabilities using Claude as the primary LLM."
    ),
    version="1.0.0",
)

# CORS middleware for Vite frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(chat.router, prefix="/api", tags=["Chat"])
app.include_router(bundle.router, prefix="/api", tags=["Bundle"])
app.include_router(voice.router, prefix="/api", tags=["Voice"])
app.include_router(image.router, prefix="/api", tags=["Image"])
app.include_router(knowledge.router, prefix="/api", tags=["Knowledge"])
app.include_router(sync.router, prefix="/api", tags=["Avni Sync"])
app.include_router(support.router, prefix="/api", tags=["Support"])
app.include_router(rules.router, prefix="/api", tags=["Rules"])


@app.on_event("startup")
async def startup_event() -> None:
    """Application startup: create required directories and log config."""
    os.makedirs(settings.BUNDLE_OUTPUT_DIR, exist_ok=True)

    logger.info("Avni AI Platform starting up")
    logger.info("  AVNI_BASE_URL: %s", settings.AVNI_BASE_URL)
    logger.info("  CLAUDE_MODEL: %s", settings.CLAUDE_MODEL)
    logger.info("  BUNDLE_OUTPUT_DIR: %s", settings.BUNDLE_OUTPUT_DIR)
    logger.info(
        "  ANTHROPIC_API_KEY: %s",
        "configured" if settings.ANTHROPIC_API_KEY else "NOT SET",
    )
    logger.info("  CORS origins: %s", settings.CORS_ORIGINS)

    # Knowledge base loads lazily on first access, so no blocking here


@app.get("/health")
async def health_check() -> dict:
    return {
        "status": "healthy",
        "service": "avni-ai-platform",
        "version": "1.0.0",
    }


@app.get("/api/health")
async def api_health_check() -> dict:
    return {
        "status": "healthy",
        "service": "avni-ai-platform",
        "version": "1.0.0",
        "model": settings.CLAUDE_MODEL,
        "api_key_configured": bool(settings.ANTHROPIC_API_KEY),
    }
