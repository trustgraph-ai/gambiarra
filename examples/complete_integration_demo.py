"""
Complete Integration Demo - All Features Working Together.

Demonstrates:
- Configuration loading
- Session management with persistence
- Rate limiting and cost control
- Transaction and rollback
- Context management
- All working together in a realistic scenario
"""

import sys
import asyncio
import tempfile
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from gambiarra.config import load_config, Config
from gambiarra.server.session.manager import SessionManager
from gambiarra.server.session.persistence import SessionPersistence
from gambiarra.server.core.rate_limiting import RateLimiter
from gambiarra.server.core.transactions import TransactionContext


async def demo_complete_integration():
    """
    Demonstrate complete integration of all features.

    Scenario: A developer using Gambiarra to refactor a project
    """
    print("=" * 80)
    print("COMPLETE INTEGRATION DEMO")
    print("=" * 80)
    print()
    print("Scenario: Developer refactoring a Python project with Gambiarra")
    print()

    # ========================================================================
    # STEP 1: Configuration
    # ========================================================================
    print("STEP 1: Loading Configuration")
    print("-" * 80)

    # Load configuration (would use config.yaml in real scenario)
    config = Config()

    print(f"✓ Configuration loaded")
    print(f"  Server: {config.server.host}:{config.server.port}")
    print(f"  Session timeout: {config.server.session.timeout_seconds}s")
    print(f"  Persistence enabled: {config.server.session.persistence_enabled}")
    print(f"  Rate limit: {config.server.ai_provider.rate_limit.session_requests_per_minute} req/min")
    print(f"  Daily budget: ${config.server.ai_provider.rate_limit.session_daily_budget}")
    print()

    # ========================================================================
    # STEP 2: Session Management with Persistence
    # ========================================================================
    print("STEP 2: Session Management")
    print("-" * 80)

    with tempfile.TemporaryDirectory() as temp_dir:
        # Create session persistence
        persistence = SessionPersistence(
            storage_dir=temp_dir,
            auto_save_interval=5.0
        )

        # Start auto-save
        await persistence.start_auto_save()

        # Create session manager with persistence
        session_manager = SessionManager(enable_persistence=False)
        session_manager._persistence = persistence

        # Create session
        session_id = await session_manager.create_session(
            connection_id="demo-connection-1",
            config={
                "working_directory": "/home/developer/project",
                "auto_approve_reads": True
            }
        )

        print(f"✓ Session created: {session_id[:16]}...")

        # Get session and add some conversation
        session = await session_manager.get_session(session_id, auto_recover=False)
        await session.add_message("user", "Help me refactor this Python project")
        await session.add_message("assistant", "I'll help you refactor. What would you like to change?")
        await session.add_message("user", "Let's rename all functions to use snake_case")

        # Add context files
        session.context_files = ["main.py", "utils.py", "helpers.py"]

        print(f"✓ Conversation started: {len(session.messages)} messages")
        print(f"✓ Context files tracked: {len(session.context_files)} files")

        # Save session
        await persistence.save_session(session, force=True)
        print(f"✓ Session saved to disk")
        print()

        # ========================================================================
        # STEP 3: Rate Limiting
        # ========================================================================
        print("STEP 3: Rate Limiting & Cost Control")
        print("-" * 80)

        # Create rate limiter with moderate limits
        rate_limiter = RateLimiter(
            session_requests_per_minute=10,
            session_tokens_per_hour=50000,
            session_daily_budget=25.0
        )

        print(f"✓ Rate limiter configured")
        print(f"  Session limit: 10 requests/min")
        print(f"  Token limit: 50,000 tokens/hour")
        print(f"  Daily budget: $25.00")
        print()

        # Simulate some AI requests
        print("Simulating AI requests:")
        request_count = 0
        total_tokens = 0
        total_cost = 0.0

        for i in range(15):
            # Estimate tokens and cost
            estimated_tokens = 1500 + (i * 100)
            estimated_cost = estimated_tokens * 0.00002  # $0.02 per 1K tokens

            # Check rate limit
            allowed, reason = rate_limiter.check_request(
                session_id=session_id,
                token_count=estimated_tokens,
                estimated_cost=estimated_cost
            )

            if allowed:
                # Record usage
                rate_limiter.record_usage(
                    session_id=session_id,
                    token_count=estimated_tokens,
                    actual_cost=estimated_cost
                )

                request_count += 1
                total_tokens += estimated_tokens
                total_cost += estimated_cost

                print(f"  Request {i+1}: ✓ Allowed ({estimated_tokens} tokens, ${estimated_cost:.4f})")
            else:
                print(f"  Request {i+1}: ✗ Denied - {reason}")

        print()
        print(f"Summary:")
        print(f"  Successful requests: {request_count}/15")
        print(f"  Total tokens used: {total_tokens:,}")
        print(f"  Total cost: ${total_cost:.2f}")

        # Get rate limit status
        status = rate_limiter.get_status(session_id=session_id)
        print()
        print(f"Rate Limit Status:")
        print(f"  Request utilization: {status['session']['limits']['requests']['utilization']*100:.1f}%")
        print(f"  Token utilization: {status['session']['limits']['tokens']['utilization']*100:.1f}%")
        print()

        # ========================================================================
        # STEP 4: Transactions for Safe Refactoring
        # ========================================================================
        print("STEP 4: Transactional Refactoring")
        print("-" * 80)

        # Create temporary project files
        project_dir = Path(temp_dir) / "project"
        project_dir.mkdir()

        file1 = project_dir / "main.py"
        file2 = project_dir / "utils.py"
        file3 = project_dir / "helpers.py"

        file1.write_text("""
def getUserName():
    return "John"

def processData(data):
    return data.upper()
""")

        file2.write_text("""
def formatOutput(text):
    return f"[{text}]"

def validateInput(value):
    return value is not None
""")

        file3.write_text("""
def helperFunction():
    pass

def anotherHelper():
    pass
""")

        print(f"✓ Created test project with 3 files")
        print()

        # Scenario 1: Successful refactoring
        print("Scenario 1: Successful Refactoring (snake_case conversion)")
        print()

        with TransactionContext("Refactor to snake_case") as txn:
            # Refactor file1
            txn.modify_file(str(file1), """
def get_user_name():
    return "John"

def process_data(data):
    return data.upper()
""")

            # Refactor file2
            txn.modify_file(str(file2), """
def format_output(text):
    return f"[{text}]"

def validate_input(value):
    return value is not None
""")

            # Refactor file3
            txn.modify_file(str(file3), """
def helper_function():
    pass

def another_helper():
    pass
""")

        print(f"✓ All 3 files refactored successfully")
        print(f"✓ Transaction committed")
        print()

        # Verify changes
        print("Verifying changes:")
        print(f"  main.py: {'get_user_name' in file1.read_text()}")
        print(f"  utils.py: {'format_output' in file2.read_text()}")
        print(f"  helpers.py: {'helper_function' in file3.read_text()}")
        print()

        # Scenario 2: Failed refactoring with rollback
        print("Scenario 2: Failed Refactoring (automatic rollback)")
        print()

        # Save current state
        file1_before = file1.read_text()
        file2_before = file2.read_text()

        try:
            with TransactionContext("Add type hints") as txn:
                # Modify file1
                txn.modify_file(str(file1), """
def get_user_name() -> str:
    return "John"

def process_data(data: str) -> str:
    return data.upper()
""")

                # Modify file2
                txn.modify_file(str(file2), """
def format_output(text: str) -> str:
    return f"[{text}]"

def validate_input(value: any) -> bool:
    return value is not None
""")

                # Try to modify non-existent file (will fail)
                txn.modify_file(str(project_dir / "nonexistent.py"), "content")

        except Exception as e:
            print(f"✗ Transaction failed: File not found")
            print(f"✓ Automatic rollback triggered")
            print()

        # Verify rollback
        print("Verifying rollback:")
        file1_after = file1.read_text()
        file2_after = file2.read_text()

        print(f"  file1 restored: {file1_before == file1_after}")
        print(f"  file2 restored: {file2_before == file2_after}")
        print()

        # ========================================================================
        # STEP 5: Session Recovery (Simulate Restart)
        # ========================================================================
        print("STEP 5: Session Recovery")
        print("-" * 80)

        # Save current session state
        await persistence.save_session(session, force=True)

        # Simulate server restart by clearing memory
        session_manager.sessions.clear()
        print(f"✓ Simulated server restart (cleared memory)")
        print()

        # Try to recover session
        recovered_session = await session_manager.get_session(
            session_id,
            auto_recover=True
        )

        if recovered_session:
            print(f"✓ Session recovered from disk")
            print(f"  Session ID: {recovered_session.session_id[:16]}...")
            print(f"  Messages: {len(recovered_session.messages)}")
            print(f"  Context files: {len(recovered_session.context_files)}")
            print(f"  Working directory: {recovered_session.config.working_directory}")
            print()

            # Verify conversation history
            print("Conversation history preserved:")
            for i, msg in enumerate(recovered_session.messages[:3], 1):
                content_preview = msg.content[:50] + "..." if len(msg.content) > 50 else msg.content
                print(f"  {i}. {msg.role}: {content_preview}")
        else:
            print(f"✗ Failed to recover session")

        print()

        # ========================================================================
        # STEP 6: Cleanup
        # ========================================================================
        print("STEP 6: Cleanup")
        print("-" * 80)

        # Stop auto-save
        await persistence.stop_auto_save()
        print(f"✓ Stopped auto-save")

        # Get storage stats
        stats = await persistence.get_storage_stats()
        print(f"✓ Storage statistics:")
        print(f"  Total sessions: {stats['session_count']}")
        print(f"  Storage used: {stats['total_size_bytes']} bytes")
        print()

    # ========================================================================
    # Summary
    # ========================================================================
    print("=" * 80)
    print("INTEGRATION DEMO COMPLETE")
    print("=" * 80)
    print()
    print("Features Demonstrated:")
    print("  ✓ Configuration management")
    print("  ✓ Session management with persistence")
    print("  ✓ Auto-save and recovery")
    print("  ✓ Rate limiting and cost control")
    print("  ✓ Transactional file operations")
    print("  ✓ Automatic rollback on failure")
    print("  ✓ Session recovery after restart")
    print()
    print("All features working together seamlessly!")
    print()


async def main():
    """Run integration demo."""
    await demo_complete_integration()


if __name__ == "__main__":
    asyncio.run(main())
