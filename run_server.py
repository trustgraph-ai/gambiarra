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
    # Change to the server directory temporarily for proper imports
    original_dir = os.getcwd()
    server_dir = os.path.join(os.path.dirname(__file__), "server")

    try:
        os.chdir(server_dir)

        # Now import and run the server main
        import sys
        sys.path.insert(0, server_dir)

        # Execute the server main.py
        exec(open("main.py").read())

    finally:
        os.chdir(original_dir)