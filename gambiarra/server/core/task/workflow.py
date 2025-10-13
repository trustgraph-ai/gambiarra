"""
Workflow definitions and execution engine.
Implements complex multi-step operations with state management.
"""

import logging
import time
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from abc import ABC, abstractmethod

from .state import Task, TaskStep, TaskState, TaskResult, TaskPriority

logger = logging.getLogger(__name__)


@dataclass
class WorkflowDefinition:
    """Definition of a workflow template."""
    name: str
    description: str
    steps: List[Dict[str, Any]]  # Step definitions
    variables: Dict[str, Any] = field(default_factory=dict)
    conditions: Dict[str, Any] = field(default_factory=dict)
    timeout_seconds: Optional[int] = None


class WorkflowStep(ABC):
    """Abstract base class for workflow steps."""

    def __init__(self, step_id: str, parameters: Dict[str, Any]):
        self.step_id = step_id
        self.parameters = parameters

    @abstractmethod
    async def execute(self, context: Dict[str, Any]) -> TaskResult:
        """Execute the workflow step."""
        pass

    @abstractmethod
    def validate(self) -> bool:
        """Validate step configuration."""
        pass


class ToolCallStep(WorkflowStep):
    """Workflow step that executes a tool call."""

    def __init__(self, step_id: str, parameters: Dict[str, Any]):
        super().__init__(step_id, parameters)
        self.tool_name = parameters.get("tool_name")
        self.tool_parameters = parameters.get("tool_parameters", {})

    async def execute(self, context: Dict[str, Any]) -> TaskResult:
        """Execute tool call step."""
        try:
            # This would integrate with the tool execution system
            logger.info(f"🔧 Executing tool: {self.tool_name}")

            # Placeholder for actual tool execution
            # In real implementation, this would call the tool registry
            result_data = {
                "tool_name": self.tool_name,
                "parameters": self.tool_parameters,
                "status": "success"
            }

            return TaskResult(
                success=True,
                data=result_data,
                metadata={"step_type": "tool_call"}
            )

        except Exception as e:
            logger.error(f"❌ Tool call failed: {e}")
            return TaskResult(
                success=False,
                error=str(e),
                metadata={"step_type": "tool_call"}
            )

    def validate(self) -> bool:
        """Validate tool call step."""
        return self.tool_name is not None


class DecisionStep(WorkflowStep):
    """Workflow step that makes a decision based on conditions."""

    def __init__(self, step_id: str, parameters: Dict[str, Any]):
        super().__init__(step_id, parameters)
        self.condition = parameters.get("condition")
        self.true_path = parameters.get("true_path", [])
        self.false_path = parameters.get("false_path", [])

    async def execute(self, context: Dict[str, Any]) -> TaskResult:
        """Execute decision step."""
        try:
            # Evaluate condition (simple implementation)
            condition_result = self._evaluate_condition(context)

            result_data = {
                "condition": self.condition,
                "result": condition_result,
                "next_path": "true" if condition_result else "false"
            }

            return TaskResult(
                success=True,
                data=result_data,
                metadata={"step_type": "decision"}
            )

        except Exception as e:
            logger.error(f"❌ Decision step failed: {e}")
            return TaskResult(
                success=False,
                error=str(e),
                metadata={"step_type": "decision"}
            )

    def _evaluate_condition(self, context: Dict[str, Any]) -> bool:
        """Evaluate the condition (simplified implementation)."""
        # This would be a more sophisticated condition evaluator
        # For now, just check if a variable exists and is truthy
        if isinstance(self.condition, str):
            return context.get(self.condition, False)
        return False

    def validate(self) -> bool:
        """Validate decision step."""
        return self.condition is not None


class WaitStep(WorkflowStep):
    """Workflow step that waits for external input."""

    def __init__(self, step_id: str, parameters: Dict[str, Any]):
        super().__init__(step_id, parameters)
        self.wait_type = parameters.get("wait_type", "approval")
        self.timeout_seconds = parameters.get("timeout_seconds")

    async def execute(self, context: Dict[str, Any]) -> TaskResult:
        """Execute wait step."""
        # This would integrate with the approval system
        result_data = {
            "wait_type": self.wait_type,
            "status": "waiting",
            "timeout_seconds": self.timeout_seconds
        }

        return TaskResult(
            success=True,
            data=result_data,
            metadata={"step_type": "wait", "requires_external_input": True}
        )

    def validate(self) -> bool:
        """Validate wait step."""
        return self.wait_type in ["approval", "input", "timeout"]


class WorkflowEngine:
    """Engine for executing workflows."""

    def __init__(self):
        self.step_types = {
            "tool_call": ToolCallStep,
            "decision": DecisionStep,
            "wait": WaitStep
        }

    def create_task_from_workflow(self,
                                 workflow: WorkflowDefinition,
                                 session_id: str,
                                 context: Optional[Dict[str, Any]] = None) -> Task:
        """Create a task from workflow definition."""
        task = Task(
            id=f"wf_{workflow.name}_{int(time.time())}",
            name=workflow.name,
            description=workflow.description,
            session_id=session_id,
            timeout_seconds=workflow.timeout_seconds,
            context=context or {},
            variables=workflow.variables.copy()
        )

        # Convert workflow steps to task steps
        for i, step_def in enumerate(workflow.steps):
            task.add_step(
                step_type=step_def.get("type", "tool_call"),
                parameters=step_def
            )

        return task

    async def execute_step(self, task: Task, step: TaskStep) -> TaskResult:
        """Execute a single workflow step."""
        step_class = self.step_types.get(step.type)
        if not step_class:
            return TaskResult(
                success=False,
                error=f"Unknown step type: {step.type}"
            )

        workflow_step = step_class(step.id, step.parameters)

        if not workflow_step.validate():
            return TaskResult(
                success=False,
                error=f"Step validation failed for {step.type}"
            )

        return await workflow_step.execute(task.context)

    def register_step_type(self, step_type: str, step_class: type) -> None:
        """Register a custom step type."""
        self.step_types[step_type] = step_class
        logger.info(f"📋 Registered step type: {step_type}")

    def get_available_step_types(self) -> List[str]:
        """Get list of available step types."""
        return list(self.step_types.keys())


# Predefined workflow templates
class StandardWorkflows:
    """Collection of standard workflow definitions."""

    @staticmethod
    def file_analysis_workflow() -> WorkflowDefinition:
        """Workflow for analyzing files in a project."""
        return WorkflowDefinition(
            name="file_analysis",
            description="Analyze files in a project directory",
            steps=[
                {
                    "type": "tool_call",
                    "tool_name": "list_files",
                    "tool_parameters": {"path": ".", "recursive": True}
                },
                {
                    "type": "decision",
                    "condition": "has_python_files",
                    "true_path": ["analyze_python"],
                    "false_path": ["general_analysis"]
                },
                {
                    "type": "tool_call",
                    "tool_name": "search_files",
                    "tool_parameters": {"path": ".", "regex": "def |class ", "file_pattern": "*.py"}
                }
            ]
        )

    @staticmethod
    def code_review_workflow() -> WorkflowDefinition:
        """Workflow for code review process."""
        return WorkflowDefinition(
            name="code_review",
            description="Comprehensive code review process",
            steps=[
                {
                    "type": "tool_call",
                    "tool_name": "list_files",
                    "tool_parameters": {"path": ".", "recursive": False}
                },
                {
                    "type": "tool_call",
                    "tool_name": "search_files",
                    "tool_parameters": {"path": ".", "regex": "TODO|FIXME|BUG"}
                },
                {
                    "type": "wait",
                    "wait_type": "approval",
                    "timeout_seconds": 300
                }
            ]
        )

    @staticmethod
    def debugging_workflow() -> WorkflowDefinition:
        """Workflow for debugging assistance."""
        return WorkflowDefinition(
            name="debugging",
            description="Debug issue in codebase",
            steps=[
                {
                    "type": "tool_call",
                    "tool_name": "search_files",
                    "tool_parameters": {"path": ".", "regex": "error|exception|traceback"}
                },
                {
                    "type": "tool_call",
                    "tool_name": "list_code_definition_names",
                    "tool_parameters": {"path": "main.py"}
                },
                {
                    "type": "decision",
                    "condition": "found_errors",
                    "true_path": ["analyze_errors"],
                    "false_path": ["general_inspection"]
                }
            ]
        )