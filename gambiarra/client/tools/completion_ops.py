"""
Task completion and workflow management tools for Gambiarra.
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List
from .base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class AttemptCompletionTool(BaseTool):
    """Tool for attempting task completion and requesting user approval."""

    def __init__(self, security_manager):
        super().__init__(security_manager)

    @property
    def name(self) -> str:
        return "attempt_completion"

    @property
    def risk_level(self) -> str:
        return "low"

    async def execute(self, parameters: Dict[str, Any]) -> ToolResult:
        """
        Attempt to complete the current task.

        Args:
            parameters: Dictionary containing 'result' and optional 'command'

        Returns:
            ToolResult with completion status and next actions
        """
        try:
            self.validate_parameters(parameters, ["result"], ["command"])
            result = parameters["result"]
            command = parameters.get("command")

            # Prepare completion data
            completion_data = {
                "result": result,
                "status": "pending_approval",
                "timestamp": asyncio.get_event_loop().time()
            }

            if command:
                completion_data["verification_command"] = command

            return ToolResult.success(
                data=completion_data,
                metadata={"message": f"Task completion attempted: {result}"}
            )

        except Exception as e:
            logger.error(f"Error in attempt completion: {e}")
            return ToolResult.create_error(
                code="execution_error",
                message=f"Failed to attempt completion: {str(e)}"
            )


class AskFollowupQuestionTool(BaseTool):
    """Tool for asking clarifying questions to the user."""

    @property
    def name(self) -> str:
        return "ask_followup_question"

    @property
    def risk_level(self) -> str:
        return "low"

    async def execute(self, parameters: Dict[str, Any]) -> ToolResult:
        """
        Ask a followup question to the user.

        Args:
            parameters: Dictionary containing 'question' and optional 'context'

        Returns:
            ToolResult with the question and instructions for user response
        """
        try:
            self.validate_parameters(parameters, ["question"], ["context"])
            question = parameters["question"]
            context = parameters.get("context")

            question_data = {
                "question": question,
                "type": "followup_question",
                "status": "waiting_for_response",
                "timestamp": asyncio.get_event_loop().time()
            }

            if context:
                question_data["context"] = context

            return ToolResult.success(
                data=question_data,
                metadata={"message": f"Question for user: {question}"}
            )

        except Exception as e:
            logger.error(f"Error asking followup question: {e}")
            return ToolResult.create_error(
                code="execution_error",
                message=f"Failed to ask question: {str(e)}"
            )


class NewTaskTool(BaseTool):
    """Tool for creating subtasks or new task workflows."""

    @property
    def name(self) -> str:
        return "new_task"

    @property
    def risk_level(self) -> str:
        return "low"

    async def execute(self, parameters: Dict[str, Any]) -> ToolResult:
        """
        Create a new task or subtask.

        Args:
            parameters: Dictionary containing task details

        Returns:
            ToolResult with new task information
        """
        try:
            self.validate_parameters(
                parameters,
                ["task_name", "description"],
                ["parent_task_id", "priority"]
            )

            import uuid

            task_data = {
                "task_id": str(uuid.uuid4()),
                "name": parameters["task_name"],
                "description": parameters["description"],
                "priority": parameters.get("priority", "medium"),
                "status": "created",
                "created_at": asyncio.get_event_loop().time(),
                "parent_task_id": parameters.get("parent_task_id")
            }

            return ToolResult.success(
                data=task_data,
                metadata={"message": f"Created new task: {parameters['task_name']}"}
            )

        except Exception as e:
            logger.error(f"Error creating new task: {e}")
            return ToolResult.create_error(
                code="execution_error",
                message=f"Failed to create task: {str(e)}"
            )


class ReportBugTool(BaseTool):
    """Tool for reporting bugs or issues encountered during task execution."""

    @property
    def name(self) -> str:
        return "report_bug"

    @property
    def risk_level(self) -> str:
        return "low"

    async def execute(self, parameters: Dict[str, Any]) -> ToolResult:
        """
        Report a bug or issue.

        Args:
            parameters: Dictionary containing bug details

        Returns:
            ToolResult with bug report information
        """
        try:
            self.validate_parameters(
                parameters,
                ["title", "description"],
                ["severity", "error_message", "context"]
            )

            import uuid

            bug_report = {
                "bug_id": str(uuid.uuid4()),
                "title": parameters["title"],
                "description": parameters["description"],
                "severity": parameters.get("severity", "medium"),
                "status": "reported",
                "reported_at": asyncio.get_event_loop().time()
            }

            if parameters.get("error_message"):
                bug_report["error_message"] = parameters["error_message"]

            if parameters.get("context"):
                bug_report["context"] = parameters["context"]

            logger.info(f"Bug reported: {parameters['title']} - {bug_report['severity']}")

            return ToolResult.success(
                data=bug_report,
                metadata={"message": f"Bug report created: {parameters['title']}"}
            )

        except Exception as e:
            logger.error(f"Error reporting bug: {e}")
            return ToolResult.create_error(
                code="execution_error",
                message=f"Failed to report bug: {str(e)}"
            )