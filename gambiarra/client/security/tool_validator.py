"""
Tool parameter validation and error tracking for Gambiarra client.
Provides comprehensive parameter validation and error tracking.
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

        # Tool parameter schemas - all tools now use nested args structure
        self.tool_schemas = {
            "read_file": {
                "nested_structure": True,
                "args": {
                    "file": {
                        "required": ["path"],
                        "optional": ["line_range"]
                    }
                }
            },
            "write_to_file": {
                "nested_structure": True,
                "args": {
                    "required": ["path", "content", "line_count"],
                    "optional": []
                }
            },
            "list_files": {
                "nested_structure": True,
                "args": {
                    "required": ["path"],
                    "optional": ["recursive"]
                }
            },
            "search_files": {
                "nested_structure": True,
                "args": {
                    "required": ["path", "regex"],
                    "optional": ["file_pattern"]
                }
            },
            "execute_command": {
                "nested_structure": True,
                "args": {
                    "required": ["command"],
                    "optional": ["cwd"]
                }
            },
            "search_and_replace": {
                "nested_structure": True,
                "args": {
                    "required": ["path", "search", "replace"],
                    "optional": []
                }
            },
            "insert_content": {
                "nested_structure": True,
                "args": {
                    "required": ["path", "line_number", "content"],
                    "optional": []
                }
            },
            "list_code_definition_names": {
                "nested_structure": True,
                "args": {
                    "required": ["path"],
                    "optional": []
                }
            },
            "attempt_completion": {
                "nested_structure": True,
                "args": {
                    "required": ["result"],
                    "optional": []
                }
            },
            "ask_followup_question": {
                "nested_structure": True,
                "args": {
                    "required": ["question"],
                    "optional": []
                }
            },
            "update_todo_list": {
                "nested_structure": True,
                "args": {
                    "required": ["todos"],
                    "optional": []
                }
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

        # All tools now use nested args structure
        if schema.get("nested_structure", False):
            self._validate_nested_args_parameters(tool_name, parameters, schema)
        else:
            # Legacy flat structure validation (kept for backward compatibility)
            self._validate_flat_parameters(tool_name, parameters, schema)

        # Validate parameter types and values
        self._validate_parameter_values(tool_name, parameters)

        logger.debug(f"✅ Tool {tool_name} parameters validated successfully")

    def _validate_nested_args_parameters(self, tool_name: str, parameters: Dict[str, Any], schema: Dict[str, Any]) -> None:
        """Validate parameters for tools using nested args structure."""
        if "args" not in parameters:
            raise ValidationError(f"{tool_name} requires 'args' parameter")

        args = parameters["args"]
        if not isinstance(args, dict):
            raise ValidationError("'args' parameter must be a dictionary")

        args_schema = schema["args"]

        # Handle special case for read_file with file.path structure
        if tool_name == "read_file":
            if "file" not in args:
                raise ValidationError("read_file args must contain 'file' parameter")

            file_params = args["file"]
            if not isinstance(file_params, dict):
                raise ValidationError("'file' parameter must be a dictionary")

            file_schema = args_schema["file"]
            required_file_params = file_schema.get("required", [])
            for param in required_file_params:
                if param not in file_params:
                    raise ValidationError(f"read_file file parameter must contain '{param}'")
        else:
            # Standard nested args validation for other tools
            required_params = args_schema.get("required", [])
            for param in required_params:
                if param not in args:
                    raise ValidationError(
                        f"Missing required parameter in args: {param}",
                        parameter=param,
                        details={"tool_name": tool_name, "required_params": required_params}
                    )

    def _validate_flat_parameters(self, tool_name: str, parameters: Dict[str, Any], schema: Dict[str, Any]) -> None:
        """Validate parameters for tools using flat structure (legacy)."""
        required_params = schema.get("required", [])
        for param in required_params:
            if param not in parameters:
                raise ValidationError(
                    f"Missing required parameter: {param}",
                    parameter=param,
                    details={"tool_name": tool_name, "required_params": required_params}
                )

    def _validate_parameter_values(self, tool_name: str, parameters: Dict[str, Any]) -> None:
        """Validate specific parameter values."""

        # Extract args for nested structure tools
        args = parameters.get("args", parameters)

        # For read_file, path is in file.path
        if tool_name == "read_file":
            file_params = args.get("file", {})
            if "path" in file_params:
                path_value = file_params["path"]
                if not isinstance(path_value, str) or not path_value.strip():
                    raise ValidationError(
                        "Parameter 'path' must be a non-empty string",
                        parameter="path"
                    )
        else:
            # For other tools, validate path in args
            if "path" in args:
                path_value = args["path"]
                if not isinstance(path_value, str) or not path_value.strip():
                    raise ValidationError(
                        "Parameter 'path' must be a non-empty string",
                        parameter="path"
                    )

        # Validate line_count for write_to_file
        if tool_name == "write_to_file" and "line_count" in args:
            try:
                line_count = int(args["line_count"])
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
        if tool_name == "list_files" and "recursive" in args:
            recursive_value = args["recursive"]
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
        if tool_name == "insert_content" and "line_number" in args:
            try:
                line_number = int(args["line_number"])
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