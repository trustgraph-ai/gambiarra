"""
Tool parameter validation and error tracking for Gambiarra client.
Based on KiloCode's validation patterns.
"""

import logging
from typing import Dict, Any, List, Optional, NamedTuple
from datetime import datetime

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Exception raised when tool parameters fail validation."""
    def __init__(self, message: str, parameter: str = None, details: Dict[str, Any] = None):
        super().__init__(message)
        self.parameter = parameter
        self.details = details or {}


class ToolError(NamedTuple):
    """Record of a tool execution error."""
    tool_name: str
    error_type: str
    message: str
    parameters: Dict[str, Any]
    timestamp: datetime


class ToolValidator:
    """Validates tool parameters and tracks tool errors."""

    def __init__(self):
        self.error_history: List[ToolError] = []
        self.consecutive_mistake_count = 0

        # Tool parameter schemas
        self.tool_schemas = {
            "read_file": {
                "required": [],
                "optional": [],
                "args": {
                    "required": [],
                    "optional": [],
                    "file": {
                        "required": ["path"],
                        "optional": ["line_range"]
                    }
                }
            },
            "write_to_file": {
                "required": ["path", "content", "line_count"],
                "optional": []
            },
            "list_files": {
                "required": ["path"],
                "optional": ["recursive"]
            },
            "search_files": {
                "required": ["path", "regex"],
                "optional": ["file_pattern"]
            },
            "execute_command": {
                "required": ["command"],
                "optional": ["cwd"]
            },
            "search_and_replace": {
                "required": ["path", "search", "replace"],
                "optional": []
            },
            "insert_content": {
                "required": ["path", "line_number", "content"],
                "optional": []
            },
            "list_code_definition_names": {
                "required": ["path"],
                "optional": []
            },
            "attempt_completion": {
                "required": ["result"],
                "optional": []
            },
            "ask_followup_question": {
                "required": ["question"],
                "optional": []
            },
            "update_todo_list": {
                "required": ["todos"],
                "optional": []
            }
        }

    def validate_tool_parameters(self, tool_name: str, parameters: Dict[str, Any]) -> None:
        """
        Validate tool parameters against schema.

        Args:
            tool_name: Name of the tool
            parameters: Parameters to validate

        Raises:
            ValidationError: If validation fails
        """
        if tool_name not in self.tool_schemas:
            raise ValidationError(f"Unknown tool: {tool_name}", details={"tool_name": tool_name})

        schema = self.tool_schemas[tool_name]

        # Handle special case for read_file with nested args structure
        if tool_name == "read_file":
            self._validate_read_file_parameters(parameters)
            return

        # Validate required parameters
        required_params = schema.get("required", [])
        for param in required_params:
            if param not in parameters:
                raise ValidationError(
                    f"Missing required parameter: {param}",
                    parameter=param,
                    details={"tool_name": tool_name, "required_params": required_params}
                )

        # Validate parameter types and values
        self._validate_parameter_values(tool_name, parameters)

        logger.debug(f"✅ Tool {tool_name} parameters validated successfully")

    def _validate_read_file_parameters(self, parameters: Dict[str, Any]) -> None:
        """Validate read_file specific nested structure."""
        if "args" not in parameters:
            raise ValidationError("read_file requires 'args' parameter")

        args = parameters["args"]
        if not isinstance(args, dict):
            raise ValidationError("'args' parameter must be a dictionary")

        if "file" not in args:
            raise ValidationError("read_file args must contain 'file' parameter")

        file_params = args["file"]
        if not isinstance(file_params, dict):
            raise ValidationError("'file' parameter must be a dictionary")

        if "path" not in file_params:
            raise ValidationError("read_file file parameter must contain 'path'")

    def _validate_parameter_values(self, tool_name: str, parameters: Dict[str, Any]) -> None:
        """Validate specific parameter values."""

        # Validate path parameters
        path_params = ["path"]
        for param in path_params:
            if param in parameters:
                path_value = parameters[param]
                if not isinstance(path_value, str) or not path_value.strip():
                    raise ValidationError(
                        f"Parameter '{param}' must be a non-empty string",
                        parameter=param
                    )

        # Validate line_count for write_to_file
        if tool_name == "write_to_file" and "line_count" in parameters:
            try:
                line_count = int(parameters["line_count"])
                if line_count < 0:
                    raise ValidationError(
                        "line_count must be a non-negative integer",
                        parameter="line_count"
                    )
            except (ValueError, TypeError):
                raise ValidationError(
                    "line_count must be a valid integer",
                    parameter="line_count"
                )

        # Validate recursive parameter for list_files
        if tool_name == "list_files" and "recursive" in parameters:
            recursive_value = parameters["recursive"]
            if isinstance(recursive_value, str):
                if recursive_value.lower() not in ["true", "false"]:
                    raise ValidationError(
                        "recursive parameter must be 'true' or 'false'",
                        parameter="recursive"
                    )
            elif not isinstance(recursive_value, bool):
                raise ValidationError(
                    "recursive parameter must be a boolean or string 'true'/'false'",
                    parameter="recursive"
                )

        # Validate line_number for insert_content
        if tool_name == "insert_content" and "line_number" in parameters:
            try:
                line_number = int(parameters["line_number"])
                if line_number < 0:
                    raise ValidationError(
                        "line_number must be a non-negative integer (0 to append at end)",
                        parameter="line_number"
                    )
            except (ValueError, TypeError):
                raise ValidationError(
                    "line_number must be a valid integer",
                    parameter="line_number"
                )

    def record_tool_error(self, tool_name: str, error_type: str, message: str, parameters: Dict[str, Any]) -> None:
        """Record a tool execution error."""
        error = ToolError(
            tool_name=tool_name,
            error_type=error_type,
            message=message,
            parameters=parameters.copy(),
            timestamp=datetime.now()
        )

        self.error_history.append(error)
        self.consecutive_mistake_count += 1

        logger.warning(f"🚫 Tool error recorded: {tool_name} - {error_type}: {message}")

        # Keep only last 50 errors to prevent memory bloat
        if len(self.error_history) > 50:
            self.error_history = self.error_history[-50:]

    def record_tool_success(self, tool_name: str) -> None:
        """Record successful tool execution."""
        self.consecutive_mistake_count = 0
        logger.debug(f"✅ Tool success recorded: {tool_name}")

    def get_recent_errors(self, count: int = 5) -> List[ToolError]:
        """Get recent tool errors."""
        return self.error_history[-count:] if self.error_history else []

    def get_error_stats(self) -> Dict[str, Any]:
        """Get error statistics."""
        if not self.error_history:
            return {
                "total_errors": 0,
                "consecutive_mistakes": self.consecutive_mistake_count,
                "most_common_errors": []
            }

        # Count errors by type
        error_counts = {}
        for error in self.error_history:
            key = f"{error.tool_name}:{error.error_type}"
            error_counts[key] = error_counts.get(key, 0) + 1

        # Get most common errors
        most_common = sorted(error_counts.items(), key=lambda x: x[1], reverse=True)[:5]

        return {
            "total_errors": len(self.error_history),
            "consecutive_mistakes": self.consecutive_mistake_count,
            "most_common_errors": most_common
        }

    def should_request_guidance(self) -> bool:
        """Determine if user guidance should be requested due to repeated errors."""
        return self.consecutive_mistake_count >= 3

    def reset_mistake_count(self) -> None:
        """Reset consecutive mistake count."""
        self.consecutive_mistake_count = 0
        logger.info("🔄 Mistake count reset")