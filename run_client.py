#!/usr/bin/env python3
"""
Gambiarra Client Runner - Run from gambiarra root directory.
"""

import sys
import os

# Add the gambiarra directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import and run the client
from client.main import main
import asyncio

if __name__ == "__main__":
    asyncio.run(main())