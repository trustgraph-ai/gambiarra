"""
Transaction Context Manager for easy transactional file operations.

Provides a context manager (with statement) for transactional operations,
automatically handling commit/rollback.
"""

import logging
from typing import Optional, Dict, Any, List
from pathlib import Path
from contextlib import contextmanager

from .manager import (
    TransactionManager,
    OperationType,
    get_transaction_manager
)

logger = logging.getLogger(__name__)


class TransactionContext:
    """
    Context manager for transactional file operations.

    Usage:
        with TransactionContext("Refactor user module") as txn:
            txn.modify_file("user.py", new_content)
            txn.modify_file("user_test.py", test_content)
            txn.delete_file("old_user.py")
            # Automatic commit on success, rollback on exception
    """

    def __init__(
        self,
        description: str,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        manager: Optional[TransactionManager] = None
    ):
        """
        Initialize transaction context.

        Args:
            description: Description of the transaction
            session_id: Optional session ID
            metadata: Optional metadata
            manager: Transaction manager (uses global if None)
        """
        self.description = description
        self.session_id = session_id
        self.metadata = metadata
        self.manager = manager or get_transaction_manager()

        self.transaction_id: Optional[str] = None
        self._committed = False

    def __enter__(self):
        """Enter transaction context."""
        self.transaction_id = self.manager.begin_transaction(
            description=self.description,
            session_id=self.session_id,
            metadata=self.metadata
        )

        logger.debug(f"Entered transaction context {self.transaction_id}")

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit transaction context."""
        if exc_type is not None:
            # Exception occurred - rollback
            logger.info(
                f"Exception in transaction {self.transaction_id}, rolling back: {exc_val}"
            )

            self.manager.rollback(self.transaction_id)

            # Don't suppress the exception
            return False

        # No exception - commit
        if not self._committed:
            success = self.manager.commit(self.transaction_id)

            if not success:
                # Commit failed - raise exception
                raise RuntimeError(
                    f"Transaction {self.transaction_id} failed to commit "
                    f"and was rolled back"
                )

        return False

    def create_file(self, file_path: str, content: str) -> None:
        """
        Create a new file in this transaction.

        Args:
            file_path: Path to the file
            content: File content
        """
        if self.transaction_id is None:
            raise RuntimeError("Transaction not started")

        self.manager.add_operation(
            transaction_id=self.transaction_id,
            operation_type=OperationType.CREATE,
            file_path=file_path,
            new_content=content
        )

    def modify_file(self, file_path: str, content: str) -> None:
        """
        Modify an existing file in this transaction.

        Args:
            file_path: Path to the file
            content: New file content
        """
        if self.transaction_id is None:
            raise RuntimeError("Transaction not started")

        self.manager.add_operation(
            transaction_id=self.transaction_id,
            operation_type=OperationType.MODIFY,
            file_path=file_path,
            new_content=content
        )

    def delete_file(self, file_path: str) -> None:
        """
        Delete a file in this transaction.

        Args:
            file_path: Path to the file
        """
        if self.transaction_id is None:
            raise RuntimeError("Transaction not started")

        self.manager.add_operation(
            transaction_id=self.transaction_id,
            operation_type=OperationType.DELETE,
            file_path=file_path
        )

    def move_file(self, file_path: str, new_path: str) -> None:
        """
        Move/rename a file in this transaction.

        Args:
            file_path: Current path to the file
            new_path: New path for the file
        """
        if self.transaction_id is None:
            raise RuntimeError("Transaction not started")

        self.manager.add_operation(
            transaction_id=self.transaction_id,
            operation_type=OperationType.MOVE,
            file_path=file_path,
            new_path=new_path
        )

    def commit(self) -> bool:
        """
        Manually commit the transaction (optional, auto-commits on exit).

        Returns:
            True if committed successfully
        """
        if self.transaction_id is None:
            raise RuntimeError("Transaction not started")

        if self._committed:
            logger.warning(f"Transaction {self.transaction_id} already committed")
            return True

        success = self.manager.commit(self.transaction_id)
        self._committed = success

        return success

    def rollback(self) -> bool:
        """
        Manually rollback the transaction.

        Returns:
            True if rolled back successfully
        """
        if self.transaction_id is None:
            raise RuntimeError("Transaction not started")

        return self.manager.rollback(self.transaction_id)

    def get_status(self) -> Dict[str, Any]:
        """
        Get status of this transaction.

        Returns:
            Transaction status dictionary
        """
        if self.transaction_id is None:
            return {"error": "Transaction not started"}

        return self.manager.get_transaction_status(self.transaction_id)


@contextmanager
def atomic_file_operations(
    description: str,
    session_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
):
    """
    Context manager for atomic file operations.

    This is a convenience function that creates a TransactionContext.

    Usage:
        with atomic_file_operations("Update configuration") as txn:
            txn.modify_file("config.yaml", new_config)
            txn.modify_file("config_backup.yaml", backup)

    Args:
        description: Description of the transaction
        session_id: Optional session ID
        metadata: Optional metadata

    Yields:
        TransactionContext instance
    """
    txn = TransactionContext(
        description=description,
        session_id=session_id,
        metadata=metadata
    )

    with txn:
        yield txn


class BatchFileOperations:
    """
    Helper class for building batch file operations.

    Collects operations and executes them transactionally.
    """

    def __init__(self):
        """Initialize batch operations."""
        self.operations: List[Dict[str, Any]] = []

    def create(self, file_path: str, content: str):
        """Queue a create operation."""
        self.operations.append({
            "type": OperationType.CREATE,
            "file_path": file_path,
            "content": content
        })
        return self

    def modify(self, file_path: str, content: str):
        """Queue a modify operation."""
        self.operations.append({
            "type": OperationType.MODIFY,
            "file_path": file_path,
            "content": content
        })
        return self

    def delete(self, file_path: str):
        """Queue a delete operation."""
        self.operations.append({
            "type": OperationType.DELETE,
            "file_path": file_path
        })
        return self

    def move(self, file_path: str, new_path: str):
        """Queue a move operation."""
        self.operations.append({
            "type": OperationType.MOVE,
            "file_path": file_path,
            "new_path": new_path
        })
        return self

    def execute(
        self,
        description: str,
        session_id: Optional[str] = None
    ) -> bool:
        """
        Execute all queued operations transactionally.

        Args:
            description: Transaction description
            session_id: Optional session ID

        Returns:
            True if all operations succeeded
        """
        manager = get_transaction_manager()

        transaction_id = manager.begin_transaction(
            description=description,
            session_id=session_id
        )

        # Add all operations
        for op in self.operations:
            if op["type"] == OperationType.CREATE:
                manager.add_operation(
                    transaction_id,
                    OperationType.CREATE,
                    op["file_path"],
                    new_content=op["content"]
                )
            elif op["type"] == OperationType.MODIFY:
                manager.add_operation(
                    transaction_id,
                    OperationType.MODIFY,
                    op["file_path"],
                    new_content=op["content"]
                )
            elif op["type"] == OperationType.DELETE:
                manager.add_operation(
                    transaction_id,
                    OperationType.DELETE,
                    op["file_path"]
                )
            elif op["type"] == OperationType.MOVE:
                manager.add_operation(
                    transaction_id,
                    OperationType.MOVE,
                    op["file_path"],
                    new_path=op["new_path"]
                )

        # Commit transaction
        return manager.commit(transaction_id)

    def clear(self):
        """Clear all queued operations."""
        self.operations.clear()
        return self
