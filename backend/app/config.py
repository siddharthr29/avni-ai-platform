import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # --- LLM Provider Settings ---
    # Supported: "ollama" (self-hosted, no API key), "groq" (free tier), "anthropic" (paid)
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "ollama")

    # Ollama settings (self-hosted, DEFAULT — no API key needed)
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "avni-coder")
    OLLAMA_VISION_MODEL: str = os.getenv("OLLAMA_VISION_MODEL", "llava:7b")

    # Groq settings (free tier, fallback)
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    GROQ_VISION_MODEL: str = os.getenv("GROQ_VISION_MODEL", "llama-3.2-90b-vision-preview")

    # Cerebras settings (free tier, ultra-fast inference)
    CEREBRAS_API_KEY: str = os.getenv("CEREBRAS_API_KEY", "")
    CEREBRAS_MODEL: str = os.getenv("CEREBRAS_MODEL", "llama-3.3-70b")

    # Gemini settings (free tier, Google AI)
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    GEMINI_VISION_MODEL: str = os.getenv("GEMINI_VISION_MODEL", "gemini-2.0-flash")

    # OpenAI settings
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o")
    OPENAI_VISION_MODEL: str = os.getenv("OPENAI_VISION_MODEL", "gpt-4o")

    # Anthropic settings (production)
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    CLAUDE_MODEL: str = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")

    # --- Provider Chain Settings ---
    # Comma-separated default provider chain (used when no task-specific routing matches)
    LLM_PROVIDER_CHAIN: str = os.getenv("LLM_PROVIDER_CHAIN", "openai,ollama")

    # Monthly budget enforcement (0 = unlimited)
    LLM_MONTHLY_BUDGET_USD: float = float(os.getenv("LLM_MONTHLY_BUDGET_USD", "0"))
    LLM_ALERT_THRESHOLD_USD: float = float(os.getenv("LLM_ALERT_THRESHOLD_USD", "0"))

    # Per-provider rate limits (requests per minute). Falls back to RATE_LIMIT_RPM.
    @property
    def LLM_RATE_LIMITS(self) -> dict[str, int]:
        """Parse per-provider rate limits from env vars like LLM_RATE_LIMIT_OPENAI=100."""
        limits: dict[str, int] = {}
        for provider in ["openai", "anthropic", "groq", "cerebras", "gemini", "ollama"]:
            env_key = f"LLM_RATE_LIMIT_{provider.upper()}"
            val = os.getenv(env_key, "")
            if val:
                limits[provider] = int(val)
        return limits

    # Task-specific routing overrides (env vars like LLM_TASK_CHAT="groq,openai,ollama")
    @property
    def LLM_TASK_ROUTING(self) -> dict[str, list[str]]:
        """Parse per-task provider routing from env vars like LLM_TASK_RULE_GENERATION=openai,anthropic."""
        routing: dict[str, list[str]] = {}
        task_types = [
            "rule_generation", "srs_parsing", "chat", "intent", "validation",
            "image", "voice", "support", "structured_output", "bundle_generation",
            "clarification",
        ]
        for task in task_types:
            env_key = f"LLM_TASK_{task.upper()}"
            val = os.getenv(env_key, "")
            if val:
                routing[task] = [p.strip() for p in val.split(",") if p.strip()]
        return routing

    # Cost rate table: provider/model -> {input_per_1m, output_per_1m} in USD
    @property
    def LLM_COST_RATES(self) -> dict[str, dict[str, float]]:
        """Cost rates per 1M tokens for each provider. Override with LLM_COST_RATES JSON env."""
        import json
        custom = os.getenv("LLM_COST_RATES", "")
        if custom:
            try:
                return json.loads(custom)
            except json.JSONDecodeError:
                pass
        # Default rates (approximate, as of early 2026)
        return {
            "openai": {"input_per_1m": 2.50, "output_per_1m": 10.00},
            "openai/gpt-4o": {"input_per_1m": 2.50, "output_per_1m": 10.00},
            "openai/gpt-4o-mini": {"input_per_1m": 0.15, "output_per_1m": 0.60},
            "anthropic": {"input_per_1m": 3.00, "output_per_1m": 15.00},
            "anthropic/claude-sonnet-4-20250514": {"input_per_1m": 3.00, "output_per_1m": 15.00},
            "groq": {"input_per_1m": 0.00, "output_per_1m": 0.00},  # Free tier
            "cerebras": {"input_per_1m": 0.00, "output_per_1m": 0.00},  # Free tier
            "gemini": {"input_per_1m": 0.00, "output_per_1m": 0.00},  # Free tier
            "ollama": {"input_per_1m": 0.00, "output_per_1m": 0.00},  # Self-hosted
        }

    # --- General Settings ---
    AVNI_BASE_URL: str = os.getenv("AVNI_BASE_URL", "https://staging.avniproject.org")
    AVNI_AUTH_TOKEN: str = os.getenv("AVNI_AUTH_TOKEN", "")
    BUNDLE_OUTPUT_DIR: str = os.getenv("BUNDLE_OUTPUT_DIR", "/tmp/avni_bundles")
    MAX_TOKENS: int = int(os.getenv("MAX_TOKENS", "4096"))
    CORS_ORIGINS: list[str] = [
        o.strip()
        for o in os.getenv(
            "CORS_ORIGINS",
            "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173,http://127.0.0.1:3000",
        ).split(",")
        if o.strip()
    ]

    # --- Security Settings ---
    API_KEYS: str = os.getenv("API_KEYS", "")  # comma-separated valid API keys (empty = dev mode, no auth)
    AVNI_DEV_MODE: bool = os.getenv("AVNI_DEV_MODE", "false").lower() == "true"
    RATE_LIMIT_RPM: int = int(os.getenv("RATE_LIMIT_RPM", "60"))
    REDIS_URL: str = os.getenv("REDIS_URL", "")

    # --- Sentry Error Tracking ---
    SENTRY_DSN: str = os.getenv("SENTRY_DSN", "")
    SENTRY_TRACES_SAMPLE_RATE: float = float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1"))
    SENTRY_ENVIRONMENT: str = os.getenv("SENTRY_ENVIRONMENT", "development")

    # --- File Upload Limits ---
    MAX_UPLOAD_SIZE_MB: int = int(os.getenv("MAX_UPLOAD_SIZE_MB", "50"))

    # --- JWT Auth Settings ---
    JWT_SECRET: str = os.getenv("JWT_SECRET", "avni-ai-dev-secret-change-in-production")
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))  # 24 hours
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "30"))

    # --- Responsible AI Guardrails ---
    GUARDRAILS_ENABLED: bool = os.getenv("GUARDRAILS_ENABLED", "true").lower() == "true"
    PII_DETECTION_ENABLED: bool = os.getenv("PII_DETECTION_ENABLED", "true").lower() == "true"
    INJECTION_DETECTION_ENABLED: bool = os.getenv("INJECTION_DETECTION_ENABLED", "true").lower() == "true"
    LOW_CONFIDENCE_THRESHOLD: float = float(os.getenv("LOW_CONFIDENCE_THRESHOLD", "0.3"))
    GENDER_BIAS_CHECK_ENABLED: bool = os.getenv("GENDER_BIAS_CHECK_ENABLED", "true").lower() == "true"
    BAN_LIST_ENABLED: bool = os.getenv("BAN_LIST_ENABLED", "true").lower() == "true"
    GUARDRAIL_ON_FAIL_DEFAULT: str = os.getenv("GUARDRAIL_ON_FAIL_DEFAULT", "fix")  # fix, exception, rephrase

    # --- Concurrency & Pool Settings ---
    LLM_CONCURRENCY_LIMIT: int = int(os.getenv("LLM_CONCURRENCY_LIMIT", "8"))
    DB_POOL_MIN: int = int(os.getenv("DB_POOL_MIN", "5"))
    DB_POOL_MAX: int = int(os.getenv("DB_POOL_MAX", "20"))

    # --- MCP Server Settings ---
    MCP_SERVER_URL: str = os.getenv("MCP_SERVER_URL", "http://localhost:8023")

    # --- RAG Pipeline Settings ---
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    RAG_SEMANTIC_WEIGHT: float = float(os.getenv("RAG_SEMANTIC_WEIGHT", "0.6"))
    RAG_KEYWORD_WEIGHT: float = float(os.getenv("RAG_KEYWORD_WEIGHT", "0.4"))

    @property
    def active_model(self) -> str:
        if self.LLM_PROVIDER == "ollama":
            return self.OLLAMA_MODEL
        if self.LLM_PROVIDER == "groq":
            return self.GROQ_MODEL
        if self.LLM_PROVIDER == "cerebras":
            return self.CEREBRAS_MODEL
        if self.LLM_PROVIDER == "gemini":
            return self.GEMINI_MODEL
        if self.LLM_PROVIDER == "openai":
            return self.OPENAI_MODEL
        return self.CLAUDE_MODEL

    @property
    def active_vision_model(self) -> str:
        if self.LLM_PROVIDER == "ollama":
            return self.OLLAMA_VISION_MODEL
        if self.LLM_PROVIDER == "groq":
            return self.GROQ_VISION_MODEL
        if self.LLM_PROVIDER == "gemini":
            return self.GEMINI_VISION_MODEL
        if self.LLM_PROVIDER == "openai":
            return self.OPENAI_VISION_MODEL
        return self.CLAUDE_MODEL

    def validate(self) -> list[str]:
        """Validate config at startup. Returns list of warnings."""
        warnings = []
        if not self.DATABASE_URL:
            warnings.append("DATABASE_URL not set — using in-memory only")
        if self.LLM_PROVIDER == "groq" and not self.GROQ_API_KEY:
            warnings.append("GROQ_API_KEY required for groq provider but not set")
        if self.LLM_PROVIDER == "cerebras" and not self.CEREBRAS_API_KEY:
            warnings.append("CEREBRAS_API_KEY required for cerebras provider but not set")
        if self.LLM_PROVIDER == "gemini" and not self.GEMINI_API_KEY:
            warnings.append("GEMINI_API_KEY required for gemini provider but not set")
        if self.LLM_PROVIDER == "openai" and not self.OPENAI_API_KEY:
            warnings.append("OPENAI_API_KEY required for openai provider but not set")
        if self.LLM_PROVIDER == "anthropic" and not self.ANTHROPIC_API_KEY:
            warnings.append("ANTHROPIC_API_KEY required for anthropic provider but not set")
        if not self.API_KEYS and not self.AVNI_DEV_MODE:
            warnings.append("API_KEYS not set and AVNI_DEV_MODE is off — unauthenticated requests without JWT will be rejected")
        if self.AVNI_DEV_MODE:
            warnings.append("AVNI_DEV_MODE is ON — unauthenticated requests get platform_admin access (NOT for production)")
        if not self.SENTRY_DSN:
            warnings.append("SENTRY_DSN not set — error tracking disabled")
        # CRITICAL: JWT secret validation
        if not self.AVNI_DEV_MODE and self.JWT_SECRET == "avni-ai-dev-secret-change-in-production":
            warnings.append(
                "CRITICAL SECURITY WARNING: JWT_SECRET is set to the default development value! "
                "Set a strong, unique JWT_SECRET environment variable before deploying to production. "
                "Tokens signed with the default secret can be forged by anyone."
            )
        return warnings

    @property
    def api_key_configured(self) -> bool:
        if self.LLM_PROVIDER == "ollama":
            return True  # No API key needed for self-hosted
        if self.LLM_PROVIDER == "groq":
            return bool(self.GROQ_API_KEY)
        if self.LLM_PROVIDER == "cerebras":
            return bool(self.CEREBRAS_API_KEY)
        if self.LLM_PROVIDER == "gemini":
            return bool(self.GEMINI_API_KEY)
        if self.LLM_PROVIDER == "openai":
            return bool(self.OPENAI_API_KEY)
        return bool(self.ANTHROPIC_API_KEY)


settings = Settings()
