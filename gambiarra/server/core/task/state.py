"""
Task state management.
Defines task states and transitions for workflow management.
"""

from enum import Enum
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
import time
import uuid


class TaskState(Enum):
    """Task execution states."""
    PENDING = "pending"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskPriority(Enum):
    """Task priority levels."""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4


@dataclass
class TaskResult:
    """Result of task execution."""
    success: bool
    data: Any = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    execution_time_ms: Optional[float] = None


@dataclass
class TaskStep:
    """Individual step within a task."""
    id: str
    type: str  # tool_call, decision, wait, etc.
    parameters: Dict[str, Any]
    state: TaskState = TaskState.PENDING
    result: Optional[TaskResult] = None
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    retry_count: int = 0
    max_retries: int = 3


@dataclass
class Task:
    """Task definition and state."""
    id: str
    name: str
    description: str
    session_id: str

    # Task configuration
    priority: TaskPriority = TaskPriority.NORMAL
    timeout_seconds: Optional[int] = None
    max_retries: int = 3

    # Task state
    state: TaskState = TaskState.PENDING
    steps: List[TaskStep] = field(default_factory=list)
    current_step_index: int = 0

    # Execution tracking
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None

    # Results
    result: Optional[TaskResult] = None
    error_message: Optional[str] = None

    # Context
    context: Dict[str, Any] = field(default_factory=dict)
    variables: Dict[str, Any] = field(default_factory=dict)

    def add_step(self, step_type: str, parameters: Dict[str, Any]) -> TaskStep:
        """Add a step to the task."""
        step = TaskStep(
            id=str(uuid.uuid4()),
            type=step_type,
            parameters=parameters
        )
        self.steps.append(step)
        return step

    def get_current_step(self) -> Optional[TaskStep]:
        """Get the current step being executed."""
        if 0 <= self.current_step_index < len(self.steps):
            return self.steps[self.current_step_index]
        return None

    def advance_step(self) -> bool:
        """Advance to the next step."""
        if self.current_step_index < len(self.steps) - 1:
            self.current_step_index += 1
            return True
        return False

    def is_complete(self) -> bool:
        """Check if task is complete."""
        return self.state in [TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED]

    def can_retry(self) -> bool:
        """Check if task can be retried."""
        current_step = self.get_current_step()
        if current_step:
            return current_step.retry_count < current_step.max_retries
        return False

    def get_progress(self) -> Dict[str, Any]:
        """Get task progress information."""
        completed_steps = sum(1 for step in self.steps if step.state == TaskState.COMPLETED)
        total_steps = len(self.steps)

        progress_percent = (completed_steps / total_steps * 100) if total_steps > 0 else 0

        return {
            "task_id": self.id,
            "state": self.state.value,
            "progress_percent": progress_percent,
            "completed_steps": completed_steps,
            "total_steps": total_steps,
            "current_step": self.current_step_index,
            "started_at": self.started_at,
            "estimated_completion": None  # Could be calculated based on step timing
        }

    def get_summary(self) -> Dict[str, Any]:
        """Get task summary."""
        execution_time = None
        if self.started_at and self.completed_at:
            execution_time = (self.completed_at - self.started_at) * 1000  # ms

        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "state": self.state.value,
            "priority": self.priority.value,
            "session_id": self.session_id,
            "created_at": self.created_at,
            "execution_time_ms": execution_time,
            "step_count": len(self.steps),
            "progress": self.get_progress()
        }


class TaskStateManager:
    """Manages task state transitions and validation."""

    # Valid state transitions
    STATE_TRANSITIONS = {
        TaskState.PENDING: [TaskState.RUNNING, TaskState.CANCELLED],
        TaskState.RUNNING: [TaskState.WAITING_APPROVAL, TaskState.PAUSED, TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED],
        TaskState.WAITING_APPROVAL: [TaskState.RUNNING, TaskState.CANCELLED],
        TaskState.PAUSED: [TaskState.RUNNING, TaskState.CANCELLED],
        TaskState.COMPLETED: [],  # Terminal state
        TaskState.FAILED: [TaskState.RUNNING],  # Can retry
        TaskState.CANCELLED: []  # Terminal state
    }

    @classmethod
    def can_transition(cls, from_state: TaskState, to_state: TaskState) -> bool:
        """Check if state transition is valid."""
        return to_state in cls.STATE_TRANSITIONS.get(from_state, [])

    @classmethod
    def transition_task(cls, task: Task, new_state: TaskState, reason: Optional[str] = None) -> bool:
        """Transition task to new state if valid."""
        if not cls.can_transition(task.state, new_state):
            return False

        old_state = task.state
        task.state = new_state

        # Update timestamps
        if new_state == TaskState.RUNNING and task.started_at is None:
            task.started_at = time.time()
        elif new_state in [TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED]:
            task.completed_at = time.time()

        return True

    @classmethod
    def transition_step(cls, step: TaskStep, new_state: TaskState) -> bool:
        """Transition step to new state."""
        old_state = step.state
        step.state = new_state

        # Update timestamps
        if new_state == TaskState.RUNNING:
            step.started_at = time.time()
        elif new_state in [TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED]:
            step.completed_at = time.time()

        return True