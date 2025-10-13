"""
Intelligent command execution module for Gambiarra client.

This module provides sophisticated command execution capabilities including:
- Pre-execution validation
- Interactive prompt detection and handling
- Hang detection with adaptive learning
- Real-time monitoring and streaming output
- Bidirectional server-client communication

Components:
- CommandKnowledgeBase: Knowledge about command behavior and requirements
- HangDetector/AdaptiveHangDetector: Detects commands that are hanging
- SmartExecutionHandler: Orchestrates intelligent command execution

Usage:
    from gambiarra.client.execution import SmartExecutionHandler

    handler = SmartExecutionHandler()
    result = await handler.execute_command(execute_request)
"""

from .command_knowledge import CommandKnowledgeBase, CommandPattern
from .hang_detector import HangDetector, AdaptiveHangDetector, HangSignal
from .smart_execution import SmartExecutionHandler

__all__ = [
    'CommandKnowledgeBase',
    'CommandPattern',
    'HangDetector',
    'AdaptiveHangDetector',
    'HangSignal',
    'SmartExecutionHandler',
]
