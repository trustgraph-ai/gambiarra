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
    from test_llm import main
    # The test_llm main.py runs when imported