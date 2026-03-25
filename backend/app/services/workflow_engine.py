"""
Workflow Engine with Checkpoint Gates.

Executes multi-step workflows where each step can be validated, reviewed,
and approved before proceeding. Designed to orchestrate bundle generation,
rule creation, and upload flows with human-in-the-loop checkpoints.
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

__all__ = [
    "CheckpointLevel",
    "StepStatus",
    "WorkflowStep",
    "Workflow",
    "WorkflowEngine",
    "workflow_engine",
]


class CheckpointLevel(Enum):
    AUTO = "auto"           # Execute + validate, no human needed
    REVIEW = "review"       # Execute + show result, human confirms
    APPROVE = "approve"     # Show plan only, human must approve before execution
    BLOCK = "block"         # Cannot proceed without human decision


class StepStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class WorkflowStep:
    id: str
    name: str
    description: str
    checkpoint: CheckpointLevel
    executor: Callable  # async function: (context: dict) -> Any
    validator: Optional[Callable] = None  # async function: (result, context) -> (bool, errors, warnings)
    auto_fix: Optional[Callable] = None  # async function: (result, errors, context) -> fixed_result
    status: StepStatus = StepStatus.PENDING
    result: Any = None
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    provider_used: Optional[str] = None  # which LLM provider handled this
    human_feedback: Optional[str] = None  # feedback from approval/rejection
    human_input: Optional[dict] = None  # input provided for BLOCK steps
    retry_count: int = 0
    max_retries: int = 2


@dataclass
class Workflow:
    id: str
    name: str
    steps: list[WorkflowStep]
    context: dict  # shared context passed between steps
    status: str = "pending"  # pending | running | paused | completed | failed | cancelled
    current_step_index: int = 0
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    error: Optional[str] = None


class WorkflowEngine:
    """Executes multi-step workflows with checkpoint gates.

    Each step runs through this lifecycle:
    1. For APPROVE checkpoints: emit checkpoint event, wait for approval BEFORE execution
    2. Set status to RUNNING, emit step_started
    3. Execute the step's executor function
    4. If validator exists, validate the result
    5. If validation fails and auto_fix exists, try auto_fix then re-validate
    6. Check checkpoint level for post-execution behavior:
       - AUTO: proceed to next step
       - REVIEW: emit checkpoint event, wait for human confirmation
       - APPROVE: (already approved pre-execution) proceed
       - BLOCK: emit checkpoint event, wait for human input
    7. On approval, proceed. On rejection, stop or retry.

    Events emitted via on_event callback (SSE-compatible):
    - {"type": "step_started", "step": {...}}
    - {"type": "step_completed", "step": {...}, "result": {...}}
    - {"type": "step_failed", "step": {...}, "errors": [...]}
    - {"type": "checkpoint", "step": {...}, "needs": "approval|review|input"}
    - {"type": "validation_warning", "step": {...}, "warnings": [...]}
    - {"type": "auto_fix_applied", "step": {...}, "fixes": [...]}
    - {"type": "workflow_completed", "summary": {...}}
    - {"type": "workflow_failed", "error": "..."}
    - {"type": "clarification_needed", "questions": [...]}
    """

    def __init__(self) -> None:
        self._workflows: dict[str, Workflow] = {}
        # Events used to signal that a paused step can resume
        self._resume_events: dict[str, asyncio.Event] = {}

    # ── Workflow lifecycle ────────────────────────────────────────────────

    def create_workflow(
        self,
        name: str,
        steps: list[WorkflowStep],
        context: dict,
    ) -> Workflow:
        """Create a new workflow and register it."""
        workflow_id = str(uuid.uuid4())
        workflow = Workflow(
            id=workflow_id,
            name=name,
            steps=steps,
            context=context,
        )
        self._workflows[workflow_id] = workflow
        logger.info(
            "Workflow created: %s (%s) with %d steps",
            workflow_id, name, len(steps),
        )
        return workflow

    async def run(self, workflow_id: str, on_event: Callable) -> None:
        """Execute workflow steps in order, pausing at checkpoint gates.

        Args:
            workflow_id: ID of a previously created workflow.
            on_event: Async callback receiving SSE-compatible event dicts.
        """
        workflow = self._get_workflow(workflow_id)
        workflow.status = "running"

        try:
            while workflow.current_step_index < len(workflow.steps):
                if workflow.status == "cancelled":
                    await on_event({
                        "type": "workflow_failed",
                        "workflow_id": workflow.id,
                        "error": "Workflow was cancelled",
                    })
                    return

                step = workflow.steps[workflow.current_step_index]

                # ── APPROVE checkpoint: wait BEFORE execution ─────────
                if step.checkpoint == CheckpointLevel.APPROVE:
                    step.status = StepStatus.WAITING_APPROVAL
                    await on_event({
                        "type": "checkpoint",
                        "workflow_id": workflow.id,
                        "step": self._step_dict(step),
                        "needs": "approval",
                        "message": f"Step '{step.name}' requires approval before execution.",
                    })
                    workflow.status = "paused"

                    # Wait for approve_step() to be called
                    approved = await self._wait_for_resume(workflow.id, step.id)
                    workflow.status = "running"

                    if not approved:
                        step.status = StepStatus.REJECTED
                        step.completed_at = time.time()
                        await on_event({
                            "type": "step_failed",
                            "workflow_id": workflow.id,
                            "step": self._step_dict(step),
                            "errors": ["Step was rejected by user"],
                            "feedback": step.human_feedback,
                        })
                        workflow.status = "failed"
                        workflow.error = f"Step '{step.name}' was rejected"
                        await on_event({
                            "type": "workflow_failed",
                            "workflow_id": workflow.id,
                            "error": workflow.error,
                        })
                        return

                    step.status = StepStatus.APPROVED

                # ── BLOCK checkpoint: wait for human input BEFORE execution
                if step.checkpoint == CheckpointLevel.BLOCK:
                    step.status = StepStatus.WAITING_APPROVAL
                    await on_event({
                        "type": "checkpoint",
                        "workflow_id": workflow.id,
                        "step": self._step_dict(step),
                        "needs": "input",
                        "message": f"Step '{step.name}' requires human input before proceeding.",
                    })
                    workflow.status = "paused"

                    approved = await self._wait_for_resume(workflow.id, step.id)
                    workflow.status = "running"

                    if not approved:
                        step.status = StepStatus.REJECTED
                        step.completed_at = time.time()
                        workflow.status = "failed"
                        workflow.error = f"Step '{step.name}' was rejected"
                        await on_event({
                            "type": "workflow_failed",
                            "workflow_id": workflow.id,
                            "error": workflow.error,
                        })
                        return

                    # Merge human input into workflow context
                    if step.human_input:
                        workflow.context.update(step.human_input)

                # ── Execute the step ──────────────────────────────────
                step.status = StepStatus.RUNNING
                step.started_at = time.time()
                await on_event({
                    "type": "step_started",
                    "workflow_id": workflow.id,
                    "step": self._step_dict(step),
                })

                try:
                    step.result = await step.executor(workflow.context)
                except Exception as exc:
                    step.status = StepStatus.FAILED
                    step.completed_at = time.time()
                    step.errors.append(str(exc))
                    logger.exception(
                        "Step '%s' failed in workflow %s", step.name, workflow.id,
                    )
                    await on_event({
                        "type": "step_failed",
                        "workflow_id": workflow.id,
                        "step": self._step_dict(step),
                        "errors": step.errors,
                    })

                    # Retry logic
                    if step.retry_count < step.max_retries:
                        step.retry_count += 1
                        step.errors = []
                        step.status = StepStatus.PENDING
                        logger.info(
                            "Retrying step '%s' (attempt %d/%d)",
                            step.name, step.retry_count, step.max_retries,
                        )
                        continue

                    workflow.status = "failed"
                    workflow.error = f"Step '{step.name}' failed: {exc}"
                    await on_event({
                        "type": "workflow_failed",
                        "workflow_id": workflow.id,
                        "error": workflow.error,
                    })
                    return

                # ── Validate the result ───────────────────────────────
                if step.validator:
                    try:
                        valid, errors, warnings = await step.validator(
                            step.result, workflow.context,
                        )
                        step.warnings.extend(warnings)

                        if warnings:
                            await on_event({
                                "type": "validation_warning",
                                "workflow_id": workflow.id,
                                "step": self._step_dict(step),
                                "warnings": warnings,
                            })

                        if not valid:
                            step.errors.extend(errors)

                            # Try auto-fix if available
                            if step.auto_fix:
                                try:
                                    fixed = await step.auto_fix(
                                        step.result, errors, workflow.context,
                                    )
                                    step.result = fixed
                                    await on_event({
                                        "type": "auto_fix_applied",
                                        "workflow_id": workflow.id,
                                        "step": self._step_dict(step),
                                        "fixes": errors,
                                    })

                                    # Re-validate after fix
                                    valid2, errors2, warnings2 = await step.validator(
                                        step.result, workflow.context,
                                    )
                                    step.warnings.extend(warnings2)
                                    if not valid2:
                                        step.errors = errors2
                                    else:
                                        step.errors = []
                                except Exception as fix_exc:
                                    logger.warning(
                                        "Auto-fix failed for step '%s': %s",
                                        step.name, fix_exc,
                                    )

                            # If still invalid after auto-fix, fail the step
                            if step.errors:
                                step.status = StepStatus.FAILED
                                step.completed_at = time.time()
                                await on_event({
                                    "type": "step_failed",
                                    "workflow_id": workflow.id,
                                    "step": self._step_dict(step),
                                    "errors": step.errors,
                                })
                                workflow.status = "failed"
                                workflow.error = f"Step '{step.name}' validation failed"
                                await on_event({
                                    "type": "workflow_failed",
                                    "workflow_id": workflow.id,
                                    "error": workflow.error,
                                })
                                return
                    except Exception as val_exc:
                        logger.warning(
                            "Validator raised for step '%s': %s",
                            step.name, val_exc,
                        )
                        step.warnings.append(f"Validation error: {val_exc}")

                # ── Post-execution checkpoint: REVIEW ─────────────────
                if step.checkpoint == CheckpointLevel.REVIEW:
                    step.status = StepStatus.WAITING_APPROVAL
                    await on_event({
                        "type": "checkpoint",
                        "workflow_id": workflow.id,
                        "step": self._step_dict(step),
                        "needs": "review",
                        "message": f"Step '{step.name}' completed. Please review the result.",
                        "result_summary": self._summarize_result(step.result),
                    })
                    workflow.status = "paused"

                    approved = await self._wait_for_resume(workflow.id, step.id)
                    workflow.status = "running"

                    if not approved:
                        step.status = StepStatus.REJECTED
                        step.completed_at = time.time()
                        await on_event({
                            "type": "step_failed",
                            "workflow_id": workflow.id,
                            "step": self._step_dict(step),
                            "errors": ["Step was rejected during review"],
                            "feedback": step.human_feedback,
                        })
                        workflow.status = "failed"
                        workflow.error = f"Step '{step.name}' was rejected during review"
                        await on_event({
                            "type": "workflow_failed",
                            "workflow_id": workflow.id,
                            "error": workflow.error,
                        })
                        return

                # ── Step complete ─────────────────────────────────────
                step.status = StepStatus.COMPLETED
                step.completed_at = time.time()

                # Store step result in shared context for downstream steps
                workflow.context[f"step_{step.id}_result"] = step.result

                await on_event({
                    "type": "step_completed",
                    "workflow_id": workflow.id,
                    "step": self._step_dict(step),
                    "result_summary": self._summarize_result(step.result),
                })

                workflow.current_step_index += 1

            # ── All steps done ────────────────────────────────────────
            workflow.status = "completed"
            workflow.completed_at = time.time()
            await on_event({
                "type": "workflow_completed",
                "workflow_id": workflow.id,
                "summary": self._workflow_summary(workflow),
            })

        except asyncio.CancelledError:
            workflow.status = "cancelled"
            logger.info("Workflow %s was cancelled", workflow.id)
            raise
        except Exception as exc:
            workflow.status = "failed"
            workflow.error = str(exc)
            logger.exception("Workflow %s failed unexpectedly", workflow.id)
            await on_event({
                "type": "workflow_failed",
                "workflow_id": workflow.id,
                "error": str(exc),
            })

    # ── Human interaction methods ─────────────────────────────────────────

    async def approve_step(
        self,
        workflow_id: str,
        step_id: str,
        approved: bool,
        feedback: str = "",
    ) -> dict:
        """Approve or reject a step that is waiting for human input.

        Returns the updated step status dict.
        """
        workflow = self._get_workflow(workflow_id)
        step = self._get_step(workflow, step_id)

        if step.status != StepStatus.WAITING_APPROVAL:
            raise ValueError(
                f"Step '{step.name}' is not waiting for approval "
                f"(current status: {step.status.value})"
            )

        step.human_feedback = feedback

        # Signal the run loop to continue
        event_key = f"{workflow_id}:{step_id}"
        resume_event = self._resume_events.get(event_key)
        if resume_event is None:
            raise ValueError(f"No pending resume event for step '{step.name}'")

        # Store approval decision in a temporary attribute
        step._approved = approved  # type: ignore[attr-defined]
        resume_event.set()

        logger.info(
            "Step '%s' in workflow %s: %s (feedback: %s)",
            step.name, workflow_id,
            "approved" if approved else "rejected",
            feedback[:100] if feedback else "none",
        )
        return self._step_dict(step)

    async def provide_input(
        self,
        workflow_id: str,
        step_id: str,
        input_data: dict,
    ) -> dict:
        """Provide human input for a BLOCK step.

        The input_data is merged into the workflow context before the step
        executes (or re-executes).

        Returns the updated step status dict.
        """
        workflow = self._get_workflow(workflow_id)
        step = self._get_step(workflow, step_id)

        if step.status != StepStatus.WAITING_APPROVAL:
            raise ValueError(
                f"Step '{step.name}' is not waiting for input "
                f"(current status: {step.status.value})"
            )

        step.human_input = input_data

        # Signal resume with approval
        event_key = f"{workflow_id}:{step_id}"
        resume_event = self._resume_events.get(event_key)
        if resume_event is None:
            raise ValueError(f"No pending resume event for step '{step.name}'")

        step._approved = True  # type: ignore[attr-defined]
        resume_event.set()

        logger.info(
            "Input provided for step '%s' in workflow %s: %d keys",
            step.name, workflow_id, len(input_data),
        )
        return self._step_dict(step)

    # ── Query methods ─────────────────────────────────────────────────────

    def get_workflow_status(self, workflow_id: str) -> dict:
        """Return the full status of a workflow including all steps."""
        workflow = self._get_workflow(workflow_id)
        return {
            "id": workflow.id,
            "name": workflow.name,
            "status": workflow.status,
            "current_step_index": workflow.current_step_index,
            "total_steps": len(workflow.steps),
            "created_at": workflow.created_at,
            "completed_at": workflow.completed_at,
            "error": workflow.error,
            "steps": [self._step_dict(s) for s in workflow.steps],
        }

    def get_step_result(self, workflow_id: str, step_id: str) -> Any:
        """Return the result of a specific step."""
        workflow = self._get_workflow(workflow_id)
        step = self._get_step(workflow, step_id)
        return step.result

    def cancel_workflow(self, workflow_id: str) -> dict:
        """Mark a workflow as cancelled. If paused at a checkpoint, unblock it."""
        workflow = self._get_workflow(workflow_id)
        workflow.status = "cancelled"

        # Unblock any waiting steps
        for step in workflow.steps:
            if step.status == StepStatus.WAITING_APPROVAL:
                event_key = f"{workflow_id}:{step.id}"
                resume_event = self._resume_events.get(event_key)
                if resume_event:
                    step._approved = False  # type: ignore[attr-defined]
                    resume_event.set()

        logger.info("Workflow %s cancelled", workflow_id)
        return self.get_workflow_status(workflow_id)

    def list_workflows(self) -> list[dict]:
        """Return a summary of all tracked workflows."""
        return [
            {
                "id": w.id,
                "name": w.name,
                "status": w.status,
                "current_step_index": w.current_step_index,
                "total_steps": len(w.steps),
                "created_at": w.created_at,
            }
            for w in self._workflows.values()
        ]

    # ── Internal helpers ──────────────────────────────────────────────────

    def _get_workflow(self, workflow_id: str) -> Workflow:
        workflow = self._workflows.get(workflow_id)
        if workflow is None:
            raise KeyError(f"Workflow '{workflow_id}' not found")
        return workflow

    def _get_step(self, workflow: Workflow, step_id: str) -> WorkflowStep:
        for step in workflow.steps:
            if step.id == step_id:
                return step
        raise KeyError(f"Step '{step_id}' not found in workflow '{workflow.id}'")

    async def _wait_for_resume(self, workflow_id: str, step_id: str) -> bool:
        """Block until approve_step/provide_input is called. Returns approval bool."""
        event_key = f"{workflow_id}:{step_id}"
        event = asyncio.Event()
        self._resume_events[event_key] = event

        await event.wait()

        # Clean up
        self._resume_events.pop(event_key, None)

        # Read the approval decision from the step
        workflow = self._get_workflow(workflow_id)
        step = self._get_step(workflow, step_id)
        approved = getattr(step, "_approved", False)
        if hasattr(step, "_approved"):
            delattr(step, "_approved")
        return approved

    def _step_dict(self, step: WorkflowStep) -> dict:
        """Serialize a step to a JSON-safe dict (excludes callables)."""
        return {
            "id": step.id,
            "name": step.name,
            "description": step.description,
            "checkpoint": step.checkpoint.value,
            "status": step.status.value,
            "errors": step.errors,
            "warnings": step.warnings,
            "started_at": step.started_at,
            "completed_at": step.completed_at,
            "provider_used": step.provider_used,
            "human_feedback": step.human_feedback,
            "retry_count": step.retry_count,
        }

    def _summarize_result(self, result: Any) -> Any:
        """Create a concise summary of a step result for SSE events."""
        if result is None:
            return None
        if isinstance(result, dict):
            # For large dicts, return keys + counts
            summary = {}
            for k, v in result.items():
                if isinstance(v, list):
                    summary[k] = f"{len(v)} items"
                elif isinstance(v, dict):
                    summary[k] = f"{len(v)} keys"
                else:
                    summary[k] = v
            return summary
        if isinstance(result, list):
            return f"{len(result)} items"
        if isinstance(result, str) and len(result) > 200:
            return result[:200] + "..."
        return result

    def _workflow_summary(self, workflow: Workflow) -> dict:
        """Build a summary of the completed workflow."""
        completed = [s for s in workflow.steps if s.status == StepStatus.COMPLETED]
        failed = [s for s in workflow.steps if s.status == StepStatus.FAILED]
        skipped = [s for s in workflow.steps if s.status == StepStatus.SKIPPED]
        total_time = 0.0
        for s in workflow.steps:
            if s.started_at and s.completed_at:
                total_time += s.completed_at - s.started_at

        return {
            "workflow_id": workflow.id,
            "name": workflow.name,
            "total_steps": len(workflow.steps),
            "completed_steps": len(completed),
            "failed_steps": len(failed),
            "skipped_steps": len(skipped),
            "total_time_seconds": round(total_time, 2),
            "steps": [
                {
                    "name": s.name,
                    "status": s.status.value,
                    "duration": round(s.completed_at - s.started_at, 2)
                    if s.started_at and s.completed_at
                    else None,
                }
                for s in workflow.steps
            ],
        }


# Module-level singleton
workflow_engine = WorkflowEngine()
