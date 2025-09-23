"""
Advanced retry mechanisms with exponential backoff and jitter.
Provides resilient operation for transient failures.
"""

import asyncio
import logging
import random
import time
from typing import Callable, Any, Type, Union, List, Optional
from dataclasses import dataclass
from enum import Enum


class RetryStrategy(Enum):
    """Retry strategy types."""
    FIXED_DELAY = "fixed_delay"
    EXPONENTIAL_BACKOFF = "exponential_backoff"
    LINEAR_BACKOFF = "linear_backoff"


@dataclass
class RetryConfig:
    """Configuration for retry mechanism."""
    max_attempts: int = 3
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL_BACKOFF
    base_delay: float = 1.0              # Base delay in seconds
    max_delay: float = 60.0              # Maximum delay in seconds
    backoff_multiplier: float = 2.0      # Multiplier for exponential backoff
    jitter: bool = True                  # Add random jitter to delays
    jitter_range: float = 0.1            # Jitter range (±10% by default)

    # Exception handling
    retryable_exceptions: List[Type[Exception]] = None
    non_retryable_exceptions: List[Type[Exception]] = None

    # Conditions
    retry_condition: Optional[Callable[[Exception], bool]] = None


@dataclass
class RetryResult:
    """Result of retry operation."""
    success: bool
    attempts: int
    total_duration: float
    last_exception: Optional[Exception] = None
    result: Any = None


class RetryExhaustedError(Exception):
    """Raised when all retry attempts are exhausted."""

    def __init__(self, attempts: int, last_exception: Exception):
        self.attempts = attempts
        self.last_exception = last_exception
        super().__init__(f"Retry exhausted after {attempts} attempts: {last_exception}")


class RetryMechanism:
    """Advanced retry mechanism with configurable strategies."""

    def __init__(self, name: str, config: RetryConfig = None):
        self.name = name
        self.config = config or RetryConfig()
        self.logger = logging.getLogger(f"retry.{name}")

        # Statistics
        self.total_attempts = 0
        self.total_successes = 0
        self.total_failures = 0

    async def execute(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with retry logic."""
        start_time = time.time()
        last_exception = None

        for attempt in range(1, self.config.max_attempts + 1):
            self.total_attempts += 1

            try:
                self.logger.debug(f"Attempt {attempt}/{self.config.max_attempts}")

                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)

                self.total_successes += 1
                total_duration = time.time() - start_time

                if attempt > 1:
                    self.logger.info(f"Succeeded on attempt {attempt}/{self.config.max_attempts}")

                return result

            except Exception as e:
                last_exception = e
                self.logger.warning(f"Attempt {attempt} failed: {e}")

                # Check if this exception should be retried
                if not self._should_retry(e, attempt):
                    self.total_failures += 1
                    raise e

                # Don't sleep after the last attempt
                if attempt < self.config.max_attempts:
                    delay = self._calculate_delay(attempt)
                    self.logger.debug(f"Sleeping for {delay:.2f} seconds before retry")
                    await asyncio.sleep(delay)

        # All attempts exhausted
        self.total_failures += 1
        total_duration = time.time() - start_time

        self.logger.error(f"All {self.config.max_attempts} attempts failed")
        raise RetryExhaustedError(self.config.max_attempts, last_exception)

    def _should_retry(self, exception: Exception, attempt: int) -> bool:
        """Determine if an exception should trigger a retry."""
        # Check if we have more attempts left
        if attempt >= self.config.max_attempts:
            return False

        # Check non-retryable exceptions
        if self.config.non_retryable_exceptions:
            for exc_type in self.config.non_retryable_exceptions:
                if isinstance(exception, exc_type):
                    self.logger.debug(f"Non-retryable exception: {type(exception).__name__}")
                    return False

        # Check retryable exceptions
        if self.config.retryable_exceptions:
            for exc_type in self.config.retryable_exceptions:
                if isinstance(exception, exc_type):
                    return True
            # If retryable list is specified, only retry those exceptions
            return False

        # Check custom retry condition
        if self.config.retry_condition:
            return self.config.retry_condition(exception)

        # Default: retry all exceptions
        return True

    def _calculate_delay(self, attempt: int) -> float:
        """Calculate delay before next retry attempt."""
        if self.config.strategy == RetryStrategy.FIXED_DELAY:
            delay = self.config.base_delay

        elif self.config.strategy == RetryStrategy.EXPONENTIAL_BACKOFF:
            delay = self.config.base_delay * (self.config.backoff_multiplier ** (attempt - 1))

        elif self.config.strategy == RetryStrategy.LINEAR_BACKOFF:
            delay = self.config.base_delay * attempt

        else:
            delay = self.config.base_delay

        # Apply maximum delay limit
        delay = min(delay, self.config.max_delay)

        # Add jitter if enabled
        if self.config.jitter:
            jitter_amount = delay * self.config.jitter_range
            jitter = random.uniform(-jitter_amount, jitter_amount)
            delay = max(0.1, delay + jitter)  # Ensure minimum delay

        return delay

    def get_stats(self) -> dict:
        """Get retry mechanism statistics."""
        success_rate = (self.total_successes / self.total_attempts * 100) if self.total_attempts > 0 else 0

        return {
            "name": self.name,
            "total_attempts": self.total_attempts,
            "total_successes": self.total_successes,
            "total_failures": self.total_failures,
            "success_rate": success_rate,
            "config": {
                "max_attempts": self.config.max_attempts,
                "strategy": self.config.strategy.value,
                "base_delay": self.config.base_delay,
                "max_delay": self.config.max_delay
            }
        }

    def reset_stats(self) -> None:
        """Reset statistics."""
        self.total_attempts = 0
        self.total_successes = 0
        self.total_failures = 0


class RetryRegistry:
    """Registry for managing retry mechanisms."""

    def __init__(self):
        self.retry_mechanisms: dict[str, RetryMechanism] = {}
        self.logger = logging.getLogger(__name__)

    def create_retry_mechanism(self, name: str, config: RetryConfig = None) -> RetryMechanism:
        """Create and register a retry mechanism."""
        if name in self.retry_mechanisms:
            return self.retry_mechanisms[name]

        retry_mechanism = RetryMechanism(name, config)
        self.retry_mechanisms[name] = retry_mechanism

        self.logger.info(f"Created retry mechanism: {name}")
        return retry_mechanism

    def get_retry_mechanism(self, name: str) -> Optional[RetryMechanism]:
        """Get retry mechanism by name."""
        return self.retry_mechanisms.get(name)

    def list_retry_mechanisms(self) -> dict[str, dict]:
        """List all retry mechanisms with their stats."""
        return {
            name: rm.get_stats()
            for name, rm in self.retry_mechanisms.items()
        }

    def reset_all_stats(self) -> None:
        """Reset statistics for all retry mechanisms."""
        for rm in self.retry_mechanisms.values():
            rm.reset_stats()
        self.logger.info("Reset all retry mechanism statistics")


# Global registry
_retry_registry = RetryRegistry()


def get_retry_registry() -> RetryRegistry:
    """Get the global retry registry."""
    return _retry_registry


def retry(name: str, config: RetryConfig = None):
    """Decorator for applying retry logic to functions."""
    def decorator(func):
        rm = _retry_registry.create_retry_mechanism(name, config)

        async def async_wrapper(*args, **kwargs):
            return await rm.execute(func, *args, **kwargs)

        def sync_wrapper(*args, **kwargs):
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                return loop.run_until_complete(rm.execute(func, *args, **kwargs))
            except RuntimeError:
                return asyncio.run(rm.execute(func, *args, **kwargs))

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


# Common retry configurations
class CommonRetryConfigs:
    """Pre-defined retry configurations for common scenarios."""

    @staticmethod
    def network_request() -> RetryConfig:
        """Configuration for network requests."""
        return RetryConfig(
            max_attempts=3,
            strategy=RetryStrategy.EXPONENTIAL_BACKOFF,
            base_delay=1.0,
            max_delay=30.0,
            retryable_exceptions=[
                ConnectionError,
                TimeoutError,
                OSError
            ]
        )

    @staticmethod
    def database_operation() -> RetryConfig:
        """Configuration for database operations."""
        return RetryConfig(
            max_attempts=5,
            strategy=RetryStrategy.EXPONENTIAL_BACKOFF,
            base_delay=0.5,
            max_delay=10.0,
            backoff_multiplier=1.5
        )

    @staticmethod
    def api_call() -> RetryConfig:
        """Configuration for API calls."""
        return RetryConfig(
            max_attempts=3,
            strategy=RetryStrategy.EXPONENTIAL_BACKOFF,
            base_delay=2.0,
            max_delay=60.0,
            jitter=True
        )

    @staticmethod
    def file_operation() -> RetryConfig:
        """Configuration for file operations."""
        return RetryConfig(
            max_attempts=3,
            strategy=RetryStrategy.FIXED_DELAY,
            base_delay=0.1,
            retryable_exceptions=[
                PermissionError,
                OSError
            ]
        )