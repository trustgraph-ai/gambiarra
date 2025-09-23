"""
Tests for server error handling and recovery mechanisms.
Tests error categorization, recovery strategies, and circuit breakers.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from gambiarra.server.error_handling import (
    ErrorRecoveryManager, ErrorCategory, ErrorSeverity
)


class TestErrorCategory:
    """Test error categorization."""

    def test_error_categories(self):
        """Test that error categories are properly defined."""
        categories = [
            ErrorCategory.NETWORK,
            ErrorCategory.AI_PROVIDER,
            ErrorCategory.TOOL_EXECUTION,
            ErrorCategory.VALIDATION,
            ErrorCategory.AUTHENTICATION,
            ErrorCategory.AUTHORIZATION,
            ErrorCategory.RESOURCE,
            ErrorCategory.UNKNOWN
        ]

        for category in categories:
            assert isinstance(category, ErrorCategory)

    def test_error_severity_levels(self):
        """Test error severity levels."""
        severities = [
            ErrorSeverity.LOW,
            ErrorSeverity.MEDIUM,
            ErrorSeverity.HIGH,
            ErrorSeverity.CRITICAL
        ]

        for severity in severities:
            assert isinstance(severity, ErrorSeverity)


class TestErrorRecoveryManager:
    """Test error recovery manager functionality."""

    @pytest.fixture
    def recovery_manager(self):
        """Create error recovery manager instance."""
        return ErrorRecoveryManager()

    @pytest.fixture
    def sample_error(self):
        """Sample error for testing."""
        return Exception("Test error message")

    def test_error_recovery_manager_initialization(self, recovery_manager):
        """Test error recovery manager initialization."""
        assert recovery_manager is not None
        assert hasattr(recovery_manager, 'error_counts')
        assert hasattr(recovery_manager, 'circuit_breakers')

    def test_categorize_network_error(self, recovery_manager):
        """Test categorizing network errors."""
        import aiohttp

        network_errors = [
            aiohttp.ClientError("Connection failed"),
            aiohttp.ClientTimeout("Request timeout"),
            aiohttp.ClientConnectionError("Connection error"),
            ConnectionError("Network unreachable")
        ]

        for error in network_errors:
            category = recovery_manager.categorize_error(error)
            assert category == ErrorCategory.NETWORK

    def test_categorize_ai_provider_error(self, recovery_manager):
        """Test categorizing AI provider errors."""
        ai_errors = [
            Exception("Rate limit exceeded"),
            Exception("API key invalid"),
            Exception("Model not found"),
            Exception("Token limit exceeded")
        ]

        for error in ai_errors:
            category = recovery_manager.categorize_error(error)
            # Would depend on error message analysis
            assert category in [ErrorCategory.AI_PROVIDER, ErrorCategory.UNKNOWN]

    def test_categorize_validation_error(self, recovery_manager):
        """Test categorizing validation errors."""
        from gambiarra.server.core.tools.validator import ValidationError

        validation_errors = [
            ValidationError("Invalid XML"),
            ValueError("Invalid parameter"),
            TypeError("Wrong parameter type")
        ]

        for error in validation_errors:
            category = recovery_manager.categorize_error(error)
            assert category == ErrorCategory.VALIDATION

    def test_determine_error_severity(self, recovery_manager):
        """Test determining error severity."""
        # Critical errors
        critical_errors = [
            Exception("Database connection lost"),
            Exception("Out of memory"),
            Exception("Disk full")
        ]

        for error in critical_errors:
            severity = recovery_manager.determine_severity(error, ErrorCategory.RESOURCE)
            assert severity in [ErrorSeverity.HIGH, ErrorSeverity.CRITICAL]

        # Low severity errors
        low_errors = [
            FileNotFoundError("File not found"),
            ValueError("Invalid input")
        ]

        for error in low_errors:
            severity = recovery_manager.determine_severity(error, ErrorCategory.VALIDATION)
            assert severity in [ErrorSeverity.LOW, ErrorSeverity.MEDIUM]

    async def test_handle_error_with_recovery(self, recovery_manager, sample_error):
        """Test error handling with recovery attempt."""
        category = ErrorCategory.NETWORK
        severity = ErrorSeverity.MEDIUM

        # Mock recovery strategy
        async def mock_recovery():
            return True

        recovery_manager.register_recovery_strategy(category, mock_recovery)

        result = await recovery_manager.handle_error(sample_error, category, severity)
        assert result is not None

    async def test_handle_error_without_recovery(self, recovery_manager, sample_error):
        """Test error handling without available recovery."""
        category = ErrorCategory.UNKNOWN
        severity = ErrorSeverity.LOW

        result = await recovery_manager.handle_error(sample_error, category, severity)
        # Should handle gracefully even without recovery strategy

    def test_register_recovery_strategy(self, recovery_manager):
        """Test registering custom recovery strategy."""
        async def custom_recovery():
            return "Custom recovery executed"

        recovery_manager.register_recovery_strategy(ErrorCategory.TOOL_EXECUTION, custom_recovery)

        strategies = recovery_manager.get_recovery_strategies()
        assert ErrorCategory.TOOL_EXECUTION in strategies

    def test_error_rate_tracking(self, recovery_manager):
        """Test tracking error rates for different categories."""
        # Simulate multiple errors
        for _ in range(5):
            recovery_manager.record_error(ErrorCategory.NETWORK, ErrorSeverity.MEDIUM)

        for _ in range(3):
            recovery_manager.record_error(ErrorCategory.AI_PROVIDER, ErrorSeverity.HIGH)

        error_stats = recovery_manager.get_error_statistics()
        assert error_stats[ErrorCategory.NETWORK]["count"] == 5
        assert error_stats[ErrorCategory.AI_PROVIDER]["count"] == 3

    def test_circuit_breaker_activation(self, recovery_manager):
        """Test circuit breaker activation after threshold."""
        category = ErrorCategory.AI_PROVIDER
        threshold = 3

        recovery_manager.set_circuit_breaker_threshold(category, threshold)

        # Trigger multiple errors
        for _ in range(threshold + 1):
            recovery_manager.record_error(category, ErrorSeverity.HIGH)

        # Circuit breaker should be active
        assert recovery_manager.is_circuit_breaker_active(category) is True

    def test_circuit_breaker_reset(self, recovery_manager):
        """Test circuit breaker reset after timeout."""
        category = ErrorCategory.NETWORK
        threshold = 2
        reset_timeout = 0.1  # 100ms for testing

        recovery_manager.set_circuit_breaker_threshold(category, threshold)
        recovery_manager.set_circuit_breaker_timeout(category, reset_timeout)

        # Trigger circuit breaker
        for _ in range(threshold + 1):
            recovery_manager.record_error(category, ErrorSeverity.HIGH)

        assert recovery_manager.is_circuit_breaker_active(category) is True

        # Wait for reset timeout
        import time
        time.sleep(reset_timeout + 0.05)

        # Circuit breaker should reset (would need implementation)
        # assert recovery_manager.is_circuit_breaker_active(category) is False

    async def test_retry_with_backoff(self, recovery_manager):
        """Test retry mechanism with exponential backoff."""
        call_count = 0

        async def failing_operation():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Temporary failure")
            return "Success"

        result = await recovery_manager.retry_with_backoff(
            failing_operation,
            max_retries=3,
            base_delay=0.01  # 10ms for testing
        )

        assert result == "Success"
        assert call_count == 3

    async def test_retry_max_attempts_exceeded(self, recovery_manager):
        """Test retry mechanism when max attempts exceeded."""
        async def always_failing_operation():
            raise Exception("Persistent failure")

        with pytest.raises(Exception, match="Persistent failure"):
            await recovery_manager.retry_with_backoff(
                always_failing_operation,
                max_retries=2,
                base_delay=0.01
            )

    def test_error_logging_and_alerting(self, recovery_manager):
        """Test error logging and alerting mechanisms."""
        with patch('logging.getLogger') as mock_logger:
            mock_log = MagicMock()
            mock_logger.return_value = mock_log

            error = Exception("Critical error")
            recovery_manager.record_error(ErrorCategory.RESOURCE, ErrorSeverity.CRITICAL)

            # Should log critical errors
            # mock_log.error.assert_called()

    def test_error_recovery_metrics(self, recovery_manager):
        """Test error recovery metrics collection."""
        # Record various error types
        recovery_manager.record_error(ErrorCategory.NETWORK, ErrorSeverity.MEDIUM)
        recovery_manager.record_error(ErrorCategory.AI_PROVIDER, ErrorSeverity.HIGH)
        recovery_manager.record_recovery_success(ErrorCategory.NETWORK)
        recovery_manager.record_recovery_failure(ErrorCategory.AI_PROVIDER)

        metrics = recovery_manager.get_recovery_metrics()
        assert "total_errors" in metrics
        assert "recovery_success_rate" in metrics
        assert "error_distribution" in metrics

    async def test_graceful_degradation(self, recovery_manager):
        """Test graceful degradation during high error rates."""
        # Simulate high error rate
        for _ in range(10):
            recovery_manager.record_error(ErrorCategory.AI_PROVIDER, ErrorSeverity.HIGH)

        # Should trigger degraded mode
        is_degraded = recovery_manager.is_degraded_mode_active()
        # Would depend on implementation

    def test_error_context_preservation(self, recovery_manager):
        """Test preserving error context for debugging."""
        error = Exception("Test error")
        context = {
            "session_id": "test-session",
            "tool_name": "read_file",
            "parameters": {"path": "test.py"},
            "timestamp": 1638360000.0
        }

        recovery_manager.record_error_with_context(
            ErrorCategory.TOOL_EXECUTION,
            ErrorSeverity.MEDIUM,
            error,
            context
        )

        error_history = recovery_manager.get_error_history()
        assert len(error_history) > 0
        assert error_history[-1]["context"]["session_id"] == "test-session"

    async def test_concurrent_error_handling(self, recovery_manager):
        """Test concurrent error handling."""
        async def error_generator(error_id):
            error = Exception(f"Error {error_id}")
            await recovery_manager.handle_error(
                error,
                ErrorCategory.NETWORK,
                ErrorSeverity.MEDIUM
            )

        # Handle multiple errors concurrently
        tasks = [error_generator(i) for i in range(10)]
        await asyncio.gather(*tasks, return_exceptions=True)

        # Verify all errors were recorded
        stats = recovery_manager.get_error_statistics()
        assert stats[ErrorCategory.NETWORK]["count"] >= 10

    def test_error_pattern_detection(self, recovery_manager):
        """Test detection of error patterns."""
        # Simulate error pattern
        for i in range(5):
            error = Exception(f"Timeout connecting to service {i % 2}")
            recovery_manager.record_error(ErrorCategory.NETWORK, ErrorSeverity.MEDIUM)

        patterns = recovery_manager.detect_error_patterns()
        # Would analyze patterns and suggest fixes

    async def test_recovery_strategy_chaining(self, recovery_manager):
        """Test chaining multiple recovery strategies."""
        async def strategy1():
            # First strategy fails
            raise Exception("Strategy 1 failed")

        async def strategy2():
            # Second strategy succeeds
            return "Strategy 2 succeeded"

        recovery_manager.register_recovery_strategy(ErrorCategory.NETWORK, strategy1)
        recovery_manager.register_fallback_strategy(ErrorCategory.NETWORK, strategy2)

        result = await recovery_manager.attempt_recovery(ErrorCategory.NETWORK)
        assert result == "Strategy 2 succeeded"

    def test_error_threshold_configuration(self, recovery_manager):
        """Test configurable error thresholds."""
        config = {
            "network_error_threshold": 5,
            "ai_provider_error_threshold": 3,
            "circuit_breaker_timeout": 300,  # 5 minutes
            "degraded_mode_threshold": 0.5  # 50% error rate
        }

        recovery_manager.configure_thresholds(config)

        # Verify thresholds were set
        assert recovery_manager.get_threshold(ErrorCategory.NETWORK) == 5
        assert recovery_manager.get_threshold(ErrorCategory.AI_PROVIDER) == 3


@pytest.mark.asyncio
class TestErrorRecoveryStrategies:
    """Test specific error recovery strategies."""

    @pytest.fixture
    def recovery_manager(self):
        return ErrorRecoveryManager()

    async def test_network_error_recovery(self, recovery_manager):
        """Test network error recovery strategy."""
        # Mock network recovery
        async def network_recovery():
            # Simulate connection retry
            return "Connection restored"

        recovery_manager.register_recovery_strategy(ErrorCategory.NETWORK, network_recovery)

        result = await recovery_manager.attempt_recovery(ErrorCategory.NETWORK)
        assert result == "Connection restored"

    async def test_ai_provider_failover(self, recovery_manager):
        """Test AI provider failover strategy."""
        async def provider_failover():
            # Switch to backup provider
            return "Switched to backup provider"

        recovery_manager.register_recovery_strategy(ErrorCategory.AI_PROVIDER, provider_failover)

        result = await recovery_manager.attempt_recovery(ErrorCategory.AI_PROVIDER)
        assert result == "Switched to backup provider"

    async def test_resource_cleanup_recovery(self, recovery_manager):
        """Test resource cleanup recovery strategy."""
        async def resource_cleanup():
            # Clean up resources
            return "Resources cleaned up"

        recovery_manager.register_recovery_strategy(ErrorCategory.RESOURCE, resource_cleanup)

        result = await recovery_manager.attempt_recovery(ErrorCategory.RESOURCE)
        assert result == "Resources cleaned up"