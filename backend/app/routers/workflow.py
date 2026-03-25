"""
Workflow API Router.

Provides endpoints to start, monitor, and interact with multi-step workflows
that have checkpoint gates (auto, review, approve, block).
"""

import asyncio
import json
import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from app.services.workflow_engine import workflow_engine
from app.services.workflow_definitions import (
    create_bundle_generation_workflow,
    create_validation_only_workflow,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Track running workflow tasks so SSE streams can push events
_workflow_tasks: dict[str, asyncio.Task] = {}
# Queues for SSE event streaming per workflow
_event_queues: dict[str, list[asyncio.Queue]] = {}


# ── Request / Response Models ─────────────────────────────────────────────────


class StartWorkflowRequest(BaseModel):
    workflow_type: str = Field(
        description="Type of workflow: 'bundle_generation' or 'validation'"
    )
    srs_data: dict | None = Field(
        default=None,
        description="Structured SRS data dict",
    )
    srs_text: str | None = Field(
        default=None,
        description="Raw SRS text to parse with LLM",
    )
    org_context: dict | None = Field(
        default=None,
        description="Organisation context (auth tokens, org name, etc.)",
    )


class StartWorkflowResponse(BaseModel):
    workflow_id: str
    name: str
    status: str
    total_steps: int
    steps: list[dict]


class ApproveStepRequest(BaseModel):
    approved: bool = Field(description="True to approve, False to reject")
    feedback: str = Field(
        default="",
        description="Optional feedback or reason for rejection",
    )


class ProvideInputRequest(BaseModel):
    input_data: dict = Field(
        description="Key-value data to provide as human input for BLOCK steps"
    )


# ── SSE Event Broadcasting ───────────────────────────────────────────────────


async def _broadcast_event(workflow_id: str, event: dict) -> None:
    """Push an event to all SSE listeners for this workflow."""
    queues = _event_queues.get(workflow_id, [])
    for q in queues:
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning("SSE queue full for workflow %s, dropping event", workflow_id)


async def _run_workflow_background(workflow_id: str) -> None:
    """Run a workflow in the background, broadcasting events via SSE."""
    try:
        await workflow_engine.run(workflow_id, on_event=_broadcast_event)
    except asyncio.CancelledError:
        logger.info("Workflow task %s cancelled", workflow_id)
    except Exception as exc:
        logger.exception("Workflow %s failed in background", workflow_id)
        await _broadcast_event(workflow_id, {
            "type": "workflow_failed",
            "workflow_id": workflow_id,
            "error": str(exc),
        })


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/workflow/start", response_model=StartWorkflowResponse)
async def start_workflow(request: StartWorkflowRequest) -> StartWorkflowResponse:
    """Start a new workflow.

    Supported workflow_type values:
    - "bundle_generation": Full SRS -> Bundle -> Validate -> Review -> Upload
    - "validation": SRS -> Parse -> Validate only (quick quality check)
    """
    if not request.srs_data and not request.srs_text:
        raise HTTPException(
            status_code=400,
            detail="Either srs_data or srs_text must be provided",
        )

    try:
        if request.workflow_type == "bundle_generation":
            workflow = create_bundle_generation_workflow(
                srs_data=request.srs_data,
                srs_text=request.srs_text,
                org_context=request.org_context,
            )
        elif request.workflow_type == "validation":
            workflow = create_validation_only_workflow(
                srs_data=request.srs_data,
                srs_text=request.srs_text,
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown workflow_type: {request.workflow_type}. "
                       f"Supported: bundle_generation, validation",
            )
    except Exception as exc:
        logger.exception("Failed to create workflow")
        raise HTTPException(status_code=500, detail=f"Failed to create workflow: {exc}")

    # Initialize SSE queue list for this workflow
    _event_queues[workflow.id] = []

    # Start the workflow in the background
    task = asyncio.create_task(_run_workflow_background(workflow.id))
    _workflow_tasks[workflow.id] = task

    status = workflow_engine.get_workflow_status(workflow.id)
    return StartWorkflowResponse(
        workflow_id=workflow.id,
        name=status["name"],
        status=status["status"],
        total_steps=status["total_steps"],
        steps=status["steps"],
    )


@router.get("/workflow/{workflow_id}/status")
async def get_workflow_status(workflow_id: str) -> dict:
    """Get the current status of a workflow including all step states."""
    try:
        return workflow_engine.get_workflow_status(workflow_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Workflow not found")


@router.post("/workflow/{workflow_id}/step/{step_id}/approve")
async def approve_step(
    workflow_id: str,
    step_id: str,
    request: ApproveStepRequest,
) -> dict:
    """Approve or reject a step that is waiting at a checkpoint gate.

    For REVIEW checkpoints, this confirms or rejects the step result.
    For APPROVE checkpoints, this authorizes or blocks execution.
    """
    try:
        result = await workflow_engine.approve_step(
            workflow_id=workflow_id,
            step_id=step_id,
            approved=request.approved,
            feedback=request.feedback,
        )
        return {"status": "ok", "step": result}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/workflow/{workflow_id}/step/{step_id}/reject")
async def reject_step(
    workflow_id: str,
    step_id: str,
    request: ApproveStepRequest,
) -> dict:
    """Reject a step. Convenience endpoint — same as approve with approved=false."""
    try:
        result = await workflow_engine.approve_step(
            workflow_id=workflow_id,
            step_id=step_id,
            approved=False,
            feedback=request.feedback,
        )
        return {"status": "ok", "step": result}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/workflow/{workflow_id}/step/{step_id}/input")
async def provide_step_input(
    workflow_id: str,
    step_id: str,
    request: ProvideInputRequest,
) -> dict:
    """Provide human input for a BLOCK step.

    The input_data is merged into the workflow's shared context before the
    step executes. Use this for answering clarification questions, providing
    missing data, or making decisions that the workflow cannot automate.
    """
    try:
        result = await workflow_engine.provide_input(
            workflow_id=workflow_id,
            step_id=step_id,
            input_data=request.input_data,
        )
        return {"status": "ok", "step": result}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/workflow/{workflow_id}/cancel")
async def cancel_workflow(workflow_id: str) -> dict:
    """Cancel a running or paused workflow."""
    try:
        result = workflow_engine.cancel_workflow(workflow_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Workflow not found")

    # Cancel the background task if it exists
    task = _workflow_tasks.pop(workflow_id, None)
    if task and not task.done():
        task.cancel()

    return result


@router.get("/workflow/{workflow_id}/step/{step_id}/result")
async def get_step_result(workflow_id: str, step_id: str) -> dict:
    """Get the full result of a specific step."""
    try:
        result = workflow_engine.get_step_result(workflow_id, step_id)
        return {"step_id": step_id, "result": result}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/workflow/list")
async def list_workflows() -> dict:
    """List all tracked workflows with summary info."""
    return {"workflows": workflow_engine.list_workflows()}


@router.get("/workflow/{workflow_id}/events")
async def workflow_events(workflow_id: str) -> EventSourceResponse:
    """SSE stream of real-time workflow events.

    Connect to this endpoint to receive live updates as the workflow
    progresses through its steps. Events include step_started,
    step_completed, checkpoint, workflow_completed, etc.

    The stream ends when the workflow completes, fails, or is cancelled.
    """
    try:
        workflow_engine.get_workflow_status(workflow_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Workflow not found")

    queue: asyncio.Queue = asyncio.Queue(maxsize=100)

    # Register this queue for event broadcasts
    if workflow_id not in _event_queues:
        _event_queues[workflow_id] = []
    _event_queues[workflow_id].append(queue)

    async def event_generator():
        try:
            while True:
                event = await queue.get()
                event_type = event.get("type", "unknown")
                yield {
                    "event": event_type,
                    "data": json.dumps(event),
                }
                # Stop streaming on terminal events
                if event_type in ("workflow_completed", "workflow_failed"):
                    break
        except asyncio.CancelledError:
            pass
        finally:
            # Unregister this queue
            queues = _event_queues.get(workflow_id, [])
            if queue in queues:
                queues.remove(queue)
            if not queues:
                _event_queues.pop(workflow_id, None)

    return EventSourceResponse(event_generator())
