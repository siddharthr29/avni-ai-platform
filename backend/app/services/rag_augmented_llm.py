"""RAG-Augmented LLM service for Avni.

Wraps the self-hosted LLM with RAG context injection. Before every LLM call,
relevant Avni knowledge (concepts, forms, rules, patterns) is retrieved from
the vector store and injected into the prompt. This makes even a small 7B model
output production-quality Avni bundles and rules.

Architecture:
    User query → Intent detection → RAG retrieval → Context injection → LLM → Validated output

Usage:
    from app.services.rag_augmented_llm import rag_llm

    # Rule generation with RAG context
    result = await rag_llm.generate_with_context(
        query="Write a skip logic rule to show 'Place of delivery' when 'Type of delivery' is 'Institutional'",
        task_type="rule",
        extra_context={"form_type": "ProgramEncounter", "concepts_json": [...]}
    )
"""

import json
import logging
from typing import Any, AsyncGenerator, Callable

from app.services.claude_client import claude_client, AVNI_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

# Task-specific retrieval collections
TASK_COLLECTIONS = {
    "rule": ["rules", "concepts"],
    "bundle": ["forms", "concepts", "srs_examples"],
    "concept": ["concepts"],
    "form": ["forms", "concepts"],
    "support": ["support", "knowledge"],
    "general": None,  # Search all
}

# Context injection templates
CONTEXT_TEMPLATES = {
    "rule": (
        "\n\n## REFERENCE: Real Avni Rule Examples\n"
        "Use these EXACT patterns for your output. Match the JSON structure precisely.\n\n"
        "{rag_context}\n"
    ),
    "bundle": (
        "\n\n## REFERENCE: Real Avni Bundle Patterns\n"
        "Use these as examples for correct JSON structure, field names, and UUIDs.\n\n"
        "{rag_context}\n"
    ),
    "concept": (
        "\n\n## REFERENCE: Existing Avni Concepts\n"
        "Reuse these concepts where applicable. Match the exact JSON format.\n\n"
        "{rag_context}\n"
    ),
    "form": (
        "\n\n## REFERENCE: Real Avni Form Patterns\n"
        "Use these as templates for form structure, groups, and elements.\n\n"
        "{rag_context}\n"
    ),
    "support": (
        "\n\n## REFERENCE: Known Issues & Solutions\n"
        "{rag_context}\n"
    ),
    "general": (
        "\n\n## REFERENCE: Avni Knowledge Base\n"
        "{rag_context}\n"
    ),
}


class RAGAugmentedLLM:
    """LLM service with automatic RAG context injection.

    Every call retrieves relevant Avni knowledge from pgvector and injects
    it into the prompt before sending to the local model. This dramatically
    improves output quality for domain-specific tasks.
    """

    def __init__(self) -> None:
        self._rag_service = None
        self._initialized = False

    async def _ensure_rag(self):
        """Lazy-initialize RAG service."""
        if not self._initialized:
            try:
                from app.services.rag.fallback import rag_service
                if not rag_service.is_rag_available:
                    await rag_service.initialize()
                self._rag_service = rag_service
            except Exception as e:
                logger.warning("RAG not available, proceeding without context: %s", e)
                self._rag_service = None
            self._initialized = True

    async def _retrieve_context(
        self,
        query: str,
        task_type: str = "general",
        top_k: int = 5,
    ) -> str:
        """Retrieve relevant Avni knowledge for the query."""
        await self._ensure_rag()
        if not self._rag_service:
            return ""

        collections = TASK_COLLECTIONS.get(task_type)
        results = []

        if collections:
            for collection in collections:
                try:
                    coll_results = await self._rag_service.search(
                        query, collection=collection, top_k=top_k
                    )
                    results.extend(coll_results)
                except Exception as e:
                    logger.warning("RAG search failed for %s: %s", collection, e)
        else:
            try:
                results = await self._rag_service.search(query, top_k=top_k)
            except Exception as e:
                logger.warning("RAG search failed: %s", e)

        if not results:
            return ""

        # Format results as context
        context_parts = []
        for i, result in enumerate(results[:top_k], 1):
            text = result.text if hasattr(result, 'text') else result.get("text", "")
            category = result.category if hasattr(result, 'category') else result.get("category", "")
            score = result.score if hasattr(result, 'score') else result.get("score", 0)
            context_parts.append(
                f"### Example {i} [{category}] (relevance: {score:.2f})\n{text}\n"
            )

        return "\n".join(context_parts)

    def _inject_context(
        self,
        user_message: str,
        rag_context: str,
        task_type: str,
        extra_context: dict[str, Any] | None = None,
    ) -> str:
        """Inject RAG context and extra context into the user message."""
        augmented = user_message

        # Add RAG context
        if rag_context:
            template = CONTEXT_TEMPLATES.get(task_type, CONTEXT_TEMPLATES["general"])
            augmented += template.format(rag_context=rag_context)

        # Add explicit context (concepts.json, form JSON, etc.)
        if extra_context:
            if "concepts_json" in extra_context:
                concepts = extra_context["concepts_json"]
                if isinstance(concepts, list):
                    concepts_str = json.dumps(concepts[:20], indent=2)
                    augmented += f"\n\n## PROVIDED CONCEPTS (use exact UUIDs):\n```json\n{concepts_str}\n```\n"
                elif isinstance(concepts, str):
                    augmented += f"\n\n## PROVIDED CONCEPTS:\n```json\n{concepts[:5000]}\n```\n"

            if "form_json" in extra_context:
                form = extra_context["form_json"]
                form_str = json.dumps(form, indent=2) if isinstance(form, dict) else str(form)
                if len(form_str) > 5000:
                    form_str = form_str[:5000] + "\n... (truncated)"
                augmented += f"\n\n## PROVIDED FORM:\n```json\n{form_str}\n```\n"

            if "form_type" in extra_context:
                augmented += f"\n\nForm type: {extra_context['form_type']}\n"

        return augmented

    async def generate_with_context(
        self,
        query: str,
        task_type: str = "general",
        extra_context: dict[str, Any] | None = None,
        system_prompt: str | None = None,
        top_k: int = 5,
    ) -> str:
        """Generate a response with RAG-augmented context.

        Args:
            query: The user's request.
            task_type: One of "rule", "bundle", "concept", "form", "support", "general".
            extra_context: Additional context (concepts_json, form_json, form_type).
            system_prompt: Override system prompt.
            top_k: Number of RAG results to inject.

        Returns:
            The LLM response text.
        """
        # Step 1: Retrieve relevant context
        rag_context = await self._retrieve_context(query, task_type, top_k)

        # Step 2: Inject context into the message
        augmented_query = self._inject_context(query, rag_context, task_type, extra_context)

        # Step 3: Call the LLM (local Ollama or fallback)
        response = await claude_client.complete(
            messages=[{"role": "user", "content": augmented_query}],
            system_prompt=system_prompt or AVNI_SYSTEM_PROMPT,
        )

        return response

    async def stream_with_context(
        self,
        query: str,
        task_type: str = "general",
        extra_context: dict[str, Any] | None = None,
        system_prompt: str | None = None,
        on_text: Callable[[str], None] | None = None,
        top_k: int = 5,
    ) -> AsyncGenerator[str, None]:
        """Stream a response with RAG-augmented context.

        Same as generate_with_context but streams chunks.
        """
        rag_context = await self._retrieve_context(query, task_type, top_k)
        augmented_query = self._inject_context(query, rag_context, task_type, extra_context)

        async for chunk in claude_client.stream_chat(
            messages=[{"role": "user", "content": augmented_query}],
            system_prompt=system_prompt or AVNI_SYSTEM_PROMPT,
            on_text=on_text,
        ):
            yield chunk

    async def generate_rule(
        self,
        description: str,
        form_type: str,
        concepts_json: list | None = None,
        form_json: dict | None = None,
    ) -> str:
        """Generate an Avni rule with full RAG context.

        Convenience method that sets up the right task type and context.
        """
        extra_context = {"form_type": form_type}
        if concepts_json:
            extra_context["concepts_json"] = concepts_json
        if form_json:
            extra_context["form_json"] = form_json

        return await self.generate_with_context(
            query=description,
            task_type="rule",
            extra_context=extra_context,
            top_k=8,
        )

    async def generate_bundle_component(
        self,
        description: str,
        component_type: str = "concept",
        existing_concepts: list | None = None,
    ) -> str:
        """Generate a bundle component (concept, form, mapping, etc.) with RAG context."""
        extra_context = {}
        if existing_concepts:
            extra_context["concepts_json"] = existing_concepts

        task_type = "concept" if component_type == "concept" else "bundle"

        return await self.generate_with_context(
            query=description,
            task_type=task_type,
            extra_context=extra_context,
            top_k=5,
        )


# Module-level singleton
rag_llm = RAGAugmentedLLM()
