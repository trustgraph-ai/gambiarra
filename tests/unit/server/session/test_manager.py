"""
Tests for server session management.
Tests session lifecycle, message handling, and state management.
"""

import pytest
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock
from gambiarra.server.session.manager import (
    SessionManager, Session, SessionMessage, SessionConfig
)


class TestSessionMessage:
    """Test SessionMessage data structure."""

    def test_session_message_creation(self):
        """Test creating a session message."""
        message = SessionMessage(
            role="user",
            content="Hello, world!",
            timestamp=1638360000.0
        )

        assert message.role == "user"
        assert message.content == "Hello, world!"
        assert message.timestamp == 1638360000.0
        assert message.images == []
        assert message.metadata == {}

    def test_session_message_with_images(self):
        """Test session message with images."""
        images = ["data:image/png;base64,iVBOR...", "path/to/image.jpg"]
        message = SessionMessage(
            role="user",
            content="Look at these images",
            images=images
        )

        assert message.images == images
        assert len(message.images) == 2

    def test_session_message_with_metadata(self):
        """Test session message with metadata."""
        metadata = {"tool_call_id": "123", "confidence": 0.95}
        message = SessionMessage(
            role="assistant",
            content="I'll help you with that",
            metadata=metadata
        )

        assert message.metadata == metadata
        assert message.metadata["tool_call_id"] == "123"

    def test_session_message_default_timestamp(self):
        """Test that timestamp defaults to current time."""
        before = time.time()
        message = SessionMessage(role="user", content="test")
        after = time.time()

        assert before <= message.timestamp <= after


class TestSessionConfig:
    """Test SessionConfig data structure."""

    def test_default_session_config(self):
        """Test default session configuration."""
        config = SessionConfig()

        assert config.working_directory == "."
        assert config.auto_approve_reads is True
        assert config.operating_mode == "code"
        assert config.require_approval_for_writes is True
        assert config.max_concurrent_file_reads == 5

    def test_custom_session_config(self):
        """Test custom session configuration."""
        config = SessionConfig(
            working_directory="/custom/path",
            auto_approve_reads=False,
            operating_mode="safe",
            require_approval_for_writes=False,
            max_concurrent_file_reads=10
        )

        assert config.working_directory == "/custom/path"
        assert config.auto_approve_reads is False
        assert config.operating_mode == "safe"
        assert config.require_approval_for_writes is False
        assert config.max_concurrent_file_reads == 10


class TestSession:
    """Test Session class functionality."""

    @pytest.fixture
    def session_config(self):
        """Create test session configuration."""
        return SessionConfig(
            working_directory="/test/workspace",
            auto_approve_reads=True,
            operating_mode="code"
        )

    @pytest.fixture
    def test_session(self, session_config):
        """Create test session instance."""
        return Session(
            session_id="test-session-123",
            connection_id="conn-456",
            config=session_config
        )

    def test_session_creation(self, test_session, session_config):
        """Test session creation with proper initialization."""
        assert test_session.session_id == "test-session-123"
        assert test_session.connection_id == "conn-456"
        assert test_session.config == session_config
        assert isinstance(test_session.created_at, float)
        assert isinstance(test_session.last_activity, float)
        assert test_session.messages == []
        assert test_session.pending_tools == {}

    async def test_add_message(self, test_session):
        """Test adding messages to session."""
        await test_session.add_message("user", "Hello")

        assert len(test_session.messages) == 1
        assert test_session.messages[0].role == "user"
        assert test_session.messages[0].content == "Hello"

    def test_multiple_messages(self, test_session):
        """Test adding multiple messages."""
        messages = [
            SessionMessage(role="user", content="Hello"),
            SessionMessage(role="assistant", content="Hi there!"),
            SessionMessage(role="user", content="How are you?")
        ]

        for msg in messages:
            test_session.add_message(msg)

        assert len(test_session.messages) == 3
        assert test_session.messages == messages

    def test_update_activity(self, test_session):
        """Test updating last activity timestamp."""
        original_time = test_session.last_activity
        time.sleep(0.01)  # Small delay
        test_session.update_activity()

        assert test_session.last_activity > original_time

    def test_get_conversation_history(self, test_session):
        """Test getting conversation history."""
        messages = [
            SessionMessage(role="user", content="Hello"),
            SessionMessage(role="assistant", content="Hi!"),
            SessionMessage(role="user", content="Bye")
        ]

        for msg in messages:
            test_session.add_message(msg)

        history = test_session.get_conversation_history()
        assert len(history) == 3
        assert all(isinstance(msg, SessionMessage) for msg in history)

    def test_get_conversation_history_limit(self, test_session):
        """Test getting limited conversation history."""
        # Add many messages
        for i in range(10):
            msg = SessionMessage(role="user" if i % 2 == 0 else "assistant", content=f"Message {i}")
            test_session.add_message(msg)

        # Get limited history
        history = test_session.get_conversation_history(limit=5)
        assert len(history) == 5
        # Should get the most recent messages
        assert history[-1].content == "Message 9"

    def test_clear_conversation(self, test_session):
        """Test clearing conversation history."""
        # Add some messages
        for i in range(5):
            msg = SessionMessage(role="user", content=f"Message {i}")
            test_session.add_message(msg)

        assert len(test_session.messages) == 5

        test_session.clear_conversation()
        assert len(test_session.messages) == 0

    def test_session_state_management(self, test_session):
        """Test session state and pending tools."""
        # Add pending tool
        tool_request = {
            "tool_name": "read_file",
            "parameters": {"path": "test.py"},
            "timestamp": time.time()
        }
        request_id = "req-123"
        test_session.pending_tools[request_id] = tool_request

        assert request_id in test_session.pending_tools
        assert test_session.pending_tools[request_id] == tool_request

        # Remove pending tool
        del test_session.pending_tools[request_id]
        assert request_id not in test_session.pending_tools


@pytest.mark.asyncio
class TestSessionManager:
    """Test SessionManager functionality."""

    @pytest.fixture
    def session_manager(self):
        """Create session manager instance."""
        return SessionManager()

    @pytest.fixture
    def session_config(self):
        """Create test session configuration."""
        return SessionConfig(working_directory="/test")

    async def test_create_session(self, session_manager, session_config):
        """Test creating a new session."""
        connection_id = "conn-456"
        config_dict = {
            "working_directory": "/test",
            "auto_approve_reads": True,
            "require_approval_for_writes": True,
            "max_concurrent_file_reads": 5
        }

        session_id = await session_manager.create_session(connection_id, config_dict)

        session = session_manager.get_session(session_id)
        assert session is not None
        assert session.session_id == session_id
        assert session.connection_id == connection_id
        assert session_id in session_manager.sessions

    async def test_get_session(self, session_manager, session_config):
        """Test getting an existing session."""
        session_id = "test-session-123"
        connection_id = "conn-456"

        # Create session
        created_session = await session_manager.create_session(session_id, connection_id, session_config)

        # Get session
        retrieved_session = await session_manager.get_session(session_id)

        assert retrieved_session == created_session
        assert retrieved_session.session_id == session_id

    async def test_get_nonexistent_session(self, session_manager):
        """Test getting a non-existent session."""
        session = await session_manager.get_session("nonexistent")
        assert session is None

    async def test_remove_session(self, session_manager, session_config):
        """Test removing a session."""
        session_id = "test-session-123"
        connection_id = "conn-456"

        # Create session
        await session_manager.create_session(session_id, connection_id, session_config)
        assert session_id in session_manager.sessions

        # Remove session
        await session_manager.remove_session(session_id)
        assert session_id not in session_manager.sessions

    async def test_remove_nonexistent_session(self, session_manager):
        """Test removing a non-existent session."""
        # Should not raise error
        await session_manager.remove_session("nonexistent")

    async def test_multiple_sessions(self, session_manager, session_config):
        """Test managing multiple sessions."""
        session_ids = ["session-1", "session-2", "session-3"]
        connection_ids = ["conn-1", "conn-2", "conn-3"]

        # Create multiple sessions
        for session_id, connection_id in zip(session_ids, connection_ids):
            await session_manager.create_session(session_id, connection_id, session_config)

        assert len(session_manager.sessions) == 3
        for session_id in session_ids:
            assert session_id in session_manager.sessions

    async def test_session_timeout_cleanup(self, session_manager, session_config):
        """Test automatic cleanup of expired sessions."""
        session_id = "test-session-123"
        connection_id = "conn-456"

        # Create session
        session = await session_manager.create_session(session_id, connection_id, session_config)

        # Simulate old session by modifying last_activity
        session.last_activity = time.time() - 7200  # 2 hours ago

        # Run cleanup (would need implementation)
        expired_sessions = await session_manager.cleanup_expired_sessions(max_age=3600)  # 1 hour

        assert session_id in expired_sessions
        assert session_id not in session_manager.sessions

    async def test_get_session_by_connection(self, session_manager, session_config):
        """Test getting session by connection ID."""
        session_id = "test-session-123"
        connection_id = "conn-456"

        await session_manager.create_session(session_id, connection_id, session_config)

        session = await session_manager.get_session_by_connection(connection_id)
        assert session is not None
        assert session.connection_id == connection_id
        assert session.session_id == session_id

    async def test_get_session_by_nonexistent_connection(self, session_manager):
        """Test getting session by non-existent connection."""
        session = await session_manager.get_session_by_connection("nonexistent")
        assert session is None

    async def test_list_active_sessions(self, session_manager, session_config):
        """Test listing all active sessions."""
        # Create multiple sessions
        for i in range(5):
            await session_manager.create_session(f"session-{i}", f"conn-{i}", session_config)

        active_sessions = await session_manager.list_active_sessions()
        assert len(active_sessions) == 5
        assert all(isinstance(session, Session) for session in active_sessions)

    async def test_session_statistics(self, session_manager, session_config):
        """Test getting session statistics."""
        # Create sessions with different ages
        for i in range(3):
            session = await session_manager.create_session(f"session-{i}", f"conn-{i}", session_config)
            # Simulate different last activity times
            session.last_activity = time.time() - (i * 1800)  # 0, 30min, 1hr ago

        stats = await session_manager.get_statistics()
        assert stats["total_sessions"] == 3
        assert stats["active_sessions"] >= 0
        assert "average_session_age" in stats

    async def test_concurrent_session_operations(self, session_manager, session_config):
        """Test concurrent session operations."""
        async def create_session_task(i):
            return await session_manager.create_session(f"session-{i}", f"conn-{i}", session_config)

        # Create multiple sessions concurrently
        tasks = [create_session_task(i) for i in range(10)]
        sessions = await asyncio.gather(*tasks)

        assert len(sessions) == 10
        assert len(session_manager.sessions) == 10
        assert all(session.session_id.startswith("session-") for session in sessions)

    async def test_session_persistence_state(self, session_manager, session_config):
        """Test session state persistence during operations."""
        session_id = "test-session"
        connection_id = "conn-123"

        # Create session and add some state
        session = await session_manager.create_session(session_id, connection_id, session_config)
        session.add_message(SessionMessage(role="user", content="Hello"))
        session.pending_tools["req-1"] = {"tool": "read_file"}

        # Retrieve session and verify state persisted
        retrieved_session = await session_manager.get_session(session_id)
        assert len(retrieved_session.messages) == 1
        assert "req-1" in retrieved_session.pending_tools
        assert retrieved_session.messages[0].content == "Hello"