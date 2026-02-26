import base64
import logging
from typing import AsyncGenerator, Callable

import anthropic

from app.config import settings

logger = logging.getLogger(__name__)

AVNI_SYSTEM_PROMPT = """You are an AI assistant for the Avni field data collection platform (avniproject.org).

Avni is an open-source platform used by NGOs and government programs across sectors including:
- Maternal & Child Health (MCH)
- Water & Sanitation (WASH)
- Education
- Sports development
- Livelihoods
- Nutrition (malnutrition screening, community-based management)
- Tuberculosis (TB) programs

You help implementers with:
1. **Bundle Generation** - Creating implementation bundles from SRS (Scoping & Requirement Specification) documents. An Avni bundle is a zip file containing JSON files for all configuration entities.
2. **Rule Writing** - JavaScript rules for skip logic, calculated fields, validation, visit scheduling, and eligibility.
3. **Voice Data Capture** - Mapping spoken transcripts to form fields for hands-free data collection.
4. **Image Data Extraction** - Extracting structured data from photos of registers, forms, or records.
5. **Troubleshooting** - Diagnosing configuration issues, sync failures, and data quality problems.
6. **General Questions** - Explaining Avni concepts, best practices, and implementation patterns.

You deeply understand the Avni data model:
- **SubjectTypes** - Person, Individual, Household, Group (the entity being tracked)
- **Programs** - Longitudinal tracking workflows (e.g., Pregnancy Program, TB Program)
- **EncounterTypes** - Scheduled or unscheduled visit types within programs or standalone
- **Forms** - Collections of FormElementGroups containing FormElements with Concepts
- **Concepts** - Reusable field definitions with data types: Text, Numeric, Date, Coded (single/multi select), Notes, Time, Image, etc.
- **FormMappings** - Links between forms and SubjectType + Program + EncounterType
- **Groups & GroupPrivileges** - User groups with granular permissions per entity type

The SRS scoping document has 9 tabs:
1. Help & Status Tracker
2. Program Summary - Location, data systems, rollout date
3. Program Detail - Per program: name, objective, eligibility, entry/exit
4. User Persona - User types, descriptions, counts
5. W3H - What (activities), When (timing), Who (which user), How (mobile/web)
6. Forms - Field Name, Data Type, Mandatory, validation, units, select options, skip logic
7. Visit Scheduling - Frequency, conditions, overdue rules
8. Offline Dashboard Cards - Card name, logic, user type
9. Permissions - Per form x per user group: View, Register, Edit, Void

Bundle file dependency order (critical for upload):
1. addressLevelTypes.json
2. subjectTypes.json
3. operationalSubjectTypes.json
4. encounterTypes.json
5. operationalEncounterTypes.json
6. programs.json
7. operationalPrograms.json
8. concepts.json
9. forms/*.json (all form files)
10. formMappings.json
11. groups.json
12. groupPrivilege.json

Keep responses concise and actionable. When generating rules, always ask for concepts.json and form JSON first so you can reference correct UUIDs and concept names."""


class ClaudeClient:
    def __init__(self) -> None:
        self._client: anthropic.AsyncAnthropic | None = None

    @property
    def client(self) -> anthropic.AsyncAnthropic:
        if self._client is None:
            if not settings.ANTHROPIC_API_KEY:
                raise ValueError(
                    "ANTHROPIC_API_KEY is not set. Please set it in your .env file."
                )
            self._client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        return self._client

    async def stream_chat(
        self,
        messages: list[dict],
        system_prompt: str | None = None,
        on_text: Callable[[str], None] | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream a chat response, yielding text chunks as they arrive."""
        effective_system = system_prompt or AVNI_SYSTEM_PROMPT

        async with self.client.messages.stream(
            model=settings.CLAUDE_MODEL,
            max_tokens=settings.MAX_TOKENS,
            system=effective_system,
            messages=messages,
        ) as stream:
            async for text in stream.text_stream:
                if on_text:
                    on_text(text)
                yield text

    async def complete(
        self,
        messages: list[dict],
        system_prompt: str | None = None,
    ) -> str:
        """Non-streaming completion. Returns the full response text."""
        effective_system = system_prompt or AVNI_SYSTEM_PROMPT

        response = await self.client.messages.create(
            model=settings.CLAUDE_MODEL,
            max_tokens=settings.MAX_TOKENS,
            system=effective_system,
            messages=messages,
        )

        text_parts = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
        return "".join(text_parts)

    async def complete_with_vision(
        self,
        messages: list[dict],
        system_prompt: str | None = None,
        image_data: bytes | None = None,
        image_media_type: str = "image/jpeg",
    ) -> str:
        """Completion with an image attachment for vision tasks."""
        effective_system = system_prompt or AVNI_SYSTEM_PROMPT

        if image_data is not None:
            b64_image = base64.b64encode(image_data).decode("utf-8")
            # Prepend the image to the last user message
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

        response = await self.client.messages.create(
            model=settings.CLAUDE_MODEL,
            max_tokens=settings.MAX_TOKENS,
            system=effective_system,
            messages=augmented_messages,
        )

        text_parts = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
        return "".join(text_parts)


claude_client = ClaudeClient()
