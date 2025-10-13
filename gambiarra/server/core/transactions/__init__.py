"""
Transaction System for Atomic Multi-File Operations.

Provides ACID-like transactions for file operations with automatic
rollback on failure.
"""

from .manager import (
    TransactionState,
    OperationType,
    FileOperation,
    Transaction,
    TransactionManager,
    get_transaction_manager,
    set_transaction_manager
)

from .context import (
    TransactionContext,
    atomic_file_operations,
    BatchFileOperations
)

__all__ = [
    # Manager
    'TransactionState',
    'OperationType',
    'FileOperation',
    'Transaction',
    'TransactionManager',
    'get_transaction_manager',
    'set_transaction_manager',

    # Context
    'TransactionContext',
    'atomic_file_operations',
    'BatchFileOperations',
]
