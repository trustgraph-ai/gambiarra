"""
Circuit breaker pattern implementation.
Provides fault tolerance and automatic recovery for system components.
"""

import asyncio
import logging
import time
from typing import Callable, Any, Dict, Optional, Union
from dataclasses import dataclass
from enum import Enum


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, requests blocked
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""
    failure_threshold: int = 5           # Failures before opening
    success_threshold: int = 3           # Successes to close from half-open
    timeout_seconds: float = 60.0        # Time before trying half-open
    slow_call_threshold: float = 5.0     # Seconds to consider call slow
    slow_call_rate_threshold: float = 0.5  # % of slow calls to trigger
    max_calls_half_open: int = 3         # Max calls in half-open state


@dataclass
class CallResult:
    """Result of a circuit breaker protected call."""
    success: bool
    duration: float
    error: Optional[Exception] = None
    result: Any = None


class CircuitBreakerError(Exception):
    """Raised when circuit breaker is open."""
    pass


class CircuitBreaker:
    """Circuit breaker implementation for fault tolerance."""

    def __init__(self, name: str, config: CircuitBreakerConfig = None):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self.state = CircuitState.CLOSED

        # Counters
        self.failure_count = 0
        self.success_count = 0
        self.slow_call_count = 0
        self.total_calls = 0
        self.half_open_calls = 0

        # Timing
        self.last_failure_time = 0.0
        self.state_changed_time = time.time()

        # Statistics
        self.total_failures = 0
        self.total_successes = 0
        self.total_slow_calls = 0

        self.logger = logging.getLogger(f"circuit_breaker.{name}")

    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute a function protected by the circuit breaker."""
        if not self._can_execute():
            raise CircuitBreakerError(f"Circuit breaker '{self.name}' is OPEN")

        start_time = time.time()

        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)

            duration = time.time() - start_time
            await self._on_success(duration)
            return result

        except Exception as e:
            duration = time.time() - start_time
            await self._on_failure(e, duration)
            raise

    def _can_execute(self) -> bool:
        """Check if calls can be executed."""
        current_time = time.time()

        if self.state == CircuitState.CLOSED:
            return True
        elif self.state == CircuitState.OPEN:
            # Check if timeout has passed
            if current_time - self.last_failure_time >= self.config.timeout_seconds:
                self._transition_to_half_open()
                return True
            return False
        elif self.state == CircuitState.HALF_OPEN:
            return self.half_open_calls < self.config.max_calls_half_open

        return False

    async def _on_success(self, duration: float) -> None:
        """Handle successful call."""
        self.success_count += 1
        self.total_successes += 1
        self.total_calls += 1

        # Check for slow call
        if duration >= self.config.slow_call_threshold:
            self.slow_call_count += 1
            self.total_slow_calls += 1

        if self.state == CircuitState.HALF_OPEN:
            self.half_open_calls += 1

            # Check if we should close the circuit
            if self.success_count >= self.config.success_threshold:
                self._transition_to_closed()

        elif self.state == CircuitState.CLOSED:
            # Reset failure count on success
            self.failure_count = 0

            # Check slow call rate
            if self.total_calls >= 10:  # Minimum sample size
                slow_rate = self.slow_call_count / min(self.total_calls, 100)
                if slow_rate >= self.config.slow_call_rate_threshold:
                    await self._transition_to_open("High slow call rate")

    async def _on_failure(self, error: Exception, duration: float) -> None:
        """Handle failed call."""
        self.failure_count += 1
        self.total_failures += 1
        self.total_calls += 1
        self.last_failure_time = time.time()

        # Check for slow call
        if duration >= self.config.slow_call_threshold:
            self.slow_call_count += 1
            self.total_slow_calls += 1

        if self.state == CircuitState.HALF_OPEN:
            # Any failure in half-open goes back to open
            await self._transition_to_open(f"Failure in half-open: {error}")

        elif self.state == CircuitState.CLOSED:
            # Check if we should open the circuit
            if self.failure_count >= self.config.failure_threshold:
                await self._transition_to_open(f"Failure threshold reached: {error}")

    def _transition_to_closed(self) -> None:
        """Transition to closed state."""
        old_state = self.state
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.slow_call_count = 0
        self.half_open_calls = 0
        self.total_calls = 0
        self.state_changed_time = time.time()

        self.logger.info(f"Circuit breaker transitioned: {old_state.value} -> {self.state.value}")

    async def _transition_to_open(self, reason: str) -> None:
        """Transition to open state."""
        old_state = self.state
        self.state = CircuitState.OPEN
        self.failure_count = 0
        self.success_count = 0
        self.slow_call_count = 0
        self.half_open_calls = 0
        self.total_calls = 0
        self.state_changed_time = time.time()

        self.logger.warning(f"Circuit breaker OPENED: {reason}")

        # Publish circuit breaker event
        from ..events.bus import publish_event
        await publish_event(
            event_type="circuit_breaker.opened",
            data={
                "circuit_name": self.name,
                "reason": reason,
                "failure_count": self.total_failures
            },
            source="circuit_breaker"
        )

    def _transition_to_half_open(self) -> None:
        """Transition to half-open state."""
        old_state = self.state
        self.state = CircuitState.HALF_OPEN
        self.failure_count = 0
        self.success_count = 0
        self.slow_call_count = 0
        self.half_open_calls = 0
        self.total_calls = 0
        self.state_changed_time = time.time()

        self.logger.info(f"Circuit breaker transitioned: {old_state.value} -> {self.state.value}")

    def get_stats(self) -> Dict[str, Any]:
        """Get circuit breaker statistics."""
        current_time = time.time()
        uptime = current_time - self.state_changed_time

        return {
            "name": self.name,
            "state": self.state.value,
            "uptime_seconds": uptime,
            "current_counters": {
                "failure_count": self.failure_count,
                "success_count": self.success_count,
                "slow_call_count": self.slow_call_count,
                "total_calls": self.total_calls
            },
            "lifetime_stats": {
                "total_failures": self.total_failures,
                "total_successes": self.total_successes,
                "total_slow_calls": self.total_slow_calls
            },
            "config": {
                "failure_threshold": self.config.failure_threshold,
                "timeout_seconds": self.config.timeout_seconds,
                "slow_call_threshold": self.config.slow_call_threshold
            }
        }

    def reset(self) -> None:
        """Reset circuit breaker to closed state."""
        self._transition_to_closed()
        self.total_failures = 0
        self.total_successes = 0
        self.total_slow_calls = 0
        self.logger.info(f"Circuit breaker '{self.name}' manually reset")


class CircuitBreakerRegistry:
    """Registry for managing multiple circuit breakers."""

    def __init__(self):
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        self.logger = logging.getLogger(__name__)

    def create_circuit_breaker(self,
                             name: str,
                             config: CircuitBreakerConfig = None) -> CircuitBreaker:
        """Create and register a new circuit breaker."""
        if name in self.circuit_breakers:
            return self.circuit_breakers[name]

        circuit_breaker = CircuitBreaker(name, config)
        self.circuit_breakers[name] = circuit_breaker

        self.logger.info(f"Created circuit breaker: {name}")
        return circuit_breaker

    def get_circuit_breaker(self, name: str) -> Optional[CircuitBreaker]:
        """Get circuit breaker by name."""
        return self.circuit_breakers.get(name)

    def list_circuit_breakers(self) -> Dict[str, Dict[str, Any]]:
        """List all circuit breakers with their stats."""
        return {
            name: cb.get_stats()
            for name, cb in self.circuit_breakers.items()
        }

    def reset_all(self) -> None:
        """Reset all circuit breakers."""
        for cb in self.circuit_breakers.values():
            cb.reset()
        self.logger.info("Reset all circuit breakers")

    def get_global_stats(self) -> Dict[str, Any]:
        """Get global circuit breaker statistics."""
        total_breakers = len(self.circuit_breakers)
        states = {}

        for cb in self.circuit_breakers.values():
            state = cb.state.value
            states[state] = states.get(state, 0) + 1

        return {
            "total_circuit_breakers": total_breakers,
            "states": states,
            "healthy_percentage": (states.get("closed", 0) / total_breakers * 100) if total_breakers > 0 else 0
        }


# Global registry
_circuit_breaker_registry = CircuitBreakerRegistry()


def get_circuit_breaker_registry() -> CircuitBreakerRegistry:
    """Get the global circuit breaker registry."""
    return _circuit_breaker_registry


def circuit_breaker(name: str, config: CircuitBreakerConfig = None):
    """Decorator for applying circuit breaker to functions."""
    def decorator(func):
        cb = _circuit_breaker_registry.create_circuit_breaker(name, config)

        async def async_wrapper(*args, **kwargs):
            return await cb.call(func, *args, **kwargs)

        def sync_wrapper(*args, **kwargs):
            # For sync functions, we need to handle this differently
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                return loop.run_until_complete(cb.call(func, *args, **kwargs))
            except RuntimeError:
                # No event loop running, create one
                return asyncio.run(cb.call(func, *args, **kwargs))

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator