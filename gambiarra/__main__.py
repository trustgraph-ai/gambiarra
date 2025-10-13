#!/usr/bin/env python3
"""
Main entry point for the Gambiarra package.
Displays help and version information when invoked with 'python -m gambiarra'.
"""

import sys
from . import __version__, __description__


def main():
    """Main entry point for package invocation."""
    print(f"Gambiarra v{__version__}")
    print(f"{__description__}")
    print()
    print("Available components:")
    print("  python -m gambiarra.client     - Start the Gambiarra client")
    print("  python -m gambiarra.server     - Start the Gambiarra server")
    print("  python -m gambiarra.test_llm   - Run the test LLM service")
    print()
    print("Entry points (after installation):")
    print("  gambiarra-client               - Start the Gambiarra client")
    print("  gambiarra-server               - Start the Gambiarra server")
    print("  gambiarra-test-llm             - Run the test LLM service")
    print()
    print("For more information, see the README.md file.")


if __name__ == "__main__":
    main()