"""
Gambiarra Client Module.

Provides the client-side functionality for the Gambiarra AI coding assistant,
including secure file operations, WebSocket communication, and user interface.
"""

from .main import main, main_sync

__all__ = ["main", "main_sync"]