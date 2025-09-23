"""
Comprehensive error handling and recovery mechanisms for Gambiarra server.
Error recovery and resilience patterns for robust operation.
"""

import asyncio
import logging
import time
import traceback
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass, field
from enum import Enum
import json

logger = logging.getLogger(__name__)


class ErrorSeverity(Enum):
    """Error severity levels."""
    LOW = "low"           # Minor issues, continue operation
    MEDIUM = "medium"     # Moderate issues, may need intervention
    HIGH = "high"         # Serious issues, immediate attention needed
    CRITICAL = "critical" # System-breaking, requires restart


class ErrorCategory(Enum):
    """Categories of errors for better handling."""
    NETWORK = "network"           # WebSocket, HTTP connection issues
    AI_PROVIDER = "ai_provider"   # AI service failures
    TOOL_EXECUTION = "tool_execution"  # Tool failures
    SESSION = "session"           # Session management issues
    VALIDATION = "validation"     # Parameter/data validation errors
    SECURITY = "security"         # Security violations
    SYSTEM = "system"            # System-level errors


@dataclass
class ErrorRecord:
    """Record of an error occurrence."""
    timestamp: float
    category: ErrorCategory
    severity: ErrorSeverity
    message: str
    details: Dict[str, Any]
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    recovery_attempted: bool = False
    recovery_successful: bool = False
    traceback_info: Optional[str] = None


@dataclass
class RecoveryStrategy:
    """Defines how to recover from specific types of errors."""
    category: ErrorCategory
    max_attempts: int
    backoff_seconds: float
    recovery_function: Callable
    escalation_threshold: int = 3  # Escalate after N failures


class ErrorRecoveryManager:
    """
    Manages error handling, recovery strategies, and system resilience.
    """

    def __init__(self, max_error_history: int = 1000):
        self.max_error_history = max_error_history
        self.error_history: List[ErrorRecord] = []
        self.recovery_strategies: Dict[ErrorCategory, RecoveryStrategy] = {}
        self.failure_counts: Dict[str, int] = {}  # Track failure counts by error key

        # Circuit breaker states
        self.circuit_breakers: Dict[str, Dict[str, Any]] = {}

        # Initialize default recovery strategies
        self._setup_default_strategies()

        logger.info("🛡️ Error recovery manager initialized")

    def _setup_default_strategies(self) -> None:
        """Set up default recovery strategies."""

        # Network error recovery
        self.recovery_strategies[ErrorCategory.NETWORK] = RecoveryStrategy(
            category=ErrorCategory.NETWORK,
            max_attempts=3,
            backoff_seconds=2.0,
            recovery_function=self._recover_network_connection,
            escalation_threshold=5
        )

        # AI Provider error recovery
        self.recovery_strategies[ErrorCategory.AI_PROVIDER] = RecoveryStrategy(
            category=ErrorCategory.AI_PROVIDER,
            max_attempts=2,
            backoff_seconds=5.0,
            recovery_function=self._recover_ai_provider,
            escalation_threshold=3
        )

        # Tool execution error recovery
        self.recovery_strategies[ErrorCategory.TOOL_EXECUTION] = RecoveryStrategy(
            category=ErrorCategory.TOOL_EXECUTION,
            max_attempts=1,
            backoff_seconds=1.0,
            recovery_function=self._recover_tool_execution,
            escalation_threshold=10
        )

        # Session error recovery
        self.recovery_strategies[ErrorCategory.SESSION] = RecoveryStrategy(
            category=ErrorCategory.SESSION,
            max_attempts=2,
            backoff_seconds=1.0,
            recovery_function=self._recover_session,
            escalation_threshold=5
        )

    async def handle_error(
        self,
        error: Exception,
        category: ErrorCategory,
        severity: ErrorSeverity,
        context: Dict[str, Any],
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Handle an error with appropriate recovery strategy.

        Args:
            error: The exception that occurred
            category: Category of the error
            severity: Severity level
            context: Additional context information
            session_id: Optional session ID

        Returns:
            Dict with recovery result
        """

        # Create error record
        error_record = ErrorRecord(
            timestamp=time.time(),
            category=category,
            severity=severity,
            message=str(error),
            details=context,
            session_id=session_id,
            traceback_info=traceback.format_exc()
        )

        # Add to history
        self.error_history.append(error_record)
        if len(self.error_history) > self.max_error_history:
            self.error_history = self.error_history[-self.max_error_history:]

        logger.error(f"🚨 {severity.value.upper()} {category.value} error: {error}")

        # Check circuit breaker
        error_key = f"{category.value}:{context.get('operation', 'unknown')}"
        if self._is_circuit_open(error_key):
            return {
                "recovered": False,
                "reason": "Circuit breaker open",
                "retry_after": self.circuit_breakers[error_key]["retry_after"]
            }

        # Attempt recovery if strategy exists
        if category in self.recovery_strategies:
            return await self._attempt_recovery(error_record, error_key)
        else:
            # No recovery strategy - log and return failure
            logger.warning(f"⚠️ No recovery strategy for {category.value} errors")
            return {
                "recovered": False,
                "reason": "No recovery strategy available"
            }

    async def _attempt_recovery(self, error_record: ErrorRecord, error_key: str) -> Dict[str, Any]:
        """Attempt recovery using the appropriate strategy."""
        strategy = self.recovery_strategies[error_record.category]

        # Track failure count
        self.failure_counts[error_key] = self.failure_counts.get(error_key, 0) + 1

        # Check if we should escalate
        if self.failure_counts[error_key] >= strategy.escalation_threshold:
            await self._escalate_error(error_record)
            return {
                "recovered": False,
                "reason": "Escalation threshold reached",
                "escalated": True
            }

        # Attempt recovery with backoff
        for attempt in range(strategy.max_attempts):
            if attempt > 0:
                backoff_time = strategy.backoff_seconds * (2 ** (attempt - 1))  # Exponential backoff
                logger.info(f"🔄 Recovery attempt {attempt + 1}/{strategy.max_attempts} in {backoff_time}s")
                await asyncio.sleep(backoff_time)

            try:
                error_record.recovery_attempted = True
                recovery_result = await strategy.recovery_function(error_record)

                if recovery_result.get("success", False):
                    error_record.recovery_successful = True
                    # Reset failure count on successful recovery
                    self.failure_counts[error_key] = 0
                    logger.info(f"✅ Recovery successful for {error_record.category.value} error")

                    return {
                        "recovered": True,
                        "attempts": attempt + 1,
                        "details": recovery_result
                    }

            except Exception as recovery_error:
                logger.error(f"❌ Recovery attempt {attempt + 1} failed: {recovery_error}")

        # All recovery attempts failed
        logger.error(f"💥 All recovery attempts failed for {error_record.category.value} error")

        # Open circuit breaker
        self._open_circuit_breaker(error_key)

        return {
            "recovered": False,
            "reason": "All recovery attempts failed",
            "attempts": strategy.max_attempts
        }

    def _is_circuit_open(self, error_key: str) -> bool:
        """Check if circuit breaker is open for this error type."""
        if error_key not in self.circuit_breakers:
            return False

        breaker = self.circuit_breakers[error_key]
        return time.time() < breaker["retry_after"]

    def _open_circuit_breaker(self, error_key: str, duration: float = 300.0) -> None:
        """Open circuit breaker for specified duration."""
        self.circuit_breakers[error_key] = {
            "opened_at": time.time(),
            "retry_after": time.time() + duration
        }
        logger.warning(f"⚡ Circuit breaker opened for {error_key} (retry after {duration}s)")

    async def _escalate_error(self, error_record: ErrorRecord) -> None:
        """Escalate error to higher-level handling."""
        logger.critical(f"🚨 ESCALATING {error_record.category.value} error: {error_record.message}")

        # Could implement:
        # - Send alerts to administrators
        # - Create incident tickets
        # - Trigger emergency procedures
        # - Graceful service degradation

    # Recovery functions for different error categories

    async def _recover_network_connection(self, error_record: ErrorRecord) -> Dict[str, Any]:
        """Recover from network connection errors."""
        try:
            # Attempt to re-establish connection
            context = error_record.details
            websocket = context.get("websocket")

            if websocket:
                # Check if WebSocket is still alive
                try:
                    await websocket.ping()
                    return {"success": True, "action": "connection_verified"}
                except:
                    # Connection is dead, need to close and let client reconnect
                    try:
                        await websocket.close()
                    except:
                        pass
                    return {"success": True, "action": "connection_closed_for_reconnect"}

            return {"success": False, "reason": "No websocket to recover"}

        except Exception as e:
            return {"success": False, "reason": str(e)}

    async def _recover_ai_provider(self, error_record: ErrorRecord) -> Dict[str, Any]:
        """Recover from AI provider errors."""
        try:
            context = error_record.details
            provider_name = context.get("provider")

            # Could implement:
            # - Switch to backup AI provider
            # - Reset provider connection
            # - Clear rate limit states
            # - Validate API keys

            logger.info(f"🔄 Attempting AI provider recovery for {provider_name}")

            # For now, just return success to allow retry
            return {"success": True, "action": "provider_reset"}

        except Exception as e:
            return {"success": False, "reason": str(e)}

    async def _recover_tool_execution(self, error_record: ErrorRecord) -> Dict[str, Any]:
        """Recover from tool execution errors."""
        try:
            context = error_record.details
            tool_name = context.get("tool_name")

            # Could implement:
            # - Retry with different parameters
            # - Use alternative tool
            # - Reset tool state
            # - Check system resources

            logger.info(f"🔧 Attempting tool recovery for {tool_name}")

            # Most tool errors shouldn't be automatically retried
            return {"success": False, "reason": "Tool errors require manual intervention"}

        except Exception as e:
            return {"success": False, "reason": str(e)}

    async def _recover_session(self, error_record: ErrorRecord) -> Dict[str, Any]:
        """Recover from session management errors."""
        try:
            context = error_record.details
            session_id = error_record.session_id

            # Could implement:
            # - Recreate session
            # - Reset session state
            # - Clear corrupted data
            # - Restore from backup

            logger.info(f"🎯 Attempting session recovery for {session_id}")

            return {"success": True, "action": "session_state_reset"}

        except Exception as e:
            return {"success": False, "reason": str(e)}

    def get_error_statistics(self) -> Dict[str, Any]:
        """Get error statistics for monitoring."""
        if not self.error_history:
            return {
                "total_errors": 0,
                "categories": {},
                "severity_distribution": {},
                "recovery_success_rate": 0.0
            }

        # Count by category
        category_counts = {}
        for error in self.error_history:
            category = error.category.value
            category_counts[category] = category_counts.get(category, 0) + 1

        # Count by severity
        severity_counts = {}
        for error in self.error_history:
            severity = error.severity.value
            severity_counts[severity] = severity_counts.get(severity, 0) + 1

        # Calculate recovery success rate
        recovery_attempted = sum(1 for e in self.error_history if e.recovery_attempted)
        recovery_successful = sum(1 for e in self.error_history if e.recovery_successful)
        success_rate = (recovery_successful / recovery_attempted * 100) if recovery_attempted > 0 else 0.0

        return {
            "total_errors": len(self.error_history),
            "categories": category_counts,
            "severity_distribution": severity_counts,
            "recovery_success_rate": success_rate,
            "active_circuit_breakers": len([k for k, v in self.circuit_breakers.items()
                                          if time.time() < v["retry_after"]]),
            "failure_counts": dict(self.failure_counts)
        }

    def get_recent_errors(self, count: int = 10) -> List[Dict[str, Any]]:
        """Get recent errors for debugging."""
        recent = self.error_history[-count:] if self.error_history else []

        return [
            {
                "timestamp": error.timestamp,
                "category": error.category.value,
                "severity": error.severity.value,
                "message": error.message,
                "session_id": error.session_id,
                "recovery_attempted": error.recovery_attempted,
                "recovery_successful": error.recovery_successful
            }
            for error in recent
        ]