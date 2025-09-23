"""
Session management for Gambiarra server.
Handles conversation state and user sessions.
"""

import asyncio
import logging
import time
import uuid
from typing import Dict, Optional, List, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class SessionMessage:
    """A message in the conversation."""
    role: str  # user, assistant, tool
    content: str
    timestamp: float = field(default_factory=time.time)
    images: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SessionConfig:
    """Configuration for a session."""
    working_directory: str = "."
    auto_approve_reads: bool = True
    operating_mode: str = "code"  # Default to full code mode
    require_approval_for_writes: bool = True
    max_concurrent_file_reads: int = 5


class Session:
    """Represents a user session with conversation history."""

    def __init__(self, session_id: str, connection_id: str, config: SessionConfig):
        self.session_id = session_id
        self.connection_id = connection_id
        self.config = config
        self.created_at = time.time()
        self.last_activity = time.time()

        # Conversation state
        self.messages: List[SessionMessage] = []
        self.pending_tools: Dict[str, Any] = {}

        # Context and memory
        self.context_files: List[str] = []
        self.working_memory: Dict[str, Any] = {}

    async def add_message(self, role: str, content: str, images: List[str] = None, metadata: Dict[str, Any] = None) -> None:
        """Add a message to the conversation."""
        message = SessionMessage(
            role=role,
            content=content,
            images=images or [],
            metadata=metadata or {}
        )

        self.messages.append(message)
        self.last_activity = time.time()

        logger.debug(f"📝 Added {role} message to session {self.session_id}")


    async def get_messages(self) -> List[Dict[str, str]]:
        """Get conversation messages in OpenAI format."""
        openai_messages = []

        for msg in self.messages:
            openai_msg = {
                "role": msg.role,
                "content": msg.content
            }

            openai_messages.append(openai_msg)

        return openai_messages

    async def get_context_summary(self) -> str:
        """Generate a summary of the current context."""
        summary_parts = []

        # Basic session info
        summary_parts.append(f"Session: {self.session_id}")
        summary_parts.append(f"Working directory: {self.config.working_directory}")
        summary_parts.append(f"Messages: {len(self.messages)}")

        # Context files
        if self.context_files:
            summary_parts.append(f"Context files: {', '.join(self.context_files)}")

        # Recent activity
        recent_messages = self.messages[-3:] if len(self.messages) > 3 else self.messages
        if recent_messages:
            summary_parts.append("Recent conversation:")
            for msg in recent_messages:
                summary_parts.append(f"  {msg.role}: {msg.content[:100]}...")

        return "\n".join(summary_parts)

    def is_expired(self, timeout: int) -> bool:
        """Check if session has expired."""
        return (time.time() - self.last_activity) > timeout

    def update_activity(self) -> None:
        """Update last activity timestamp."""
        self.last_activity = time.time()


class SessionManager:
    """Manages user sessions."""

    def __init__(self):
        self.sessions: Dict[str, Session] = {}
        self.connection_to_session: Dict[str, str] = {}
        self._lock = asyncio.Lock()
        self._total_sessions = 0

    async def create_session(self, connection_id: str, config: Dict[str, Any]) -> str:
        """Create a new session."""
        async with self._lock:
            session_id = str(uuid.uuid4())

            # Parse config
            session_config = SessionConfig(
                working_directory=config.get("working_directory", "."),
                auto_approve_reads=config.get("auto_approve_reads", True),
                require_approval_for_writes=config.get("require_approval_for_writes", True),
                max_concurrent_file_reads=config.get("max_concurrent_file_reads", 5)
            )

            # Create session
            session = Session(session_id, connection_id, session_config)

            # Store session
            self.sessions[session_id] = session
            self.connection_to_session[connection_id] = session_id
            self._total_sessions += 1

            logger.info(f"🎯 Created session {session_id} for connection {connection_id}")

            return session_id

    def get_session(self, session_id: str) -> Optional[Session]:
        """Get session by ID."""
        session = self.sessions.get(session_id)
        if session:
            session.update_activity()
        return session

    def get_session_by_connection(self, connection_id: str) -> Optional[Session]:
        """Get session by connection ID."""
        session_id = self.connection_to_session.get(connection_id)
        if session_id:
            return self.get_session(session_id)
        return None

    async def cleanup_session(self, connection_id: str) -> None:
        """Clean up session for a connection."""
        async with self._lock:
            session_id = self.connection_to_session.get(connection_id)

            if session_id:
                # Remove session
                if session_id in self.sessions:
                    del self.sessions[session_id]
                    logger.info(f"🧹 Cleaned up session {session_id}")

                # Remove connection mapping
                del self.connection_to_session[connection_id]

    async def cleanup_expired_sessions(self, timeout: int) -> int:
        """Clean up expired sessions."""
        async with self._lock:
            expired_sessions = []

            for session_id, session in self.sessions.items():
                if session.is_expired(timeout):
                    expired_sessions.append(session_id)

            # Remove expired sessions
            for session_id in expired_sessions:
                session = self.sessions[session_id]

                # Remove connection mapping
                if session.connection_id in self.connection_to_session:
                    del self.connection_to_session[session.connection_id]

                # Remove session
                del self.sessions[session_id]

                logger.info(f"⏰ Expired session {session_id}")

            return len(expired_sessions)

    async def cleanup_all(self) -> None:
        """Clean up all sessions."""
        async with self._lock:
            session_count = len(self.sessions)
            self.sessions.clear()
            self.connection_to_session.clear()

            logger.info(f"🧹 Cleaned up {session_count} sessions")

    def active_session_count(self) -> int:
        """Get number of active sessions."""
        return len(self.sessions)

    def total_session_count(self) -> int:
        """Get total number of sessions created."""
        return self._total_sessions

    def list_sessions(self) -> List[Dict[str, Any]]:
        """List all active sessions."""
        sessions_info = []

        for session_id, session in self.sessions.items():
            sessions_info.append({
                "session_id": session_id,
                "connection_id": session.connection_id,
                "created_at": session.created_at,
                "last_activity": session.last_activity,
                "message_count": len(session.messages),
                "config": {
                    "working_directory": session.config.working_directory
                }
            })

        return sessions_info

    async def start_cleanup_task(self, timeout: int = 3600, interval: int = 300) -> None:
        """Start background task to clean up expired sessions."""
        async def cleanup_loop():
            while True:
                try:
                    await asyncio.sleep(interval)
                    expired_count = await self.cleanup_expired_sessions(timeout)
                    if expired_count > 0:
                        logger.info(f"🧹 Cleaned up {expired_count} expired sessions")
                except Exception as e:
                    logger.error(f"❌ Error in session cleanup: {e}")

        asyncio.create_task(cleanup_loop())
        logger.info(f"🕐 Started session cleanup task (timeout: {timeout}s, interval: {interval}s)")