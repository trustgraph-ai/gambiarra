"""
Rate Limiting System with Token Bucket Algorithm.

Prevents runaway costs by limiting API requests and tracking token usage.
Provides per-session, per-user, and global rate limits.

Key features:
- Token bucket algorithm for smooth rate limiting
- Multiple limit levels (session, user, global)
- Cost tracking with budgets
- Automatic refill
- Warning thresholds
"""

import time
import logging
from typing import Dict, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum
import threading

logger = logging.getLogger(__name__)


class LimitLevel(Enum):
    """Level at which rate limit applies."""
    SESSION = "session"
    USER = "user"
    GLOBAL = "global"


class LimitType(Enum):
    """Type of rate limit."""
    REQUESTS_PER_MINUTE = "requests_per_minute"
    TOKENS_PER_HOUR = "tokens_per_hour"
    COST_PER_DAY = "cost_per_day"


@dataclass
class TokenBucket:
    """
    Token bucket for rate limiting.

    Tokens are added at a fixed rate. Each request consumes tokens.
    If bucket is empty, request is denied.
    """

    capacity: float  # Maximum tokens
    refill_rate: float  # Tokens added per second
    tokens: float = field(default=0.0)  # Current tokens
    last_refill: float = field(default_factory=time.time)

    def __post_init__(self):
        """Initialize with full bucket."""
        if self.tokens == 0.0:
            self.tokens = self.capacity

    def consume(self, tokens: float = 1.0) -> bool:
        """
        Try to consume tokens from bucket.

        Args:
            tokens: Number of tokens to consume

        Returns:
            True if tokens were consumed, False if insufficient
        """
        # Refill bucket
        self._refill()

        if self.tokens >= tokens:
            self.tokens -= tokens
            return True

        return False

    def _refill(self) -> None:
        """Refill bucket based on elapsed time."""
        now = time.time()
        elapsed = now - self.last_refill

        # Add tokens based on refill rate
        tokens_to_add = elapsed * self.refill_rate
        self.tokens = min(self.capacity, self.tokens + tokens_to_add)

        self.last_refill = now

    def get_wait_time(self, tokens: float = 1.0) -> float:
        """
        Get time to wait before tokens are available.

        Args:
            tokens: Number of tokens needed

        Returns:
            Seconds to wait (0 if available now)
        """
        self._refill()

        if self.tokens >= tokens:
            return 0.0

        tokens_needed = tokens - self.tokens
        return tokens_needed / self.refill_rate

    def get_status(self) -> Dict[str, Any]:
        """Get bucket status."""
        self._refill()

        return {
            "capacity": self.capacity,
            "tokens": self.tokens,
            "refill_rate": self.refill_rate,
            "utilization": (self.capacity - self.tokens) / self.capacity
        }


@dataclass
class RateLimit:
    """Configuration for a rate limit."""

    limit_type: LimitType
    limit_level: LimitLevel
    capacity: float
    refill_period_seconds: float

    # Warning threshold (0-1)
    warning_threshold: float = 0.8

    # Bucket for this limit
    bucket: Optional[TokenBucket] = None

    def __post_init__(self):
        """Initialize token bucket."""
        if self.bucket is None:
            refill_rate = self.capacity / self.refill_period_seconds
            self.bucket = TokenBucket(
                capacity=self.capacity,
                refill_rate=refill_rate
            )

    def check(self, cost: float = 1.0) -> Tuple[bool, Optional[float]]:
        """
        Check if request is allowed.

        Args:
            cost: Cost of the request (tokens)

        Returns:
            Tuple of (allowed, wait_time)
        """
        if self.bucket.consume(cost):
            return True, None

        wait_time = self.bucket.get_wait_time(cost)
        return False, wait_time

    def is_warning(self) -> bool:
        """Check if usage is above warning threshold."""
        status = self.bucket.get_status()
        return status["utilization"] >= self.warning_threshold


@dataclass
class CostTracker:
    """
    Tracks costs for API usage.

    Accumulates costs and checks against budgets.
    """

    daily_budget: Optional[float] = None
    weekly_budget: Optional[float] = None
    monthly_budget: Optional[float] = None

    # Usage tracking
    daily_cost: float = 0.0
    weekly_cost: float = 0.0
    monthly_cost: float = 0.0

    # Reset times
    last_daily_reset: float = field(default_factory=time.time)
    last_weekly_reset: float = field(default_factory=time.time)
    last_monthly_reset: float = field(default_factory=time.time)

    def add_cost(self, cost: float) -> None:
        """
        Add cost to tracker.

        Args:
            cost: Cost to add (in dollars or credits)
        """
        self._reset_if_needed()

        self.daily_cost += cost
        self.weekly_cost += cost
        self.monthly_cost += cost

    def check_budget(self) -> Tuple[bool, Optional[str]]:
        """
        Check if within budget.

        Returns:
            Tuple of (within_budget, reason_if_exceeded)
        """
        self._reset_if_needed()

        if self.daily_budget and self.daily_cost >= self.daily_budget:
            return False, f"Daily budget exceeded ({self.daily_cost:.2f} >= {self.daily_budget:.2f})"

        if self.weekly_budget and self.weekly_cost >= self.weekly_budget:
            return False, f"Weekly budget exceeded ({self.weekly_cost:.2f} >= {self.weekly_budget:.2f})"

        if self.monthly_budget and self.monthly_cost >= self.monthly_budget:
            return False, f"Monthly budget exceeded ({self.monthly_cost:.2f} >= {self.monthly_budget:.2f})"

        return True, None

    def is_warning(self, threshold: float = 0.8) -> Tuple[bool, Optional[str]]:
        """
        Check if approaching budget limit.

        Args:
            threshold: Warning threshold (0-1)

        Returns:
            Tuple of (is_warning, message)
        """
        self._reset_if_needed()

        if self.daily_budget and self.daily_cost >= self.daily_budget * threshold:
            return True, f"Daily budget at {(self.daily_cost / self.daily_budget * 100):.1f}%"

        if self.weekly_budget and self.weekly_cost >= self.weekly_budget * threshold:
            return True, f"Weekly budget at {(self.weekly_cost / self.weekly_budget * 100):.1f}%"

        if self.monthly_budget and self.monthly_cost >= self.monthly_budget * threshold:
            return True, f"Monthly budget at {(self.monthly_cost / self.monthly_budget * 100):.1f}%"

        return False, None

    def _reset_if_needed(self) -> None:
        """Reset counters if time periods have elapsed."""
        now = time.time()

        # Daily reset (24 hours)
        if now - self.last_daily_reset >= 86400:
            self.daily_cost = 0.0
            self.last_daily_reset = now

        # Weekly reset (7 days)
        if now - self.last_weekly_reset >= 604800:
            self.weekly_cost = 0.0
            self.last_weekly_reset = now

        # Monthly reset (30 days)
        if now - self.last_monthly_reset >= 2592000:
            self.monthly_cost = 0.0
            self.last_monthly_reset = now

    def get_status(self) -> Dict[str, Any]:
        """Get cost tracking status."""
        self._reset_if_needed()

        return {
            "daily": {
                "cost": self.daily_cost,
                "budget": self.daily_budget,
                "remaining": self.daily_budget - self.daily_cost if self.daily_budget else None,
                "utilization": self.daily_cost / self.daily_budget if self.daily_budget else None
            },
            "weekly": {
                "cost": self.weekly_cost,
                "budget": self.weekly_budget,
                "remaining": self.weekly_budget - self.weekly_cost if self.weekly_budget else None,
                "utilization": self.weekly_cost / self.weekly_budget if self.weekly_budget else None
            },
            "monthly": {
                "cost": self.monthly_cost,
                "budget": self.monthly_budget,
                "remaining": self.monthly_budget - self.monthly_cost if self.monthly_budget else None,
                "utilization": self.monthly_cost / self.monthly_budget if self.monthly_budget else None
            }
        }


class RateLimiter:
    """
    Multi-level rate limiter with cost tracking.

    Enforces rate limits at session, user, and global levels.
    Tracks costs and enforces budgets.
    """

    def __init__(
        self,
        # Session limits (per session)
        session_requests_per_minute: int = 60,
        session_tokens_per_hour: int = 100000,

        # User limits (across all sessions)
        user_requests_per_minute: int = 120,
        user_tokens_per_hour: int = 500000,

        # Global limits (across all users)
        global_requests_per_minute: int = 1000,
        global_tokens_per_hour: int = 5000000,

        # Cost budgets (optional)
        session_daily_budget: Optional[float] = None,
        user_daily_budget: Optional[float] = None,
        global_daily_budget: Optional[float] = None
    ):
        """
        Initialize rate limiter.

        Args:
            session_requests_per_minute: Max requests per minute per session
            session_tokens_per_hour: Max tokens per hour per session
            user_requests_per_minute: Max requests per minute per user
            user_tokens_per_hour: Max tokens per hour per user
            global_requests_per_minute: Max requests per minute globally
            global_tokens_per_hour: Max tokens per hour globally
            session_daily_budget: Daily cost budget per session
            user_daily_budget: Daily cost budget per user
            global_daily_budget: Daily cost budget globally
        """
        # Session limits
        self._session_limits: Dict[str, Dict[str, RateLimit]] = {}

        # User limits
        self._user_limits: Dict[str, Dict[str, RateLimit]] = {}

        # Global limits
        self._global_limits: Dict[str, RateLimit] = {
            "requests": RateLimit(
                limit_type=LimitType.REQUESTS_PER_MINUTE,
                limit_level=LimitLevel.GLOBAL,
                capacity=global_requests_per_minute,
                refill_period_seconds=60
            ),
            "tokens": RateLimit(
                limit_type=LimitType.TOKENS_PER_HOUR,
                limit_level=LimitLevel.GLOBAL,
                capacity=global_tokens_per_hour,
                refill_period_seconds=3600
            )
        }

        # Cost trackers
        self._session_costs: Dict[str, CostTracker] = {}
        self._user_costs: Dict[str, CostTracker] = {}
        self._global_cost = CostTracker(daily_budget=global_daily_budget)

        # Configuration
        self._config = {
            "session_requests_per_minute": session_requests_per_minute,
            "session_tokens_per_hour": session_tokens_per_hour,
            "user_requests_per_minute": user_requests_per_minute,
            "user_tokens_per_hour": user_tokens_per_hour,
            "session_daily_budget": session_daily_budget,
            "user_daily_budget": user_daily_budget
        }

        # Thread lock for concurrent access
        self._lock = threading.Lock()

        logger.info("Initialized RateLimiter with global limits")

    def check_request(
        self,
        session_id: str,
        user_id: Optional[str] = None,
        token_count: int = 0,
        estimated_cost: float = 0.0
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if request is allowed under rate limits.

        Args:
            session_id: Session identifier
            user_id: Optional user identifier
            token_count: Number of tokens for this request
            estimated_cost: Estimated cost in dollars

        Returns:
            Tuple of (allowed, reason_if_denied)
        """
        with self._lock:
            # Check global limits first
            allowed, reason = self._check_global_limits(token_count)
            if not allowed:
                return False, f"Global limit: {reason}"

            # Check user limits
            if user_id:
                allowed, reason = self._check_user_limits(user_id, token_count)
                if not allowed:
                    return False, f"User limit: {reason}"

            # Check session limits
            allowed, reason = self._check_session_limits(session_id, token_count)
            if not allowed:
                return False, f"Session limit: {reason}"

            # Check budgets
            allowed, reason = self._check_budgets(session_id, user_id, estimated_cost)
            if not allowed:
                return False, f"Budget limit: {reason}"

            return True, None

    def record_usage(
        self,
        session_id: str,
        user_id: Optional[str] = None,
        token_count: int = 0,
        actual_cost: float = 0.0
    ) -> None:
        """
        Record actual usage after request completion.

        Args:
            session_id: Session identifier
            user_id: Optional user identifier
            token_count: Actual tokens used
            actual_cost: Actual cost incurred
        """
        with self._lock:
            # Record costs
            if actual_cost > 0:
                self._get_session_cost_tracker(session_id).add_cost(actual_cost)

                if user_id:
                    self._get_user_cost_tracker(user_id).add_cost(actual_cost)

                self._global_cost.add_cost(actual_cost)

            # Check for warnings
            self._check_warnings(session_id, user_id)

    def _check_global_limits(self, token_count: int) -> Tuple[bool, Optional[str]]:
        """Check global rate limits."""
        # Check request limit
        allowed, wait_time = self._global_limits["requests"].check(1)
        if not allowed:
            return False, f"Global request limit exceeded (wait {wait_time:.1f}s)"

        # Check token limit
        if token_count > 0:
            allowed, wait_time = self._global_limits["tokens"].check(token_count)
            if not allowed:
                return False, f"Global token limit exceeded (wait {wait_time:.1f}s)"

        return True, None

    def _check_user_limits(self, user_id: str, token_count: int) -> Tuple[bool, Optional[str]]:
        """Check user-level rate limits."""
        if user_id not in self._user_limits:
            self._user_limits[user_id] = {
                "requests": RateLimit(
                    limit_type=LimitType.REQUESTS_PER_MINUTE,
                    limit_level=LimitLevel.USER,
                    capacity=self._config["user_requests_per_minute"],
                    refill_period_seconds=60
                ),
                "tokens": RateLimit(
                    limit_type=LimitType.TOKENS_PER_HOUR,
                    limit_level=LimitLevel.USER,
                    capacity=self._config["user_tokens_per_hour"],
                    refill_period_seconds=3600
                )
            }

        # Check request limit
        allowed, wait_time = self._user_limits[user_id]["requests"].check(1)
        if not allowed:
            return False, f"User request limit exceeded (wait {wait_time:.1f}s)"

        # Check token limit
        if token_count > 0:
            allowed, wait_time = self._user_limits[user_id]["tokens"].check(token_count)
            if not allowed:
                return False, f"User token limit exceeded (wait {wait_time:.1f}s)"

        return True, None

    def _check_session_limits(self, session_id: str, token_count: int) -> Tuple[bool, Optional[str]]:
        """Check session-level rate limits."""
        if session_id not in self._session_limits:
            self._session_limits[session_id] = {
                "requests": RateLimit(
                    limit_type=LimitType.REQUESTS_PER_MINUTE,
                    limit_level=LimitLevel.SESSION,
                    capacity=self._config["session_requests_per_minute"],
                    refill_period_seconds=60
                ),
                "tokens": RateLimit(
                    limit_type=LimitType.TOKENS_PER_HOUR,
                    limit_level=LimitLevel.SESSION,
                    capacity=self._config["session_tokens_per_hour"],
                    refill_period_seconds=3600
                )
            }

        # Check request limit
        allowed, wait_time = self._session_limits[session_id]["requests"].check(1)
        if not allowed:
            return False, f"Session request limit exceeded (wait {wait_time:.1f}s)"

        # Check token limit
        if token_count > 0:
            allowed, wait_time = self._session_limits[session_id]["tokens"].check(token_count)
            if not allowed:
                return False, f"Session token limit exceeded (wait {wait_time:.1f}s)"

        return True, None

    def _check_budgets(
        self,
        session_id: str,
        user_id: Optional[str],
        estimated_cost: float
    ) -> Tuple[bool, Optional[str]]:
        """Check cost budgets."""
        # Check global budget
        within_budget, reason = self._global_cost.check_budget()
        if not within_budget:
            return False, f"Global: {reason}"

        # Check user budget
        if user_id:
            tracker = self._get_user_cost_tracker(user_id)
            within_budget, reason = tracker.check_budget()
            if not within_budget:
                return False, f"User: {reason}"

        # Check session budget
        tracker = self._get_session_cost_tracker(session_id)
        within_budget, reason = tracker.check_budget()
        if not within_budget:
            return False, f"Session: {reason}"

        return True, None

    def _check_warnings(self, session_id: str, user_id: Optional[str]) -> None:
        """Check and log warnings for approaching limits."""
        # Check session limits
        if session_id in self._session_limits:
            for limit_name, limit in self._session_limits[session_id].items():
                if limit.is_warning():
                    logger.warning(
                        f"Session {session_id} approaching {limit_name} limit: "
                        f"{limit.bucket.get_status()['utilization']:.1%}"
                    )

        # Check session budget
        tracker = self._get_session_cost_tracker(session_id)
        is_warning, message = tracker.is_warning()
        if is_warning:
            logger.warning(f"Session {session_id} budget warning: {message}")

    def _get_session_cost_tracker(self, session_id: str) -> CostTracker:
        """Get or create cost tracker for session."""
        if session_id not in self._session_costs:
            self._session_costs[session_id] = CostTracker(
                daily_budget=self._config["session_daily_budget"]
            )
        return self._session_costs[session_id]

    def _get_user_cost_tracker(self, user_id: str) -> CostTracker:
        """Get or create cost tracker for user."""
        if user_id not in self._user_costs:
            self._user_costs[user_id] = CostTracker(
                daily_budget=self._config["user_daily_budget"]
            )
        return self._user_costs[user_id]

    def get_status(
        self,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get rate limiter status.

        Args:
            session_id: Optional session ID for session-specific status
            user_id: Optional user ID for user-specific status

        Returns:
            Status dictionary
        """
        with self._lock:
            status = {
                "global": {
                    "limits": {
                        name: limit.bucket.get_status()
                        for name, limit in self._global_limits.items()
                    },
                    "costs": self._global_cost.get_status()
                }
            }

            if session_id and session_id in self._session_limits:
                status["session"] = {
                    "limits": {
                        name: limit.bucket.get_status()
                        for name, limit in self._session_limits[session_id].items()
                    },
                    "costs": self._get_session_cost_tracker(session_id).get_status()
                }

            if user_id and user_id in self._user_limits:
                status["user"] = {
                    "limits": {
                        name: limit.bucket.get_status()
                        for name, limit in self._user_limits[user_id].items()
                    },
                    "costs": self._get_user_cost_tracker(user_id).get_status()
                }

            return status


# Global instance
_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter() -> RateLimiter:
    """Get global rate limiter instance."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter


def set_rate_limiter(limiter: RateLimiter):
    """Set global rate limiter instance."""
    global _rate_limiter
    _rate_limiter = limiter
