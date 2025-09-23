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

    @property
    def name(self) -> str:
        return "attempt_completion"

    @property
    def risk_level(self) -> str:
        return "low"

    def __init__(self, prevent_completion_with_todos: bool = False):
        self.prevent_completion_with_todos = prevent_completion_with_todos

    async def execute(self, result: str, command: Optional[str] = None, **kwargs) -> ToolResult:
        """
        Attempt to complete the current task.

        Args:
            result: Summary of what was accomplished
            command: Optional verification command to run

        Returns:
            ToolResult with completion status and next actions
        """
        try:
            # Check for incomplete todos if enabled
            if self.prevent_completion_with_todos and hasattr(self, '_todo_list'):
                incomplete_todos = [todo for todo in self._todo_list if todo.get('status') != 'completed']
                if incomplete_todos:
                    return ToolResult(
                        success=False,
                        error="Cannot complete task while there are incomplete todos. Please finish all todos before attempting completion.",
                        data={
                            "incomplete_todos": incomplete_todos,
                            "action_required": "Complete all todos first"
                        }
                    )

            # Prepare completion data
            completion_data = {
                "result": result,
                "status": "pending_approval",
                "timestamp": asyncio.get_event_loop().time()
            }

            if command:
                completion_data["verification_command"] = command
                # Note: In a full implementation, we might run the command here
                # or prepare it for execution after user approval

            # In a real implementation, this would trigger user approval workflow
            # For now, we'll return the completion attempt data
            return ToolResult(
                success=True,
                data=completion_data,
                message=f"Task completion attempted: {result}"
            )

        except Exception as e:
            logger.error(f"Error in attempt completion: {e}")
            return ToolResult(
                success=False,
                error=f"Failed to attempt completion: {str(e)}"
            )


class AskFollowupQuestionTool(BaseTool):
    """Tool for asking clarifying questions to the user."""

    @property
    def name(self) -> str:
        return "ask_followup_question"

    @property
    def risk_level(self) -> str:
        return "low"

    async def execute(self, question: str, context: Optional[str] = None, **kwargs) -> ToolResult:
        """
        Ask a followup question to the user.

        Args:
            question: The question to ask
            context: Optional context about why the question is needed

        Returns:
            ToolResult with the question and instructions for user response
        """
        try:
            question_data = {
                "question": question,
                "type": "followup_question",
                "status": "waiting_for_response",
                "timestamp": asyncio.get_event_loop().time()
            }

            if context:
                question_data["context"] = context

            return ToolResult(
                success=True,
                data=question_data,
                message=f"Question for user: {question}"
            )

        except Exception as e:
            logger.error(f"Error asking followup question: {e}")
            return ToolResult(
                success=False,
                error=f"Failed to ask question: {str(e)}"
            )


class NewTaskTool(BaseTool):
    """Tool for creating subtasks or new task workflows."""

    @property
    def name(self) -> str:
        return "new_task"

    @property
    def risk_level(self) -> str:
        return "low"

    async def execute(self, task_name: str, description: str,
                     parent_task_id: Optional[str] = None,
                     priority: str = "medium", **kwargs) -> ToolResult:
        """
        Create a new task or subtask.

        Args:
            task_name: Name of the new task
            description: Task description
            parent_task_id: Optional parent task ID
            priority: Task priority level

        Returns:
            ToolResult with new task information
        """
        try:
            import uuid

            task_data = {
                "task_id": str(uuid.uuid4()),
                "name": task_name,
                "description": description,
                "priority": priority,
                "status": "created",
                "created_at": asyncio.get_event_loop().time(),
                "parent_task_id": parent_task_id
            }

            return ToolResult(
                success=True,
                data=task_data,
                message=f"Created new task: {task_name}"
            )

        except Exception as e:
            logger.error(f"Error creating new task: {e}")
            return ToolResult(
                success=False,
                error=f"Failed to create task: {str(e)}"
            )


class ReportBugTool(BaseTool):
    """Tool for reporting bugs or issues encountered during task execution."""

    @property
    def name(self) -> str:
        return "report_bug"

    @property
    def risk_level(self) -> str:
        return "low"

    async def execute(self, title: str, description: str,
                     severity: str = "medium",
                     error_message: Optional[str] = None,
                     context: Optional[Dict[str, Any]] = None, **kwargs) -> ToolResult:
        """
        Report a bug or issue.

        Args:
            title: Bug title
            description: Bug description
            severity: Severity level
            error_message: Optional error message
            context: Optional additional context

        Returns:
            ToolResult with bug report information
        """
        try:
            import uuid

            bug_report = {
                "bug_id": str(uuid.uuid4()),
                "title": title,
                "description": description,
                "severity": severity,
                "status": "reported",
                "reported_at": asyncio.get_event_loop().time()
            }

            if error_message:
                bug_report["error_message"] = error_message

            if context:
                bug_report["context"] = context

            # In a real implementation, this would integrate with a bug tracking system
            # For now, we'll just log and return the report
            logger.info(f"Bug reported: {title} - {severity}")

            return ToolResult(
                success=True,
                data=bug_report,
                message=f"Bug report created: {title}"
            )

        except Exception as e:
            logger.error(f"Error reporting bug: {e}")
            return ToolResult(
                success=False,
                error=f"Failed to report bug: {str(e)}"
            )