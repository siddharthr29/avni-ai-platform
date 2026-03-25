"""Prometheus metrics middleware and collectors."""

import re
import time
import logging

from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

logger = logging.getLogger(__name__)

# HTTP metrics
HTTP_REQUESTS = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "path_template", "status"],
)

HTTP_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration",
    ["method", "path_template"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
)

# LLM metrics
LLM_REQUESTS = Counter(
    "llm_requests_total",
    "Total LLM requests",
    ["provider", "model", "status"],
)

LLM_DURATION = Histogram(
    "llm_request_duration_seconds",
    "LLM request duration",
    ["provider", "model"],
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
)

# RAG metrics
RAG_DURATION = Histogram(
    "rag_search_duration_seconds",
    "RAG search duration",
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5],
)

# Bundle metrics
BUNDLE_OPS = Counter(
    "bundle_operations_total",
    "Bundle operations",
    ["operation"],
)

# Session gauge
ACTIVE_SESSIONS = Gauge(
    "active_sessions",
    "Number of active chat sessions",
)


_UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_HEX_ID_RE = re.compile(r"/[a-f0-9]{8,}(?=/|$)")


def _normalize_path(path: str) -> str:
    """Normalize path for Prometheus labels (replace IDs with placeholders)."""
    # Replace UUIDs
    path = _UUID_RE.sub("{id}", path)
    # Replace other hex IDs (8+ chars)
    path = _HEX_ID_RE.sub("/{id}", path)
    return path


class MetricsMiddleware:
    """Pure ASGI middleware — avoids BaseHTTPMiddleware body-buffering overhead."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"] == "/metrics":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "GET")
        path = _normalize_path(scope["path"])
        start = time.time()
        status_code = 500  # default in case send is never called

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration = time.time() - start
            HTTP_REQUESTS.labels(method=method, path_template=path, status=str(status_code)).inc()
            HTTP_DURATION.labels(method=method, path_template=path).observe(duration)
