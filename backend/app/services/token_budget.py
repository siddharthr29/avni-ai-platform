"""Token budget and cost control.

Tracks LLM token usage per org and enforces monthly budgets.
Prevents runaway costs and provides usage visibility.

Pricing (approximate):
- Ollama: $0 (self-hosted)
- Groq: $0 (free tier, rate limited)
- Anthropic Claude Sonnet: $3/$15 per 1M input/output tokens
- Anthropic Claude Haiku: $0.25/$1.25 per 1M input/output tokens
"""

import json
import logging
import uuid
from dataclasses import asdict, dataclass
from typing import Any

from app import db

logger = logging.getLogger(__name__)


# ── Pricing ───────────────────────────────────────────────────────────────────

# Cost per 1M tokens (input, output) in USD
PROVIDER_COSTS: dict[str, Any] = {
    "ollama": (0.0, 0.0),
    "groq": (0.0, 0.0),  # free tier
    "anthropic": {
        "claude-sonnet-4-20250514": (3.0, 15.0),
        "claude-haiku-4-5-20251001": (0.25, 1.25),
    },
}

DEFAULT_MONTHLY_BUDGET_USD = 50.0  # per org
DEFAULT_MONTHLY_TOKEN_LIMIT = 5_000_000  # tokens per org


# ── Schema ────────────────────────────────────────────────────────────────────

TOKEN_USAGE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS token_usage (
    id                TEXT PRIMARY KEY,
    org_id            TEXT NOT NULL,
    user_id           TEXT,
    provider          TEXT NOT NULL,
    model             TEXT NOT NULL,
    prompt_tokens     INT NOT NULL DEFAULT 0,
    completion_tokens INT NOT NULL DEFAULT 0,
    total_tokens      INT NOT NULL DEFAULT 0,
    cost_usd          DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_token_usage_org_id ON token_usage(org_id);
CREATE INDEX IF NOT EXISTS idx_token_usage_created_at ON token_usage(created_at);
CREATE INDEX IF NOT EXISTS idx_token_usage_org_month ON token_usage(org_id, created_at);

CREATE TABLE IF NOT EXISTS org_budgets (
    org_id              TEXT PRIMARY KEY,
    monthly_budget_usd  DOUBLE PRECISION NOT NULL DEFAULT 50.0,
    monthly_token_limit INT NOT NULL DEFAULT 5000000,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


async def init_token_budget_schema() -> None:
    """Create token usage and budget tables if they do not exist."""
    if not db._pool:
        logger.warning("DB pool not available — token budget schema creation skipped")
        return
    try:
        async with db._pool.acquire() as conn:
            await conn.execute(TOKEN_USAGE_SCHEMA_SQL)
        logger.info("Token budget schema ready")
    except Exception as e:
        logger.error("Failed to create token budget schema: %s", e)


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class BudgetStatus:
    allowed: bool
    total_tokens_used: int
    total_cost_usd: float
    monthly_token_limit: int
    monthly_budget_usd: float
    usage_percent: float
    remaining_tokens: int
    remaining_usd: float
    warning: str | None  # "80% of budget used" etc

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ── Cost calculation ──────────────────────────────────────────────────────────

def calculate_cost(provider: str, model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Calculate USD cost for a given LLM call."""
    cost_entry = PROVIDER_COSTS.get(provider)
    if cost_entry is None:
        return 0.0

    if isinstance(cost_entry, tuple):
        input_cost_per_m, output_cost_per_m = cost_entry
    elif isinstance(cost_entry, dict):
        model_costs = cost_entry.get(model)
        if model_costs is None:
            # Try partial match (model name may have version suffix)
            for key, val in cost_entry.items():
                if key in model or model in key:
                    model_costs = val
                    break
            if model_costs is None:
                return 0.0
        input_cost_per_m, output_cost_per_m = model_costs
    else:
        return 0.0

    cost = (prompt_tokens * input_cost_per_m + completion_tokens * output_cost_per_m) / 1_000_000
    return round(cost, 6)


# ── Core functions ────────────────────────────────────────────────────────────

async def track_usage(
    org_id: str,
    user_id: str | None,
    provider: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> dict | None:
    """Record token usage and calculate cost. Returns the created row."""
    if not db._pool:
        logger.debug("Token usage tracking skipped (no DB)")
        return None

    total_tokens = prompt_tokens + completion_tokens
    cost = calculate_cost(provider, model, prompt_tokens, completion_tokens)
    entry_id = str(uuid.uuid4())

    try:
        async with db._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO token_usage
                    (id, org_id, user_id, provider, model, prompt_tokens, completion_tokens, total_tokens, cost_usd)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                RETURNING *
                """,
                entry_id, org_id, user_id, provider, model,
                prompt_tokens, completion_tokens, total_tokens, cost,
            )
            return dict(row) if row else None
    except Exception as e:
        logger.error("Failed to track token usage: %s", e)
        return None


async def get_monthly_usage(org_id: str) -> dict[str, Any]:
    """Get current month's token usage breakdown."""
    if not db._pool:
        return {"tokens": 0, "cost_usd": 0.0, "by_provider": {}, "by_user": {}}

    try:
        async with db._pool.acquire() as conn:
            # Total for current month
            totals = await conn.fetchrow(
                """
                SELECT COALESCE(SUM(total_tokens), 0) as tokens,
                       COALESCE(SUM(cost_usd), 0) as cost_usd
                FROM token_usage
                WHERE org_id = $1
                  AND created_at >= date_trunc('month', now())
                """,
                org_id,
            )

            # By provider
            provider_rows = await conn.fetch(
                """
                SELECT provider, model,
                       SUM(prompt_tokens) as prompt_tokens,
                       SUM(completion_tokens) as completion_tokens,
                       SUM(total_tokens) as total_tokens,
                       SUM(cost_usd) as cost_usd
                FROM token_usage
                WHERE org_id = $1
                  AND created_at >= date_trunc('month', now())
                GROUP BY provider, model
                ORDER BY cost_usd DESC
                """,
                org_id,
            )

            # By user
            user_rows = await conn.fetch(
                """
                SELECT user_id,
                       SUM(total_tokens) as total_tokens,
                       SUM(cost_usd) as cost_usd
                FROM token_usage
                WHERE org_id = $1
                  AND created_at >= date_trunc('month', now())
                  AND user_id IS NOT NULL
                GROUP BY user_id
                ORDER BY cost_usd DESC
                """,
                org_id,
            )

            return {
                "tokens": totals["tokens"],
                "cost_usd": round(float(totals["cost_usd"]), 4),
                "by_provider": [
                    {
                        "provider": r["provider"],
                        "model": r["model"],
                        "prompt_tokens": r["prompt_tokens"],
                        "completion_tokens": r["completion_tokens"],
                        "total_tokens": r["total_tokens"],
                        "cost_usd": round(float(r["cost_usd"]), 4),
                    }
                    for r in provider_rows
                ],
                "by_user": [
                    {
                        "user_id": r["user_id"],
                        "total_tokens": r["total_tokens"],
                        "cost_usd": round(float(r["cost_usd"]), 4),
                    }
                    for r in user_rows
                ],
            }
    except Exception as e:
        logger.error("Failed to get monthly usage: %s", e)
        return {"tokens": 0, "cost_usd": 0.0, "by_provider": [], "by_user": [], "error": str(e)}


async def check_budget(org_id: str) -> BudgetStatus:
    """Check whether the org is within its monthly budget."""
    if not db._pool:
        return BudgetStatus(
            allowed=True,
            total_tokens_used=0,
            total_cost_usd=0.0,
            monthly_token_limit=DEFAULT_MONTHLY_TOKEN_LIMIT,
            monthly_budget_usd=DEFAULT_MONTHLY_BUDGET_USD,
            usage_percent=0.0,
            remaining_tokens=DEFAULT_MONTHLY_TOKEN_LIMIT,
            remaining_usd=DEFAULT_MONTHLY_BUDGET_USD,
            warning=None,
        )

    try:
        async with db._pool.acquire() as conn:
            # Get org budget (or defaults)
            budget_row = await conn.fetchrow(
                "SELECT * FROM org_budgets WHERE org_id = $1", org_id
            )
            budget_usd = budget_row["monthly_budget_usd"] if budget_row else DEFAULT_MONTHLY_BUDGET_USD
            token_limit = budget_row["monthly_token_limit"] if budget_row else DEFAULT_MONTHLY_TOKEN_LIMIT

            # Get current month usage
            usage = await conn.fetchrow(
                """
                SELECT COALESCE(SUM(total_tokens), 0) as tokens,
                       COALESCE(SUM(cost_usd), 0) as cost_usd
                FROM token_usage
                WHERE org_id = $1
                  AND created_at >= date_trunc('month', now())
                """,
                org_id,
            )

            tokens_used = usage["tokens"]
            cost_used = float(usage["cost_usd"])

            # Calculate percentages (use the more restrictive limit)
            token_pct = (tokens_used / token_limit * 100) if token_limit > 0 else 0
            cost_pct = (cost_used / budget_usd * 100) if budget_usd > 0 else 0
            usage_pct = max(token_pct, cost_pct)

            remaining_tokens = max(0, token_limit - tokens_used)
            remaining_usd = max(0.0, budget_usd - cost_used)

            allowed = tokens_used < token_limit and cost_used < budget_usd

            warning = None
            if usage_pct >= 100:
                warning = "Monthly budget exceeded"
            elif usage_pct >= 90:
                warning = f"{usage_pct:.0f}% of monthly budget used"
            elif usage_pct >= 80:
                warning = f"{usage_pct:.0f}% of monthly budget used"

            return BudgetStatus(
                allowed=allowed,
                total_tokens_used=tokens_used,
                total_cost_usd=round(cost_used, 4),
                monthly_token_limit=token_limit,
                monthly_budget_usd=budget_usd,
                usage_percent=round(usage_pct, 1),
                remaining_tokens=remaining_tokens,
                remaining_usd=round(remaining_usd, 4),
                warning=warning,
            )
    except Exception as e:
        logger.error("Failed to check budget: %s", e)
        return BudgetStatus(
            allowed=True,  # fail open — don't block on DB errors
            total_tokens_used=0,
            total_cost_usd=0.0,
            monthly_token_limit=DEFAULT_MONTHLY_TOKEN_LIMIT,
            monthly_budget_usd=DEFAULT_MONTHLY_BUDGET_USD,
            usage_percent=0.0,
            remaining_tokens=DEFAULT_MONTHLY_TOKEN_LIMIT,
            remaining_usd=DEFAULT_MONTHLY_BUDGET_USD,
            warning="Budget check failed — using defaults",
        )


async def set_budget(
    org_id: str,
    monthly_limit_usd: float | None = None,
    monthly_token_limit: int | None = None,
) -> dict | None:
    """Set or update the monthly budget for an org."""
    if not db._pool:
        return None

    budget_usd = monthly_limit_usd if monthly_limit_usd is not None else DEFAULT_MONTHLY_BUDGET_USD
    token_limit = monthly_token_limit if monthly_token_limit is not None else DEFAULT_MONTHLY_TOKEN_LIMIT

    try:
        async with db._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO org_budgets (org_id, monthly_budget_usd, monthly_token_limit)
                VALUES ($1, $2, $3)
                ON CONFLICT (org_id) DO UPDATE SET
                    monthly_budget_usd = EXCLUDED.monthly_budget_usd,
                    monthly_token_limit = EXCLUDED.monthly_token_limit,
                    updated_at = now()
                RETURNING *
                """,
                org_id, budget_usd, token_limit,
            )
            return dict(row) if row else None
    except Exception as e:
        logger.error("Failed to set budget: %s", e)
        return None


async def get_usage_trend(org_id: str, months: int = 6) -> list[dict]:
    """Get monthly token usage trend over the past N months."""
    if not db._pool:
        return []

    try:
        async with db._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT date_trunc('month', created_at) as month,
                       SUM(total_tokens) as total_tokens,
                       SUM(prompt_tokens) as prompt_tokens,
                       SUM(completion_tokens) as completion_tokens,
                       SUM(cost_usd) as cost_usd,
                       COUNT(*) as request_count
                FROM token_usage
                WHERE org_id = $1
                  AND created_at >= date_trunc('month', now()) - ($2 || ' months')::interval
                GROUP BY date_trunc('month', created_at)
                ORDER BY month ASC
                """,
                org_id,
                str(months),
            )
            return [
                {
                    "month": r["month"].isoformat(),
                    "total_tokens": r["total_tokens"],
                    "prompt_tokens": r["prompt_tokens"],
                    "completion_tokens": r["completion_tokens"],
                    "cost_usd": round(float(r["cost_usd"]), 4),
                    "request_count": r["request_count"],
                }
                for r in rows
            ]
    except Exception as e:
        logger.error("Failed to get usage trend: %s", e)
        return []


async def get_top_users(org_id: str, limit: int = 10) -> list[dict]:
    """Get top token consumers for an org in the current month."""
    if not db._pool:
        return []

    try:
        async with db._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT user_id,
                       SUM(total_tokens) as total_tokens,
                       SUM(prompt_tokens) as prompt_tokens,
                       SUM(completion_tokens) as completion_tokens,
                       SUM(cost_usd) as cost_usd,
                       COUNT(*) as request_count
                FROM token_usage
                WHERE org_id = $1
                  AND user_id IS NOT NULL
                  AND created_at >= date_trunc('month', now())
                GROUP BY user_id
                ORDER BY total_tokens DESC
                LIMIT $2
                """,
                org_id,
                limit,
            )
            return [
                {
                    "user_id": r["user_id"],
                    "total_tokens": r["total_tokens"],
                    "prompt_tokens": r["prompt_tokens"],
                    "completion_tokens": r["completion_tokens"],
                    "cost_usd": round(float(r["cost_usd"]), 4),
                    "request_count": r["request_count"],
                }
                for r in rows
            ]
    except Exception as e:
        logger.error("Failed to get top users: %s", e)
        return []
