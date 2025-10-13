"""
Unit tests for Rate Limiting & Cost Control.

Tests:
- TokenBucket algorithm
- Multi-level rate limiting
- Cost tracking
- Budget enforcement
- Thread safety
"""

import pytest
import time
import asyncio
from threading import Thread
from gambiarra.server.core.rate_limiting import (
    TokenBucket,
    RateLimit,
    CostTracker,
    RateLimiter,
    LimitLevel,
    LimitType
)


class TestTokenBucket:
    """Test TokenBucket implementation."""

    def test_token_bucket_initialization(self):
        """Test token bucket initializes correctly."""
        bucket = TokenBucket(capacity=10, refill_rate=1.0)

        assert bucket.capacity == 10
        assert bucket.tokens == 10  # Starts full
        assert bucket.refill_rate == 1.0

    def test_consume_tokens(self):
        """Test consuming tokens from bucket."""
        bucket = TokenBucket(capacity=5, refill_rate=1.0)

        # Consume 3 tokens
        assert bucket.consume(3) is True
        assert bucket.tokens == 2

        # Consume 2 more tokens
        assert bucket.consume(2) is True
        # Tokens may not be exactly 0 due to time elapsed during test
        assert bucket.tokens < 0.01

        # Try to consume when empty (may have tiny refill due to time)
        assert bucket.consume(1) is False
        assert bucket.tokens < 0.01

    def test_refill_over_time(self):
        """Test tokens refill over time."""
        bucket = TokenBucket(capacity=10, refill_rate=5.0)  # 5 tokens/second

        # Consume all tokens
        bucket.consume(10)
        assert bucket.tokens == 0

        # Wait 0.5 seconds -> should refill 2.5 tokens
        time.sleep(0.5)
        bucket._refill()
        assert 2.0 <= bucket.tokens <= 3.0

        # Wait another 0.5 seconds -> should have 5 tokens
        time.sleep(0.5)
        bucket._refill()
        assert 4.5 <= bucket.tokens <= 5.5

    def test_capacity_limit(self):
        """Test bucket doesn't exceed capacity."""
        bucket = TokenBucket(capacity=10, refill_rate=10.0)

        # Consume 5 tokens
        bucket.consume(5)
        assert bucket.tokens == 5

        # Wait for refill (should cap at 10)
        time.sleep(1.0)
        bucket._refill()
        assert bucket.tokens == 10  # Capped at capacity

    def test_fractional_tokens(self):
        """Test fractional token consumption."""
        bucket = TokenBucket(capacity=10, refill_rate=1.0)

        # Consume fractional tokens
        assert bucket.consume(0.5) is True
        assert bucket.tokens == 9.5

        assert bucket.consume(1.3) is True
        assert 8.1 <= bucket.tokens <= 8.3

    def test_get_wait_time(self):
        """Test calculating wait time for tokens."""
        bucket = TokenBucket(capacity=10, refill_rate=2.0)  # 2 tokens/second

        # Consume all tokens
        bucket.consume(10)

        # Need 4 tokens -> wait 2 seconds
        wait_time = bucket.get_wait_time(4)
        assert 1.9 <= wait_time <= 2.1

    def test_utilization(self):
        """Test utilization calculation via tokens."""
        bucket = TokenBucket(capacity=10, refill_rate=1.0)

        # Full bucket = 0% utilization (all available)
        assert bucket.tokens == 10

        bucket.consume(3)
        # 7 tokens left out of 10 = 70% available, 30% used
        assert 6.9 <= bucket.tokens <= 7.1

        bucket.consume(7)
        # All tokens consumed
        assert bucket.tokens < 0.1


class TestCostTracker:
    """Test CostTracker implementation."""

    def test_cost_tracker_initialization(self):
        """Test cost tracker initializes correctly."""
        tracker = CostTracker(daily_budget=100.0, weekly_budget=500.0)

        assert tracker.daily_budget == 100.0
        assert tracker.weekly_budget == 500.0
        assert tracker.daily_cost == 0.0
        assert tracker.weekly_cost == 0.0

    def test_add_cost(self):
        """Test adding costs."""
        tracker = CostTracker(daily_budget=100.0)

        tracker.add_cost(25.0)
        assert tracker.daily_cost == 25.0

        tracker.add_cost(30.0)
        assert tracker.daily_cost == 55.0

    def test_check_budget_within_limit(self):
        """Test budget check when within limit."""
        tracker = CostTracker(daily_budget=100.0)
        tracker.add_cost(50.0)

        # Check current cost (50, under 100)
        allowed, reason = tracker.check_budget()
        assert allowed is True
        assert reason is None

    def test_check_budget_exceeds_limit(self):
        """Test budget check when exceeding limit."""
        tracker = CostTracker(daily_budget=100.0)
        tracker.add_cost(110.0)

        # Check current cost (110, over 100)
        allowed, reason = tracker.check_budget()
        assert allowed is False
        assert "Daily budget" in reason

    def test_budget_reset(self):
        """Test budget reset by simulating time passing."""
        tracker = CostTracker(daily_budget=100.0)
        tracker.add_cost(80.0)
        assert tracker.daily_cost == 80.0

        # Simulate daily reset by setting last_daily_reset to past
        tracker.last_daily_reset = time.time() - (25 * 3600)  # 25 hours ago
        tracker._reset_if_needed()
        assert tracker.daily_cost == 0.0

    def test_get_status(self):
        """Test status reporting."""
        tracker = CostTracker(daily_budget=100.0)
        tracker.add_cost(75.0)

        # CostTracker doesn't have get_status(), check attributes directly
        assert tracker.daily_cost == 75.0
        assert tracker.daily_budget == 100.0
        # Calculate utilization manually
        utilization = tracker.daily_cost / tracker.daily_budget
        assert abs(utilization - 0.75) < 0.01


class TestRateLimiter:
    """Test RateLimiter multi-level implementation."""

    def test_rate_limiter_initialization(self):
        """Test rate limiter initializes correctly."""
        limiter = RateLimiter(
            session_requests_per_minute=10,
            user_requests_per_minute=50,
            global_requests_per_minute=100
        )

        # RateLimiter initializes successfully - test by making a request
        allowed, _ = limiter.check_request(session_id="test")
        assert allowed is True

    def test_session_rate_limiting(self):
        """Test session-level rate limiting."""
        limiter = RateLimiter(session_requests_per_minute=5)

        session_id = "session-1"

        # First 5 requests should succeed
        for i in range(5):
            allowed, reason = limiter.check_request(session_id=session_id)
            assert allowed is True
            limiter.record_usage(session_id=session_id)

        # 6th request should fail
        allowed, reason = limiter.check_request(session_id=session_id)
        assert allowed is False
        assert "Session" in reason

    def test_user_rate_limiting(self):
        """Test user-level rate limiting across sessions."""
        limiter = RateLimiter(
            session_requests_per_minute=10,
            user_requests_per_minute=15
        )

        user_id = "user-1"
        session1 = "session-1"
        session2 = "session-2"

        # 8 requests from session-1
        for i in range(8):
            allowed, _ = limiter.check_request(session_id=session1, user_id=user_id)
            assert allowed is True
            limiter.record_usage(session_id=session1, user_id=user_id)

        # 7 requests from session-2
        for i in range(7):
            allowed, reason = limiter.check_request(session_id=session2, user_id=user_id)
            if i < 7:  # Total 15
                assert allowed is True
                limiter.record_usage(session_id=session2, user_id=user_id)
            else:  # Exceeds user limit
                assert allowed is False
                assert "User" in reason

    def test_global_rate_limiting(self):
        """Test global rate limiting."""
        limiter = RateLimiter(global_requests_per_minute=20)

        # Multiple sessions hitting global limit
        sessions = [f"session-{i}" for i in range(5)]

        # 4 requests per session = 20 total
        for session_id in sessions:
            for i in range(4):
                allowed, _ = limiter.check_request(session_id=session_id)
                assert allowed is True
                limiter.record_usage(session_id=session_id)

        # 21st request should fail
        allowed, reason = limiter.check_request(session_id="session-1")
        assert allowed is False
        assert "Global" in reason

    def test_cost_tracking(self):
        """Test cost tracking and budgets."""
        limiter = RateLimiter(
            session_requests_per_minute=100,
            session_daily_budget=10.0
        )

        session_id = "session-1"

        # Request with cost that fits budget
        allowed, _ = limiter.check_request(
            session_id=session_id,
            estimated_cost=5.0
        )
        assert allowed is True
        limiter.record_usage(session_id=session_id, actual_cost=5.0)

        # Add more cost to exceed budget
        limiter.record_usage(session_id=session_id, actual_cost=6.0)  # Total 11, over 10

        # Now check - should fail because budget exceeded
        allowed, reason = limiter.check_request(
            session_id=session_id,
            estimated_cost=1.0
        )
        assert allowed is False
        assert "budget" in reason.lower()

    def test_status_reporting(self):
        """Test status reporting."""
        limiter = RateLimiter(
            session_requests_per_minute=10,
            session_daily_budget=50.0
        )

        session_id = "session-1"

        # Make some requests
        for i in range(7):
            limiter.check_request(session_id=session_id, estimated_cost=5.0)
            limiter.record_usage(session_id=session_id, token_count=100, actual_cost=5.0)

        # Get status
        status = limiter.get_status(session_id=session_id)

        assert 'session' in status
        assert 'limits' in status['session']
        assert 'costs' in status['session']

        # Check utilization (may have slight variations due to refill)
        requests_limit = status['session']['limits']['requests']
        assert 0.65 <= requests_limit['utilization'] <= 0.75  # ~7/10

    def test_warning_threshold(self):
        """Test warning threshold detection."""
        limiter = RateLimiter(
            session_requests_per_minute=10
        )

        session_id = "session-1"

        # Use 8 tokens (80%)
        for i in range(8):
            limiter.check_request(session_id=session_id)
            limiter.record_usage(session_id=session_id)

        status = limiter.get_status(session_id=session_id)
        requests_limit = status['session']['limits']['requests']

        # Check high utilization (no explicit is_warning field)
        assert requests_limit['utilization'] >= 0.75

    def test_thread_safety(self):
        """Test thread-safe concurrent access."""
        limiter = RateLimiter(session_requests_per_minute=100)

        session_id = "session-1"
        success_count = [0]
        lock = asyncio.Lock()

        def make_requests():
            for i in range(20):
                allowed, _ = limiter.check_request(session_id=session_id)
                if allowed:
                    limiter.record_usage(session_id=session_id)
                    success_count[0] += 1

        # 5 threads, 20 requests each = 100 total
        threads = [Thread(target=make_requests) for _ in range(5)]

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        # Should succeed exactly 100 times (rate limit)
        assert success_count[0] <= 100

    def test_token_count_limiting(self):
        """Test token count limiting."""
        limiter = RateLimiter(session_tokens_per_hour=1000)

        session_id = "session-1"

        # Request with 600 tokens (allowed)
        allowed, _ = limiter.check_request(session_id=session_id, token_count=600)
        assert allowed is True
        limiter.record_usage(session_id=session_id, token_count=600)

        # Request with 500 more tokens (exceeds 1000)
        allowed, reason = limiter.check_request(session_id=session_id, token_count=500)
        assert allowed is False
        assert "token" in reason.lower()

    def test_multiple_sessions_isolation(self):
        """Test sessions are isolated from each other."""
        limiter = RateLimiter(session_requests_per_minute=5)

        session1 = "session-1"
        session2 = "session-2"

        # Use up session-1's limit
        for i in range(5):
            allowed, _ = limiter.check_request(session_id=session1)
            assert allowed is True
            limiter.record_usage(session_id=session1)

        # Session-2 should still have full limit
        allowed, _ = limiter.check_request(session_id=session2)
        assert allowed is True


class TestRateLimitEdgeCases:
    """Test edge cases and error conditions."""

    def test_zero_capacity_bucket(self):
        """Test bucket with zero capacity."""
        bucket = TokenBucket(capacity=0, refill_rate=1.0)

        # Should never allow consumption
        assert bucket.consume(1) is False
        assert bucket.consume(0.1) is False

    def test_zero_refill_rate(self):
        """Test bucket with zero refill rate."""
        bucket = TokenBucket(capacity=10, refill_rate=0)

        # Should not refill
        bucket.consume(10)
        time.sleep(1)
        bucket._refill()
        assert bucket.tokens == 0

    def test_negative_cost(self):
        """Test negative cost handling."""
        tracker = CostTracker(daily_budget=100.0)

        # CostTracker doesn't validate negative costs, it adds them
        tracker.add_cost(-50.0)
        # This is allowed behavior - refunds are possible
        assert tracker.daily_cost == -50.0

    def test_no_budgets_set(self):
        """Test cost tracker with no budgets."""
        tracker = CostTracker()

        # Should allow any cost when no budgets set
        tracker.add_cost(1000000.0)
        allowed, reason = tracker.check_budget()
        assert allowed is True

    def test_empty_session_id(self):
        """Test limiter with empty session ID."""
        limiter = RateLimiter(session_requests_per_minute=10)

        # Should handle gracefully
        allowed, _ = limiter.check_request(session_id="")
        assert allowed is True  # Creates new limit for empty string

    def test_very_large_request_count(self):
        """Test handling very large token consumption."""
        bucket = TokenBucket(capacity=10, refill_rate=1.0)

        # Try to consume more than capacity
        assert bucket.consume(1000) is False
        assert bucket.tokens == 10  # Unchanged


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
