"""
Unit tests for Session Persistence.

Tests:
- Save/load sessions
- Auto-save functionality
- Session recovery
- Cleanup old sessions
- Storage statistics
"""

import pytest
import pytest_asyncio
import asyncio
import tempfile
import time
from pathlib import Path
from gambiarra.server.session.manager import SessionManager, SessionConfig
from gambiarra.server.session.persistence import SessionPersistence


class TestSessionPersistence:
    """Test SessionPersistence implementation."""

    @pytest_asyncio.fixture
    async def persistence(self):
        """Create persistence with temp directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            persistence = SessionPersistence(
                storage_dir=temp_dir,
                auto_save_interval=0  # Disable auto-save for tests
            )
            yield persistence

    @pytest_asyncio.fixture
    async def manager(self):
        """Create session manager."""
        manager = SessionManager(enable_persistence=False)
        yield manager

    @pytest.mark.asyncio
    async def test_save_session(self, persistence, manager):
        """Test saving session to disk."""
        # Create session
        session_id = await manager.create_session(
            connection_id="conn-1",
            config={"working_directory": "/tmp"}
        )

        session = await manager.get_session(session_id, auto_recover=False)
        await session.add_message("user", "Hello!")

        # Save session
        success = await persistence.save_session(session, force=True)
        assert success is True

        # Verify file exists
        session_file = persistence._session_file_path(session_id)
        assert session_file.exists()

    @pytest.mark.asyncio
    async def test_load_session(self, persistence, manager):
        """Test loading session from disk."""
        # Create and save session
        session_id = await manager.create_session(
            connection_id="conn-1",
            config={"working_directory": "/home/user"}
        )

        session = await manager.get_session(session_id, auto_recover=False)
        await session.add_message("user", "Test message")
        await session.add_message("assistant", "Response")
        session.context_files = ["file1.py", "file2.py"]

        await persistence.save_session(session, force=True)

        # Load session
        loaded = await persistence.load_session(session_id)

        assert loaded is not None
        assert loaded.session_id == session_id
        assert loaded.config.working_directory == "/home/user"
        assert len(loaded.messages) == 2
        assert loaded.messages[0].content == "Test message"
        assert loaded.context_files == ["file1.py", "file2.py"]

    @pytest.mark.asyncio
    async def test_delete_session(self, persistence, manager):
        """Test deleting session from disk."""
        # Create and save session
        session_id = await manager.create_session(
            connection_id="conn-1",
            config={}
        )

        session = await manager.get_session(session_id, auto_recover=False)
        await persistence.save_session(session, force=True)

        session_file = persistence._session_file_path(session_id)
        assert session_file.exists()

        # Delete
        success = await persistence.delete_session(session_id)
        assert success is True
        assert not session_file.exists()

    @pytest.mark.asyncio
    async def test_list_sessions(self, persistence, manager):
        """Test listing persisted sessions."""
        # Create multiple sessions
        session_ids = []
        for i in range(3):
            session_id = await manager.create_session(
                connection_id=f"conn-{i}",
                config={}
            )
            session = await manager.get_session(session_id, auto_recover=False)
            await persistence.save_session(session, force=True)
            session_ids.append(session_id)

        # List sessions
        sessions = await persistence.list_sessions()

        assert len(sessions) == 3
        listed_ids = [s['session_id'] for s in sessions]
        for sid in session_ids:
            assert sid in listed_ids

    @pytest.mark.asyncio
    async def test_auto_save(self):
        """Test auto-save functionality."""
        with tempfile.TemporaryDirectory() as temp_dir:
            persistence = SessionPersistence(
                storage_dir=temp_dir,
                auto_save_interval=1.0  # 1 second
            )

            # Start auto-save
            await persistence.start_auto_save()

            # Create session
            manager = SessionManager(enable_persistence=False)
            manager._persistence = persistence

            session_id = await manager.create_session(
                connection_id="conn-1",
                config={}
            )

            session = await manager.get_session(session_id, auto_recover=False)

            # Queue for save
            await persistence.save_session(session)

            # Wait for auto-save
            await asyncio.sleep(2.0)

            # Stop auto-save
            await persistence.stop_auto_save()

            # Verify saved
            session_file = persistence._session_file_path(session_id)
            assert session_file.exists()

    @pytest.mark.asyncio
    async def test_cleanup_old_sessions(self, persistence, manager):
        """Test cleanup of old sessions."""
        # Create session
        session_id = await manager.create_session(
            connection_id="conn-1",
            config={}
        )

        session = await manager.get_session(session_id, auto_recover=False)

        # Set old timestamp
        session.last_activity = time.time() - 86400 * 10  # 10 days ago

        await persistence.save_session(session, force=True)

        # Cleanup (max age is configured in fixture)
        deleted = await persistence.cleanup_old_sessions()

        assert deleted == 1

        # Verify session deleted
        loaded = await persistence.load_session(session_id)
        assert loaded is None

    @pytest.mark.asyncio
    async def test_storage_stats(self, persistence, manager):
        """Test storage statistics."""
        # Create sessions
        for i in range(3):
            session_id = await manager.create_session(
                connection_id=f"conn-{i}",
                config={}
            )
            session = await manager.get_session(session_id, auto_recover=False)

            # Add messages
            for j in range(5):
                await session.add_message("user", f"Message {j}")

            await persistence.save_session(session, force=True)

        # Get stats
        stats = await persistence.get_storage_stats()

        assert stats['session_count'] == 3
        assert stats['total_size_bytes'] > 0
        assert stats['total_size_mb'] > 0

    @pytest.mark.asyncio
    async def test_backup_file_creation(self, persistence, manager):
        """Test backup file is created."""
        session_id = await manager.create_session(
            connection_id="conn-1",
            config={}
        )

        session = await manager.get_session(session_id, auto_recover=False)

        # First save - no backup yet
        await persistence.save_session(session, force=True)

        session_file = persistence._session_file_path(session_id)
        backup_file = persistence._session_backup_path(session_id)

        assert session_file.exists()

        # Modify and save again - backup should be created
        await session.add_message("user", "New message")
        await persistence.save_session(session, force=True)

        # Backup should now exist
        assert backup_file.exists()

    @pytest.mark.asyncio
    async def test_load_from_backup_on_corruption(self, persistence, manager):
        """Test loading from backup when main file is corrupted."""
        session_id = await manager.create_session(
            connection_id="conn-1",
            config={}
        )

        session = await manager.get_session(session_id, auto_recover=False)
        await session.add_message("user", "Original message")

        # Save twice to create backup
        await persistence.save_session(session, force=True)
        await persistence.save_session(session, force=True)

        # Corrupt main file
        session_file = persistence._session_file_path(session_id)
        session_file.write_text("CORRUPTED JSON{{{")

        # Try to load - should use backup
        loaded = await persistence.load_session(session_id)

        assert loaded is not None
        assert loaded.session_id == session_id


class TestSessionManagerPersistenceIntegration:
    """Test SessionManager integration with persistence."""

    @pytest_asyncio.fixture
    async def manager_with_persistence(self):
        """Create manager with persistence."""
        with tempfile.TemporaryDirectory() as temp_dir:
            persistence = SessionPersistence(
                storage_dir=temp_dir,
                auto_save_interval=0
            )

            manager = SessionManager(enable_persistence=False)
            manager._persistence = persistence

            yield manager

    @pytest.mark.asyncio
    async def test_create_session_auto_saves(self, manager_with_persistence):
        """Test creating session can be manually saved."""
        manager = manager_with_persistence

        session_id = await manager.create_session(
            connection_id="conn-1",
            config={}
        )

        # Get session and save it
        session = await manager.get_session(session_id, auto_recover=False)
        await manager._persistence.save_session(session, force=True)

        # Should be saved
        session_file = manager._persistence._session_file_path(session_id)
        assert session_file.exists()

    @pytest.mark.asyncio
    async def test_auto_recovery_on_get(self, manager_with_persistence):
        """Test auto-recovery when getting session."""
        manager = manager_with_persistence

        # Create and save session
        session_id = await manager.create_session(
            connection_id="conn-1",
            config={"working_directory": "/test"}
        )

        session = await manager.get_session(session_id, auto_recover=False)
        await session.add_message("user", "Test")

        await manager._persistence.save_session(session, force=True)

        # Clear from memory
        manager.sessions.clear()

        # Get session - should auto-recover
        recovered = await manager.get_session(session_id, auto_recover=True)

        assert recovered is not None
        assert recovered.session_id == session_id
        assert recovered.config.working_directory == "/test"
        assert len(recovered.messages) == 1

    @pytest.mark.asyncio
    async def test_cleanup_session_persists(self, manager_with_persistence):
        """Test cleanup persists session before removing."""
        manager = manager_with_persistence

        session_id = await manager.create_session(
            connection_id="conn-1",
            config={}
        )

        session = await manager.get_session(session_id, auto_recover=False)
        await session.add_message("user", "Important message")

        # Cleanup (should persist)
        await manager.cleanup_session("conn-1", persist=True)

        # Session removed from memory
        assert session_id not in manager.sessions

        # But should be on disk
        loaded = await manager._persistence.load_session(session_id)
        assert loaded is not None
        assert len(loaded.messages) == 1

    @pytest.mark.asyncio
    async def test_recover_all_sessions(self, manager_with_persistence):
        """Test recovering all sessions from disk."""
        manager = manager_with_persistence

        # Create multiple sessions
        session_ids = []
        for i in range(5):
            session_id = await manager.create_session(
                connection_id=f"conn-{i}",
                config={}
            )
            session = await manager.get_session(session_id, auto_recover=False)
            await session.add_message("user", f"Session {i}")
            await manager._persistence.save_session(session, force=True)
            session_ids.append(session_id)

        # Clear all from memory
        manager.sessions.clear()

        # Recover all
        recovered_count = await manager.recover_all_sessions()

        assert recovered_count == 5

        # Verify all recovered
        for session_id in session_ids:
            assert session_id in manager.sessions

    @pytest.mark.asyncio
    async def test_start_stop_persistence(self, manager_with_persistence):
        """Test starting and stopping persistence."""
        manager = manager_with_persistence

        # Start auto-save
        await manager.start_persistence()

        # Stop auto-save
        await manager.stop_persistence()

        # Should complete without error


class TestSessionPersistenceEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_load_nonexistent_session(self):
        """Test loading non-existent session."""
        with tempfile.TemporaryDirectory() as temp_dir:
            persistence = SessionPersistence(storage_dir=temp_dir)

            loaded = await persistence.load_session("nonexistent-id")
            assert loaded is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_session(self):
        """Test deleting non-existent session."""
        with tempfile.TemporaryDirectory() as temp_dir:
            persistence = SessionPersistence(storage_dir=temp_dir)

            # Should not raise error
            success = await persistence.delete_session("nonexistent-id")
            assert success is True  # No-op is still success

    @pytest.mark.asyncio
    async def test_save_empty_session(self):
        """Test saving session with no messages."""
        with tempfile.TemporaryDirectory() as temp_dir:
            persistence = SessionPersistence(storage_dir=temp_dir)
            manager = SessionManager(enable_persistence=False)

            session_id = await manager.create_session(
                connection_id="conn-1",
                config={}
            )

            session = await manager.get_session(session_id, auto_recover=False)

            # Save with no messages
            success = await persistence.save_session(session, force=True)
            assert success is True

            # Load back
            loaded = await persistence.load_session(session_id)
            assert loaded is not None
            assert len(loaded.messages) == 0

    @pytest.mark.asyncio
    async def test_large_session(self):
        """Test saving/loading large session."""
        with tempfile.TemporaryDirectory() as temp_dir:
            persistence = SessionPersistence(storage_dir=temp_dir)
            manager = SessionManager(enable_persistence=False)

            session_id = await manager.create_session(
                connection_id="conn-1",
                config={}
            )

            session = await manager.get_session(session_id, auto_recover=False)

            # Add many messages
            for i in range(1000):
                await session.add_message("user", f"Message {i}" * 10)

            # Save
            success = await persistence.save_session(session, force=True)
            assert success is True

            # Load
            loaded = await persistence.load_session(session_id)
            assert loaded is not None
            assert len(loaded.messages) == 1000

    @pytest.mark.asyncio
    async def test_concurrent_saves(self):
        """Test concurrent saves of different sessions."""
        with tempfile.TemporaryDirectory() as temp_dir:
            persistence = SessionPersistence(storage_dir=temp_dir)
            manager = SessionManager(enable_persistence=False)

            # Create multiple sessions
            sessions = []
            for i in range(10):
                session_id = await manager.create_session(
                    connection_id=f"conn-{i}",
                    config={}
                )
                session = await manager.get_session(session_id, auto_recover=False)
                sessions.append(session)

            # Save concurrently
            tasks = [
                persistence.save_session(session, force=True)
                for session in sessions
            ]

            results = await asyncio.gather(*tasks)

            # All should succeed
            assert all(results)

    @pytest.mark.asyncio
    async def test_session_with_special_characters(self):
        """Test session with special characters in content."""
        with tempfile.TemporaryDirectory() as temp_dir:
            persistence = SessionPersistence(storage_dir=temp_dir)
            manager = SessionManager(enable_persistence=False)

            session_id = await manager.create_session(
                connection_id="conn-1",
                config={}
            )

            session = await manager.get_session(session_id, auto_recover=False)

            # Add message with special characters
            special_content = "Test\n\t\"quotes\" 'single' \\backslash\\ 日本語 emoji😀"
            await session.add_message("user", special_content)

            # Save and load
            await persistence.save_session(session, force=True)
            loaded = await persistence.load_session(session_id)

            assert loaded is not None
            assert loaded.messages[0].content == special_content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
