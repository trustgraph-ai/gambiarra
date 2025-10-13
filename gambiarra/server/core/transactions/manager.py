"""
Transaction Manager for Atomic Multi-File Operations.

Provides ACID-like transactions for file operations, enabling:
- Atomic multi-file changes (all or nothing)
- Rollback on failure
- Transaction logging
- Recovery from crashes

This prevents the codebase from being left in an inconsistent state
when multi-file refactoring operations fail partway through.
"""

import json
import logging
import shutil
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
import uuid

logger = logging.getLogger(__name__)


class TransactionState(Enum):
    """State of a transaction."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMMITTED = "committed"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


class OperationType(Enum):
    """Type of file operation."""
    CREATE = "create"
    MODIFY = "modify"
    DELETE = "delete"
    MOVE = "move"


@dataclass
class FileOperation:
    """Represents a file operation within a transaction."""

    operation_type: OperationType
    file_path: str

    # For CREATE and MODIFY
    new_content: Optional[str] = None

    # For MODIFY and DELETE (backup of original)
    original_content: Optional[str] = None
    original_existed: bool = False

    # For MOVE
    new_path: Optional[str] = None

    # Execution state
    executed: bool = False
    execution_time: Optional[float] = None
    error: Optional[str] = None


@dataclass
class Transaction:
    """
    Represents a transaction containing multiple file operations.

    Provides atomicity: either all operations succeed or all are rolled back.
    """

    transaction_id: str
    description: str
    operations: List[FileOperation] = field(default_factory=list)

    state: TransactionState = TransactionState.PENDING
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None

    # Transaction metadata
    session_id: Optional[str] = None
    user_metadata: Dict[str, Any] = field(default_factory=dict)

    # Backup directory for rollback
    backup_dir: Optional[Path] = None


class TransactionManager:
    """
    Manages file operation transactions with rollback support.

    Provides atomic multi-file operations with automatic rollback
    on failure, ensuring consistency of the codebase.
    """

    def __init__(
        self,
        backup_root: Optional[Path] = None,
        log_dir: Optional[Path] = None,
        auto_cleanup_hours: int = 24
    ):
        """
        Initialize transaction manager.

        Args:
            backup_root: Root directory for transaction backups
            log_dir: Directory for transaction logs
            auto_cleanup_hours: Hours before cleaning up old transactions
        """
        self.backup_root = backup_root or Path.home() / ".cache" / "gambiarra" / "transactions"
        self.log_dir = log_dir or Path.home() / ".cache" / "gambiarra" / "transaction_logs"
        self.auto_cleanup_hours = auto_cleanup_hours

        # Create directories
        self.backup_root.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # Active transactions
        self._active_transactions: Dict[str, Transaction] = {}

        logger.info(
            f"Initialized TransactionManager "
            f"(backup={self.backup_root}, logs={self.log_dir})"
        )

    def begin_transaction(
        self,
        description: str,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Begin a new transaction.

        Args:
            description: Human-readable description of the transaction
            session_id: Optional session identifier
            metadata: Optional metadata

        Returns:
            Transaction ID
        """
        transaction_id = str(uuid.uuid4())

        # Create backup directory for this transaction
        backup_dir = self.backup_root / transaction_id
        backup_dir.mkdir(parents=True, exist_ok=True)

        transaction = Transaction(
            transaction_id=transaction_id,
            description=description,
            session_id=session_id,
            user_metadata=metadata or {},
            backup_dir=backup_dir
        )

        self._active_transactions[transaction_id] = transaction

        logger.info(f"Started transaction {transaction_id}: {description}")

        # Log transaction start
        self._log_transaction_event(transaction, "begin")

        return transaction_id

    def add_operation(
        self,
        transaction_id: str,
        operation_type: OperationType,
        file_path: str,
        new_content: Optional[str] = None,
        new_path: Optional[str] = None
    ) -> None:
        """
        Add a file operation to a transaction.

        Args:
            transaction_id: Transaction ID
            operation_type: Type of operation
            file_path: Path to the file
            new_content: New content for CREATE/MODIFY operations
            new_path: New path for MOVE operations
        """
        transaction = self._get_transaction(transaction_id)

        if transaction.state != TransactionState.PENDING:
            raise ValueError(
                f"Cannot add operations to transaction in state {transaction.state.value}"
            )

        # Backup original content if file exists
        path_obj = Path(file_path)
        original_content = None
        original_existed = False

        if path_obj.exists() and path_obj.is_file():
            try:
                original_content = path_obj.read_text()
                original_existed = True
            except Exception as e:
                logger.warning(f"Could not read original content of {file_path}: {e}")

        operation = FileOperation(
            operation_type=operation_type,
            file_path=file_path,
            new_content=new_content,
            new_path=new_path,
            original_content=original_content,
            original_existed=original_existed
        )

        transaction.operations.append(operation)

        logger.debug(
            f"Added {operation_type.value} operation for {file_path} "
            f"to transaction {transaction_id}"
        )

    def commit(self, transaction_id: str) -> bool:
        """
        Commit a transaction, executing all operations.

        If any operation fails, automatically rolls back all changes.

        Args:
            transaction_id: Transaction ID

        Returns:
            True if committed successfully, False if rolled back
        """
        transaction = self._get_transaction(transaction_id)

        if transaction.state != TransactionState.PENDING:
            raise ValueError(
                f"Cannot commit transaction in state {transaction.state.value}"
            )

        transaction.state = TransactionState.IN_PROGRESS
        transaction.started_at = time.time()

        logger.info(
            f"Committing transaction {transaction_id} "
            f"with {len(transaction.operations)} operations"
        )

        try:
            # Execute all operations
            for i, operation in enumerate(transaction.operations):
                try:
                    self._execute_operation(transaction, operation)
                    operation.executed = True
                    operation.execution_time = time.time()

                except Exception as e:
                    # Operation failed - rollback everything
                    logger.error(
                        f"Operation {i+1}/{len(transaction.operations)} failed in "
                        f"transaction {transaction_id}: {e}"
                    )
                    operation.error = str(e)

                    # Rollback
                    self._rollback_transaction(transaction)

                    transaction.state = TransactionState.FAILED
                    transaction.completed_at = time.time()

                    self._log_transaction_event(transaction, "failed", error=str(e))

                    return False

            # All operations succeeded
            transaction.state = TransactionState.COMMITTED
            transaction.completed_at = time.time()

            logger.info(f"Transaction {transaction_id} committed successfully")

            self._log_transaction_event(transaction, "committed")

            # Cleanup backup after successful commit
            self._cleanup_transaction_backup(transaction)

            return True

        except Exception as e:
            logger.error(f"Unexpected error during transaction {transaction_id}: {e}")

            transaction.state = TransactionState.FAILED
            transaction.completed_at = time.time()

            self._log_transaction_event(transaction, "error", error=str(e))

            # Attempt rollback
            try:
                self._rollback_transaction(transaction)
            except Exception as rollback_error:
                logger.error(f"Rollback also failed: {rollback_error}")

            return False

    def rollback(self, transaction_id: str) -> bool:
        """
        Manually rollback a transaction.

        Args:
            transaction_id: Transaction ID

        Returns:
            True if rolled back successfully
        """
        transaction = self._get_transaction(transaction_id)

        if transaction.state == TransactionState.ROLLED_BACK:
            logger.warning(f"Transaction {transaction_id} already rolled back")
            return True

        if transaction.state == TransactionState.COMMITTED:
            raise ValueError("Cannot rollback a committed transaction")

        logger.info(f"Rolling back transaction {transaction_id}")

        try:
            self._rollback_transaction(transaction)

            transaction.state = TransactionState.ROLLED_BACK
            transaction.completed_at = time.time()

            self._log_transaction_event(transaction, "rolled_back")

            return True

        except Exception as e:
            logger.error(f"Rollback failed for transaction {transaction_id}: {e}")
            return False

    def _execute_operation(self, transaction: Transaction, operation: FileOperation) -> None:
        """Execute a single file operation."""
        path = Path(operation.file_path)

        if operation.operation_type == OperationType.CREATE:
            # Create new file
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(operation.new_content or "")

            logger.debug(f"Created file {operation.file_path}")

        elif operation.operation_type == OperationType.MODIFY:
            # Modify existing file (or create if doesn't exist)
            path.parent.mkdir(parents=True, exist_ok=True)

            # Backup original if exists
            if operation.original_existed and transaction.backup_dir:
                backup_path = transaction.backup_dir / Path(operation.file_path).name
                backup_path.write_text(operation.original_content or "")

            path.write_text(operation.new_content or "")

            logger.debug(f"Modified file {operation.file_path}")

        elif operation.operation_type == OperationType.DELETE:
            # Delete file
            if path.exists():
                # Backup before deleting
                if transaction.backup_dir:
                    backup_path = transaction.backup_dir / path.name
                    shutil.copy2(path, backup_path)

                path.unlink()

                logger.debug(f"Deleted file {operation.file_path}")

        elif operation.operation_type == OperationType.MOVE:
            # Move/rename file
            new_path = Path(operation.new_path)

            if path.exists():
                # Backup original
                if transaction.backup_dir:
                    backup_path = transaction.backup_dir / path.name
                    shutil.copy2(path, backup_path)

                new_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(path), str(new_path))

                logger.debug(f"Moved file {operation.file_path} to {operation.new_path}")

    def _rollback_transaction(self, transaction: Transaction) -> None:
        """Rollback all executed operations in a transaction."""
        logger.info(
            f"Rolling back {len([op for op in transaction.operations if op.executed])} "
            f"operations in transaction {transaction.transaction_id}"
        )

        # Rollback in reverse order
        for operation in reversed(transaction.operations):
            if not operation.executed:
                continue  # Skip operations that weren't executed

            try:
                self._rollback_operation(transaction, operation)

            except Exception as e:
                logger.error(
                    f"Failed to rollback operation for {operation.file_path}: {e}"
                )
                # Continue with other rollbacks

    def _rollback_operation(self, transaction: Transaction, operation: FileOperation) -> None:
        """Rollback a single operation."""
        path = Path(operation.file_path)

        if operation.operation_type == OperationType.CREATE:
            # Delete created file
            if path.exists():
                path.unlink()
                logger.debug(f"Rolled back CREATE: deleted {operation.file_path}")

        elif operation.operation_type == OperationType.MODIFY:
            # Restore original content
            if operation.original_existed and operation.original_content is not None:
                path.write_text(operation.original_content)
                logger.debug(f"Rolled back MODIFY: restored {operation.file_path}")
            elif not operation.original_existed and path.exists():
                # File didn't exist before, delete it
                path.unlink()
                logger.debug(f"Rolled back MODIFY: deleted {operation.file_path}")

        elif operation.operation_type == OperationType.DELETE:
            # Restore deleted file from backup
            if transaction.backup_dir:
                backup_path = transaction.backup_dir / path.name
                if backup_path.exists():
                    shutil.copy2(backup_path, path)
                    logger.debug(f"Rolled back DELETE: restored {operation.file_path}")

        elif operation.operation_type == OperationType.MOVE:
            # Move file back to original location
            new_path = Path(operation.new_path)
            if new_path.exists():
                shutil.move(str(new_path), str(path))
                logger.debug(
                    f"Rolled back MOVE: moved {operation.new_path} back to {operation.file_path}"
                )

    def _get_transaction(self, transaction_id: str) -> Transaction:
        """Get transaction by ID."""
        if transaction_id not in self._active_transactions:
            raise ValueError(f"Transaction {transaction_id} not found")
        return self._active_transactions[transaction_id]

    def _log_transaction_event(
        self,
        transaction: Transaction,
        event: str,
        error: Optional[str] = None
    ) -> None:
        """Log transaction event to disk."""
        log_entry = {
            "transaction_id": transaction.transaction_id,
            "event": event,
            "timestamp": time.time(),
            "description": transaction.description,
            "state": transaction.state.value,
            "operation_count": len(transaction.operations),
            "session_id": transaction.session_id,
            "error": error
        }

        log_file = self.log_dir / f"{transaction.transaction_id}.jsonl"

        try:
            with open(log_file, 'a') as f:
                f.write(json.dumps(log_entry) + '\n')
        except Exception as e:
            logger.warning(f"Failed to write transaction log: {e}")

    def _cleanup_transaction_backup(self, transaction: Transaction) -> None:
        """Cleanup transaction backup directory."""
        if transaction.backup_dir and transaction.backup_dir.exists():
            try:
                shutil.rmtree(transaction.backup_dir)
                logger.debug(f"Cleaned up backup for transaction {transaction.transaction_id}")
            except Exception as e:
                logger.warning(f"Failed to cleanup backup: {e}")

    def get_transaction_status(self, transaction_id: str) -> Dict[str, Any]:
        """
        Get status of a transaction.

        Args:
            transaction_id: Transaction ID

        Returns:
            Dictionary with transaction status
        """
        transaction = self._get_transaction(transaction_id)

        return {
            "transaction_id": transaction.transaction_id,
            "description": transaction.description,
            "state": transaction.state.value,
            "operation_count": len(transaction.operations),
            "executed_count": len([op for op in transaction.operations if op.executed]),
            "failed_operations": [
                {
                    "file_path": op.file_path,
                    "operation_type": op.operation_type.value,
                    "error": op.error
                }
                for op in transaction.operations if op.error
            ],
            "created_at": transaction.created_at,
            "started_at": transaction.started_at,
            "completed_at": transaction.completed_at,
            "duration": (
                transaction.completed_at - transaction.started_at
                if transaction.started_at and transaction.completed_at
                else None
            )
        }

    def cleanup_old_transactions(self) -> int:
        """
        Cleanup old transaction backups and logs.

        Returns:
            Number of transactions cleaned up
        """
        cutoff_time = time.time() - (self.auto_cleanup_hours * 3600)
        cleaned_count = 0

        # Cleanup old backups
        if self.backup_root.exists():
            for backup_dir in self.backup_root.iterdir():
                if backup_dir.is_dir():
                    try:
                        # Check modification time
                        mtime = backup_dir.stat().st_mtime
                        if mtime < cutoff_time:
                            shutil.rmtree(backup_dir)
                            cleaned_count += 1
                    except Exception as e:
                        logger.warning(f"Failed to cleanup {backup_dir}: {e}")

        logger.info(f"Cleaned up {cleaned_count} old transaction backups")
        return cleaned_count


# Global instance
_transaction_manager: Optional[TransactionManager] = None


def get_transaction_manager() -> TransactionManager:
    """Get global transaction manager instance."""
    global _transaction_manager
    if _transaction_manager is None:
        _transaction_manager = TransactionManager()
    return _transaction_manager


def set_transaction_manager(manager: TransactionManager):
    """Set global transaction manager instance."""
    global _transaction_manager
    _transaction_manager = manager
