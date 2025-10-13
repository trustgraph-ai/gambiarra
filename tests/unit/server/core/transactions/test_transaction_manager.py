"""
Unit tests for Transaction & Rollback System.

Tests:
- Transaction lifecycle
- Atomic operations
- Rollback on failure
- Backup and restore
- Transaction logging
"""

import pytest
import tempfile
import asyncio
from pathlib import Path
from gambiarra.server.core.transactions import (
    TransactionManager,
    TransactionContext,
    BatchFileOperations,
    TransactionState,
    OperationType
)


class TestTransactionManager:
    """Test TransactionManager implementation."""

    @pytest.fixture
    def manager(self):
        """Create transaction manager with temp directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = TransactionManager(
                backup_root=Path(temp_dir) / "backups",
                log_dir=Path(temp_dir) / "logs"
            )
            yield manager

    @pytest.fixture
    def temp_files(self):
        """Create temporary files for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create test files
            file1 = temp_path / "file1.txt"
            file2 = temp_path / "file2.txt"
            file3 = temp_path / "file3.txt"

            file1.write_text("Original content 1")
            file2.write_text("Original content 2")
            file3.write_text("Original content 3")

            yield {
                'dir': temp_path,
                'file1': file1,
                'file2': file2,
                'file3': file3
            }

    def test_begin_transaction(self, manager):
        """Test beginning a transaction."""
        txn_id = manager.begin_transaction("Test transaction")

        assert txn_id is not None
        assert len(txn_id) > 0

        # Check transaction exists
        status = manager.get_transaction_status(txn_id)
        assert status['state'] == TransactionState.PENDING.value
        assert status['description'] == "Test transaction"

    def test_add_modify_operation(self, manager, temp_files):
        """Test adding modify operation."""
        txn_id = manager.begin_transaction("Modify file")

        file_path = str(temp_files['file1'])
        new_content = "Modified content"

        manager.add_operation(
            txn_id,
            OperationType.MODIFY,
            file_path,
            new_content=new_content
        )

        status = manager.get_transaction_status(txn_id)
        assert status['operation_count'] == 1

    def test_commit_successful(self, manager, temp_files):
        """Test successful commit."""
        txn_id = manager.begin_transaction("Modify files")

        file1 = temp_files['file1']
        file2 = temp_files['file2']

        # Add operations
        manager.add_operation(txn_id, OperationType.MODIFY, str(file1), new_content="New 1")
        manager.add_operation(txn_id, OperationType.MODIFY, str(file2), new_content="New 2")

        # Commit
        success = manager.commit(txn_id)
        assert success is True

        # Verify changes applied
        assert file1.read_text() == "New 1"
        assert file2.read_text() == "New 2"

        # Check transaction state
        status = manager.get_transaction_status(txn_id)
        assert status['state'] == TransactionState.COMMITTED.value

    def test_rollback_on_failure(self, manager, temp_files):
        """Test automatic rollback on failure."""
        txn_id = manager.begin_transaction("Test rollback")

        file1 = temp_files['file1']
        original_content = file1.read_text()

        # Add valid operation
        manager.add_operation(txn_id, OperationType.MODIFY, str(file1), new_content="New content")

        # Add invalid operation (try to write to a directory path - will fail)
        invalid_path = str(temp_files['dir'])  # This is a directory, not a file
        manager.add_operation(
            txn_id,
            OperationType.MODIFY,
            invalid_path,
            new_content="This will fail"
        )

        # Commit should fail and rollback
        success = manager.commit(txn_id)
        assert success is False

        # Verify file1 is restored to original
        assert file1.read_text() == original_content

        # Check transaction state
        status = manager.get_transaction_status(txn_id)
        assert status['state'] in [TransactionState.FAILED.value, TransactionState.ROLLED_BACK.value]

    def test_create_operation(self, manager, temp_files):
        """Test create operation."""
        txn_id = manager.begin_transaction("Create file")

        new_file = temp_files['dir'] / "new_file.txt"
        assert not new_file.exists()

        # Add create operation
        manager.add_operation(
            txn_id,
            OperationType.CREATE,
            str(new_file),
            new_content="New file content"
        )

        # Commit
        success = manager.commit(txn_id)
        assert success is True

        # Verify file created
        assert new_file.exists()
        assert new_file.read_text() == "New file content"

    def test_delete_operation(self, manager, temp_files):
        """Test delete operation."""
        txn_id = manager.begin_transaction("Delete file")

        file_to_delete = temp_files['file1']
        original_content = file_to_delete.read_text()

        # Add delete operation
        manager.add_operation(txn_id, OperationType.DELETE, str(file_to_delete))

        # Commit
        success = manager.commit(txn_id)
        assert success is True

        # Verify file deleted
        assert not file_to_delete.exists()

    def test_delete_rollback(self, manager, temp_files):
        """Test delete operation rollback."""
        txn_id = manager.begin_transaction("Delete with rollback")

        file_to_delete = temp_files['file1']
        original_content = file_to_delete.read_text()

        # Add delete operation
        manager.add_operation(txn_id, OperationType.DELETE, str(file_to_delete))

        # Add invalid operation to trigger rollback (write to directory)
        manager.add_operation(
            txn_id,
            OperationType.MODIFY,
            str(temp_files['dir']),
            new_content="Fail"
        )

        # Commit should fail
        success = manager.commit(txn_id)
        assert success is False

        # Verify file restored
        assert file_to_delete.exists()
        assert file_to_delete.read_text() == original_content

    def test_multiple_operations_atomic(self, manager, temp_files):
        """Test multiple operations are atomic."""
        txn_id = manager.begin_transaction("Multi-op")

        file1 = temp_files['file1']
        file2 = temp_files['file2']
        file3 = temp_files['file3']

        original1 = file1.read_text()
        original2 = file2.read_text()
        original3 = file3.read_text()

        # Add multiple operations
        manager.add_operation(txn_id, OperationType.MODIFY, str(file1), new_content="New 1")
        manager.add_operation(txn_id, OperationType.MODIFY, str(file2), new_content="New 2")
        manager.add_operation(txn_id, OperationType.MODIFY, str(file3), new_content="New 3")

        # Add invalid operation (write to directory - will fail)
        manager.add_operation(
            txn_id,
            OperationType.CREATE,
            str(temp_files['dir']),
            new_content="Fail"
        )

        # Commit should fail
        success = manager.commit(txn_id)
        assert success is False

        # All files should be restored
        assert file1.read_text() == original1
        assert file2.read_text() == original2
        assert file3.read_text() == original3

    def test_transaction_logging(self, manager):
        """Test transaction logging."""
        txn_id = manager.begin_transaction("Test logging")

        # Commit empty transaction
        manager.commit(txn_id)

        # Check log file exists
        log_file = manager.log_dir / f"{txn_id}.jsonl"
        assert log_file.exists()

        # Read log entries
        log_content = log_file.read_text()
        assert "begin" in log_content
        assert "commit" in log_content

    def test_manual_rollback(self, manager, temp_files):
        """Test manual rollback before commit."""
        txn_id = manager.begin_transaction("Manual rollback")

        file1 = temp_files['file1']
        original_content = file1.read_text()

        # Add operation
        manager.add_operation(txn_id, OperationType.MODIFY, str(file1), new_content="Modified")

        # Manual rollback (before commit)
        manager.rollback(txn_id)

        # Verify file is unchanged (rollback should do nothing since not committed)
        # The operations were never executed, so file should be original
        assert file1.read_text() == original_content

        # Check transaction state
        status = manager.get_transaction_status(txn_id)
        assert status['state'] == TransactionState.ROLLED_BACK.value


class TestTransactionContext:
    """Test TransactionContext context manager."""

    @pytest.fixture
    def temp_files(self):
        """Create temporary files for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            file1 = temp_path / "file1.txt"
            file1.write_text("Original 1")

            yield {'dir': temp_path, 'file1': file1}

    def test_context_manager_success(self, temp_files):
        """Test successful transaction with context manager."""
        file1 = temp_files['file1']

        with TransactionContext("Test transaction") as txn:
            txn.modify_file(str(file1), "Modified content")

        # Verify committed
        assert file1.read_text() == "Modified content"

    def test_context_manager_rollback_on_exception(self, temp_files):
        """Test automatic rollback on exception."""
        file1 = temp_files['file1']
        original = file1.read_text()

        try:
            with TransactionContext("Test rollback") as txn:
                txn.modify_file(str(file1), "Modified")
                raise RuntimeError("Simulated error")
        except RuntimeError:
            pass

        # Verify rolled back
        assert file1.read_text() == original

    def test_create_file_in_context(self, temp_files):
        """Test creating file in context."""
        new_file = temp_files['dir'] / "new.txt"

        with TransactionContext("Create file") as txn:
            txn.create_file(str(new_file), "New content")

        assert new_file.exists()
        assert new_file.read_text() == "New content"

    def test_delete_file_in_context(self, temp_files):
        """Test deleting file in context."""
        file1 = temp_files['file1']

        with TransactionContext("Delete file") as txn:
            txn.delete_file(str(file1))

        assert not file1.exists()

    def test_multiple_operations_in_context(self, temp_files):
        """Test multiple operations in one transaction."""
        file1 = temp_files['file1']
        file2 = temp_files['dir'] / "file2.txt"
        file3 = temp_files['dir'] / "file3.txt"

        with TransactionContext("Multi-op") as txn:
            txn.modify_file(str(file1), "Modified 1")
            txn.create_file(str(file2), "New 2")
            txn.create_file(str(file3), "New 3")

        assert file1.read_text() == "Modified 1"
        assert file2.read_text() == "New 2"
        assert file3.read_text() == "New 3"

    def test_get_status_in_context(self):
        """Test getting status during transaction."""
        with tempfile.TemporaryDirectory() as temp_dir:
            file1 = Path(temp_dir) / "test.txt"
            file1.write_text("Content")

            with TransactionContext("Status test") as txn:
                txn.modify_file(str(file1), "Modified")

                status = txn.get_status()
                assert status['state'] == TransactionState.PENDING.value
                assert status['operation_count'] == 1


class TestBatchFileOperations:
    """Test BatchFileOperations builder."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield Path(temp_dir)

    def test_batch_create_files(self, temp_dir):
        """Test batch creating files."""
        file1 = temp_dir / "file1.txt"
        file2 = temp_dir / "file2.txt"

        batch = BatchFileOperations()
        batch.create(str(file1), "Content 1")
        batch.create(str(file2), "Content 2")

        success = batch.execute("Batch create")
        assert success is True

        assert file1.read_text() == "Content 1"
        assert file2.read_text() == "Content 2"

    def test_batch_chaining(self, temp_dir):
        """Test method chaining."""
        file1 = temp_dir / "file1.txt"
        file2 = temp_dir / "file2.txt"

        batch = BatchFileOperations()
        batch.create(str(file1), "A").create(str(file2), "B")

        success = batch.execute("Chain test")
        assert success is True

        assert file1.exists()
        assert file2.exists()

    def test_batch_mixed_operations(self, temp_dir):
        """Test mixed operations in batch."""
        file1 = temp_dir / "existing.txt"
        file1.write_text("Original")

        file2 = temp_dir / "new.txt"

        batch = BatchFileOperations()
        batch.modify(str(file1), "Modified")
        batch.create(str(file2), "New")

        success = batch.execute("Mixed ops")
        assert success is True

        assert file1.read_text() == "Modified"
        assert file2.read_text() == "New"

    def test_batch_rollback_on_failure(self, temp_dir):
        """Test batch rollback on failure."""
        file1 = temp_dir / "file1.txt"
        file1.write_text("Original")

        batch = BatchFileOperations()
        batch.modify(str(file1), "Modified")
        batch.create(str(temp_dir), "Fail")  # Write to dir - will fail

        success = batch.execute("Batch rollback")
        assert success is False

        # Should be rolled back
        assert file1.read_text() == "Original"


class TestTransactionEdgeCases:
    """Test edge cases and error conditions."""

    def test_commit_twice(self):
        """Test committing same transaction twice."""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = TransactionManager(backup_root=Path(temp_dir))
            txn_id = manager.begin_transaction("Test")

            # First commit
            success1 = manager.commit(txn_id)
            assert success1 is True

            # Second commit should raise ValueError
            with pytest.raises(ValueError, match="Cannot commit"):
                manager.commit(txn_id)

    def test_rollback_committed_transaction(self):
        """Test rolling back already committed transaction."""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = TransactionManager(backup_root=Path(temp_dir))
            txn_id = manager.begin_transaction("Test")

            manager.commit(txn_id)

            # Try to rollback committed transaction
            # Should handle gracefully

    def test_invalid_transaction_id(self):
        """Test operations with invalid transaction ID."""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = TransactionManager(backup_root=Path(temp_dir))

            # Try to commit non-existent transaction
            with pytest.raises(Exception):
                manager.commit("invalid-id")

    def test_empty_transaction(self):
        """Test committing empty transaction."""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = TransactionManager(backup_root=Path(temp_dir))
            txn_id = manager.begin_transaction("Empty")

            # Commit with no operations
            success = manager.commit(txn_id)
            assert success is True

    def test_concurrent_transactions(self):
        """Test multiple concurrent transactions."""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = TransactionManager(backup_root=Path(temp_dir))

            file1 = Path(temp_dir) / "file1.txt"
            file2 = Path(temp_dir) / "file2.txt"

            file1.write_text("Original 1")
            file2.write_text("Original 2")

            # Two independent transactions
            txn1 = manager.begin_transaction("Txn 1")
            txn2 = manager.begin_transaction("Txn 2")

            # Modify different files
            manager.add_operation(txn1, OperationType.MODIFY, str(file1), new_content="New 1")
            manager.add_operation(txn2, OperationType.MODIFY, str(file2), new_content="New 2")

            # Both should succeed
            assert manager.commit(txn1) is True
            assert manager.commit(txn2) is True

            assert file1.read_text() == "New 1"
            assert file2.read_text() == "New 2"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
