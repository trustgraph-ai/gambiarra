"""
Event handlers for task lifecycle management.
Integrates task events with session management and context tracking.
"""

import logging
from typing import Dict, Any

from ..events.bus import Event, EventTypes, get_event_bus
from ..session.context import get_context_manager
from .manager import get_task_manager

logger = logging.getLogger(__name__)


class TaskEventHandlers:
    """Event handlers for task lifecycle events."""

    def __init__(self):
        self.context_manager = get_context_manager()
        self.task_manager = get_task_manager()
        self.event_bus = get_event_bus()

    def register_handlers(self) -> None:
        """Register all task event handlers."""
        # Task lifecycle events
        self.event_bus.subscribe(EventTypes.TASK_CREATED, self.on_task_created)
        self.event_bus.subscribe(EventTypes.TASK_STARTED, self.on_task_started)
        self.event_bus.subscribe(EventTypes.TASK_COMPLETED, self.on_task_completed)
        self.event_bus.subscribe(EventTypes.TASK_FAILED, self.on_task_failed)
        self.event_bus.subscribe(EventTypes.TASK_CANCELLED, self.on_task_cancelled)

        # Tool execution events
        self.event_bus.subscribe(EventTypes.TOOL_CALL_EXECUTED, self.on_tool_executed)
        self.event_bus.subscribe(EventTypes.TOOL_CALL_FAILED, self.on_tool_failed)

        # File operation events
        self.event_bus.subscribe(EventTypes.FILE_READ, self.on_file_read)
        self.event_bus.subscribe(EventTypes.FILE_WRITTEN, self.on_file_written)

        logger.info("📝 Registered task event handlers")

    async def on_task_created(self, event: Event) -> None:
        """Handle task creation event."""
        try:
            data = event.data
            session_id = event.session_id
            task_id = data.get("task_id")
            task_name = data.get("task_name")

            logger.info(f"📋 Task created: {task_name} ({task_id}) for session {session_id}")

            # Update session context
            if session_id:
                context = self.context_manager.get_context(session_id)
                if context:
                    context.set_current_task(task_name)
                    context.update_task_progress({
                        "current_task_id": task_id,
                        "current_task_name": task_name,
                        "task_state": "created"
                    })

        except Exception as e:
            logger.error(f"❌ Error in task created handler: {e}")

    async def on_task_started(self, event: Event) -> None:
        """Handle task started event."""
        try:
            data = event.data
            session_id = event.session_id
            task_id = data.get("task_id")

            logger.info(f"🚀 Task started: {task_id}")

            # Update context
            if session_id:
                context = self.context_manager.get_context(session_id)
                if context:
                    context.update_task_progress({
                        "task_state": "running",
                        "started_at": event.timestamp
                    })

                    # If task is waiting for approval, set special state
                    if data.get("waiting_for") == "external_input":
                        context.update_task_progress({
                            "task_state": "waiting_approval",
                            "waiting_step": data.get("step_id")
                        })

        except Exception as e:
            logger.error(f"❌ Error in task started handler: {e}")

    async def on_task_completed(self, event: Event) -> None:
        """Handle task completion event."""
        try:
            data = event.data
            session_id = event.session_id
            task_id = data.get("task_id")

            logger.info(f"✅ Task completed: {task_id}")

            # Update context
            if session_id:
                context = self.context_manager.get_context(session_id)
                if context:
                    context.update_task_progress({
                        "task_state": "completed",
                        "completed_at": event.timestamp
                    })

                    # Clear current task
                    context.set_current_task(None)

                    # Optimize context after task completion
                    optimizations = context.optimize_context()
                    if optimizations.get("files_removed", 0) > 0:
                        logger.info(f"🧹 Optimized context: removed {optimizations['files_removed']} stale files")

        except Exception as e:
            logger.error(f"❌ Error in task completed handler: {e}")

    async def on_task_failed(self, event: Event) -> None:
        """Handle task failure event."""
        try:
            data = event.data
            session_id = event.session_id
            task_id = data.get("task_id")
            error = data.get("error")

            logger.error(f"❌ Task failed: {task_id} - {error}")

            # Update context
            if session_id:
                context = self.context_manager.get_context(session_id)
                if context:
                    context.update_task_progress({
                        "task_state": "failed",
                        "failed_at": event.timestamp,
                        "error": error
                    })

                    # Clear current task
                    context.set_current_task(None)

        except Exception as e:
            logger.error(f"❌ Error in task failed handler: {e}")

    async def on_task_cancelled(self, event: Event) -> None:
        """Handle task cancellation event."""
        try:
            data = event.data
            session_id = event.session_id
            task_id = data.get("task_id")

            logger.info(f"❌ Task cancelled: {task_id}")

            # Update context
            if session_id:
                context = self.context_manager.get_context(session_id)
                if context:
                    context.update_task_progress({
                        "task_state": "cancelled",
                        "cancelled_at": event.timestamp
                    })

                    # Clear current task
                    context.set_current_task(None)

        except Exception as e:
            logger.error(f"❌ Error in task cancelled handler: {e}")

    async def on_tool_executed(self, event: Event) -> None:
        """Handle tool execution event."""
        try:
            data = event.data
            session_id = event.session_id
            tool_name = data.get("tool_name")
            parameters = data.get("parameters", {})
            result = data.get("result")
            duration_ms = data.get("duration_ms")

            # Track tool call in context
            if session_id:
                self.context_manager.track_tool_call(
                    session_id=session_id,
                    tool_name=tool_name,
                    parameters=parameters,
                    result=result,
                    duration_ms=duration_ms
                )

            logger.debug(f"🔧 Tool executed: {tool_name}")

        except Exception as e:
            logger.error(f"❌ Error in tool executed handler: {e}")

    async def on_tool_failed(self, event: Event) -> None:
        """Handle tool failure event."""
        try:
            data = event.data
            session_id = event.session_id
            tool_name = data.get("tool_name")
            error = data.get("error")

            logger.warning(f"⚠️ Tool failed: {tool_name} - {error}")

            # Track failed tool call
            if session_id:
                self.context_manager.track_tool_call(
                    session_id=session_id,
                    tool_name=tool_name,
                    parameters=data.get("parameters", {}),
                    result={"error": error, "success": False}
                )

        except Exception as e:
            logger.error(f"❌ Error in tool failed handler: {e}")

    async def on_file_read(self, event: Event) -> None:
        """Handle file read event."""
        try:
            data = event.data
            session_id = event.session_id
            file_path = data.get("file_path")
            content = data.get("content", "")

            # Track file access
            if session_id and file_path:
                self.context_manager.track_file_access(
                    session_id=session_id,
                    file_path=file_path,
                    content=content
                )

            logger.debug(f"📄 File read: {file_path}")

        except Exception as e:
            logger.error(f"❌ Error in file read handler: {e}")

    async def on_file_written(self, event: Event) -> None:
        """Handle file write event."""
        try:
            data = event.data
            session_id = event.session_id
            file_path = data.get("file_path")
            content = data.get("content", "")

            # Track file modification
            if session_id and file_path:
                self.context_manager.track_file_access(
                    session_id=session_id,
                    file_path=file_path,
                    content=content
                )

                # Mark any cached version as stale
                context = self.context_manager.get_context(session_id)
                if context and file_path in context.file_contexts:
                    context.file_contexts[file_path].is_stale = True

            logger.debug(f"✏️ File written: {file_path}")

        except Exception as e:
            logger.error(f"❌ Error in file written handler: {e}")


class SessionEventHandlers:
    """Event handlers for session lifecycle events."""

    def __init__(self):
        self.context_manager = get_context_manager()
        self.task_manager = get_task_manager()
        self.event_bus = get_event_bus()

    def register_handlers(self) -> None:
        """Register session event handlers."""
        self.event_bus.subscribe(EventTypes.SESSION_CREATED, self.on_session_created)
        self.event_bus.subscribe(EventTypes.SESSION_ENDED, self.on_session_ended)
        self.event_bus.subscribe(EventTypes.SESSION_TIMEOUT, self.on_session_timeout)

        logger.info("📝 Registered session event handlers")

    async def on_session_created(self, event: Event) -> None:
        """Handle session creation."""
        try:
            data = event.data
            session_id = event.session_id
            working_directory = data.get("working_directory", ".")

            # Create context for session
            self.context_manager.create_context(session_id, working_directory)

            logger.info(f"📱 Session created: {session_id}")

        except Exception as e:
            logger.error(f"❌ Error in session created handler: {e}")

    async def on_session_ended(self, event: Event) -> None:
        """Handle session end."""
        try:
            session_id = event.session_id

            # Cancel any running tasks for this session
            if session_id:
                running_tasks = await self.task_manager.list_tasks(
                    session_id=session_id,
                    state=None  # Get all states
                )

                for task in running_tasks:
                    if not task.is_complete():
                        await self.task_manager.cancel_task(task.id)

                # Remove context
                self.context_manager.remove_context(session_id)

            logger.info(f"📱 Session ended: {session_id}")

        except Exception as e:
            logger.error(f"❌ Error in session ended handler: {e}")

    async def on_session_timeout(self, event: Event) -> None:
        """Handle session timeout."""
        try:
            session_id = event.session_id

            logger.warning(f"⏰ Session timeout: {session_id}")

            # Same cleanup as session end
            await self.on_session_ended(event)

        except Exception as e:
            logger.error(f"❌ Error in session timeout handler: {e}")


# Global handler instances
_task_handlers = TaskEventHandlers()
_session_handlers = SessionEventHandlers()


def register_all_handlers() -> None:
    """Register all event handlers."""
    _task_handlers.register_handlers()
    _session_handlers.register_handlers()
    logger.info("🎛️ All event handlers registered")


def get_task_handlers() -> TaskEventHandlers:
    """Get task event handlers instance."""
    return _task_handlers


def get_session_handlers() -> SessionEventHandlers:
    """Get session event handlers instance."""
    return _session_handlers