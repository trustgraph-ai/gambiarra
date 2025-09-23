"""
Tool Repetition Detector for Gambiarra client.
Prevents AI from getting stuck in infinite loops by detecting identical consecutive tool calls.
Detects and prevents AI tool call repetition loops.
"""

import json
import logging
from typing import Dict, Any, Optional, NamedTuple

logger = logging.getLogger(__name__)


class RepetitionCheckResult(NamedTuple):
    """Result of repetition check."""
    allow_execution: bool
    ask_user: Optional[Dict[str, str]] = None


class ToolRepetitionDetector:
    """Detects consecutive identical tool calls to prevent infinite loops."""

    def __init__(self, limit: int = 3):
        """
        Initialize detector.

        Args:
            limit: Maximum number of identical consecutive tool calls allowed
        """
        self.consecutive_identical_tool_call_limit = limit
        self.previous_tool_call_json: Optional[str] = None
        self.consecutive_identical_tool_call_count = 0

    def check(self, tool_name: str, tool_params: Dict[str, Any]) -> RepetitionCheckResult:
        """
        Check if the current tool call is identical to the previous one.

        Args:
            tool_name: Name of the tool being called
            tool_params: Parameters for the tool call

        Returns:
            RepetitionCheckResult indicating if execution should be allowed
        """
        # Browser scroll actions should not be subject to repetition detection
        if self._is_browser_scroll_action(tool_name, tool_params):
            return RepetitionCheckResult(allow_execution=True)

        # Serialize the tool call to a canonical JSON string for comparison
        current_tool_call_json = self._serialize_tool_call(tool_name, tool_params)

        # Compare with previous tool call
        if self.previous_tool_call_json == current_tool_call_json:
            self.consecutive_identical_tool_call_count += 1
        else:
            self.consecutive_identical_tool_call_count = 0  # Reset for new tool
            self.previous_tool_call_json = current_tool_call_json

        # Check if limit is reached (0 means unlimited)
        if (self.consecutive_identical_tool_call_limit > 0 and
            self.consecutive_identical_tool_call_count >= self.consecutive_identical_tool_call_limit):

            # Reset counters to allow recovery if user guides the AI past this point
            self.consecutive_identical_tool_call_count = 0
            self.previous_tool_call_json = None

            return RepetitionCheckResult(
                allow_execution=False,
                ask_user={
                    "message_key": "tool_repetition_limit_reached",
                    "message_detail": f"AI is repeating the same '{tool_name}' tool call. This may indicate it's stuck in a loop."
                }
            )

        # Execution is allowed
        return RepetitionCheckResult(allow_execution=True)

    def _is_browser_scroll_action(self, tool_name: str, tool_params: Dict[str, Any]) -> bool:
        """Check if tool call is a browser scroll action."""
        if tool_name != "browser_action":
            return False

        action = tool_params.get("action", "")
        return action in ("scroll_down", "scroll_up")

    def _serialize_tool_call(self, tool_name: str, tool_params: Dict[str, Any]) -> str:
        """
        Serialize a tool call into a canonical JSON string for comparison.

        Args:
            tool_name: Name of the tool
            tool_params: Parameters for the tool call

        Returns:
            JSON string representation with sorted parameter keys
        """
        # Create sorted parameters object
        sorted_params = {key: tool_params[key] for key in sorted(tool_params.keys())}

        # Create the object with tool name and sorted parameters
        tool_object = {
            "name": tool_name,
            "parameters": sorted_params
        }

        # Convert to canonical JSON string
        return json.dumps(tool_object, sort_keys=True, separators=(',', ':'))

    def reset(self):
        """Reset the detector state."""
        self.previous_tool_call_json = None
        self.consecutive_identical_tool_call_count = 0
        logger.info("🔄 Tool repetition detector reset")