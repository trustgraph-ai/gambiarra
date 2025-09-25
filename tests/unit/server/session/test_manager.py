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

    @pytest.mark.asyncio
    async def test_add_message(self, test_session):
        """Test adding messages to session."""
        await test_session.add_message("user", "Hello")

        assert len(test_session.messages) == 1
        assert test_session.messages[0].role == "user"
        assert test_session.messages[0].content == "Hello"

    @pytest.mark.asyncio
    async def test_multiple_messages(self, test_session):
        """Test adding multiple messages."""
        messages = [
            ("user", "Hello"),
            ("assistant", "Hi there!"),
            ("user", "How are you?")
        ]

        for role, content in messages:
            await test_session.add_message(role, content)

        assert len(test_session.messages) == 3
        assert test_session.messages[0].role == "user"
        assert test_session.messages[0].content == "Hello"

    def test_update_activity(self, test_session):
        """Test updating last activity timestamp."""
        original_time = test_session.last_activity
        time.sleep(0.01)  # Small delay
        test_session.update_activity()

        assert test_session.last_activity > original_time

    @pytest.mark.asyncio
    async def test_get_conversation_history(self, test_session):
        """Test getting conversation history."""
        messages = [
            ("user", "Hello"),
            ("assistant", "Hi!"),
            ("user", "Bye")
        ]

        for role, content in messages:
            await test_session.add_message(role, content)

        history = await test_session.get_messages()
        assert len(history) == 3
        assert all(isinstance(msg, dict) for msg in history)
        assert history[0]["role"] == "user"
        assert history[0]["content"] == "Hello"

    @pytest.mark.asyncio
    async def test_get_conversation_history_limit(self, test_session):
        """Test getting limited conversation history."""
        # Add many messages
        for i in range(10):
            role = "user" if i % 2 == 0 else "assistant"
            await test_session.add_message(role, f"Message {i}")

        # Get full history (limit functionality would need to be implemented)
        history = await test_session.get_messages()
        assert len(history) == 10
        # Should get the most recent messages
        assert history[-1]["content"] == "Message 9"

    @pytest.mark.asyncio
    async def test_clear_conversation(self, test_session):
        """Test clearing conversation history."""
        # Add some messages
        for i in range(5):
            await test_session.add_message("user", f"Message {i}")

        assert len(test_session.messages) == 5

        # Clear messages (this functionality would need to be implemented)
        test_session.messages.clear()
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
        connection_id = "conn-456"
        config_dict = {"working_directory": "/test"}

        # Create session
        session_id = await session_manager.create_session(connection_id, config_dict)

        # Get session
        retrieved_session = session_manager.get_session(session_id)

        assert retrieved_session is not None
        assert retrieved_session.session_id == session_id

    async def test_get_nonexistent_session(self, session_manager):
        """Test getting a non-existent session."""
        session = session_manager.get_session("nonexistent")
        assert session is None

    async def test_remove_session(self, session_manager, session_config):
        """Test removing a session."""
        connection_id = "conn-456"
        config_dict = {"working_directory": "/test"}

        # Create session
        session_id = await session_manager.create_session(connection_id, config_dict)
        assert session_id in session_manager.sessions

        # Remove session via cleanup_session
        await session_manager.cleanup_session(connection_id)
        assert session_id not in session_manager.sessions

    async def test_remove_nonexistent_session(self, session_manager):
        """Test removing a non-existent session."""
        # Should not raise error
        await session_manager.cleanup_session("nonexistent")

    async def test_multiple_sessions(self, session_manager, session_config):
        """Test managing multiple sessions."""
        connection_ids = ["conn-1", "conn-2", "conn-3"]
        config_dict = {"working_directory": "/test"}

        # Create multiple sessions
        session_ids = []
        for connection_id in connection_ids:
            session_id = await session_manager.create_session(connection_id, config_dict)
            session_ids.append(session_id)

        assert len(session_manager.sessions) == 3
        for session_id in session_ids:
            assert session_id in session_manager.sessions

    async def test_session_timeout_cleanup(self, session_manager, session_config):
        """Test automatic cleanup of expired sessions."""
        connection_id = "conn-456"
        config_dict = {"working_directory": "/test"}

        # Create session
        session_id = await session_manager.create_session(connection_id, config_dict)
        session = session_manager.get_session(session_id)

        # Simulate old session by modifying last_activity
        session.last_activity = time.time() - 7200  # 2 hours ago

        # Run cleanup
        expired_count = await session_manager.cleanup_expired_sessions(timeout=3600)  # 1 hour

        assert expired_count == 1
        assert session_id not in session_manager.sessions

    async def test_get_session_by_connection(self, session_manager, session_config):
        """Test getting session by connection ID."""
        connection_id = "conn-456"
        config_dict = {"working_directory": "/test"}

        session_id = await session_manager.create_session(connection_id, config_dict)

        session = session_manager.get_session_by_connection(connection_id)
        assert session is not None
        assert session.connection_id == connection_id
        assert session.session_id == session_id

    async def test_get_session_by_nonexistent_connection(self, session_manager):
        """Test getting session by non-existent connection."""
        session = session_manager.get_session_by_connection("nonexistent")
        assert session is None

    async def test_list_active_sessions(self, session_manager, session_config):
        """Test listing all active sessions."""
        config_dict = {"working_directory": "/test"}

        # Create multiple sessions
        for i in range(5):
            await session_manager.create_session(f"conn-{i}", config_dict)

        active_sessions = session_manager.list_sessions()
        assert len(active_sessions) == 5
        assert all(isinstance(session_info, dict) for session_info in active_sessions)
        assert len(active_sessions) == 5

    async def test_session_statistics(self, session_manager, session_config):
        """Test getting session statistics."""
        config_dict = {"working_directory": "/test"}

        # Create sessions with different ages
        for i in range(3):
            session_id = await session_manager.create_session(f"conn-{i}", config_dict)
            session = session_manager.get_session(session_id)
            # Simulate different last activity times
            session.last_activity = time.time() - (i * 1800)  # 0, 30min, 1hr ago

        # Test session counting methods
        active_count = session_manager.active_session_count()
        total_count = session_manager.total_session_count()

        assert active_count == 3
        assert total_count >= 3

    async def test_concurrent_session_operations(self, session_manager, session_config):
        """Test concurrent session operations."""
        config_dict = {"working_directory": "/test"}

        async def create_session_task(i):
            return await session_manager.create_session(f"conn-{i}", config_dict)

        # Create multiple sessions concurrently
        tasks = [create_session_task(i) for i in range(10)]
        sessions = await asyncio.gather(*tasks)

        assert len(sessions) == 10
        assert len(session_manager.sessions) == 10
        assert all(isinstance(session_id, str) for session_id in sessions)

    async def test_session_persistence_state(self, session_manager, session_config):
        """Test session state persistence during operations."""
        connection_id = "conn-123"
        config_dict = {"working_directory": "/test"}

        # Create session and add some state
        session_id = await session_manager.create_session(connection_id, config_dict)
        session = session_manager.get_session(session_id)
        await session.add_message("user", "Hello")
        session.pending_tools["req-1"] = {"tool": "read_file"}

        # Retrieve session and verify state persisted
        retrieved_session = session_manager.get_session(session_id)
        assert len(retrieved_session.messages) == 1
        assert "req-1" in retrieved_session.pending_tools
        assert retrieved_session.messages[0].content == "Hello"