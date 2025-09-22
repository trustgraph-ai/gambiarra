#!/usr/bin/env python3
"""
Gambiarra Test LLM Runner - Run from gambiarra root directory.
"""

import sys
import os

# Add the gambiarra directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import and run the test LLM
if __name__ == "__main__":
    import importlib.util
    import os

    # Load and run the test-llm main.py file directly
    test_llm_path = os.path.join(os.path.dirname(__file__), "test-llm", "main.py")

    # Execute the file as if it were run directly
    with open(test_llm_path, 'r') as f:
        code = f.read()

    # Replace the module's __name__ to trigger the main execution
    exec(code, {"__name__": "__main__"})