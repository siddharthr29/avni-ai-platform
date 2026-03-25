import base64
import logging
import time
from dataclasses import dataclass, field
from typing import AsyncGenerator, Callable

from app.config import settings
from app.middleware.metrics import LLM_REQUESTS, LLM_DURATION

logger = logging.getLogger(__name__)

AVNI_SYSTEM_PROMPT = """You are the Avni Platform Architect — the foremost expert on the Avni field data collection platform (avniproject.org). You have deep knowledge from 18+ production implementations, the complete server/client/webapp source code, and years of implementation experience.

## YOUR EXPERTISE

You are the go-to expert for everything Avni:
- **Bundle Architecture** — You know the exact processing order, JSON structure of every file, and every validation rule the server enforces. You've studied BundleZipFileImporter.java and understand dependency chains.
- **Rule Engine** — You write production-quality JavaScript rules (skip logic, visit scheduling, decisions, validations, eligibility). You know the FormElementStatusBuilder API, RuleCondition fluent API, VisitScheduleBuilder, and declarative rule JSON format.
- **Form Design** — You design forms with proper data types, skip logic, question groups, and validations. You've seen 600+ production forms across 18 organizations.
- **Concept Modeling** — You understand 16,000+ concepts across MCH, WASH, Education, Nutrition, Livelihoods, TB, Sickle Cell, and more. You know the standard UUID registry (Yes, No, Male, Female, SC, ST, OBC).
- **Troubleshooting** — You diagnose sync failures, UUID mismatches, missing form mappings, privilege gaps, and rule errors with surgical precision.
- **SRS to Bundle** — You convert scoping documents into production-ready bundles, asking the right clarifying questions.

## AVNI DATA MODEL

- **SubjectType** — Person, Individual, Household, Group. Defines the entity being tracked. `type` field determines registration form behavior.
- **Program** — Longitudinal tracking (Pregnancy, TB, Nutrition). Subjects enroll/exit. Has colour, eligibility rules, summary rules.
- **EncounterType** — Visit types, either within a Program (ProgramEncounter) or standalone (Encounter). Has eligibility rules.
- **Form** — Collection of FormElementGroups → FormElements → Concepts. formType determines context: IndividualProfile, ProgramEnrolment, ProgramExit, ProgramEncounter, ProgramEncounterCancellation, Encounter, IndividualEncounterCancellation.
- **Concept** — Reusable field definition. dataTypes: Text, Numeric, Date, DateTime, Time, Coded, Notes, Image, ImageV2, Video, Audio, File, PhoneNumber, Location, Duration, QuestionGroup, Subject, Id, GroupAffiliation, NA (for answer concepts). Coded concepts have an answers[] array of {answerConcept, order}. Numeric concepts can have unit, lowAbsolute, highAbsolute, lowNormal, highNormal.
- **FormMapping** — Links a Form to SubjectType + optional Program + optional EncounterType. Determines when/where a form appears.
- **Groups & GroupPrivileges** — User groups (Everyone, Admin, Supervisor, MLHW) with per-entity permissions: ViewSubject, RegisterSubject, EditSubject, VoidSubject, EnrolSubject, ViewEnrolmentDetails, EditEnrolmentDetails, ExitEnrolment, ViewVisit, ScheduleVisit, PerformVisit, EditVisit, CancelVisit, ViewChecklist, EditChecklist.

## BUNDLE FILE ORDER (CRITICAL)

The server processes files in this EXACT dependency order. Violating it causes "Entity not found" errors:
1. organisationConfig.json → 2. addressLevelTypes.json → 3. locations.json → 4. catchments.json
5. subjectTypes.json → 6. operationalSubjectTypes.json
7. programs.json → 8. operationalPrograms.json
9. encounterTypes.json → 10. operationalEncounterTypes.json
11. concepts.json → 12. forms/*.json → 13. formMappings.json
14. individualRelation.json → 15. relationshipType.json → 16. identifierSource.json → 17. checklist.json
18. groups.json → 19. groupRole.json → 20. groupPrivilege.json
21. video.json → 22. reportCard.json → 23. reportDashboard.json → 24. groupDashboards.json
25. translations/ → 26. ruleDependency.json → 27. oldRules/

## RULE WRITING

Rules are JavaScript functions executed on mobile (GraalVM). Available context:
- `params.entity` — The current encounter/enrolment/individual
- `params.formElement` — Current form element (in ViewFilter rules)
- `imports.rulesConfig` — FormElementStatusBuilder, RuleCondition, VisitScheduleBuilder, FormElementStatus
- `imports.common` — createValidationError, utilities
- `imports.moment` — Date library
- `imports.lodash` — Utility library (_)

Rule types: ViewFilter (skip logic), Validation, Decision, VisitSchedule, Checklist, Summary, Eligibility.

**MANDATORY: Before writing any rule, you MUST have concepts.json and the relevant form JSON. UUIDs cannot be guessed.**

## HOW YOU RESPOND

1. **Ask clarifying questions** before generating bundles or rules. Don't guess — ask for: concepts.json, form JSON, SRS data, sector, subject types.
2. **Be precise** — Use exact concept names, correct formTypes, proper UUID references.
3. **Explain boundaries** — Tell users what Avni can and can't do. Don't over-promise.
4. **Debug systematically** — For issues: check bundle order → concept existence → formMapping → privileges → sync status.
5. **Reference real patterns** — You know how Ashwini (6,130 concepts), CInI (1,467 concepts), Goonj, APF Odisha, and 14 other orgs structured their implementations.
6. **Be concise** — Implementers are busy. Give direct answers, not essays.

## RESPONSIBLE AI GUIDELINES

You are operating in a context where real communities and beneficiaries are affected by the systems built on Avni. Follow these principles strictly:

### Safety & Harm Prevention
- **Never generate content** that could harm beneficiaries, field workers, or communities — including discriminatory form designs, biased skip logic, or exclusionary eligibility rules.
- **Never generate executable code** outside of Avni's rule engine context (no shell commands, SQL queries intended for direct execution, or system-level scripts).
- **Never suggest workarounds** that bypass Avni's security model (privileges, user groups, catchment restrictions).

### Acknowledging Uncertainty
- **When you are not sure**, say so explicitly. Phrases like "I believe", "Based on my training data", or "You should verify this with your Avni admin" are encouraged.
- **When RAG context is thin**, acknowledge the gap: "I don't have specific examples from similar implementations. Here's my best understanding, but please verify."
- **Never fabricate UUIDs, concept names, or API endpoints.** If you don't know the exact UUID, tell the user to look it up in their concepts.json or Avni admin.

### Privacy & Data Protection
- **Never ask users to share** beneficiary-level personally identifiable information (names, Aadhaar numbers, phone numbers, health records) in chat.
- **If a user shares PII**, do not repeat it back. Respond to the intent without echoing the sensitive data.
- **Never store or reference** specific beneficiary data across sessions. Each conversation should treat beneficiary details as ephemeral.

### No Assumptions About Beneficiary Data
- **Never assume** demographic details, health conditions, or socioeconomic status of beneficiaries based on the organisation's sector.
- **Never hardcode** caste categories, gender options, or disability types without the implementor explicitly specifying them.
- **Always recommend** that coded concepts for sensitive categories (caste, religion, disability) be defined by the implementing organisation based on their local context and government guidelines.

### Transparency
- **Be transparent** about what you can and cannot do. If a task requires Avni server access you don't have, say so.
- **Cite your sources** when referencing specific implementation patterns: "Based on the Ashwini MCH implementation..." rather than presenting knowledge as universal truth."""


FALLBACK_ORDER = ["openai", "ollama", "cerebras", "groq", "gemini", "anthropic"]

# Global semaphore to limit concurrent LLM requests (prevents Ollama queue explosion)
import asyncio as _asyncio
_llm_semaphore: _asyncio.Semaphore | None = None


def get_llm_semaphore() -> _asyncio.Semaphore:
    """Lazy-init semaphore (must be created inside an event loop)."""
    global _llm_semaphore
    if _llm_semaphore is None:
        _llm_semaphore = _asyncio.Semaphore(settings.LLM_CONCURRENCY_LIMIT)
    return _llm_semaphore


@dataclass
class CircuitState:
    """Per-provider circuit breaker state.

    States:
      closed    — normal operation, requests flow through
      open      — provider is broken, requests are blocked
      half_open — recovery window, one test request allowed
    """

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
                "Circuit breaker OPEN for provider '%s' after %d consecutive failures",
                self.provider,
                self.failures,
            )

    def record_success(self) -> None:
        if self.state != "closed":
            logger.info(
                "Circuit breaker CLOSED for provider '%s' (recovered from %s)",
                self.provider,
                self.state,
            )
        self.failures = 0
        self.state = "closed"

    def can_attempt(self) -> bool:
        if self.state == "closed":
            return True
        if self.state == "open":
            elapsed = time.time() - self.last_failure_time
            if elapsed > self.RECOVERY_TIMEOUT:
                self.state = "half_open"
                logger.info(
                    "Circuit breaker HALF-OPEN for provider '%s' (%.0fs elapsed, allowing test request)",
                    self.provider,
                    elapsed,
                )
                return True
            return False
        # half_open — allow one test request
        return True


class LLMClient:
    """Unified LLM client supporting Ollama (self-hosted), Groq (free), and Anthropic (production).

    Provider priority: ollama (no API key needed) > groq (free tier) > anthropic (paid)

    Circuit breaker: After 3 consecutive failures a provider is marked "open" (broken)
    for 60 seconds.  Requests automatically fall back to the next available provider
    in order: ollama -> groq -> anthropic.  After 60s one test request is allowed
    ("half-open"); if it succeeds the circuit closes back to normal.
    """

    def __init__(self) -> None:
        self._groq_client = None
        self._cerebras_client = None
        self._gemini_client = None
        self._anthropic_client = None
        self._ollama_client = None
        self._openai_client = None
        self._circuits: dict[str, CircuitState] = {
            p: CircuitState(provider=p) for p in FALLBACK_ORDER
        }

    @property
    def provider(self) -> str:
        return settings.LLM_PROVIDER

    # ── Ollama (self-hosted, NO API key) ──────────────────────────────

    def _get_ollama_client(self):
        if self._ollama_client is None:
            from openai import AsyncOpenAI
            self._ollama_client = AsyncOpenAI(
                api_key="ollama",  # Ollama ignores this but openai lib requires it
                base_url=settings.OLLAMA_BASE_URL,
            )
        return self._ollama_client

    async def _ollama_stream_chat(
        self,
        messages: list[dict],
        system_prompt: str,
        on_text: Callable[[str], None] | None = None,
    ) -> AsyncGenerator[str, None]:
        client = self._get_ollama_client()
        oai_messages = [{"role": "system", "content": system_prompt}]
        for m in messages:
            oai_messages.append({"role": m["role"], "content": m["content"]})

        stream = await client.chat.completions.create(
            model=settings.OLLAMA_MODEL,
            max_tokens=settings.MAX_TOKENS,
            messages=oai_messages,
            stream=True,
            temperature=0.1,  # Low temp for deterministic code generation
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                if on_text:
                    on_text(delta.content)
                yield delta.content

    async def _ollama_complete(
        self,
        messages: list[dict],
        system_prompt: str,
    ) -> str:
        client = self._get_ollama_client()
        oai_messages = [{"role": "system", "content": system_prompt}]
        for m in messages:
            oai_messages.append({"role": m["role"], "content": m["content"]})

        response = await client.chat.completions.create(
            model=settings.OLLAMA_MODEL,
            max_tokens=settings.MAX_TOKENS,
            messages=oai_messages,
            temperature=0.1,
        )
        return response.choices[0].message.content or ""

    async def _ollama_complete_with_vision(
        self,
        messages: list[dict],
        system_prompt: str,
        image_data: bytes | None = None,
        image_media_type: str = "image/jpeg",
    ) -> str:
        client = self._get_ollama_client()
        oai_messages = [{"role": "system", "content": system_prompt}]

        for msg in messages:
            if msg["role"] == "user" and msg is messages[-1] and image_data is not None:
                b64 = base64.b64encode(image_data).decode("utf-8")
                content = [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{image_media_type};base64,{b64}"
                        },
                    },
                    {"type": "text", "text": msg["content"]},
                ]
                oai_messages.append({"role": "user", "content": content})
            else:
                oai_messages.append({"role": msg["role"], "content": msg["content"]})

        response = await client.chat.completions.create(
            model=settings.OLLAMA_VISION_MODEL,
            max_tokens=settings.MAX_TOKENS,
            messages=oai_messages,
            temperature=0.1,
        )
        return response.choices[0].message.content or ""

    # ── Groq (OpenAI-compatible) ──────────────────────────────────────

    def _get_groq_client(self):
        if self._groq_client is None:
            if not settings.GROQ_API_KEY:
                raise ValueError(
                    "GROQ_API_KEY is not set. Get a free key at https://console.groq.com"
                )
            from openai import AsyncOpenAI
            self._groq_client = AsyncOpenAI(
                api_key=settings.GROQ_API_KEY,
                base_url="https://api.groq.com/openai/v1",
            )
        return self._groq_client

    async def _groq_stream_chat(
        self,
        messages: list[dict],
        system_prompt: str,
        on_text: Callable[[str], None] | None = None,
    ) -> AsyncGenerator[str, None]:
        client = self._get_groq_client()
        oai_messages = [{"role": "system", "content": system_prompt}]
        for m in messages:
            oai_messages.append({"role": m["role"], "content": m["content"]})

        stream = await client.chat.completions.create(
            model=settings.GROQ_MODEL,
            max_tokens=settings.MAX_TOKENS,
            messages=oai_messages,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                if on_text:
                    on_text(delta.content)
                yield delta.content

    async def _groq_complete(
        self,
        messages: list[dict],
        system_prompt: str,
    ) -> str:
        client = self._get_groq_client()
        oai_messages = [{"role": "system", "content": system_prompt}]
        for m in messages:
            oai_messages.append({"role": m["role"], "content": m["content"]})

        response = await client.chat.completions.create(
            model=settings.GROQ_MODEL,
            max_tokens=settings.MAX_TOKENS,
            messages=oai_messages,
        )
        return response.choices[0].message.content or ""

    async def _groq_complete_with_vision(
        self,
        messages: list[dict],
        system_prompt: str,
        image_data: bytes | None = None,
        image_media_type: str = "image/jpeg",
    ) -> str:
        client = self._get_groq_client()
        oai_messages = [{"role": "system", "content": system_prompt}]

        for msg in messages:
            if msg["role"] == "user" and msg is messages[-1] and image_data is not None:
                b64 = base64.b64encode(image_data).decode("utf-8")
                content = [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{image_media_type};base64,{b64}"
                        },
                    },
                    {"type": "text", "text": msg["content"]},
                ]
                oai_messages.append({"role": "user", "content": content})
            else:
                oai_messages.append({"role": msg["role"], "content": msg["content"]})

        response = await client.chat.completions.create(
            model=settings.GROQ_VISION_MODEL,
            max_tokens=settings.MAX_TOKENS,
            messages=oai_messages,
        )
        return response.choices[0].message.content or ""

    # ── Cerebras (OpenAI-compatible, ultra-fast inference) ──────────────

    def _get_cerebras_client(self):
        if self._cerebras_client is None:
            if not settings.CEREBRAS_API_KEY:
                raise ValueError(
                    "CEREBRAS_API_KEY is not set. Get a free key at https://cloud.cerebras.ai"
                )
            from openai import AsyncOpenAI
            self._cerebras_client = AsyncOpenAI(
                api_key=settings.CEREBRAS_API_KEY,
                base_url="https://api.cerebras.ai/v1",
            )
        return self._cerebras_client

    async def _cerebras_stream_chat(
        self,
        messages: list[dict],
        system_prompt: str,
        on_text: Callable[[str], None] | None = None,
    ) -> AsyncGenerator[str, None]:
        client = self._get_cerebras_client()
        oai_messages = [{"role": "system", "content": system_prompt}]
        for m in messages:
            oai_messages.append({"role": m["role"], "content": m["content"]})

        stream = await client.chat.completions.create(
            model=settings.CEREBRAS_MODEL,
            max_tokens=settings.MAX_TOKENS,
            messages=oai_messages,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                if on_text:
                    on_text(delta.content)
                yield delta.content

    async def _cerebras_complete(
        self,
        messages: list[dict],
        system_prompt: str,
    ) -> str:
        client = self._get_cerebras_client()
        oai_messages = [{"role": "system", "content": system_prompt}]
        for m in messages:
            oai_messages.append({"role": m["role"], "content": m["content"]})

        response = await client.chat.completions.create(
            model=settings.CEREBRAS_MODEL,
            max_tokens=settings.MAX_TOKENS,
            messages=oai_messages,
        )
        return response.choices[0].message.content or ""

    async def _cerebras_complete_with_vision(
        self,
        messages: list[dict],
        system_prompt: str,
        image_data: bytes | None = None,
        image_media_type: str = "image/jpeg",
    ) -> str:
        # Cerebras does not support vision — fall through to next provider
        raise NotImplementedError("Cerebras does not support vision models")

    # ── Gemini (OpenAI-compatible endpoint) ───────────────────────────

    def _get_gemini_client(self):
        if self._gemini_client is None:
            if not settings.GEMINI_API_KEY:
                raise ValueError(
                    "GEMINI_API_KEY is not set. Get a free key at https://aistudio.google.com"
                )
            from openai import AsyncOpenAI
            self._gemini_client = AsyncOpenAI(
                api_key=settings.GEMINI_API_KEY,
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            )
        return self._gemini_client

    async def _gemini_stream_chat(
        self,
        messages: list[dict],
        system_prompt: str,
        on_text: Callable[[str], None] | None = None,
    ) -> AsyncGenerator[str, None]:
        client = self._get_gemini_client()
        oai_messages = [{"role": "system", "content": system_prompt}]
        for m in messages:
            oai_messages.append({"role": m["role"], "content": m["content"]})

        stream = await client.chat.completions.create(
            model=settings.GEMINI_MODEL,
            max_tokens=settings.MAX_TOKENS,
            messages=oai_messages,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                if on_text:
                    on_text(delta.content)
                yield delta.content

    async def _gemini_complete(
        self,
        messages: list[dict],
        system_prompt: str,
    ) -> str:
        client = self._get_gemini_client()
        oai_messages = [{"role": "system", "content": system_prompt}]
        for m in messages:
            oai_messages.append({"role": m["role"], "content": m["content"]})

        response = await client.chat.completions.create(
            model=settings.GEMINI_MODEL,
            max_tokens=settings.MAX_TOKENS,
            messages=oai_messages,
        )
        return response.choices[0].message.content or ""

    async def _gemini_complete_with_vision(
        self,
        messages: list[dict],
        system_prompt: str,
        image_data: bytes | None = None,
        image_media_type: str = "image/jpeg",
    ) -> str:
        client = self._get_gemini_client()
        oai_messages = [{"role": "system", "content": system_prompt}]

        for msg in messages:
            if msg["role"] == "user" and msg is messages[-1] and image_data is not None:
                b64 = base64.b64encode(image_data).decode("utf-8")
                content = [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{image_media_type};base64,{b64}"
                        },
                    },
                    {"type": "text", "text": msg["content"]},
                ]
                oai_messages.append({"role": "user", "content": content})
            else:
                oai_messages.append({"role": msg["role"], "content": msg["content"]})

        response = await client.chat.completions.create(
            model=settings.GEMINI_VISION_MODEL,
            max_tokens=settings.MAX_TOKENS,
            messages=oai_messages,
        )
        return response.choices[0].message.content or ""

    # ── OpenAI ─────────────────────────────────────────────────────────

    def _get_openai_client(self):
        if self._openai_client is None:
            if not settings.OPENAI_API_KEY:
                raise ValueError(
                    "OPENAI_API_KEY is not set. Please set it in your .env file."
                )
            from openai import AsyncOpenAI
            self._openai_client = AsyncOpenAI(
                api_key=settings.OPENAI_API_KEY,
            )
        return self._openai_client

    async def _openai_stream_chat(
        self,
        messages: list[dict],
        system_prompt: str,
        on_text: Callable[[str], None] | None = None,
    ) -> AsyncGenerator[str, None]:
        client = self._get_openai_client()
        oai_messages = [{"role": "system", "content": system_prompt}]
        for m in messages:
            oai_messages.append({"role": m["role"], "content": m["content"]})

        stream = await client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            max_tokens=settings.MAX_TOKENS,
            messages=oai_messages,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                if on_text:
                    on_text(delta.content)
                yield delta.content

    async def _openai_complete(
        self,
        messages: list[dict],
        system_prompt: str,
    ) -> str:
        client = self._get_openai_client()
        oai_messages = [{"role": "system", "content": system_prompt}]
        for m in messages:
            oai_messages.append({"role": m["role"], "content": m["content"]})

        response = await client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            max_tokens=settings.MAX_TOKENS,
            messages=oai_messages,
        )
        return response.choices[0].message.content or ""

    async def _openai_complete_with_vision(
        self,
        messages: list[dict],
        system_prompt: str,
        image_data: bytes | None = None,
        image_media_type: str = "image/jpeg",
    ) -> str:
        client = self._get_openai_client()
        oai_messages = [{"role": "system", "content": system_prompt}]

        for msg in messages:
            if msg["role"] == "user" and msg is messages[-1] and image_data is not None:
                b64 = base64.b64encode(image_data).decode("utf-8")
                content = [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{image_media_type};base64,{b64}"
                        },
                    },
                    {"type": "text", "text": msg["content"]},
                ]
                oai_messages.append({"role": "user", "content": content})
            else:
                oai_messages.append({"role": msg["role"], "content": msg["content"]})

        response = await client.chat.completions.create(
            model=settings.OPENAI_VISION_MODEL,
            max_tokens=settings.MAX_TOKENS,
            messages=oai_messages,
        )
        return response.choices[0].message.content or ""

    # ── Anthropic ─────────────────────────────────────────────────────

    def _get_anthropic_client(self):
        if self._anthropic_client is None:
            if not settings.ANTHROPIC_API_KEY:
                raise ValueError(
                    "ANTHROPIC_API_KEY is not set. Please set it in your .env file."
                )
            import anthropic
            self._anthropic_client = anthropic.AsyncAnthropic(
                api_key=settings.ANTHROPIC_API_KEY
            )
        return self._anthropic_client

    async def _anthropic_stream_chat(
        self,
        messages: list[dict],
        system_prompt: str,
        on_text: Callable[[str], None] | None = None,
    ) -> AsyncGenerator[str, None]:
        client = self._get_anthropic_client()
        async with client.messages.stream(
            model=settings.CLAUDE_MODEL,
            max_tokens=settings.MAX_TOKENS,
            system=system_prompt,
            messages=messages,
        ) as stream:
            async for text in stream.text_stream:
                if on_text:
                    on_text(text)
                yield text

    async def _anthropic_complete(
        self,
        messages: list[dict],
        system_prompt: str,
    ) -> str:
        client = self._get_anthropic_client()
        response = await client.messages.create(
            model=settings.CLAUDE_MODEL,
            max_tokens=settings.MAX_TOKENS,
            system=system_prompt,
            messages=messages,
        )
        text_parts = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
        return "".join(text_parts)

    async def _anthropic_complete_with_vision(
        self,
        messages: list[dict],
        system_prompt: str,
        image_data: bytes | None = None,
        image_media_type: str = "image/jpeg",
    ) -> str:
        client = self._get_anthropic_client()
        if image_data is not None:
            b64_image = base64.b64encode(image_data).decode("utf-8")
            augmented_messages = []
            for msg in messages:
                if msg["role"] == "user" and msg is messages[-1]:
                    content_blocks = [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": image_media_type,
                                "data": b64_image,
                            },
                        },
                    ]
                    if isinstance(msg["content"], str):
                        content_blocks.append(
                            {"type": "text", "text": msg["content"]}
                        )
                    elif isinstance(msg["content"], list):
                        content_blocks.extend(msg["content"])
                    augmented_messages.append(
                        {"role": "user", "content": content_blocks}
                    )
                else:
                    augmented_messages.append(msg)
        else:
            augmented_messages = messages

        response = await client.messages.create(
            model=settings.CLAUDE_MODEL,
            max_tokens=settings.MAX_TOKENS,
            system=system_prompt,
            messages=augmented_messages,
        )
        text_parts = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
        return "".join(text_parts)

    # ── Circuit breaker helpers ─────────────────────────────────────

    @staticmethod
    def _provider_is_configured(provider: str) -> bool:
        """Check whether the provider has the necessary credentials / setup."""
        if provider == "ollama":
            return True  # Self-hosted, always "configured"
        if provider == "groq":
            return bool(settings.GROQ_API_KEY)
        if provider == "cerebras":
            return bool(settings.CEREBRAS_API_KEY)
        if provider == "gemini":
            return bool(settings.GEMINI_API_KEY)
        if provider == "openai":
            return bool(settings.OPENAI_API_KEY)
        if provider == "anthropic":
            return bool(settings.ANTHROPIC_API_KEY)
        return False

    def _get_available_providers(self) -> list[str]:
        """Return providers whose circuits allow an attempt, in fallback order.

        The configured primary provider (settings.LLM_PROVIDER) always comes
        first; the rest follow the standard fallback order.
        """
        primary = settings.LLM_PROVIDER
        ordered = [primary] + [p for p in FALLBACK_ORDER if p != primary]

        available: list[str] = []
        for p in ordered:
            if not self._provider_is_configured(p):
                continue
            circuit = self._circuits[p]
            if circuit.can_attempt():
                available.append(p)
        return available

    def _model_for_provider(self, provider: str) -> str:
        """Return the model name for a given provider (for metrics)."""
        if provider == "ollama":
            return settings.OLLAMA_MODEL
        if provider == "groq":
            return settings.GROQ_MODEL
        if provider == "cerebras":
            return settings.CEREBRAS_MODEL
        if provider == "gemini":
            return settings.GEMINI_MODEL
        if provider == "openai":
            return settings.OPENAI_MODEL
        return settings.CLAUDE_MODEL

    async def _complete_with_provider(
        self, provider: str, messages: list[dict], system_prompt: str
    ) -> str:
        """Dispatch a non-streaming completion to a specific provider."""
        if provider == "ollama":
            return await self._ollama_complete(messages, system_prompt)
        elif provider == "groq":
            return await self._groq_complete(messages, system_prompt)
        elif provider == "cerebras":
            return await self._cerebras_complete(messages, system_prompt)
        elif provider == "gemini":
            return await self._gemini_complete(messages, system_prompt)
        elif provider == "openai":
            return await self._openai_complete(messages, system_prompt)
        else:
            return await self._anthropic_complete(messages, system_prompt)

    async def _stream_with_provider(
        self,
        provider: str,
        messages: list[dict],
        system_prompt: str,
        on_text: Callable[[str], None] | None = None,
    ) -> AsyncGenerator[str, None]:
        """Dispatch a streaming completion to a specific provider."""
        if provider == "ollama":
            async for chunk in self._ollama_stream_chat(messages, system_prompt, on_text):
                yield chunk
        elif provider == "groq":
            async for chunk in self._groq_stream_chat(messages, system_prompt, on_text):
                yield chunk
        elif provider == "cerebras":
            async for chunk in self._cerebras_stream_chat(messages, system_prompt, on_text):
                yield chunk
        elif provider == "gemini":
            async for chunk in self._gemini_stream_chat(messages, system_prompt, on_text):
                yield chunk
        elif provider == "openai":
            async for chunk in self._openai_stream_chat(messages, system_prompt, on_text):
                yield chunk
        else:
            async for chunk in self._anthropic_stream_chat(messages, system_prompt, on_text):
                yield chunk

    async def _complete_vision_with_provider(
        self,
        provider: str,
        messages: list[dict],
        system_prompt: str,
        image_data: bytes | None,
        image_media_type: str,
    ) -> str:
        """Dispatch a vision completion to a specific provider."""
        if provider == "ollama":
            return await self._ollama_complete_with_vision(
                messages, system_prompt, image_data, image_media_type
            )
        elif provider == "groq":
            return await self._groq_complete_with_vision(
                messages, system_prompt, image_data, image_media_type
            )
        elif provider == "cerebras":
            return await self._cerebras_complete_with_vision(
                messages, system_prompt, image_data, image_media_type
            )
        elif provider == "gemini":
            return await self._gemini_complete_with_vision(
                messages, system_prompt, image_data, image_media_type
            )
        elif provider == "openai":
            return await self._openai_complete_with_vision(
                messages, system_prompt, image_data, image_media_type
            )
        else:
            return await self._anthropic_complete_with_vision(
                messages, system_prompt, image_data, image_media_type
            )

    # ── BYOK (Bring Your Own Key) support ──────────────────────────

    BYOK_PROVIDER_URLS = {
        "groq": "https://api.groq.com/openai/v1",
        "cerebras": "https://api.cerebras.ai/v1",
        "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "openai": "https://api.openai.com/v1",
    }

    BYOK_DEFAULT_MODELS = {
        "groq": "llama-3.3-70b-versatile",
        "cerebras": "llama-3.3-70b",
        "gemini": "gemini-2.0-flash",
        "openai": "gpt-4o",
        "anthropic": "claude-sonnet-4-20250514",
    }

    async def _byok_stream_chat(
        self,
        provider: str,
        api_key: str,
        messages: list[dict],
        system_prompt: str,
        on_text: Callable[[str], None] | None = None,
        model: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream chat using a user-provided API key (BYOK). Bypasses circuit breaker."""
        effective_model = model or self.BYOK_DEFAULT_MODELS.get(provider, "")

        if provider == "anthropic":
            import anthropic
            client = anthropic.AsyncAnthropic(api_key=api_key)
            stream = await client.messages.create(
                model=effective_model,
                max_tokens=settings.MAX_TOKENS,
                system=system_prompt,
                messages=[{"role": m["role"], "content": m["content"]} for m in messages],
                stream=True,
            )
            async for event in stream:
                if event.type == "content_block_delta" and hasattr(event.delta, "text"):
                    if on_text:
                        on_text(event.delta.text)
                    yield event.delta.text
        else:
            # OpenAI-compatible providers (groq, cerebras, gemini, openai)
            base_url = self.BYOK_PROVIDER_URLS.get(provider)
            if not base_url:
                raise ValueError(f"Unsupported BYOK provider: {provider}")
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=api_key, base_url=base_url)
            oai_messages = [{"role": "system", "content": system_prompt}]
            for m in messages:
                oai_messages.append({"role": m["role"], "content": m["content"]})
            stream = await client.chat.completions.create(
                model=effective_model,
                max_tokens=settings.MAX_TOKENS,
                messages=oai_messages,
                stream=True,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    if on_text:
                        on_text(delta.content)
                    yield delta.content

    async def _byok_complete(
        self,
        provider: str,
        api_key: str,
        messages: list[dict],
        system_prompt: str,
        model: str | None = None,
    ) -> str:
        """Non-streaming completion using a user-provided API key (BYOK)."""
        effective_model = model or self.BYOK_DEFAULT_MODELS.get(provider, "")

        if provider == "anthropic":
            import anthropic
            client = anthropic.AsyncAnthropic(api_key=api_key)
            response = await client.messages.create(
                model=effective_model,
                max_tokens=settings.MAX_TOKENS,
                system=system_prompt,
                messages=[{"role": m["role"], "content": m["content"]} for m in messages],
            )
            return "".join(b.text for b in response.content if b.type == "text")
        else:
            base_url = self.BYOK_PROVIDER_URLS.get(provider)
            if not base_url:
                raise ValueError(f"Unsupported BYOK provider: {provider}")
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=api_key, base_url=base_url)
            oai_messages = [{"role": "system", "content": system_prompt}]
            for m in messages:
                oai_messages.append({"role": m["role"], "content": m["content"]})
            response = await client.chat.completions.create(
                model=effective_model,
                max_tokens=settings.MAX_TOKENS,
                messages=oai_messages,
            )
            return response.choices[0].message.content or ""

    # ── Public API (delegates to ProviderChain with backward compat) ──

    async def complete(
        self,
        messages: list[dict],
        system_prompt: str | None = None,
        byok_provider: str | None = None,
        byok_api_key: str | None = None,
        task_type: str = "chat",
    ) -> str:
        """Non-streaming completion with automatic failover.

        Delegates to ProviderChain for task-aware routing, cost tracking,
        and budget enforcement. Returns plain string for backward compatibility.

        Args:
            messages: Chat messages [{"role": "user", "content": "..."}]
            system_prompt: Override system prompt (defaults to AVNI_SYSTEM_PROMPT)
            byok_provider: BYOK provider name (bypasses routing)
            byok_api_key: BYOK API key
            task_type: Task type for routing (chat, rule_generation, srs_parsing, etc.)

        Returns:
            The LLM response content as a string.
        """
        from app.services.provider_chain import provider_chain

        result = await provider_chain.complete(
            messages=messages,
            task_type=task_type,
            system_prompt=system_prompt,
            byok_provider=byok_provider,
            byok_api_key=byok_api_key,
        )
        # Store last result for callers that want cost/provider info
        self._last_result = result
        return result.content

    async def complete_with_result(
        self,
        messages: list[dict],
        system_prompt: str | None = None,
        byok_provider: str | None = None,
        byok_api_key: str | None = None,
        task_type: str = "chat",
    ):
        """Like complete() but returns the full ProviderResult with cost/latency info."""
        from app.services.provider_chain import provider_chain

        result = await provider_chain.complete(
            messages=messages,
            task_type=task_type,
            system_prompt=system_prompt,
            byok_provider=byok_provider,
            byok_api_key=byok_api_key,
        )
        self._last_result = result
        return result

    @property
    def last_result(self):
        """Access the ProviderResult from the most recent complete/stream call."""
        return getattr(self, "_last_result", None)

    async def stream_chat(
        self,
        messages: list[dict],
        system_prompt: str | None = None,
        on_text: Callable[[str], None] | None = None,
        byok_provider: str | None = None,
        byok_api_key: str | None = None,
        task_type: str = "chat",
    ) -> AsyncGenerator[str, None]:
        """Stream a chat response with task-aware routing and automatic failover.

        Delegates to ProviderChain for routing. If a provider fails during
        streaming setup, falls back to the next provider. If a provider fails
        mid-stream, falls back to non-streaming on the next provider.

        Args:
            messages: Chat messages [{"role": "user", "content": "..."}]
            system_prompt: Override system prompt (defaults to AVNI_SYSTEM_PROMPT)
            on_text: Callback for each text chunk
            byok_provider: BYOK provider name (bypasses routing)
            byok_api_key: BYOK API key
            task_type: Task type for routing (chat, rule_generation, etc.)

        Yields:
            Text chunks as they arrive from the LLM provider.
        """
        from app.services.provider_chain import provider_chain

        async with get_llm_semaphore():
            async for chunk in provider_chain.stream(
                messages=messages,
                task_type=task_type,
                system_prompt=system_prompt,
                on_text=on_text,
                byok_provider=byok_provider,
                byok_api_key=byok_api_key,
            ):
                yield chunk

    async def complete_with_vision(
        self,
        messages: list[dict],
        system_prompt: str | None = None,
        image_data: bytes | None = None,
        image_media_type: str = "image/jpeg",
    ) -> str:
        """Completion with an image attachment, with automatic failover."""
        effective_system = system_prompt or AVNI_SYSTEM_PROMPT
        providers = self._get_available_providers()
        if not providers:
            raise RuntimeError("All LLM providers are unavailable (circuits open)")

        last_error: Exception | None = None
        for provider in providers:
            model = self._model_for_provider(provider)
            start = time.time()
            try:
                result = await self._complete_vision_with_provider(
                    provider, messages, effective_system, image_data, image_media_type
                )
                self._circuits[provider].record_success()
                LLM_REQUESTS.labels(provider=provider, model=model, status="success").inc()
                if provider != settings.LLM_PROVIDER:
                    logger.info("LLM vision request served by fallback provider '%s'", provider)
                return result
            except Exception as e:
                LLM_REQUESTS.labels(provider=provider, model=model, status="error").inc()
                logger.warning(
                    "LLM vision provider '%s' failed: %s — trying next provider...", provider, e
                )
                self._circuits[provider].record_failure()
                last_error = e
            finally:
                LLM_DURATION.labels(provider=provider, model=model).observe(time.time() - start)

        raise RuntimeError(f"All LLM vision providers failed. Last error: {last_error}")


# Backward-compatible singleton
claude_client = LLMClient()
