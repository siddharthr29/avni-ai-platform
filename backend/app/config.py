import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    AVNI_BASE_URL: str = os.getenv("AVNI_BASE_URL", "https://staging.avniproject.org")
    AVNI_AUTH_TOKEN: str = os.getenv("AVNI_AUTH_TOKEN", "")
    CLAUDE_MODEL: str = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")
    BUNDLE_OUTPUT_DIR: str = os.getenv("BUNDLE_OUTPUT_DIR", "/tmp/avni_bundles")
    MAX_TOKENS: int = int(os.getenv("MAX_TOKENS", "4096"))
    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ]


settings = Settings()
