"""Task-aware LLM routing with automatic fallback, cost tracking, and budget enforcement.

The ProviderChain replaces the simple single-provider approach with intelligent
task-based routing. Each task type (chat, rule_generation, srs_parsing, etc.)
has a preferred provider order. If the preferred provider fails, the chain
falls through to the next one.

Usage:
    from app.services.provider_chain import provider_chain, ProviderResult

    # Non-streaming
    result: ProviderResult = await provider_chain.complete(messages, task_type="rule_generation")

    # Streaming
    async for chunk in provider_chain.stream(messages, task_type="chat"):
        print(chunk)
"""

import logging
import time
from dataclasses import dataclass, field
from typing import AsyncGenerator, Callable

from app.config import settings

logger = logging.getLogger(__name__)

__all__ = [
    "ProviderResult",
    "ProviderChain",
    "provider_chain",
]


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ProviderResult:
    """Result from a provider chain completion."""
    content: str
    provider: str        # which provider handled it
    model: str
    latency_ms: float
    input_tokens: int
    output_tokens: int
    cost_usd: float
    fallback_used: bool
    task_type: str


@dataclass
class _CircuitState:
    """Per-provider circuit breaker state."""
    provider: str = ""
    failures: int = 0
    state: str = "closed"  # closed | open | half_open
    last_failure_time: float = 0.0

    FAILURE_THRESHOLD: int = 3
    RECOVERY_TIMEOUT: float = 60.0

    def record_failure(self) -> None:
        self.failures += 1
        self.last_failure_time = time.time()
        if self.failures >= self.FAILURE_THRESHOLD and self.state != "open":
            self.state = "open"
            logger.warning(
                "Circuit OPEN for provider '%s' after %d failures",
                self.provider, self.failures,
            )

    def record_success(self) -> None:
        if self.state != "closed":
            logger.info("Circuit CLOSED for provider '%s' (recovered)", self.provider)
        self.failures = 0
        self.state = "closed"

    def can_attempt(self) -> bool:
        if self.state == "closed":
            return True
        if self.state == "open":
            elapsed = time.time() - self.last_failure_time
            if elapsed > self.RECOVERY_TIMEOUT:
                self.state = "half_open"
                logger.info("Circuit HALF-OPEN for '%s' (%.0fs elapsed)", self.provider, elapsed)
                return True
            return False
        return True  # half_open


@dataclass
class _RateLimitState:
    """Simple sliding-window rate limiter per provider."""
    provider: str = ""
    window_start: float = 0.0
    request_count: int = 0
    window_seconds: float = 60.0
    max_requests: int = 60

    def can_attempt(self) -> bool:
        now = time.time()
        if now - self.window_start > self.window_seconds:
            self.window_start = now
            self.request_count = 0
        return self.request_count < self.max_requests

    def record_request(self) -> None:
        now = time.time()
        if now - self.window_start > self.window_seconds:
            self.window_start = now
            self.request_count = 0
        self.request_count += 1


# ---------------------------------------------------------------------------
# Cost tracking
# ---------------------------------------------------------------------------

class _CostTracker:
    """Tracks cumulative cost and enforces monthly budget."""

    def __init__(self) -> None:
        self._month_total_usd: float = 0.0
        self._month_key: str = ""  # "2026-03" format

    def _current_month_key(self) -> str:
        import datetime
        return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m")

    def _maybe_reset(self) -> None:
        key = self._current_month_key()
        if key != self._month_key:
            if self._month_key:
                logger.info(
                    "Monthly cost reset: previous month '%s' total $%.4f",
                    self._month_key, self._month_total_usd,
                )
            self._month_key = key
            self._month_total_usd = 0.0

    @property
    def month_total_usd(self) -> float:
        self._maybe_reset()
        return self._month_total_usd

    def record(self, cost_usd: float) -> None:
        self._maybe_reset()
        self._month_total_usd += cost_usd
        budget = settings.LLM_MONTHLY_BUDGET_USD
        alert_threshold = settings.LLM_ALERT_THRESHOLD_USD
        if alert_threshold > 0 and self._month_total_usd >= alert_threshold:
            logger.warning(
                "LLM spend alert: $%.4f / $%.2f budget (%.0f%%)",
                self._month_total_usd, budget,
                (self._month_total_usd / budget * 100) if budget > 0 else 0,
            )

    def budget_exceeded(self) -> bool:
        self._maybe_reset()
        budget = settings.LLM_MONTHLY_BUDGET_USD
        if budget <= 0:
            return False  # No budget enforcement
        return self._month_total_usd >= budget

    @staticmethod
    def estimate_cost(provider: str, model: str, input_tokens: int, output_tokens: int) -> float:
        """Estimate cost in USD based on provider rate table."""
        rates = settings.LLM_COST_RATES
        key = f"{provider}/{model}"
        if key in rates:
            rate = rates[key]
        elif provider in rates:
            rate = rates[provider]
        else:
            return 0.0  # Unknown provider/model, no cost tracking

        input_cost = (input_tokens / 1_000_000) * rate.get("input_per_1m", 0.0)
        output_cost = (output_tokens / 1_000_000) * rate.get("output_per_1m", 0.0)
        return input_cost + output_cost


# ---------------------------------------------------------------------------
# Provider adapters
# ---------------------------------------------------------------------------

# Provider base URLs and their OpenAI-compatible endpoints
_PROVIDER_URLS = {
    "ollama":    lambda: settings.OLLAMA_BASE_URL,
    "groq":      lambda: "https://api.groq.com/openai/v1",
    "cerebras":  lambda: "https://api.cerebras.ai/v1",
    "gemini":    lambda: "https://generativelanguage.googleapis.com/v1beta/openai/",
    "openai":    lambda: "https://api.openai.com/v1",
}

_PROVIDER_API_KEYS = {
    "ollama":    lambda: "ollama",
    "groq":      lambda: settings.GROQ_API_KEY,
    "cerebras":  lambda: settings.CEREBRAS_API_KEY,
    "gemini":    lambda: settings.GEMINI_API_KEY,
    "openai":    lambda: settings.OPENAI_API_KEY,
    "anthropic": lambda: settings.ANTHROPIC_API_KEY,
}


def _model_for_provider(provider: str) -> str:
    """Return the configured model name for a given provider."""
    mapping = {
        "ollama":    lambda: settings.OLLAMA_MODEL,
        "groq":      lambda: settings.GROQ_MODEL,
        "cerebras":  lambda: settings.CEREBRAS_MODEL,
        "gemini":    lambda: settings.GEMINI_MODEL,
        "openai":    lambda: settings.OPENAI_MODEL,
        "anthropic": lambda: settings.CLAUDE_MODEL,
    }
    fn = mapping.get(provider)
    return fn() if fn else provider


def _provider_is_configured(provider: str) -> bool:
    """Check whether the provider has the necessary credentials."""
    if provider == "ollama":
        return True
    key_fn = _PROVIDER_API_KEYS.get(provider)
    return bool(key_fn and key_fn())


# ---------------------------------------------------------------------------
# ProviderChain
# ---------------------------------------------------------------------------

ALL_PROVIDERS = ["openai", "anthropic", "groq", "cerebras", "gemini", "ollama"]


class ProviderChain:
    """Task-aware LLM routing with automatic fallback and cost tracking.

    Features:
    - Task-based provider routing (each task type has a preferred provider order)
    - Circuit breaker per provider (3 failures = open for 60s)
    - Rate limiting per provider
    - Cost tracking with monthly budget enforcement
    - BYOK (Bring Your Own Key) support
    - Prometheus metrics integration
    """

    # Default task-to-provider routing table. Overridden by env vars LLM_TASK_*.
    # Default routing: OpenAI primary, Ollama fallback.
    # Groq is available via BYOK only (users bring their own key).
    DEFAULT_TASK_ROUTING: dict[str, list[str]] = {
        "rule_generation":   ["openai", "anthropic", "ollama"],
        "srs_parsing":       ["openai", "ollama"],
        "chat":              ["openai", "ollama"],
        "intent":            ["openai", "ollama"],
        "validation":        ["ollama", "openai"],
        "image":             ["openai", "gemini"],
        "voice":             ["openai", "ollama"],
        "support":           ["openai", "ollama"],
        "structured_output": ["openai", "anthropic", "ollama"],
        "bundle_generation": ["openai", "ollama"],
        "clarification":     ["openai", "ollama"],
    }

    def __init__(self) -> None:
        self._clients: dict[str, object] = {}
        self._circuits: dict[str, _CircuitState] = {
            p: _CircuitState(provider=p) for p in ALL_PROVIDERS
        }
        self._rate_limits: dict[str, _RateLimitState] = {}
        self._cost_tracker = _CostTracker()
        self._task_routing: dict[str, list[str]] = self._load_task_routing()

        # Initialize rate limiters from settings
        for provider in ALL_PROVIDERS:
            rpm = settings.LLM_RATE_LIMITS.get(provider, settings.RATE_LIMIT_RPM)
            self._rate_limits[provider] = _RateLimitState(
                provider=provider, max_requests=rpm,
            )

    def _load_task_routing(self) -> dict[str, list[str]]:
        """Load task routing from settings, falling back to defaults."""
        routing = dict(self.DEFAULT_TASK_ROUTING)
        # Override from settings (env vars like LLM_TASK_CHAT="groq,openai,ollama")
        overrides = settings.LLM_TASK_ROUTING
        for task, providers in overrides.items():
            routing[task] = providers
        return routing

    # -- Client management --------------------------------------------------

    def _get_openai_compatible_client(self, provider: str, api_key: str | None = None):
        """Get or create an AsyncOpenAI client for OpenAI-compatible providers."""
        cache_key = f"{provider}:{api_key or 'platform'}"
        if cache_key in self._clients:
            return self._clients[cache_key]

        from openai import AsyncOpenAI

        effective_key = api_key or _PROVIDER_API_KEYS[provider]()
        url_fn = _PROVIDER_URLS.get(provider)
        if not url_fn:
            raise ValueError(f"No URL configured for provider: {provider}")

        client = AsyncOpenAI(api_key=effective_key, base_url=url_fn())
        self._clients[cache_key] = client
        return client

    def _get_anthropic_client(self, api_key: str | None = None):
        """Get or create an AsyncAnthropic client."""
        cache_key = f"anthropic:{api_key or 'platform'}"
        if cache_key in self._clients:
            return self._clients[cache_key]

        import anthropic
        effective_key = api_key or settings.ANTHROPIC_API_KEY
        if not effective_key:
            raise ValueError("ANTHROPIC_API_KEY is not set.")
        client = anthropic.AsyncAnthropic(api_key=effective_key)
        self._clients[cache_key] = client
        return client

    # -- Provider resolution ------------------------------------------------

    def _get_providers_for_task(self, task_type: str) -> list[str]:
        """Return ordered provider list for a task type, filtered by availability."""
        chain = self._task_routing.get(task_type, self._task_routing.get("chat", ["ollama"]))

        available: list[str] = []
        for provider in chain:
            if not _provider_is_configured(provider):
                continue
            circuit = self._circuits[provider]
            if not circuit.can_attempt():
                continue
            rate_limit = self._rate_limits.get(provider)
            if rate_limit and not rate_limit.can_attempt():
                logger.warning("Provider '%s' rate-limited for task '%s'", provider, task_type)
                continue
            available.append(provider)

        return available

    # -- Low-level provider dispatch ----------------------------------------

    async def _complete_with_provider(
        self,
        provider: str,
        messages: list[dict],
        system_prompt: str,
        api_key: str | None = None,
        **kwargs,
    ) -> tuple[str, int, int]:
        """Dispatch a non-streaming completion. Returns (content, input_tokens, output_tokens)."""
        if provider == "anthropic":
            return await self._anthropic_complete(messages, system_prompt, api_key)
        else:
            return await self._openai_complete(provider, messages, system_prompt, api_key, **kwargs)

    async def _openai_complete(
        self,
        provider: str,
        messages: list[dict],
        system_prompt: str,
        api_key: str | None = None,
        **kwargs,
    ) -> tuple[str, int, int]:
        """OpenAI-compatible completion."""
        client = self._get_openai_compatible_client(provider, api_key)
        model = _model_for_provider(provider)

        oai_messages = [{"role": "system", "content": system_prompt}]
        for m in messages:
            oai_messages.append({"role": m["role"], "content": m["content"]})

        temperature = kwargs.get("temperature", 0.1 if provider == "ollama" else None)
        create_kwargs = {
            "model": model,
            "max_tokens": kwargs.get("max_tokens", settings.MAX_TOKENS),
            "messages": oai_messages,
        }
        if temperature is not None:
            create_kwargs["temperature"] = temperature

        response = await client.chat.completions.create(**create_kwargs)

        content = response.choices[0].message.content or ""
        usage = response.usage
        input_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0
        return content, input_tokens, output_tokens

    async def _anthropic_complete(
        self,
        messages: list[dict],
        system_prompt: str,
        api_key: str | None = None,
    ) -> tuple[str, int, int]:
        """Anthropic completion."""
        client = self._get_anthropic_client(api_key)
        model = _model_for_provider("anthropic")

        response = await client.messages.create(
            model=model,
            max_tokens=settings.MAX_TOKENS,
            system=system_prompt,
            messages=[{"role": m["role"], "content": m["content"]} for m in messages],
        )

        content = "".join(b.text for b in response.content if b.type == "text")
        input_tokens = response.usage.input_tokens if response.usage else 0
        output_tokens = response.usage.output_tokens if response.usage else 0
        return content, input_tokens, output_tokens

    async def _stream_with_provider(
        self,
        provider: str,
        messages: list[dict],
        system_prompt: str,
        on_text: Callable[[str], None] | None = None,
        api_key: str | None = None,
        **kwargs,
    ) -> AsyncGenerator[str, None]:
        """Dispatch a streaming completion to a specific provider."""
        if provider == "anthropic":
            async for chunk in self._anthropic_stream(messages, system_prompt, on_text, api_key):
                yield chunk
        else:
            async for chunk in self._openai_stream(
                provider, messages, system_prompt, on_text, api_key, **kwargs
            ):
                yield chunk

    async def _openai_stream(
        self,
        provider: str,
        messages: list[dict],
        system_prompt: str,
        on_text: Callable[[str], None] | None = None,
        api_key: str | None = None,
        **kwargs,
    ) -> AsyncGenerator[str, None]:
        """OpenAI-compatible streaming."""
        client = self._get_openai_compatible_client(provider, api_key)
        model = _model_for_provider(provider)

        oai_messages = [{"role": "system", "content": system_prompt}]
        for m in messages:
            oai_messages.append({"role": m["role"], "content": m["content"]})

        temperature = kwargs.get("temperature", 0.1 if provider == "ollama" else None)
        create_kwargs = {
            "model": model,
            "max_tokens": kwargs.get("max_tokens", settings.MAX_TOKENS),
            "messages": oai_messages,
            "stream": True,
        }
        if temperature is not None:
            create_kwargs["temperature"] = temperature

        stream = await client.chat.completions.create(**create_kwargs)
        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                if on_text:
                    on_text(delta.content)
                yield delta.content

    async def _anthropic_stream(
        self,
        messages: list[dict],
        system_prompt: str,
        on_text: Callable[[str], None] | None = None,
        api_key: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """Anthropic streaming."""
        client = self._get_anthropic_client(api_key)
        model = _model_for_provider("anthropic")

        async with client.messages.stream(
            model=model,
            max_tokens=settings.MAX_TOKENS,
            system=system_prompt,
            messages=[{"role": m["role"], "content": m["content"]} for m in messages],
        ) as stream:
            async for text in stream.text_stream:
                if on_text:
                    on_text(text)
                yield text

    # -- Metrics helpers ----------------------------------------------------

    def _record_metrics(self, provider: str, model: str, status: str, duration: float) -> None:
        """Record Prometheus metrics if available."""
        try:
            from app.middleware.metrics import LLM_REQUESTS, LLM_DURATION
            LLM_REQUESTS.labels(provider=provider, model=model, status=status).inc()
            LLM_DURATION.labels(provider=provider, model=model).observe(duration)
        except Exception:
            pass  # Metrics not critical

    # -- Public API ---------------------------------------------------------

    async def complete(
        self,
        messages: list[dict],
        task_type: str = "chat",
        system_prompt: str | None = None,
        byok_provider: str | None = None,
        byok_api_key: str | None = None,
        on_text: Callable[[str], None] | None = None,
        **kwargs,
    ) -> ProviderResult:
        """Non-streaming completion with task-aware routing and automatic fallback.

        Args:
            messages: Chat messages in OpenAI format [{"role": "user", "content": "..."}]
            task_type: Task type for routing (chat, rule_generation, srs_parsing, etc.)
            system_prompt: Override system prompt (defaults to AVNI_SYSTEM_PROMPT)
            byok_provider: BYOK provider name (bypasses routing)
            byok_api_key: BYOK API key
            **kwargs: Extra args passed to provider (temperature, max_tokens, etc.)

        Returns:
            ProviderResult with content, provider info, cost, and latency.

        Raises:
            RuntimeError: If all providers fail or budget exceeded.
        """
        from app.services.claude_client import AVNI_SYSTEM_PROMPT
        effective_system = system_prompt or AVNI_SYSTEM_PROMPT

        # Budget check
        if self._cost_tracker.budget_exceeded():
            raise RuntimeError(
                f"Monthly LLM budget exceeded (${self._cost_tracker.month_total_usd:.2f} "
                f"/ ${settings.LLM_MONTHLY_BUDGET_USD:.2f}). "
                "Contact admin or wait for next month."
            )

        # BYOK: user's own API key bypasses routing
        if byok_provider and byok_api_key:
            logger.info("BYOK complete: provider=%s, task=%s", byok_provider, task_type)
            start = time.time()
            try:
                content, in_tok, out_tok = await self._complete_with_provider(
                    byok_provider, messages, effective_system, api_key=byok_api_key, **kwargs,
                )
                latency = (time.time() - start) * 1000
                model = _model_for_provider(byok_provider)
                self._record_metrics(f"byok_{byok_provider}", model, "success", time.time() - start)
                return ProviderResult(
                    content=content, provider=f"byok_{byok_provider}", model=model,
                    latency_ms=latency, input_tokens=in_tok, output_tokens=out_tok,
                    cost_usd=0.0, fallback_used=False, task_type=task_type,
                )
            except Exception as e:
                self._record_metrics(f"byok_{byok_provider}", "custom", "error", time.time() - start)
                logger.warning("BYOK provider '%s' failed: %s -- falling back", byok_provider, e)

        # Task-aware routing
        providers = self._get_providers_for_task(task_type)
        if not providers:
            raise RuntimeError(
                f"No available providers for task '{task_type}'. "
                "All providers are either unconfigured, circuit-broken, or rate-limited."
            )

        primary_provider = providers[0]
        last_error: Exception | None = None

        for provider in providers:
            model = _model_for_provider(provider)
            start = time.time()
            try:
                # Record rate limit
                rate_limit = self._rate_limits.get(provider)
                if rate_limit:
                    rate_limit.record_request()

                content, in_tok, out_tok = await self._complete_with_provider(
                    provider, messages, effective_system, **kwargs,
                )

                latency = (time.time() - start) * 1000
                self._circuits[provider].record_success()
                self._record_metrics(provider, model, "success", time.time() - start)

                # Cost tracking
                cost = _CostTracker.estimate_cost(provider, model, in_tok, out_tok)
                self._cost_tracker.record(cost)

                fallback_used = provider != primary_provider
                if fallback_used:
                    logger.info(
                        "Task '%s' served by fallback '%s' (primary was '%s')",
                        task_type, provider, primary_provider,
                    )

                return ProviderResult(
                    content=content, provider=provider, model=model,
                    latency_ms=latency, input_tokens=in_tok, output_tokens=out_tok,
                    cost_usd=cost, fallback_used=fallback_used, task_type=task_type,
                )

            except Exception as e:
                duration = time.time() - start
                self._record_metrics(provider, model, "error", duration)
                logger.warning(
                    "Provider '%s' failed for task '%s' (%.1fms): %s -- trying next...",
                    provider, task_type, duration * 1000, e,
                )
                self._circuits[provider].record_failure()
                last_error = e

        raise RuntimeError(f"All providers failed for task '{task_type}'. Last error: {last_error}")

    async def stream(
        self,
        messages: list[dict],
        task_type: str = "chat",
        system_prompt: str | None = None,
        on_text: Callable[[str], None] | None = None,
        byok_provider: str | None = None,
        byok_api_key: str | None = None,
        **kwargs,
    ) -> AsyncGenerator[str, None]:
        """Streaming completion with task-aware routing and automatic fallback.

        If a provider fails during stream setup, tries the next provider.
        If a provider fails mid-stream (after yielding chunks), falls back
        to a non-streaming complete() on the next provider.

        Yields:
            Text chunks as they arrive from the provider.
        """
        from app.services.claude_client import AVNI_SYSTEM_PROMPT
        effective_system = system_prompt or AVNI_SYSTEM_PROMPT

        # Budget check
        if self._cost_tracker.budget_exceeded():
            raise RuntimeError(
                f"Monthly LLM budget exceeded (${self._cost_tracker.month_total_usd:.2f})"
            )

        # BYOK streaming
        if byok_provider and byok_api_key:
            logger.info("BYOK stream: provider=%s, task=%s", byok_provider, task_type)
            start = time.time()
            try:
                async for chunk in self._stream_with_provider(
                    byok_provider, messages, effective_system, on_text,
                    api_key=byok_api_key, **kwargs,
                ):
                    yield chunk
                self._record_metrics(
                    f"byok_{byok_provider}", "custom", "success", time.time() - start
                )
                return
            except Exception as e:
                self._record_metrics(
                    f"byok_{byok_provider}", "custom", "error", time.time() - start
                )
                logger.warning("BYOK stream '%s' failed: %s -- falling back", byok_provider, e)

        # Task-aware routing
        providers = self._get_providers_for_task(task_type)
        if not providers:
            raise RuntimeError(f"No available providers for task '{task_type}'")

        last_error: Exception | None = None

        for provider in providers:
            model = _model_for_provider(provider)
            start = time.time()
            try:
                rate_limit = self._rate_limits.get(provider)
                if rate_limit:
                    rate_limit.record_request()

                yielded_any = False
                async for chunk in self._stream_with_provider(
                    provider, messages, effective_system, on_text, **kwargs,
                ):
                    yielded_any = True
                    yield chunk

                # Stream completed successfully
                self._circuits[provider].record_success()
                self._record_metrics(provider, model, "success", time.time() - start)
                return

            except Exception as e:
                duration = time.time() - start
                self._record_metrics(provider, model, "error", duration)
                logger.warning(
                    "Stream provider '%s' failed for task '%s' (yielded=%s): %s",
                    provider, task_type, yielded_any, e,
                )
                self._circuits[provider].record_failure()
                last_error = e

                if yielded_any:
                    # Mid-stream failure: fall back to non-streaming on remaining providers
                    logger.warning("Mid-stream failure on '%s'; trying non-streaming fallback", provider)
                    remaining = [
                        p for p in providers
                        if p != provider and self._circuits[p].can_attempt()
                    ]
                    for fb_provider in remaining:
                        fb_model = _model_for_provider(fb_provider)
                        fb_start = time.time()
                        try:
                            content, _, _ = await self._complete_with_provider(
                                fb_provider, messages, effective_system, **kwargs,
                            )
                            self._circuits[fb_provider].record_success()
                            self._record_metrics(fb_provider, fb_model, "success", time.time() - fb_start)
                            if on_text:
                                on_text(content)
                            yield content
                            return
                        except Exception as fb_err:
                            self._record_metrics(fb_provider, fb_model, "error", time.time() - fb_start)
                            self._circuits[fb_provider].record_failure()
                            last_error = fb_err
                    raise RuntimeError(
                        f"All providers failed after mid-stream failure for task '{task_type}'. "
                        f"Last error: {last_error}"
                    )

        raise RuntimeError(
            f"All providers failed for task '{task_type}'. Last error: {last_error}"
        )

    # -- Introspection ------------------------------------------------------

    @property
    def month_cost_usd(self) -> float:
        """Current month's cumulative LLM cost."""
        return self._cost_tracker.month_total_usd

    def get_task_routing(self) -> dict[str, list[str]]:
        """Return the current task routing table."""
        return dict(self._task_routing)

    def get_circuit_states(self) -> dict[str, str]:
        """Return circuit breaker states for all providers."""
        return {p: c.state for p, c in self._circuits.items()}

    def get_available_providers(self, task_type: str = "chat") -> list[str]:
        """Return currently available providers for a given task type."""
        return self._get_providers_for_task(task_type)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
provider_chain = ProviderChain()
