"""Tests for configuration settings."""

import os
from unittest.mock import patch

import pytest


class TestSettings:
    """Tests for the Settings class."""

    def _make_settings(self, **env_overrides):
        """Create a fresh Settings instance with optional env overrides.

        Settings reads os.getenv at class definition time, so we must
        patch os.environ BEFORE the class body executes. We achieve this
        by reloading the module.
        """
        import importlib
        env = {
            "DATABASE_URL": "",
            "LLM_PROVIDER": "ollama",
            "API_KEYS": "",
            "GROQ_API_KEY": "",
            "ANTHROPIC_API_KEY": "",
        }
        env.update(env_overrides)
        with patch.dict(os.environ, env, clear=False):
            import app.config
            importlib.reload(app.config)
            return app.config.Settings()

    def test_default_settings(self):
        s = self._make_settings()
        assert s.LLM_PROVIDER == "ollama"
        assert s.MAX_TOKENS == 4096
        assert s.RATE_LIMIT_RPM == 60

    def test_active_model_ollama(self):
        s = self._make_settings(LLM_PROVIDER="ollama", OLLAMA_MODEL="avni-coder")
        assert s.active_model == "avni-coder"

    def test_active_model_groq(self):
        s = self._make_settings(LLM_PROVIDER="groq", GROQ_MODEL="llama-3.3-70b-versatile")
        assert s.active_model == "llama-3.3-70b-versatile"

    def test_active_model_anthropic(self):
        s = self._make_settings(LLM_PROVIDER="anthropic", CLAUDE_MODEL="claude-sonnet-4-20250514")
        assert s.active_model == "claude-sonnet-4-20250514"

    def test_validate_warns_missing_db(self):
        s = self._make_settings(DATABASE_URL="")
        warnings = s.validate()
        assert any("DATABASE_URL" in w for w in warnings)

    def test_validate_warns_missing_groq_key(self):
        s = self._make_settings(LLM_PROVIDER="groq", GROQ_API_KEY="")
        warnings = s.validate()
        assert any("GROQ_API_KEY" in w for w in warnings)

    def test_validate_warns_missing_anthropic_key(self):
        s = self._make_settings(LLM_PROVIDER="anthropic", ANTHROPIC_API_KEY="")
        warnings = s.validate()
        assert any("ANTHROPIC_API_KEY" in w for w in warnings)

    def test_validate_warns_missing_api_keys(self):
        s = self._make_settings(API_KEYS="", AVNI_DEV_MODE="false")
        warnings = s.validate()
        assert any("API_KEYS" in w for w in warnings)

    def test_validate_no_groq_warning_for_ollama(self):
        s = self._make_settings(LLM_PROVIDER="ollama", GROQ_API_KEY="")
        warnings = s.validate()
        assert not any("GROQ_API_KEY" in w for w in warnings)

    def test_api_key_configured_ollama_always_true(self):
        s = self._make_settings(LLM_PROVIDER="ollama")
        assert s.api_key_configured is True

    def test_api_key_configured_groq_false_without_key(self):
        s = self._make_settings(LLM_PROVIDER="groq", GROQ_API_KEY="")
        assert s.api_key_configured is False

    def test_api_key_configured_groq_true_with_key(self):
        s = self._make_settings(LLM_PROVIDER="groq", GROQ_API_KEY="gsk_test123")
        assert s.api_key_configured is True

    def test_api_key_configured_anthropic_false_without_key(self):
        s = self._make_settings(LLM_PROVIDER="anthropic", ANTHROPIC_API_KEY="")
        assert s.api_key_configured is False

    def test_api_key_configured_anthropic_true_with_key(self):
        s = self._make_settings(LLM_PROVIDER="anthropic", ANTHROPIC_API_KEY="sk-ant-test")
        assert s.api_key_configured is True

    def test_active_vision_model_ollama(self):
        s = self._make_settings(LLM_PROVIDER="ollama")
        assert s.active_vision_model == s.OLLAMA_VISION_MODEL

    def test_active_vision_model_groq(self):
        s = self._make_settings(LLM_PROVIDER="groq")
        assert s.active_vision_model == s.GROQ_VISION_MODEL

    def test_active_vision_model_anthropic(self):
        s = self._make_settings(LLM_PROVIDER="anthropic")
        assert s.active_vision_model == s.CLAUDE_MODEL

    def test_cors_origins_default(self):
        s = self._make_settings()
        assert "http://localhost:5173" in s.CORS_ORIGINS
        assert "http://localhost:3000" in s.CORS_ORIGINS
