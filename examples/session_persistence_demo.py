"""
Demo script for Session Persistence.

Demonstrates:
- Saving sessions to disk
- Loading sessions after restart
- Auto-save functionality
- Session recovery
- Cleanup of old sessions
"""

import sys
import asyncio
from pathlib import Path
import tempfile
import time

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from gambiarra.server.session.manager import SessionManager, SessionConfig
from gambiarra.server.session.persistence import SessionPersistence


async def demo_basic_save_load():
    """Demonstrate basic save and load."""
    print("=" * 80)
    print("DEMO 1: Basic Save & Load")
    print("=" * 80)
    print()

    with tempfile.TemporaryDirectory() as temp_dir:
        # Create persistence system
        persistence = SessionPersistence(
            storage_dir=temp_dir,
            auto_save_interval=0  # Disable auto-save for manual demo
        )

        # Create session manager
        manager = SessionManager(enable_persistence=False)
        manager._persistence = persistence

        print("Creating session...")
        session_id = await manager.create_session(
            connection_id="conn-1",
            config={"working_directory": "/tmp/test"}
        )
        print(f"  Session ID: {session_id}")
        print()

        # Add some messages
        session = await manager.get_session(session_id, auto_recover=False)
        await session.add_message("user", "Hello, how are you?")
        await session.add_message("assistant", "I'm doing well, thank you!")
        await session.add_message("user", "Can you help me with Python?")
        session.context_files = ["main.py", "utils.py"]

        print(f"Added {len(session.messages)} messages")
        print(f"Context files: {session.context_files}")
        print()

        # Save session
        print("Saving session to disk...")
        await persistence.save_session(session, force=True)
        print("  ✓ Saved")
        print()

        # Verify file exists
        session_file = Path(temp_dir) / f"{session_id}.json"
        print(f"Session file: {session_file}")
        print(f"  Exists: {session_file.exists()}")
        print(f"  Size: {session_file.stat().st_size} bytes")
        print()

        # Clear session from memory
        manager.sessions.clear()
        print("Cleared session from memory")
        print()

        # Load session back
        print("Loading session from disk...")
        loaded_session = await persistence.load_session(session_id)

        if loaded_session:
            print("  ✓ Loaded successfully")
            print(f"  Session ID: {loaded_session.session_id}")
            print(f"  Messages: {len(loaded_session.messages)}")
            print(f"  Context files: {loaded_session.context_files}")
            print()

            # Verify messages
            print("Messages:")
            for msg in loaded_session.messages:
                print(f"  {msg.role}: {msg.content[:50]}...")
        else:
            print("  ✗ Failed to load")

        print()


async def demo_auto_recovery():
    """Demonstrate automatic session recovery."""
    print("=" * 80)
    print("DEMO 2: Automatic Session Recovery")
    print("=" * 80)
    print()

    with tempfile.TemporaryDirectory() as temp_dir:
        persistence = SessionPersistence(storage_dir=temp_dir, auto_save_interval=0)

        # Create first manager and session
        print("Creating session with Manager 1...")
        manager1 = SessionManager(enable_persistence=False)
        manager1._persistence = persistence

        session_id = await manager1.create_session(
            connection_id="conn-1",
            config={"working_directory": "/home/user/project"}
        )

        session = await manager1.get_session(session_id, auto_recover=False)
        await session.add_message("user", "Let's start a project")
        await session.add_message("assistant", "Sure! What are we building?")
        session.context_files = ["README.md", "setup.py"]

        print(f"  Session ID: {session_id}")
        print(f"  Messages: {len(session.messages)}")
        print()

        # Save and "crash"
        print("Saving session and simulating server restart...")
        await persistence.save_session(session, force=True)
        manager1.sessions.clear()  # Simulate crash/restart
        print("  ✓ Session cleared from memory (simulated restart)")
        print()

        # Create new manager (simulating restart)
        print("Creating Manager 2 (after restart)...")
        manager2 = SessionManager(enable_persistence=False)
        manager2._persistence = persistence

        # Try to get session - should auto-recover
        print(f"Attempting to get session {session_id}...")
        recovered_session = await manager2.get_session(session_id, auto_recover=True)

        if recovered_session:
            print("  ✓ Session automatically recovered!")
            print(f"  Working directory: {recovered_session.config.working_directory}")
            print(f"  Messages: {len(recovered_session.messages)}")
            print(f"  Context files: {recovered_session.context_files}")
            print()

            print("Conversation history:")
            for msg in recovered_session.messages:
                print(f"  {msg.role}: {msg.content}")
        else:
            print("  ✗ Recovery failed")

        print()


async def demo_auto_save():
    """Demonstrate auto-save functionality."""
    print("=" * 80)
    print("DEMO 3: Auto-Save")
    print("=" * 80)
    print()

    with tempfile.TemporaryDirectory() as temp_dir:
        persistence = SessionPersistence(
            storage_dir=temp_dir,
            auto_save_interval=2.0  # Save every 2 seconds
        )

        # Start auto-save
        await persistence.start_auto_save()
        print("Started auto-save (interval: 2 seconds)")
        print()

        manager = SessionManager(enable_persistence=False)
        manager._persistence = persistence

        # Create session
        session_id = await manager.create_session(
            connection_id="conn-1",
            config={"working_directory": "/tmp"}
        )

        session = await manager.get_session(session_id, auto_recover=False)

        print("Adding messages over time...")
        for i in range(5):
            await session.add_message("user", f"Message {i+1}")
            print(f"  Added message {i+1}")
            await asyncio.sleep(0.5)

        print()
        print("Waiting for auto-save (3 seconds)...")
        await asyncio.sleep(3)

        # Check if saved
        session_file = Path(temp_dir) / f"{session_id}.json"
        if session_file.exists():
            print("  ✓ Session auto-saved to disk")
            print(f"  File size: {session_file.stat().st_size} bytes")
        else:
            print("  ✗ Auto-save did not occur")

        # Stop auto-save
        await persistence.stop_auto_save()
        print()
        print("Stopped auto-save")
        print()


async def demo_bulk_recovery():
    """Demonstrate recovering all sessions."""
    print("=" * 80)
    print("DEMO 4: Bulk Session Recovery")
    print("=" * 80)
    print()

    with tempfile.TemporaryDirectory() as temp_dir:
        persistence = SessionPersistence(storage_dir=temp_dir, auto_save_interval=0)

        # Create multiple sessions
        print("Creating 5 sessions...")
        manager1 = SessionManager(enable_persistence=False)
        manager1._persistence = persistence

        session_ids = []
        for i in range(5):
            session_id = await manager1.create_session(
                connection_id=f"conn-{i}",
                config={"working_directory": f"/project-{i}"}
            )
            session = await manager1.get_session(session_id, auto_recover=False)
            await session.add_message("user", f"Session {i+1} message")
            session.context_files = [f"file{i}.py"]
            session_ids.append(session_id)

            print(f"  {i+1}. {session_id[:8]}...")

        print()

        # Save all
        print("Saving all sessions...")
        for session_id in session_ids:
            session = manager1.sessions[session_id]
            await persistence.save_session(session, force=True)
        print("  ✓ All saved")
        print()

        # List persisted sessions
        persisted = await persistence.list_sessions()
        print(f"Persisted sessions: {len(persisted)}")
        print()

        # Clear memory
        manager1.sessions.clear()
        print("Cleared all sessions from memory (simulated restart)")
        print()

        # Create new manager and recover all
        print("Creating new manager and recovering all sessions...")
        manager2 = SessionManager(enable_persistence=False)
        manager2._persistence = persistence

        recovered_count = await manager2.recover_all_sessions()
        print(f"  ✓ Recovered {recovered_count} sessions")
        print()

        # Verify
        print("Active sessions after recovery:")
        for session_id, session in manager2.sessions.items():
            print(f"  - {session_id[:8]}...: {len(session.messages)} messages, "
                  f"files: {session.context_files}")

        print()


async def demo_cleanup():
    """Demonstrate cleanup of old sessions."""
    print("=" * 80)
    print("DEMO 5: Cleanup Old Sessions")
    print("=" * 80)
    print()

    with tempfile.TemporaryDirectory() as temp_dir:
        persistence = SessionPersistence(
            storage_dir=temp_dir,
            auto_save_interval=0,
            max_session_age_days=0.00001  # Very short for demo (~1 second)
        )

        manager = SessionManager(enable_persistence=False)
        manager._persistence = persistence

        # Create old session
        print("Creating session...")
        session_id = await manager.create_session(
            connection_id="conn-1",
            config={"working_directory": "/tmp"}
        )

        session = await manager.get_session(session_id, auto_recover=False)
        await session.add_message("user", "Old session")

        # Manually set old timestamp
        session.last_activity = time.time() - 3600  # 1 hour ago

        await persistence.save_session(session, force=True)
        print(f"  Session ID: {session_id[:8]}...")
        print(f"  Last activity: {session.last_activity} (1 hour ago)")
        print()

        # List before cleanup
        before = await persistence.list_sessions()
        print(f"Sessions before cleanup: {len(before)}")
        print()

        # Cleanup
        print("Running cleanup (max age: ~1 second)...")
        deleted_count = await persistence.cleanup_old_sessions()
        print(f"  ✓ Deleted {deleted_count} old sessions")
        print()

        # List after cleanup
        after = await persistence.list_sessions()
        print(f"Sessions after cleanup: {len(after)}")
        print()


async def demo_storage_stats():
    """Demonstrate storage statistics."""
    print("=" * 80)
    print("DEMO 6: Storage Statistics")
    print("=" * 80)
    print()

    with tempfile.TemporaryDirectory() as temp_dir:
        persistence = SessionPersistence(storage_dir=temp_dir, auto_save_interval=0)

        manager = SessionManager(enable_persistence=False)
        manager._persistence = persistence

        # Create several sessions
        print("Creating sessions with varying sizes...")
        for i in range(3):
            session_id = await manager.create_session(
                connection_id=f"conn-{i}",
                config={"working_directory": "/tmp"}
            )

            session = await manager.get_session(session_id, auto_recover=False)

            # Add varying numbers of messages
            for j in range((i + 1) * 5):
                await session.add_message("user", f"Message {j}" * 10)

            await persistence.save_session(session, force=True)
            print(f"  Session {i+1}: {len(session.messages)} messages")

        print()

        # Get stats
        stats = await persistence.get_storage_stats()

        print("Storage Statistics:")
        print(f"  Directory: {stats['storage_dir']}")
        print(f"  Total size: {stats['total_size_bytes']} bytes ({stats['total_size_mb']:.2f} MB)")
        print(f"  Session count: {stats['session_count']}")
        print(f"  Auto-save interval: {stats['auto_save_interval']}s")
        print(f"  Max session age: {stats['max_session_age_days']} days")

        if stats['oldest_session_age_hours']:
            print(f"  Oldest session age: {stats['oldest_session_age_hours']:.2f} hours")

        print()


async def main():
    """Run all demos."""
    print()
    print("╔" + "=" * 78 + "╗")
    print("║" + " " * 20 + "SESSION PERSISTENCE DEMO" + " " * 35 + "║")
    print("╚" + "=" * 78 + "╝")
    print()

    await demo_basic_save_load()
    await demo_auto_recovery()
    await demo_auto_save()
    await demo_bulk_recovery()
    await demo_cleanup()
    await demo_storage_stats()

    print("=" * 80)
    print("KEY BENEFITS")
    print("=" * 80)
    print()
    print("✓ Sessions survive server restarts")
    print("✓ Automatic recovery on reconnection")
    print("✓ Auto-save prevents data loss")
    print("✓ Atomic writes prevent corruption")
    print("✓ Backup files for safety")
    print("✓ Automatic cleanup of old sessions")
    print("✓ JSON format for portability")
    print("✓ Storage statistics for monitoring")
    print()
    print("=" * 80)
    print("DEMO COMPLETE")
    print("=" * 80)
    print()


if __name__ == "__main__":
    asyncio.run(main())
