"""Error handling and recovery modules for Gambiarra server."""

from .recovery import ErrorRecoveryManager, ErrorCategory, ErrorSeverity, ErrorRecord

__all__ = ["ErrorRecoveryManager", "ErrorCategory", "ErrorSeverity", "ErrorRecord"]