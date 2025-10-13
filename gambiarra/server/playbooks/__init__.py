"""
Playbook system for Gambiarra.
Provides tested, reliable command sequences for common operations.
"""

from .registry import (
    PlaybookDefinition,
    PlaybookStep,
    PlaybookVariable,
    PlaybookRegistry,
    get_playbook_registry
)
from .executor import (
    PlaybookExecutor,
    PlaybookExecutionResult,
    get_playbook_executor
)

__all__ = [
    'PlaybookDefinition',
    'PlaybookStep',
    'PlaybookVariable',
    'PlaybookRegistry',
    'get_playbook_registry',
    'PlaybookExecutor',
    'PlaybookExecutionResult',
    'get_playbook_executor'
]
