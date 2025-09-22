#!/usr/bin/env python3
"""
Gambiarra Server Runner - Run from gambiarra root directory.
"""

import sys
import os

# Add the gambiarra directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import and run the server
if __name__ == "__main__":
    from server import main
    # The server main.py runs when imported