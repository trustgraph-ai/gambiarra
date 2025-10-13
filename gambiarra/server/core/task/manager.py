"""
Task Manager - orchestrates task execution and lifecycle.
Task-centric architecture with workflow orchestration.
"""

import asyncio
import logging
import time
from typing import Dict, List, Any, Optional, Callable
import uuid

from .state import Task, TaskStep, TaskState, TaskResult, TaskPriority, TaskStateManager
from .workflow import WorkflowEngine, WorkflowDefinition
from ..events.bus import get_event_bus, EventTypes, publish_event, EventPriority

logger = logging.getLogger(__name__)


class TaskExecutor:
    """Executes individual tasks."""

    def __init__(self, workflow_engine: WorkflowEngine):
        self.workflow_engine = workflow_engine
        self.event_bus = get_event_bus()

    async def execute_task(self, task: Task) -> TaskResult:
        """Execute a complete task."""
        try:
            # Transition to running state
            TaskStateManager.transition_task(task, TaskState.RUNNING)
            await self._publish_task_event(EventTypes.TASK_STARTED, task)

            while not task.is_complete() and task.current_step_index < len(task.steps):
                current_step = task.get_current_step()
                if not current_step:
                    break

                # Execute current step
                step_result = await self._execute_step(task, current_step)

                if step_result.success:
                    TaskStateManager.transition_step(current_step, TaskState.COMPLETED)
                    current_step.result = step_result

                    # Check if we need external input
                    if step_result.metadata.get("requires_external_input"):
                        TaskStateManager.transition_task(task, TaskState.WAITING_APPROVAL)
                        await self._publish_task_event(EventTypes.TASK_STARTED, task, {
                            "waiting_for": "external_input",
                            "step_id": current_step.id
                        })
                        return TaskResult(success=True, data={"status": "waiting_approval"})

                    # Advance to next step
                    if not task.advance_step():
                        # No more steps, task is complete
                        break
                else:
                    # Step failed
                    TaskStateManager.transition_step(current_step, TaskState.FAILED)
                    current_step.result = step_result

                    if task.can_retry():
                        current_step.retry_count += 1
                        logger.info(f"🔄 Retrying step {current_step.id} (attempt {current_step.retry_count})")
                        TaskStateManager.transition_step(current_step, TaskState.PENDING)
                    else:
                        TaskStateManager.transition_task(task, TaskState.FAILED)
                        task.error_message = step_result.error
                        await self._publish_task_event(EventTypes.TASK_FAILED, task, {
                            "error": step_result.error,
                            "failed_step": current_step.id
                        })
                        return TaskResult(success=False, error=step_result.error)

            # Task completed successfully
            TaskStateManager.transition_task(task, TaskState.COMPLETED)
            task_result = TaskResult(
                success=True,
                data={"completed_steps": len(task.steps)},
                metadata={"task_id": task.id}
            )
            task.result = task_result

            await self._publish_task_event(EventTypes.TASK_COMPLETED, task)
            return task_result

        except Exception as e:
            logger.error(f"❌ Task execution error: {e}")
            TaskStateManager.transition_task(task, TaskState.FAILED)
            task.error_message = str(e)
            await self._publish_task_event(EventTypes.TASK_FAILED, task, {"error": str(e)})
            return TaskResult(success=False, error=str(e))

    async def _execute_step(self, task: Task, step: TaskStep) -> TaskResult:
        """Execute a single task step."""
        TaskStateManager.transition_step(step, TaskState.RUNNING)

        try:
            start_time = time.time()
            result = await self.workflow_engine.execute_step(task, step)
            execution_time = (time.time() - start_time) * 1000

            result.execution_time_ms = execution_time
            return result

        except Exception as e:
            logger.error(f"❌ Step execution error: {e}")
            return TaskResult(success=False, error=str(e))

    async def _publish_task_event(self, event_type: str, task: Task, extra_data: Dict[str, Any] = None) -> None:
        """Publish task-related event."""
        data = {
            "task_id": task.id,
            "task_name": task.name,
            "session_id": task.session_id,
            "state": task.state.value
        }
        if extra_data:
            data.update(extra_data)

        await publish_event(
            event_type=event_type,
            data=data,
            source="task_executor",
            session_id=task.session_id
        )


class TaskManager:
    """Manages task lifecycle and execution."""

    def __init__(self):
        self.tasks: Dict[str, Task] = {}
        self.workflow_engine = WorkflowEngine()
        self.task_executor = TaskExecutor(self.workflow_engine)
        self.event_bus = get_event_bus()
        self._execution_queue: asyncio.Queue = asyncio.Queue()
        self._executor_task: Optional[asyncio.Task] = None
        self._max_concurrent_tasks = 5
        self._running_tasks: Dict[str, asyncio.Task] = {}

    async def start(self) -> None:
        """Start the task manager."""
        await self.event_bus.start()
        if self._executor_task is None or self._executor_task.done():
            self._executor_task = asyncio.create_task(self._execution_loop())
            logger.info("🎯 Task manager started")

    async def stop(self) -> None:
        """Stop the task manager."""
        if self._executor_task and not self._executor_task.done():
            self._executor_task.cancel()
            try:
                await self._executor_task
            except asyncio.CancelledError:
                pass

        # Cancel running tasks
        for task_id, task in self._running_tasks.items():
            task.cancel()

        await self.event_bus.stop()
        logger.info("🛑 Task manager stopped")

    async def create_task(self,
                         name: str,
                         description: str,
                         session_id: str,
                         steps: Optional[List[Dict[str, Any]]] = None,
                         priority: TaskPriority = TaskPriority.NORMAL,
                         workflow: Optional[WorkflowDefinition] = None) -> Task:
        """Create a new task."""

        if workflow:
            task = self.workflow_engine.create_task_from_workflow(workflow, session_id)
        else:
            task = Task(
                id=str(uuid.uuid4()),
                name=name,
                description=description,
                session_id=session_id,
                priority=priority
            )

            # Add steps if provided
            if steps:
                for step_def in steps:
                    task.add_step(
                        step_type=step_def.get("type", "tool_call"),
                        parameters=step_def
                    )

        self.tasks[task.id] = task

        await publish_event(
            event_type=EventTypes.TASK_CREATED,
            data={
                "task_id": task.id,
                "task_name": task.name,
                "session_id": task.session_id,
                "step_count": len(task.steps)
            },
            source="task_manager",
            session_id=session_id
        )

        logger.info(f"📋 Created task: {task.name} ({task.id})")
        return task

    async def execute_task(self, task_id: str) -> Optional[TaskResult]:
        """Queue task for execution."""
        task = self.tasks.get(task_id)
        if not task:
            return None

        # Add to execution queue
        await self._execution_queue.put(task)
        logger.info(f"⏳ Queued task for execution: {task.name}")

        return None

    async def get_task(self, task_id: str) -> Optional[Task]:
        """Get task by ID."""
        return self.tasks.get(task_id)

    async def list_tasks(self, session_id: Optional[str] = None, state: Optional[TaskState] = None) -> List[Task]:
        """List tasks with optional filtering."""
        tasks = list(self.tasks.values())

        if session_id:
            tasks = [t for t in tasks if t.session_id == session_id]

        if state:
            tasks = [t for t in tasks if t.state == state]

        return tasks

    async def cancel_task(self, task_id: str) -> bool:
        """Cancel a task."""
        task = self.tasks.get(task_id)
        if not task:
            return False

        if task.state in [TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED]:
            return False

        TaskStateManager.transition_task(task, TaskState.CANCELLED)

        # Cancel running execution if any
        if task_id in self._running_tasks:
            self._running_tasks[task_id].cancel()
            del self._running_tasks[task_id]

        await publish_event(
            event_type=EventTypes.TASK_CANCELLED,
            data={"task_id": task_id, "session_id": task.session_id},
            source="task_manager",
            session_id=task.session_id
        )

        logger.info(f"❌ Cancelled task: {task.name}")
        return True

    async def _execution_loop(self) -> None:
        """Main execution loop for processing queued tasks."""
        while True:
            try:
                # Wait for a task to execute
                task = await self._execution_queue.get()

                # Check if we can run more tasks concurrently
                if len(self._running_tasks) >= self._max_concurrent_tasks:
                    await self._execution_queue.put(task)  # Put it back
                    await asyncio.sleep(0.1)  # Brief delay
                    continue

                # Start task execution
                execution_task = asyncio.create_task(self.task_executor.execute_task(task))
                self._running_tasks[task.id] = execution_task

                # Set up completion callback
                execution_task.add_done_callback(
                    lambda t, task_id=task.id: self._on_task_execution_complete(task_id, t)
                )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Error in execution loop: {e}")

    def _on_task_execution_complete(self, task_id: str, execution_task: asyncio.Task) -> None:
        """Handle task execution completion."""
        if task_id in self._running_tasks:
            del self._running_tasks[task_id]

        try:
            result = execution_task.result()
            logger.info(f"✅ Task execution completed: {task_id}")
        except Exception as e:
            logger.error(f"❌ Task execution failed: {task_id} - {e}")

    def get_stats(self) -> Dict[str, Any]:
        """Get task manager statistics."""
        states = {}
        for task in self.tasks.values():
            state = task.state.value
            states[state] = states.get(state, 0) + 1

        return {
            "total_tasks": len(self.tasks),
            "running_tasks": len(self._running_tasks),
            "queued_tasks": self._execution_queue.qsize(),
            "states": states,
            "max_concurrent": self._max_concurrent_tasks
        }


# Global task manager instance
_task_manager = TaskManager()


def get_task_manager() -> TaskManager:
    """Get the global task manager instance."""
    return _task_manager