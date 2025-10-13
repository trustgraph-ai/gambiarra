"""
Demo script for Rate Limiting & Cost Control.

Demonstrates multi-level rate limiting with token buckets and cost tracking.
"""

import sys
from pathlib import Path
import time

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from gambiarra.server.core.rate_limiting import RateLimiter


def demo_basic_rate_limiting():
    """Demonstrate basic rate limiting."""
    print("=" * 80)
    print("DEMO 1: Basic Rate Limiting")
    print("=" * 80)
    print()

    # Create limiter with low limits for demo
    limiter = RateLimiter(
        session_requests_per_minute=5,  # 5 requests per minute
        session_tokens_per_hour=1000,   # 1000 tokens per hour
        user_requests_per_minute=10,
        global_requests_per_minute=100
    )

    session_id = "demo-session-1"

    print("Limits:")
    print("  - 5 requests per minute per session")
    print("  - 1000 tokens per hour per session")
    print()

    print("Making requests...")
    print()

    # Make several requests
    for i in range(7):
        allowed, reason = limiter.check_request(
            session_id=session_id,
            token_count=100
        )

        if allowed:
            print(f"  Request {i+1}: ✓ Allowed")
            limiter.record_usage(session_id=session_id, token_count=100)
        else:
            print(f"  Request {i+1}: ✗ Denied - {reason}")

    print()

    # Show status
    status = limiter.get_status(session_id=session_id)
    session_limits = status["session"]["limits"]

    print("Status after requests:")
    print(f"  Requests bucket: {session_limits['requests']['tokens']:.1f}/{session_limits['requests']['capacity']:.1f} tokens")
    print(f"  Tokens bucket: {session_limits['tokens']['tokens']:.0f}/{session_limits['tokens']['capacity']:.0f} tokens")
    print()


def demo_token_bucket_refill():
    """Demonstrate token bucket refill."""
    print("=" * 80)
    print("DEMO 2: Token Bucket Refill")
    print("=" * 80)
    print()

    # Create limiter with very fast refill for demo
    limiter = RateLimiter(
        session_requests_per_minute=3,  # 3 per minute = 1 every 20 seconds
        session_tokens_per_hour=10000
    )

    session_id = "demo-session-2"

    print("Limits: 3 requests per minute (refills 1 every 20 seconds)")
    print()

    # Use all tokens
    print("Using all 3 tokens...")
    for i in range(3):
        allowed, _ = limiter.check_request(session_id=session_id)
        if allowed:
            limiter.record_usage(session_id=session_id)
            print(f"  Request {i+1}: ✓")

    print()

    # Try one more (should fail)
    allowed, reason = limiter.check_request(session_id=session_id)
    print(f"Request 4 (immediate): {'✓ Allowed' if allowed else f'✗ Denied - {reason}'}")
    print()

    # Wait for refill
    print("Waiting 2 seconds for refill...")
    time.sleep(2)

    # Try again (should still have tokens now due to refill)
    allowed, reason = limiter.check_request(session_id=session_id)
    status = limiter.get_status(session_id=session_id)
    tokens = status["session"]["limits"]["requests"]["tokens"]

    print(f"Request 5 (after wait): {'✓ Allowed' if allowed else f'✗ Denied'}")
    print(f"Tokens in bucket: {tokens:.2f}/3.00 (refilled!)")
    print()


def demo_cost_tracking():
    """Demonstrate cost tracking and budgets."""
    print("=" * 80)
    print("DEMO 3: Cost Tracking & Budgets")
    print("=" * 80)
    print()

    # Create limiter with cost budgets
    limiter = RateLimiter(
        session_requests_per_minute=100,
        session_tokens_per_hour=100000,
        session_daily_budget=10.00,  # $10 per day per session
        user_daily_budget=50.00,     # $50 per day per user
        global_daily_budget=500.00   # $500 per day globally
    )

    session_id = "demo-session-3"
    user_id = "demo-user-1"

    print("Budgets:")
    print("  - Session: $10/day")
    print("  - User: $50/day")
    print("  - Global: $500/day")
    print()

    print("Making requests with costs...")
    print()

    # Simulate requests with costs
    costs = [0.50, 1.00, 2.50, 3.00, 1.50, 2.00]  # Total: $10.50

    total_spent = 0.0
    for i, cost in enumerate(costs):
        allowed, reason = limiter.check_request(
            session_id=session_id,
            user_id=user_id,
            estimated_cost=cost
        )

        if allowed:
            print(f"  Request {i+1}: ✓ Allowed (cost: ${cost:.2f})")
            limiter.record_usage(
                session_id=session_id,
                user_id=user_id,
                actual_cost=cost
            )
            total_spent += cost
        else:
            print(f"  Request {i+1}: ✗ Denied (cost: ${cost:.2f}) - {reason}")

    print()
    print(f"Total spent: ${total_spent:.2f}")
    print()

    # Show cost status
    status = limiter.get_status(session_id=session_id, user_id=user_id)

    print("Cost Status:")
    print(f"  Session daily: ${status['session']['costs']['daily']['cost']:.2f}/$10.00")
    print(f"  User daily: ${status['user']['costs']['daily']['cost']:.2f}/$50.00")
    print(f"  Global daily: ${status['global']['costs']['daily']['cost']:.2f}/$500.00")
    print()


def demo_multi_level_limits():
    """Demonstrate multi-level rate limiting."""
    print("=" * 80)
    print("DEMO 4: Multi-Level Rate Limiting")
    print("=" * 80)
    print()

    limiter = RateLimiter(
        session_requests_per_minute=10,  # Session: 10/min
        user_requests_per_minute=15,     # User: 15/min (across sessions)
        global_requests_per_minute=20    # Global: 20/min (across all users)
    )

    print("Limits:")
    print("  - Session: 10 requests/minute")
    print("  - User: 15 requests/minute")
    print("  - Global: 20 requests/minute")
    print()

    # Two sessions for same user
    session1 = "session-1"
    session2 = "session-2"
    user_id = "user-1"

    print(f"Making 8 requests from session-1 (user: {user_id})...")
    for i in range(8):
        allowed, _ = limiter.check_request(session_id=session1, user_id=user_id)
        if allowed:
            limiter.record_usage(session_id=session1, user_id=user_id)
            print(f"  Request {i+1}: ✓")

    print()

    print(f"Making 8 requests from session-2 (user: {user_id})...")
    for i in range(8):
        allowed, reason = limiter.check_request(session_id=session2, user_id=user_id)
        if allowed:
            limiter.record_usage(session_id=session2, user_id=user_id)
            print(f"  Request {i+1}: ✓")
        else:
            print(f"  Request {i+1}: ✗ {reason}")

    print()

    # Show status
    status = limiter.get_status(session_id=session1, user_id=user_id)

    print("Status:")
    print(f"  Session-1: {status['session']['limits']['requests']['tokens']:.1f}/10 tokens")
    print(f"  User (both sessions): {status['user']['limits']['requests']['tokens']:.1f}/15 tokens")
    print(f"  Global: {status['global']['limits']['requests']['tokens']:.1f}/20 tokens")
    print()

    print("Note: Session-2 hit user-level limit after 7 requests")
    print("(8 from session-1 + 7 from session-2 = 15 total for user)")
    print()


def demo_status_monitoring():
    """Demonstrate status monitoring."""
    print("=" * 80)
    print("DEMO 5: Status Monitoring")
    print("=" * 80)
    print()

    limiter = RateLimiter(
        session_requests_per_minute=10,
        session_tokens_per_hour=5000,
        session_daily_budget=20.00
    )

    session_id = "demo-session-5"

    # Make some requests
    for i in range(7):
        limiter.check_request(session_id=session_id, token_count=500)
        limiter.record_usage(session_id=session_id, token_count=500, actual_cost=1.50)

    # Get detailed status
    status = limiter.get_status(session_id=session_id)

    print("Detailed Status Report:")
    print()

    # Session limits
    print("Session Rate Limits:")
    for limit_name, limit_status in status["session"]["limits"].items():
        utilization = limit_status["utilization"] * 100
        tokens = limit_status["tokens"]
        capacity = limit_status["capacity"]
        print(f"  {limit_name}:")
        print(f"    - Tokens: {tokens:.1f}/{capacity:.0f}")
        print(f"    - Utilization: {utilization:.1f}%")
        print(f"    - Refill rate: {limit_status['refill_rate']:.2f} tokens/second")

    print()

    # Session costs
    print("Session Costs:")
    daily_cost = status["session"]["costs"]["daily"]
    print(f"  Daily:")
    print(f"    - Spent: ${daily_cost['cost']:.2f}")
    print(f"    - Budget: ${daily_cost['budget']:.2f}")
    print(f"    - Remaining: ${daily_cost['remaining']:.2f}")
    print(f"    - Utilization: {daily_cost['utilization']*100:.1f}%")

    print()


def main():
    """Run all demos."""
    print()
    print("╔" + "=" * 78 + "╗")
    print("║" + " " * 20 + "RATE LIMITING & COST CONTROL DEMO" + " " * 25 + "║")
    print("╚" + "=" * 78 + "╝")
    print()

    demo_basic_rate_limiting()
    demo_token_bucket_refill()
    demo_cost_tracking()
    demo_multi_level_limits()
    demo_status_monitoring()

    print("=" * 80)
    print("KEY BENEFITS")
    print("=" * 80)
    print()
    print("✓ Prevents runaway costs: Hard limits on spending")
    print("✓ Multi-level protection: Session, user, and global limits")
    print("✓ Smooth rate limiting: Token bucket algorithm")
    print("✓ Automatic refill: Capacity replenishes over time")
    print("✓ Cost tracking: Monitor spending in real-time")
    print("✓ Budget enforcement: Daily/weekly/monthly budgets")
    print("✓ Warning thresholds: Alerts before hitting limits")
    print("✓ Thread-safe: Safe for concurrent requests")
    print()
    print("=" * 80)
    print("DEMO COMPLETE")
    print("=" * 80)
    print()


if __name__ == "__main__":
    main()
