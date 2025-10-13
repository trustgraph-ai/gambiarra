"""
Session Persistence for Gambiarra.

Provides:
- JSON serialization of sessions to disk
- Automatic save on session changes
- Session recovery after restart
- Automatic cleanup of old sessions
- Backup and restore capabilities
"""

import json
import asyncio
import logging
import time
from typing import Optional, Dict, Any, List
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import asdict

from .manager import Session, SessionMessage, SessionConfig

logger = logging.getLogger(__name__)


class SessionPersistence:
    """
    Persist sessions to disk for recovery after restart.

    Features:
    - JSON serialization for portability
    - Automatic save on changes
    - Session recovery on restart
    - Automatic cleanup of old sessions
    - Corruption-resistant saves (atomic writes)
    """

    def __init__(
        self,
        storage_dir: str = "~/.cache/gambiarra/sessions",
        auto_save_interval: float = 30.0,
        max_session_age_days: int = 7
    ):
        """
        Initialize session persistence.

        Args:
            storage_dir: Directory to store session files
            auto_save_interval: Seconds between auto-saves (0 to disable)
            max_session_age_days: Days to keep old sessions before cleanup
        """
        self.storage_dir = Path(storage_dir).expanduser()
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        self.auto_save_interval = auto_save_interval
        self.max_session_age_days = max_session_age_days

        self._save_queue: asyncio.Queue = asyncio.Queue()
        self._save_task: Optional[asyncio.Task] = None
        self._running = False

        logger.info(f"📁 Session persistence initialized: {self.storage_dir}")

    def _session_file_path(self, session_id: str) -> Path:
        """Get file path for a session."""
        return self.storage_dir / f"{session_id}.json"

    def _session_backup_path(self, session_id: str) -> Path:
        """Get backup file path for a session."""
        return self.storage_dir / f"{session_id}.json.backup"

    def _serialize_session(self, session: Session) -> Dict[str, Any]:
        """
        Serialize session to JSON-compatible dict.

        Args:
            session: Session to serialize

        Returns:
            Dict ready for JSON serialization
        """
        return {
            'session_id': session.session_id,
            'connection_id': session.connection_id,
            'created_at': session.created_at,
            'last_activity': session.last_activity,
            'config': {
                'working_directory': session.config.working_directory,
                'auto_approve_reads': session.config.auto_approve_reads,
                'operating_mode': session.config.operating_mode,
                'require_approval_for_writes': session.config.require_approval_for_writes,
                'max_concurrent_file_reads': session.config.max_concurrent_file_reads
            },
            'messages': [
                {
                    'role': msg.role,
                    'content': msg.content,
                    'timestamp': msg.timestamp,
                    'images': msg.images,
                    'metadata': msg.metadata
                }
                for msg in session.messages
            ],
            'context_files': session.context_files,
            'working_memory': session.working_memory,
            'pending_tools': session.pending_tools
        }

    def _deserialize_session(self, data: Dict[str, Any]) -> Session:
        """
        Deserialize session from JSON dict.

        Args:
            data: JSON dict

        Returns:
            Reconstructed Session
        """
        # Create config
        config_data = data['config']
        config = SessionConfig(
            working_directory=config_data['working_directory'],
            auto_approve_reads=config_data['auto_approve_reads'],
            operating_mode=config_data.get('operating_mode', 'code'),
            require_approval_for_writes=config_data.get('require_approval_for_writes', True),
            max_concurrent_file_reads=config_data.get('max_concurrent_file_reads', 5)
        )

        # Create session
        session = Session(
            session_id=data['session_id'],
            connection_id=data['connection_id'],
            config=config
        )

        # Restore timestamps
        session.created_at = data['created_at']
        session.last_activity = data['last_activity']

        # Restore messages
        session.messages = [
            SessionMessage(
                role=msg['role'],
                content=msg['content'],
                timestamp=msg['timestamp'],
                images=msg.get('images', []),
                metadata=msg.get('metadata', {})
            )
            for msg in data['messages']
        ]

        # Restore context and memory
        session.context_files = data.get('context_files', [])
        session.working_memory = data.get('working_memory', {})
        session.pending_tools = data.get('pending_tools', {})

        return session

    async def save_session(
        self,
        session: Session,
        force: bool = False
    ) -> bool:
        """
        Save session to disk.

        Args:
            session: Session to save
            force: Force immediate save (bypass queue)

        Returns:
            True if saved successfully
        """
        if force:
            return await self._save_session_now(session)
        else:
            # Queue for batch save
            await self._save_queue.put(session)
            return True

    async def _save_session_now(self, session: Session) -> bool:
        """
        Immediately save session to disk (atomic write).

        Args:
            session: Session to save

        Returns:
            True if saved successfully
        """
        try:
            session_file = self._session_file_path(session.session_id)
            backup_file = self._session_backup_path(session.session_id)
            temp_file = session_file.with_suffix('.tmp')

            # Serialize session
            data = self._serialize_session(session)

            # Write to temporary file first (atomic)
            with open(temp_file, 'w') as f:
                json.dump(data, f, indent=2)

            # Backup existing file if present
            if session_file.exists():
                if backup_file.exists():
                    backup_file.unlink()
                session_file.rename(backup_file)

            # Move temp to final location (atomic on POSIX)
            temp_file.rename(session_file)

            logger.debug(f"💾 Saved session {session.session_id}")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to save session {session.session_id}: {e}")
            return False

    async def load_session(
        self,
        session_id: str
    ) -> Optional[Session]:
        """
        Load session from disk.

        Args:
            session_id: ID of session to load

        Returns:
            Loaded Session or None if not found/failed
        """
        try:
            session_file = self._session_file_path(session_id)

            if not session_file.exists():
                logger.debug(f"Session file not found: {session_id}")
                return None

            # Load JSON
            with open(session_file, 'r') as f:
                data = json.load(f)

            # Deserialize
            session = self._deserialize_session(data)

            logger.info(f"📂 Loaded session {session_id} ({len(session.messages)} messages)")
            return session

        except json.JSONDecodeError as e:
            logger.error(f"❌ Corrupted session file {session_id}: {e}")

            # Try backup
            return await self._load_from_backup(session_id)

        except Exception as e:
            logger.error(f"❌ Failed to load session {session_id}: {e}")
            return None

    async def _load_from_backup(self, session_id: str) -> Optional[Session]:
        """
        Load session from backup file.

        Args:
            session_id: ID of session to load

        Returns:
            Loaded Session or None
        """
        try:
            backup_file = self._session_backup_path(session_id)

            if not backup_file.exists():
                logger.warning(f"No backup found for session {session_id}")
                return None

            with open(backup_file, 'r') as f:
                data = json.load(f)

            session = self._deserialize_session(data)

            logger.info(f"📂 Loaded session {session_id} from backup")
            return session

        except Exception as e:
            logger.error(f"❌ Failed to load backup for {session_id}: {e}")
            return None

    async def delete_session(self, session_id: str) -> bool:
        """
        Delete session from disk.

        Args:
            session_id: ID of session to delete

        Returns:
            True if deleted successfully
        """
        try:
            session_file = self._session_file_path(session_id)
            backup_file = self._session_backup_path(session_id)

            # Delete both files
            if session_file.exists():
                session_file.unlink()

            if backup_file.exists():
                backup_file.unlink()

            logger.debug(f"🗑️ Deleted session {session_id}")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to delete session {session_id}: {e}")
            return False

    async def list_sessions(self) -> List[Dict[str, Any]]:
        """
        List all persisted sessions.

        Returns:
            List of session metadata dicts
        """
        sessions = []

        for session_file in self.storage_dir.glob("*.json"):
            if session_file.name.endswith('.backup') or session_file.name.endswith('.tmp'):
                continue

            try:
                with open(session_file, 'r') as f:
                    data = json.load(f)

                sessions.append({
                    'session_id': data['session_id'],
                    'created_at': data['created_at'],
                    'last_activity': data['last_activity'],
                    'message_count': len(data['messages']),
                    'file_size': session_file.stat().st_size
                })

            except Exception as e:
                logger.error(f"❌ Failed to read session file {session_file.name}: {e}")

        return sessions

    async def cleanup_old_sessions(self) -> int:
        """
        Delete sessions older than max_session_age_days.

        Returns:
            Number of sessions deleted
        """
        cutoff_time = time.time() - (self.max_session_age_days * 86400)
        deleted_count = 0

        for session_file in self.storage_dir.glob("*.json"):
            if session_file.name.endswith('.backup') or session_file.name.endswith('.tmp'):
                continue

            try:
                with open(session_file, 'r') as f:
                    data = json.load(f)

                if data['last_activity'] < cutoff_time:
                    session_id = data['session_id']
                    await self.delete_session(session_id)
                    deleted_count += 1
                    logger.info(f"🧹 Cleaned up old session {session_id}")

            except Exception as e:
                logger.error(f"❌ Failed to check session {session_file.name}: {e}")

        return deleted_count

    async def start_auto_save(self) -> None:
        """Start auto-save background task."""
        if self._running:
            logger.warning("Auto-save already running")
            return

        self._running = True
        self._save_task = asyncio.create_task(self._auto_save_loop())

        logger.info(f"🔄 Started auto-save (interval: {self.auto_save_interval}s)")

    async def stop_auto_save(self) -> None:
        """Stop auto-save background task."""
        self._running = False

        if self._save_task:
            self._save_task.cancel()
            try:
                await self._save_task
            except asyncio.CancelledError:
                pass

        # Flush remaining saves
        await self._flush_save_queue()

        logger.info("🛑 Stopped auto-save")

    async def _auto_save_loop(self) -> None:
        """Background loop for auto-saving sessions."""
        while self._running:
            try:
                # Wait for interval or until queue has items
                try:
                    await asyncio.wait_for(
                        asyncio.sleep(self.auto_save_interval),
                        timeout=self.auto_save_interval
                    )
                except asyncio.TimeoutError:
                    pass

                # Flush save queue
                await self._flush_save_queue()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Error in auto-save loop: {e}")

    async def _flush_save_queue(self) -> None:
        """Flush all pending saves from queue."""
        saved_count = 0
        seen_sessions = set()

        while not self._save_queue.empty():
            try:
                session = self._save_queue.get_nowait()

                # Only save each session once (keep latest)
                if session.session_id in seen_sessions:
                    continue

                seen_sessions.add(session.session_id)

                await self._save_session_now(session)
                saved_count += 1

            except asyncio.QueueEmpty:
                break
            except Exception as e:
                logger.error(f"❌ Error flushing save queue: {e}")

        if saved_count > 0:
            logger.debug(f"💾 Flushed {saved_count} sessions to disk")

    async def get_storage_stats(self) -> Dict[str, Any]:
        """
        Get storage statistics.

        Returns:
            Dict with storage stats
        """
        total_size = 0
        session_count = 0
        oldest_session = None
        newest_session = None

        for session_file in self.storage_dir.glob("*.json"):
            if session_file.name.endswith('.backup') or session_file.name.endswith('.tmp'):
                continue

            try:
                total_size += session_file.stat().st_size
                session_count += 1

                with open(session_file, 'r') as f:
                    data = json.load(f)

                last_activity = data['last_activity']

                if oldest_session is None or last_activity < oldest_session:
                    oldest_session = last_activity

                if newest_session is None or last_activity > newest_session:
                    newest_session = last_activity

            except Exception as e:
                logger.error(f"❌ Failed to stat session {session_file.name}: {e}")

        return {
            'storage_dir': str(self.storage_dir),
            'total_size_bytes': total_size,
            'total_size_mb': total_size / (1024 * 1024),
            'session_count': session_count,
            'oldest_session_timestamp': oldest_session,
            'newest_session_timestamp': newest_session,
            'oldest_session_age_hours': (time.time() - oldest_session) / 3600 if oldest_session else None,
            'auto_save_interval': self.auto_save_interval,
            'max_session_age_days': self.max_session_age_days
        }


# Global singleton instance
_persistence_instance: Optional[SessionPersistence] = None


def get_session_persistence() -> SessionPersistence:
    """Get the global SessionPersistence instance."""
    global _persistence_instance
    if _persistence_instance is None:
        _persistence_instance = SessionPersistence()
    return _persistence_instance


def set_session_persistence(persistence: SessionPersistence) -> None:
    """Set the global SessionPersistence instance."""
    global _persistence_instance
    _persistence_instance = persistence
