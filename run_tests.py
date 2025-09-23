#!/usr/bin/env python3
"""
Test runner script for Gambiarra test suite.
Provides convenient commands for running different test categories.
"""

import sys
import subprocess
import argparse
from pathlib import Path


def run_command(cmd):
    """Run a command and return success/failure."""
    print(f"🚀 Running: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(result.stdout)
        if result.stderr:
            print(result.stderr)
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Command failed with exit code {e.returncode}")
        print(e.stdout)
        print(e.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(description="Run Gambiarra tests")
    parser.add_argument(
        "--category",
        choices=["unit", "integration", "security", "all", "fast"],
        default="all",
        help="Test category to run"
    )
    parser.add_argument(
        "--coverage",
        action="store_true",
        help="Run with coverage reporting"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Verbose output"
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop on first failure"
    )

    args = parser.parse_args()

    # Base pytest command
    cmd = ["python", "-m", "pytest"]

    # Add test path based on category
    if args.category == "unit":
        cmd.append("tests/unit/")
        print("🧪 Running unit tests...")
    elif args.category == "integration":
        cmd.append("tests/integration/")
        print("🔗 Running integration tests...")
    elif args.category == "security":
        cmd.extend(["-m", "security"])
        print("🛡️ Running security tests...")
    elif args.category == "fast":
        cmd.extend(["-m", "not slow"])
        print("⚡ Running fast tests...")
    else:  # all
        print("🎯 Running all tests...")

    # Add options
    if args.coverage:
        cmd.extend(["--cov=gambiarra", "--cov-report=term-missing"])

    if args.verbose:
        cmd.append("-v")

    if args.fail_fast:
        cmd.append("-x")

    # Check if tests directory exists
    if not Path("tests").exists():
        print("❌ Tests directory not found. Run from project root.")
        return False

    # Run the tests
    success = run_command(cmd)

    if success:
        print("✅ All tests passed!")
        return True
    else:
        print("❌ Some tests failed!")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)