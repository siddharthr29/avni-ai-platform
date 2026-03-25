"""Agent endpoints for autonomous Avni setup tasks.

Provides:
  POST /api/agent/run        -- Start a new agent task
  GET  /api/agent/task/{id}  -- Get task status and steps
  POST /api/agent/resume/{id} -- Resume a task waiting for user input
  POST /api/agent/translate-error -- Translate Avni errors to suggestions
"""

import logging
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.error_translator import translate_avni_error, translate_multiple
from app.services.react_agent import react_agent

logger = logging.getLogger(__name__)

router = APIRouter()


class AgentRunRequest(BaseModel):
    goal: str = Field(
        description="What the agent should accomplish, e.g. 'Upload bundle abc123 to the org'"
    )
    auth_token: str = Field(description="Avni AUTH-TOKEN for the target org")
    context: dict = Field(
        default_factory=dict,
        description="Optional context: bundle_id, org_name, etc.",
    )


class AgentResumeRequest(BaseModel):
    user_response: str = Field(
        description="User's response to the agent's question"
    )


class ErrorTranslateRequest(BaseModel):
    errors: list[str] = Field(
        description="List of error messages to translate"
    )


@router.post("/agent/run")
async def run_agent_task(request: AgentRunRequest) -> dict:
    """Start a new autonomous agent task.

    The agent will plan, execute MCP tools, validate bundles, and
    self-correct errors up to 3 retries per step.
    """
    task_id = str(uuid.uuid4())[:12]
    task = await react_agent.run(
        task_id=task_id,
        goal=request.goal,
        auth_token=request.auth_token,
        context=request.context,
    )
    return task.to_dict()


@router.get("/agent/task/{task_id}")
async def get_agent_task(task_id: str) -> dict:
    """Get the current status and execution trace of an agent task."""
    task = react_agent.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return task.to_dict()


@router.post("/agent/resume/{task_id}")
async def resume_agent_task(task_id: str, request: AgentResumeRequest) -> dict:
    """Resume an agent task that is waiting for user input.

    When the agent uses ask_user, it pauses and returns status 'needs_user'.
    Call this endpoint with the user's response to continue execution.
    """
    task = await react_agent.resume_task(task_id, request.user_response)
    if not task:
        raise HTTPException(
            status_code=404,
            detail=f"Task {task_id} not found or not in 'needs_user' state",
        )
    return task.to_dict()


@router.post("/agent/translate-error")
async def translate_errors(request: ErrorTranslateRequest) -> dict:
    """Translate Avni server errors into actionable fix suggestions.

    Useful for:
    - Chat UI showing friendly error messages
    - Agent loop deciding what to fix
    - Bundle upload error diagnosis
    """
    translations = translate_multiple(request.errors)
    auto_fixable = [t for t in translations if t["auto_fixable"]]
    return {
        "translations": translations,
        "total": len(translations),
        "auto_fixable_count": len(auto_fixable),
    }
