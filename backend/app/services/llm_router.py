"""LLM-based intent router — replaces regex pattern matching for bundle workflows.

Instead of regex guessing what the user wants, we make a fast LLM call with
structured tool definitions. The LLM decides the next action based on:
- The user's message
- The current conversation state (pending SRS, last bundle, etc.)
- File attachments present

This handles 100 users with 100 different personalities correctly because
the LLM understands natural language — no regex patterns to maintain.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.services.claude_client import claude_client

logger = logging.getLogger(__name__)

# The router prompt — tells the LLM about Avni's data model and available actions
ROUTER_SYSTEM_PROMPT = """You are an intent router for the Avni AI platform. Your ONLY job is to decide the next action based on the user's message and current state.

You must respond with EXACTLY one JSON object (no markdown, no explanation):

{
  "action": "<one of the actions below>",
  "reason": "<one sentence why>"
}

Available actions:

1. "show_summary" — User uploaded files and we parsed them. Show the parsed summary and ask for confirmation before generating. USE THIS when files were just uploaded, regardless of what the user says.

2. "generate_bundle" — User has confirmed they want to generate. USE THIS when:
   - There is stored SRS data from a previous parse AND
   - User's message is a short confirmation (yes, generate, go, looks good, ok, proceed, etc.)

3. "apply_correction" — User wants to change something about the parsed SRS. USE THIS when:
   - There is stored SRS data AND
   - User describes a change (e.g., "X should be a program", "add field Y", "remove Z")

4. "ask_clarification" — Not enough info to generate a bundle. USE THIS when:
   - User asks to generate a bundle but provides no SRS content or files
   - User's message is vague about requirements

5. "chat" — Normal conversation. USE THIS for:
   - Questions about Avni concepts
   - Help requests
   - Anything not related to bundle generation

CRITICAL RULES:
- If files were just uploaded, ALWAYS pick "show_summary". Never "generate_bundle" on first upload.
- If user says "read first", "scan first", "review first", "check this" — pick "show_summary".
- Short replies (1-5 words) when stored SRS exists = "generate_bundle" (user is confirming).
- Anything describing a change to stored SRS = "apply_correction".
"""


async def route_bundle_intent(
    message: str,
    has_file_attachments: bool,
    has_stored_srs: bool,
    has_pending_text: bool,
    parsed_summary: str | None = None,
) -> dict[str, str]:
    """Use LLM to decide the next action for a bundle workflow message.

    Args:
        message: The user's message text
        has_file_attachments: Whether XLSX/CSV files were uploaded with this message
        has_stored_srs: Whether we have stored SRS data from a previous parse
        has_pending_text: Whether there's a pending text-based bundle request
        parsed_summary: Summary of parsed SRS (if files were just processed)

    Returns:
        {"action": "show_summary|generate_bundle|apply_correction|ask_clarification|chat",
         "reason": "..."}
    """
    # Build context for the router
    state_parts = []
    if has_file_attachments:
        state_parts.append("User just uploaded Excel/CSV files with this message.")
    if has_stored_srs:
        state_parts.append("There is stored SRS data from a previous file upload (user has already seen the summary).")
    if has_pending_text:
        state_parts.append("There is a pending text-based bundle request (user was asked clarifying questions).")
    if parsed_summary:
        state_parts.append(f"Parsed SRS summary: {parsed_summary[:500]}")

    state_context = "\n".join(state_parts) if state_parts else "No prior state."

    user_prompt = f"""Current state:
{state_context}

User's message: "{message}"

Decide the next action. Respond with JSON only."""

    try:
        response = await claude_client.complete(
            messages=[{"role": "user", "content": user_prompt}],
            system_prompt=ROUTER_SYSTEM_PROMPT,
            task_type="intent",
        )

        # Parse JSON from response
        text = response.strip()
        # Handle markdown fences
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        result = json.loads(text)
        action = result.get("action", "chat")
        reason = result.get("reason", "")

        # Validate action
        valid_actions = {"show_summary", "generate_bundle", "apply_correction", "ask_clarification", "chat"}
        if action not in valid_actions:
            logger.warning("LLM router returned invalid action '%s', defaulting to 'chat'", action)
            action = "chat"

        logger.info("LLM router: action=%s reason=%s (msg='%s')", action, reason, message[:80])
        return {"action": action, "reason": reason}

    except json.JSONDecodeError:
        logger.warning("LLM router returned non-JSON, falling back to heuristic")
        return _fallback_route(message, has_file_attachments, has_stored_srs)
    except Exception as e:
        logger.warning("LLM router failed: %s, falling back to heuristic", e)
        return _fallback_route(message, has_file_attachments, has_stored_srs)


def _fallback_route(
    message: str,
    has_file_attachments: bool,
    has_stored_srs: bool,
) -> dict[str, str]:
    """Simple fallback when LLM router fails. Follows safe defaults:
    - Files uploaded → show_summary (always)
    - Stored SRS + short message → generate_bundle
    - Stored SRS + long message → apply_correction
    - Otherwise → chat
    """
    if has_file_attachments:
        return {"action": "show_summary", "reason": "Files uploaded, showing summary (fallback)"}
    if has_stored_srs:
        if len(message.split()) <= 10:
            return {"action": "generate_bundle", "reason": "Short reply to stored SRS (fallback)"}
        else:
            return {"action": "apply_correction", "reason": "Long reply to stored SRS (fallback)"}
    return {"action": "chat", "reason": "No bundle context (fallback)"}
