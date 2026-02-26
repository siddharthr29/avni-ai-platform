import json
import logging
from typing import Any

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from app.models.schemas import (
    Attachment,
    ChatMessage,
    ChatRequest,
    IntentType,
    SSEEventType,
)
from app.services.claude_client import claude_client
from app.services.intent_router import classify_intent
from app.services.knowledge_base import knowledge_base

logger = logging.getLogger(__name__)

router = APIRouter()

# In-memory session store (keyed by session_id)
_sessions: dict[str, dict[str, Any]] = {}

MAX_HISTORY = 50


def _get_session(session_id: str) -> dict[str, Any]:
    if session_id not in _sessions:
        _sessions[session_id] = {
            "messages": [],
            "intent_history": [],
        }
    return _sessions[session_id]


def _add_message(session_id: str, role: str, content: str) -> None:
    session = _get_session(session_id)
    session["messages"].append({"role": role, "content": content})
    # Trim old messages to prevent unbounded growth
    if len(session["messages"]) > MAX_HISTORY:
        session["messages"] = session["messages"][-MAX_HISTORY:]


def _build_knowledge_context(intent: IntentType, message: str) -> str:
    """Build additional context from the knowledge base based on intent."""
    results = []

    if intent == IntentType.KNOWLEDGE:
        results = knowledge_base.search_all(message, limit=5)
    elif intent == IntentType.SUPPORT:
        results = knowledge_base.search_tickets(message, limit=3)
    elif intent == IntentType.RULE:
        results = knowledge_base.search_rules(message, limit=3)
    elif intent in (IntentType.BUNDLE, IntentType.CONFIG):
        results = knowledge_base.search_concepts(message, limit=3)

    if not results:
        return ""

    context_parts = ["\n\n--- Relevant Avni Knowledge ---"]
    for r in results:
        context_parts.append(f"[{r.category}] {r.text}")
    return "\n".join(context_parts)


@router.post("/chat")
async def chat(request: ChatRequest) -> EventSourceResponse:
    """Main chat endpoint with SSE streaming.

    Classifies the user's intent, enriches with knowledge context, and streams
    the response back via Server-Sent Events.
    """
    session_id = request.session_id
    message = request.message
    attachments = request.attachments

    # Classify intent
    intent_result = await classify_intent(message, attachments)
    intent = intent_result.intent

    # Record in session
    session = _get_session(session_id)
    session["intent_history"].append(intent.value)
    _add_message(session_id, "user", message)

    async def event_generator():
        try:
            # Send intent classification as progress event
            yield {
                "event": "message",
                "data": json.dumps({
                    "type": SSEEventType.PROGRESS.value,
                    "content": f"Intent: {intent.value} (confidence: {intent_result.confidence:.2f})",
                }),
            }

            # For bundle intent with SRS data, redirect to bundle endpoint
            if intent == IntentType.BUNDLE and any(
                a.type == "file" for a in attachments
            ):
                yield {
                    "event": "message",
                    "data": json.dumps({
                        "type": SSEEventType.TEXT.value,
                        "content": "I see you've uploaded a file for bundle generation. "
                                   "Please use the `/api/bundle/generate` endpoint to process SRS data, "
                                   "or paste the SRS content directly in the chat and I'll help you structure it.",
                    }),
                }
                yield {
                    "event": "message",
                    "data": json.dumps({
                        "type": SSEEventType.DONE.value,
                        "content": "",
                    }),
                }
                return

            # Build knowledge context
            knowledge_context = _build_knowledge_context(intent, message)

            # Build messages for Claude
            history = session["messages"][-20:]  # Last 20 messages for context window
            claude_messages = [
                {"role": m["role"], "content": m["content"]} for m in history
            ]

            # Add knowledge context to the user's message
            if knowledge_context:
                augmented_content = message + knowledge_context
                if claude_messages:
                    claude_messages[-1] = {
                        "role": "user",
                        "content": augmented_content,
                    }

            # Add intent-specific system prompt additions
            system_suffix = ""
            if intent == IntentType.RULE:
                system_suffix = (
                    "\n\nThe user is asking about rules. Provide working JavaScript code "
                    "that follows Avni's rule engine patterns. If you need the form JSON "
                    "or concepts.json to write accurate rules, ask for them."
                )
            elif intent == IntentType.SUPPORT:
                system_suffix = (
                    "\n\nThe user is troubleshooting an issue. Ask clarifying questions "
                    "to diagnose the problem. Check common causes: sync issues, UUID mismatches, "
                    "missing form mappings, privilege gaps."
                )
            elif intent == IntentType.CONFIG:
                system_suffix = (
                    "\n\nThe user wants to configure Avni entities. Guide them through the "
                    "process and explain the Avni API calls needed. The avni-ai-main MCP server "
                    "can handle CRUD operations for subjects, programs, encounters, and forms."
                )

            from app.services.claude_client import AVNI_SYSTEM_PROMPT
            full_system = AVNI_SYSTEM_PROMPT + system_suffix

            # Stream the response
            full_response = ""
            async for chunk in claude_client.stream_chat(
                messages=claude_messages,
                system_prompt=full_system,
            ):
                full_response += chunk
                yield {
                    "event": "message",
                    "data": json.dumps({
                        "type": SSEEventType.TEXT.value,
                        "content": chunk,
                    }),
                }

            # Save assistant response to session
            _add_message(session_id, "assistant", full_response)

            # Send done event
            yield {
                "event": "message",
                "data": json.dumps({
                    "type": SSEEventType.DONE.value,
                    "content": "",
                }),
            }

        except Exception as e:
            logger.exception("Chat streaming error for session %s", session_id)
            yield {
                "event": "message",
                "data": json.dumps({
                    "type": SSEEventType.ERROR.value,
                    "content": f"An error occurred: {str(e)}",
                }),
            }

    return EventSourceResponse(event_generator())
