"""
Event bus system for component communication.
Event-driven architecture with async message dispatch.
"""

import asyncio
import logging
import time
from typing import Dict, List, Any, Callable, Optional, Set
from dataclasses import dataclass, field
from enum import Enum
import weakref


class EventPriority(Enum):
    """Event priority levels."""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class Event:
    """Base event class."""
    type: str
    data: Dict[str, Any]
    source: str
    timestamp: float = field(default_factory=time.time)
    priority: EventPriority = EventPriority.NORMAL
    correlation_id: Optional[str] = None
    session_id: Optional[str] = None


@dataclass
class EventHandler:
    """Event handler registration."""
    callback: Callable
    event_types: Set[str]
    priority: int = 0
    filter_func: Optional[Callable[[Event], bool]] = None


class EventBus:
    """Asynchronous event bus for component communication."""

    def __init__(self):
        self._handlers: Dict[str, List[EventHandler]] = {}
        self._global_handlers: List[EventHandler] = []
        self._event_queue: asyncio.Queue = asyncio.Queue()
        self._processing_task: Optional[asyncio.Task] = None
        self._stats = {
            "events_published": 0,
            "events_processed": 0,
            "handler_errors": 0
        }
        self._logger = logging.getLogger(__name__)

    async def start(self) -> None:
        """Start the event processing loop."""
        if self._processing_task is None or self._processing_task.done():
            self._processing_task = asyncio.create_task(self._process_events())
            self._logger.info("🚌 Event bus started")

    async def stop(self) -> None:
        """Stop the event processing loop."""
        if self._processing_task and not self._processing_task.done():
            self._processing_task.cancel()
            try:
                await self._processing_task
            except asyncio.CancelledError:
                pass
            self._logger.info("🛑 Event bus stopped")

    def subscribe(self,
                 event_types: str | List[str],
                 handler: Callable[[Event], Any],
                 priority: int = 0,
                 filter_func: Optional[Callable[[Event], bool]] = None) -> None:
        """Subscribe to events."""
        if isinstance(event_types, str):
            event_types = [event_types]

        handler_obj = EventHandler(
            callback=handler,
            event_types=set(event_types),
            priority=priority,
            filter_func=filter_func
        )

        # Register for specific event types
        for event_type in event_types:
            if event_type not in self._handlers:
                self._handlers[event_type] = []
            self._handlers[event_type].append(handler_obj)
            # Sort by priority (higher first)
            self._handlers[event_type].sort(key=lambda h: h.priority, reverse=True)

        self._logger.debug(f"📬 Subscribed to events: {event_types}")

    def subscribe_all(self,
                     handler: Callable[[Event], Any],
                     priority: int = 0,
                     filter_func: Optional[Callable[[Event], bool]] = None) -> None:
        """Subscribe to all events."""
        handler_obj = EventHandler(
            callback=handler,
            event_types=set(),
            priority=priority,
            filter_func=filter_func
        )

        self._global_handlers.append(handler_obj)
        self._global_handlers.sort(key=lambda h: h.priority, reverse=True)

        self._logger.debug("📬 Subscribed to all events")

    async def publish(self, event: Event) -> None:
        """Publish an event."""
        await self._event_queue.put(event)
        self._stats["events_published"] += 1
        self._logger.debug(f"📤 Published event: {event.type}")

    async def publish_sync(self, event: Event) -> List[Any]:
        """Publish an event and wait for all handlers to complete."""
        handlers = self._get_handlers_for_event(event)
        results = []

        for handler in handlers:
            try:
                if self._should_handle_event(handler, event):
                    if asyncio.iscoroutinefunction(handler.callback):
                        result = await handler.callback(event)
                    else:
                        result = handler.callback(event)
                    results.append(result)
            except Exception as e:
                self._stats["handler_errors"] += 1
                self._logger.error(f"❌ Handler error for {event.type}: {e}")

        self._stats["events_processed"] += 1
        return results

    async def _process_events(self) -> None:
        """Process events from the queue."""
        while True:
            try:
                event = await self._event_queue.get()
                await self._handle_event(event)
                self._stats["events_processed"] += 1
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.error(f"❌ Event processing error: {e}")

    async def _handle_event(self, event: Event) -> None:
        """Handle a single event."""
        handlers = self._get_handlers_for_event(event)

        # Process handlers in priority order
        for handler in handlers:
            try:
                if self._should_handle_event(handler, event):
                    if asyncio.iscoroutinefunction(handler.callback):
                        await handler.callback(event)
                    else:
                        handler.callback(event)
            except Exception as e:
                self._stats["handler_errors"] += 1
                self._logger.error(f"❌ Handler error for {event.type}: {e}")

    def _get_handlers_for_event(self, event: Event) -> List[EventHandler]:
        """Get all handlers for an event."""
        handlers = []

        # Add specific handlers
        if event.type in self._handlers:
            handlers.extend(self._handlers[event.type])

        # Add global handlers
        handlers.extend(self._global_handlers)

        # Sort by priority
        handlers.sort(key=lambda h: h.priority, reverse=True)
        return handlers

    def _should_handle_event(self, handler: EventHandler, event: Event) -> bool:
        """Check if handler should process this event."""
        # Check event type filter
        if handler.event_types and event.type not in handler.event_types:
            return False

        # Check custom filter
        if handler.filter_func:
            try:
                return handler.filter_func(event)
            except Exception as e:
                self._logger.error(f"❌ Filter function error: {e}")
                return False

        return True

    def unsubscribe(self, handler: Callable) -> None:
        """Unsubscribe a handler from all events."""
        # Remove from specific event handlers
        for event_type, handlers in self._handlers.items():
            self._handlers[event_type] = [h for h in handlers if h.callback != handler]

        # Remove from global handlers
        self._global_handlers = [h for h in self._global_handlers if h.callback != handler]

        self._logger.debug("📭 Unsubscribed handler")

    def get_stats(self) -> Dict[str, Any]:
        """Get event bus statistics."""
        return {
            **self._stats,
            "registered_event_types": len(self._handlers),
            "total_handlers": sum(len(handlers) for handlers in self._handlers.values()) + len(self._global_handlers),
            "queue_size": self._event_queue.qsize()
        }

    def clear_handlers(self) -> None:
        """Clear all event handlers."""
        self._handlers.clear()
        self._global_handlers.clear()
        self._logger.debug("🧹 Cleared all event handlers")


# Event type constants
class EventTypes:
    """Standard event types for the system."""

    # Task events
    TASK_CREATED = "task.created"
    TASK_STARTED = "task.started"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    TASK_CANCELLED = "task.cancelled"

    # Tool events
    TOOL_CALL_REQUESTED = "tool.call.requested"
    TOOL_CALL_APPROVED = "tool.call.approved"
    TOOL_CALL_DENIED = "tool.call.denied"
    TOOL_CALL_EXECUTED = "tool.call.executed"
    TOOL_CALL_FAILED = "tool.call.failed"

    # Session events
    SESSION_CREATED = "session.created"
    SESSION_ENDED = "session.ended"
    SESSION_TIMEOUT = "session.timeout"

    # AI events
    AI_RESPONSE_STARTED = "ai.response.started"
    AI_RESPONSE_CHUNK = "ai.response.chunk"
    AI_RESPONSE_COMPLETED = "ai.response.completed"
    AI_RESPONSE_FAILED = "ai.response.failed"

    # System events
    SYSTEM_STARTUP = "system.startup"
    SYSTEM_SHUTDOWN = "system.shutdown"
    SYSTEM_ERROR = "system.error"

    # File events
    FILE_READ = "file.read"
    FILE_WRITTEN = "file.written"
    FILE_MODIFIED = "file.modified"


# Global event bus instance
_event_bus = EventBus()


def get_event_bus() -> EventBus:
    """Get the global event bus instance."""
    return _event_bus


async def publish_event(event_type: str,
                       data: Dict[str, Any],
                       source: str,
                       priority: EventPriority = EventPriority.NORMAL,
                       session_id: Optional[str] = None) -> None:
    """Convenience function to publish an event."""
    event = Event(
        type=event_type,
        data=data,
        source=source,
        priority=priority,
        session_id=session_id
    )
    await _event_bus.publish(event)