"""
Demo script for Transaction System.

Demonstrates atomic multi-file operations with automatic rollback on failure.
"""

import sys
from pathlib import Path
import tempfile

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from gambiarra.server.core.transactions import (
    TransactionContext,
    atomic_file_operations,
    BatchFileOperations,
    get_transaction_manager
)


def demo_successful_transaction():
    """Demonstrate a successful transaction."""
    print("=" * 80)
    print("DEMO 1: Successful Transaction")
    print("=" * 80)
    print()

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create initial files
        file1 = temp_path / "module.py"
        file2 = temp_path / "test_module.py"
        file3 = temp_path / "old_module.py"

        file1.write_text("# Old module implementation\ndef old_function():\n    pass\n")
        file3.write_text("# Deprecated module\n")

        print(f"Initial files in {temp_dir}:")
        print(f"  - module.py (exists)")
        print(f"  - old_module.py (exists)")
        print()

        # Perform transactional refactoring
        print("Performing transactional refactoring...")
        print("  1. Modifying module.py")
        print("  2. Creating test_module.py")
        print("  3. Deleting old_module.py")
        print()

        with TransactionContext("Refactor module") as txn:
            # Modify existing file
            txn.modify_file(
                str(file1),
                "# New module implementation\ndef new_function():\n    return 'improved'\n"
            )

            # Create new file
            txn.create_file(
                str(file2),
                "# Test for module\ndef test_new_function():\n    assert new_function() == 'improved'\n"
            )

            # Delete old file
            txn.delete_file(str(file3))

        print("Transaction committed successfully! ✓")
        print()

        # Verify results
        print("Final files:")
        for f in temp_path.iterdir():
            content = f.read_text()
            print(f"  - {f.name}:")
            print(f"    {content[:50]}...")
        print()

        if not file3.exists():
            print("✓ old_module.py was deleted")
        if file2.exists():
            print("✓ test_module.py was created")

        print()


def demo_failed_transaction_with_rollback():
    """Demonstrate a failed transaction with automatic rollback."""
    print("=" * 80)
    print("DEMO 2: Failed Transaction (Automatic Rollback)")
    print("=" * 80)
    print()

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create initial file
        file1 = temp_path / "config.py"
        original_content = "# Original config\nDEBUG = False\n"
        file1.write_text(original_content)

        print(f"Initial file: config.py")
        print(f"Content: {original_content}")
        print()

        # Attempt transaction that will fail
        print("Attempting transaction with 3 operations...")
        print("  1. Modifying config.py ✓")
        print("  2. Creating settings.py ✓")
        print("  3. Writing to read-only file ✗ (will fail)")
        print()

        try:
            with TransactionContext("Update configuration") as txn:
                # Operation 1: Succeed
                txn.modify_file(
                    str(file1),
                    "# Modified config\nDEBUG = True\n"
                )

                # Operation 2: Succeed
                txn.create_file(
                    str(temp_path / "settings.py"),
                    "# Settings file\nENV = 'production'\n"
                )

                # Operation 3: Simulate failure
                raise RuntimeError("Simulated error during transaction")

        except RuntimeError as e:
            print(f"Transaction failed: {e}")
            print()

        # Verify rollback
        print("Verifying rollback...")
        final_content = file1.read_text()

        if final_content == original_content:
            print("✓ config.py was rolled back to original content")
        else:
            print("✗ Rollback failed!")

        if not (temp_path / "settings.py").exists():
            print("✓ settings.py was not created (rolled back)")
        else:
            print("✗ settings.py still exists!")

        print()
        print("All changes were automatically rolled back! ✓")
        print()


def demo_batch_operations():
    """Demonstrate batch operations."""
    print("=" * 80)
    print("DEMO 3: Batch Operations")
    print("=" * 80)
    print()

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        print("Building batch of operations...")
        print()

        # Create batch
        batch = BatchFileOperations()

        batch.create(
            str(temp_path / "user.py"),
            "class User:\n    def __init__(self, name):\n        self.name = name\n"
        ).create(
            str(temp_path / "user_test.py"),
            "def test_user():\n    user = User('Alice')\n    assert user.name == 'Alice'\n"
        ).create(
            str(temp_path / "README.md"),
            "# User Module\nUser management functionality.\n"
        )

        print("Queued 3 operations:")
        print("  1. Create user.py")
        print("  2. Create user_test.py")
        print("  3. Create README.md")
        print()

        # Execute batch
        print("Executing batch transactionally...")
        success = batch.execute("Create user module")

        if success:
            print("✓ All operations completed successfully")
            print()

            print("Created files:")
            for f in temp_path.iterdir():
                print(f"  - {f.name}")

        print()


def demo_transaction_status():
    """Demonstrate transaction status tracking."""
    print("=" * 80)
    print("DEMO 4: Transaction Status Tracking")
    print("=" * 80)
    print()

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        manager = get_transaction_manager()

        with TransactionContext("Status demo") as txn:
            txn.create_file(str(temp_path / "test.txt"), "content")

            # Get status during transaction
            status = txn.get_status()

            print("Transaction Status:")
            print(f"  ID: {status['transaction_id']}")
            print(f"  Description: {status['description']}")
            print(f"  State: {status['state']}")
            print(f"  Operations: {status['operation_count']}")
            print()

        # Get final status
        status = manager.get_transaction_status(txn.transaction_id)

        print("Final Status:")
        print(f"  State: {status['state']}")
        print(f"  Duration: {status['duration']:.3f}s")
        print(f"  Operations executed: {status['executed_count']}/{status['operation_count']}")
        print()


def main():
    """Run all demos."""
    print()
    print("╔" + "=" * 78 + "╗")
    print("║" + " " * 20 + "TRANSACTION SYSTEM DEMO" + " " * 35 + "║")
    print("╚" + "=" * 78 + "╝")
    print()

    demo_successful_transaction()
    demo_failed_transaction_with_rollback()
    demo_batch_operations()
    demo_transaction_status()

    print("=" * 80)
    print("KEY BENEFITS")
    print("=" * 80)
    print()
    print("✓ Atomicity: All operations succeed or all are rolled back")
    print("✓ Consistency: Never left in partial/broken state")
    print("✓ Isolation: Each transaction is independent")
    print("✓ Durability: Transaction logs persist")
    print()
    print("✓ Easy to use: Context managers handle commit/rollback")
    print("✓ Automatic rollback: Exceptions trigger rollback")
    print("✓ Batch operations: Queue multiple operations")
    print("✓ Status tracking: Monitor transaction progress")
    print()
    print("=" * 80)
    print("DEMO COMPLETE")
    print("=" * 80)
    print()


if __name__ == "__main__":
    main()
