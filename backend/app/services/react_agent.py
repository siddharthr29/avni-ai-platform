"""ReAct Agent: Plan -> Execute -> Observe -> Correct.

Autonomous agent loop for multi-step Avni setup tasks.
Uses MCP tools for CRUD, bundle validator for pre-upload checks,
and LLM reasoning for planning and error correction.
"""

import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ActionType(str, Enum):
    MCP_CALL = "mcp_call"
    BUNDLE_VALIDATE = "bundle_validate"
    BUNDLE_UPLOAD = "bundle_upload"
    SEARCH_KNOWLEDGE = "search_knowledge"
    ASK_USER = "ask_user"
    DONE = "done"


class StepStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    NEEDS_RETRY = "needs_retry"
    NEEDS_USER = "needs_user"


@dataclass
class AgentStep:
    step_number: int
    thought: str
    action_type: ActionType
    action_input: dict
    observation: str = ""
    status: StepStatus = StepStatus.SUCCESS
    retry_count: int = 0
    duration_ms: int = 0

    def to_dict(self) -> dict:
        return {
            "step": self.step_number,
            "thought": self.thought,
            "action": self.action_type.value,
            "input": self.action_input,
            "observation": self.observation,
            "status": self.status.value,
            "retries": self.retry_count,
            "duration_ms": self.duration_ms,
        }


@dataclass
class AgentTask:
    task_id: str
    goal: str
    auth_token: str
    steps: list[AgentStep] = field(default_factory=list)
    status: str = "running"  # running | completed | failed | needs_user
    error: str = ""
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "status": self.status,
            "steps": [s.to_dict() for s in self.steps],
            "error": self.error,
            "step_count": len(self.steps),
        }


MAX_STEPS = 15
MAX_RETRIES = 3


class ReactAgent:
    """ReAct agent that plans and executes multi-step Avni tasks."""

    def __init__(self) -> None:
        self._tasks: dict[str, AgentTask] = {}

    async def run(
        self,
        task_id: str,
        goal: str,
        auth_token: str,
        context: dict | None = None,
    ) -> AgentTask:
        """Execute a goal using the ReAct loop.

        Args:
            task_id: Unique task identifier
            goal: Natural language description of what to achieve
            auth_token: Avni AUTH-TOKEN for MCP/bundle operations
            context: Optional dict with org_name, bundle_id, etc.
        """
        from app.services.mcp_client import mcp_client

        task = AgentTask(task_id=task_id, goal=goal, auth_token=auth_token)
        self._tasks[task_id] = task
        context = context or {}

        # Get available tools for the planning prompt
        tools = await mcp_client.list_tools()
        tool_names = [t.get("name", "") for t in tools] if tools else []

        for step_num in range(1, MAX_STEPS + 1):
            # Build the reasoning prompt
            history = "\n".join(
                f"Step {s.step_number}: [{s.action_type.value}] {s.thought} -> {s.observation}"
                for s in task.steps
            )

            planning_prompt = f"""You are an Avni setup agent. Your goal: {goal}

Context: {context}

Available MCP tools: {', '.join(tool_names) if tool_names else 'MCP server unavailable'}
Other actions: bundle_validate, bundle_upload, search_knowledge, ask_user, done

Previous steps:
{history if history else '(none yet)'}

Think step by step. What should you do next?

Respond in this exact JSON format:
{{"thought": "your reasoning", "action": "action_type", "input": {{"key": "value"}}}}

If the goal is achieved, use action "done" with input {{"summary": "what was accomplished"}}.
If you need user confirmation for a destructive action, use "ask_user".
"""

            try:
                # Get LLM reasoning
                from app.services.claude_client import claude_client

                llm_response = await claude_client.complete(
                    messages=[{"role": "user", "content": planning_prompt}],
                    system_prompt="You are an Avni configuration agent. Respond only with valid JSON.",
                )

                # Parse the response
                response_text = llm_response.strip()
                # Handle markdown code blocks
                if "```json" in response_text:
                    response_text = response_text.split("```json")[1].split("```")[0].strip()
                elif "```" in response_text:
                    response_text = response_text.split("```")[1].split("```")[0].strip()

                parsed = json.loads(response_text)
                thought = parsed.get("thought", "")
                action_type_str = parsed.get("action", "done")
                action_input = parsed.get("input", {})

            except Exception as e:
                logger.warning("Agent step %d: LLM parse error: %s", step_num, e)
                thought = f"Failed to parse LLM response: {e}"
                action_type_str = "done"
                action_input = {"summary": f"Stopped due to planning error: {e}"}

            # Map action type
            try:
                action_type = ActionType(action_type_str)
            except ValueError:
                action_type = ActionType.DONE
                action_input = {"summary": f"Unknown action '{action_type_str}', stopping"}

            step = AgentStep(
                step_number=step_num,
                thought=thought,
                action_type=action_type,
                action_input=action_input,
            )

            start = time.time()

            # Execute the action
            try:
                observation = await self._execute_action(
                    action_type, action_input, auth_token, context
                )
                step.observation = observation
                step.status = StepStatus.SUCCESS
            except Exception as e:
                step.observation = str(e)
                step.status = StepStatus.FAILED
                step.retry_count += 1

                # Retry logic
                if step.retry_count < MAX_RETRIES and action_type != ActionType.DONE:
                    step.status = StepStatus.NEEDS_RETRY
                    # Translate the error for the next planning cycle
                    from app.services.error_translator import translate_avni_error

                    translated = translate_avni_error(str(e))
                    step.observation = f"FAILED: {e}\nSuggested fix: {translated['suggestion']}"

            step.duration_ms = int((time.time() - start) * 1000)
            task.steps.append(step)

            logger.info(
                "Agent step %d: [%s] %s -> %s",
                step_num,
                action_type.value,
                thought[:80],
                step.observation[:100],
            )

            # Check termination conditions
            if action_type == ActionType.DONE:
                task.status = "completed"
                break
            if action_type == ActionType.ASK_USER:
                task.status = "needs_user"
                break
            if step.status == StepStatus.FAILED and step.retry_count >= MAX_RETRIES:
                task.status = "failed"
                task.error = f"Max retries exceeded at step {step_num}: {step.observation}"
                break

        else:
            task.status = "failed"
            task.error = f"Max steps ({MAX_STEPS}) reached without completing goal"

        return task

    async def _execute_action(
        self,
        action_type: ActionType,
        action_input: dict,
        auth_token: str,
        context: dict,
    ) -> str:
        """Execute a single agent action and return the observation."""
        from app.services.mcp_client import mcp_client

        if action_type == ActionType.MCP_CALL:
            tool_name = action_input.get("tool_name", "")
            arguments = action_input.get("arguments", {})
            # Inject auth_token if not present
            if "auth_token" not in arguments:
                arguments["auth_token"] = auth_token
            result = await mcp_client.call_tool(tool_name, arguments)
            if result["success"]:
                return f"Success: {result['result']}"
            else:
                raise RuntimeError(result["error"] or "MCP tool call failed")

        elif action_type == ActionType.BUNDLE_VALIDATE:
            bundle_id = action_input.get("bundle_id", context.get("bundle_id", ""))
            if not bundle_id:
                return "No bundle_id provided"
            from app.services.bundle_generator import get_bundle_zip_path

            zip_path = get_bundle_zip_path(bundle_id)
            if not zip_path:
                return f"Bundle {bundle_id} not found"
            from app.services.preflight_validator import validate_bundle

            result = validate_bundle(zip_path)
            if result["valid"]:
                return f"Validation passed ({result['warning_count']} warnings)"
            else:
                issues = result["issues"][:5]  # First 5 issues
                issue_text = "; ".join(
                    f"[{i['severity']}] {i['message']}" for i in issues
                )
                raise RuntimeError(f"Validation failed: {issue_text}")

        elif action_type == ActionType.BUNDLE_UPLOAD:
            bundle_id = action_input.get("bundle_id", context.get("bundle_id", ""))
            if not bundle_id:
                return "No bundle_id provided"
            from app.services.avni_org_service import avni_org_service
            from app.services.bundle_generator import get_bundle_zip_path

            zip_path = get_bundle_zip_path(bundle_id)
            if not zip_path:
                return f"Bundle {bundle_id} not found"
            result = await avni_org_service.upload_bundle_two_pass(
                auth_token=auth_token,
                bundle_zip_path=zip_path,
            )
            return f"Upload {result.get('status', 'unknown')}: {result.get('message', '')}"

        elif action_type == ActionType.SEARCH_KNOWLEDGE:
            query = action_input.get("query", "")
            if not query:
                return "No search query provided"
            from app.services.rag.fallback import rag_service

            results = await rag_service.search(query, top_k=3)
            if results:
                return "\n".join(f"- {r.text[:200]}" for r in results)
            return "No relevant knowledge found"

        elif action_type == ActionType.ASK_USER:
            question = action_input.get("question", "Please confirm this action")
            return f"WAITING_FOR_USER: {question}"

        elif action_type == ActionType.DONE:
            return action_input.get("summary", "Task completed")

        return "Unknown action"

    def get_task(self, task_id: str) -> AgentTask | None:
        return self._tasks.get(task_id)

    async def resume_task(self, task_id: str, user_response: str) -> AgentTask | None:
        """Resume a task that was waiting for user input."""
        task = self._tasks.get(task_id)
        if not task or task.status != "needs_user":
            return None

        # Add user response as an observation
        if task.steps:
            task.steps[-1].observation += f"\nUser response: {user_response}"

        # Continue the agent loop
        task.status = "running"
        context = {"user_response": user_response}
        return await self.run(task.task_id, task.goal, task.auth_token, context)


# Singleton
react_agent = ReactAgent()
