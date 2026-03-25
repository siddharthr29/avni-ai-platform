"""System prompt assembly — 5-layer prompt construction with guardrails.

Builds the composite system prompt from org context, RAG knowledge,
intent-specific instructions, action instructions, and guardrail rules.
"""
import logging
from typing import Any

from app.models.schemas import IntentType

logger = logging.getLogger(__name__)


def build_system_prompt(
    *,
    org_name: str | None,
    sector: str | None,
    org_context_text: str | None,
    knowledge_context: str,
    intent: IntentType,
    action: str | None,
    attachment_context: str,
    clarification_questions: list[str],
    is_pending_bundle: bool,
    skip_bundle_block: bool,
    session_id: str,
) -> str:
    """Assemble the full system prompt from multiple layers.

    Returns the complete system prompt string.
    """
    from app.services.claude_client import AVNI_SYSTEM_PROMPT

    system_parts = [AVNI_SYSTEM_PROMPT]

    # Layer 1: Organisation context (from persisted + request)
    if org_name or sector or org_context_text:
        org_lines = ["\n\n--- User's Organisation ---"]
        if org_name:
            org_lines.append(f"Organisation: {org_name}")
        if sector:
            org_lines.append(f"Sector: {sector}")
        if org_context_text:
            org_lines.append(f"About: {org_context_text}")
        org_lines.append("Tailor your responses to this organisation's sector, scale, and context.")
        system_parts.append("\n".join(org_lines))

    # Layer 2: Reference knowledge (vector search + skills + PageIndex)
    if knowledge_context:
        system_parts.append(
            "\n\n--- Internal Reference Knowledge (from Avni's training corpus) ---\n"
            "The following is reference data from other Avni implementations. "
            "Use it to inform your answers but NEVER tell the user they provided this data. "
            "NEVER say 'the concepts you provided' or 'your earlier data' when referring to this. "
            "This is background knowledge, not user input.\n\n"
            + knowledge_context
        )

    # Layer 3: Intent-specific instructions
    if intent == IntentType.RULE:
        system_parts.append(
            "\n\nThe user is asking about rules. Provide working JavaScript code "
            "that follows Avni's rule engine patterns. If you need the form JSON "
            "or concepts.json to write accurate rules, ask for them."
        )
    elif intent == IntentType.SUPPORT:
        system_parts.append(
            "\n\nThe user is troubleshooting an issue. Ask clarifying questions "
            "to diagnose the problem. Check common causes: sync issues, UUID mismatches, "
            "missing form mappings, privilege gaps."
        )
    elif intent == IntentType.CONFIG:
        system_parts.append(
            "\n\nThe user wants to configure Avni entities. Guide them through the "
            "process and explain the Avni API calls needed."
        )

    # Layer 4: Action-specific instructions
    if action == "bundle_create":
        system_parts.append(
            "\n\n--- ACTION: Bundle Creation ---\n"
            "The user wants to create an Avni bundle. To generate a complete bundle, you need:\n"
            "1. Subject types (Person/Individual/Household/Group)\n"
            "2. Programs (if any — e.g., Pregnancy, TB)\n"
            "3. Encounter types (visit types)\n"
            "4. Form fields with data types\n"
            "5. Any skip logic / rules\n\n"
            "Stay in this chat conversation to gather requirements. "
            "If the user hasn't provided enough detail, ask clarifying questions about "
            "their subject types, programs, and form fields. "
            "Do NOT redirect the user to another page or API endpoint. "
            "The bundle will be generated automatically right here in chat once requirements are clear."
        )
    elif action == "org_setup":
        system_parts.append(
            "\n\n--- ACTION: Organisation Setup ---\n"
            "The user wants to create or configure an Avni organisation. Guide them through:\n"
            "1. Organisation name and settings\n"
            "2. Address hierarchy (location types and locations)\n"
            "3. User groups and privileges\n"
            "4. Catchment areas\n"
            "5. Bundle upload/application\n\n"
            "If they have an Avni auth token configured, they can use the API directly. "
            "Otherwise, guide them through the Avni webapp admin interface."
        )

    # If user is in pending bundle flow (answering clarification questions),
    # give context so the LLM can continue the conversation naturally
    if skip_bundle_block and is_pending_bundle:
        system_parts.append(
            "\n\n--- Context: Bundle Generation In Progress ---\n"
            "You previously asked the user clarification questions about their program "
            "requirements for generating an Avni implementation bundle. The user is now "
            "providing answers. Acknowledge their answers, ask any remaining follow-up "
            "questions if needed, and when you have enough information, tell the user "
            "to say 'generate the bundle' or 'proceed' to start bundle generation."
        )

    # Layer 5: User-uploaded file data
    if attachment_context:
        system_parts.append(
            "\n\n--- User's Uploaded File Data ---\n"
            "The user has uploaded the following file(s) in this message. "
            "Reference this data when answering their question. "
            "You CAN say 'based on the file you uploaded' because the user DID upload these.\n"
            + attachment_context
        )

    # Layer 5.5: Clarification questions (BUNDLE — text or file upload)
    if clarification_questions:
        numbered = "\n".join(
            f"{i}. {q}" for i, q in enumerate(clarification_questions, 1)
        )
        source_desc = (
            "uploaded a file with" if attachment_context
            else "described"
        )
        system_parts.append(
            "\n\n--- IMPORTANT: Clarification Required Before Bundle Generation ---\n"
            f"The user has {source_desc} their program requirements and wants to generate an Avni bundle. "
            "Before generating, you MUST ask the following clarification questions "
            "to ensure the bundle is accurate and complete. Present them naturally "
            "in your response — do NOT dump them as a raw list. Weave them into a "
            "conversational message that acknowledges what you understood from their "
            "description and asks for the missing pieces:\n\n"
            f"{numbered}\n\n"
            "After the user answers, you will proceed with bundle generation. "
            "Do NOT generate the bundle in this response — only ask the questions. "
            "Tell the user you'll generate the bundle once they answer these questions."
        )

    # Layer 6: Guardrails
    system_parts.append(
        "\n\nIMPORTANT RULES:"
        "\n- Only reference data the user has actually provided in this conversation."
        "\n- Never claim the user uploaded or shared files they haven't."
        "\n- If you need concepts.json, form JSON, or SRS data to give accurate answers, ask the user to provide them."
        "\n- Be helpful and conversational. Don't dump the entire Avni data model unless asked."
    )

    return "".join(system_parts)
