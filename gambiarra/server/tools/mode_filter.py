"""
Mode-based tool filtering for Gambiarra server.
Provides different tool sets based on operating mode (e.g., code, ask, architect).
Operating mode filtering for context-aware tool execution.
"""

import logging
from typing import Dict, List, Set, Any
from enum import Enum

logger = logging.getLogger(__name__)


class OperatingMode(Enum):
    """Available operating modes for Gambiarra."""
    CODE = "code"           # Full coding assistant with all tools
    ASK = "ask"             # Question answering, limited file operations
    ARCHITECT = "architect" # System design, read-only operations
    DEBUG = "debug"         # Debugging mode with enhanced diagnostics
    REVIEW = "review"       # Code review mode, read-only with analysis tools


class ToolModeFilter:
    """
    Filters available tools based on the current operating mode.
    Different modes have different tool access patterns for security and focus.
    """

    def __init__(self):
        # Define tool categories
        self.tool_categories = {
            # File operations
            "file_read": {"read_file", "list_files", "search_files", "list_code_definition_names"},
            "file_write": {"write_to_file", "search_and_replace", "insert_content"},

            # Command execution
            "command_exec": {"execute_command"},

            # Communication
            "communication": {"attempt_completion", "ask_followup_question"},

            # Task management
            "task_management": {"update_todo_list"},

            # Analysis (read-only diagnostic tools)
            "analysis": {"analyze_code_quality", "check_dependencies", "run_tests"},
        }

        # Define mode-specific tool access
        self.mode_tool_access = {
            OperatingMode.CODE: {
                "allowed_categories": ["file_read", "file_write", "command_exec", "communication", "task_management", "analysis"],
                "denied_tools": set(),  # No restrictions in full code mode
                "risk_modifications": {}  # No risk level changes
            },

            OperatingMode.ASK: {
                "allowed_categories": ["file_read", "communication"],
                "denied_tools": {"execute_command"},  # No command execution
                "risk_modifications": {
                    "read_file": "minimal",      # Reduce risk for read operations
                    "list_files": "minimal",
                    "search_files": "low"
                }
            },

            OperatingMode.ARCHITECT: {
                "allowed_categories": ["file_read", "communication", "analysis"],
                "denied_tools": {"write_to_file", "search_and_replace", "insert_content", "execute_command"},
                "risk_modifications": {
                    "read_file": "minimal",
                    "list_files": "minimal",
                    "search_files": "low",
                    "list_code_definition_names": "minimal"
                }
            },

            OperatingMode.DEBUG: {
                "allowed_categories": ["file_read", "command_exec", "communication", "analysis"],
                "denied_tools": {"write_to_file", "search_and_replace", "insert_content"},  # Read-only for safety
                "risk_modifications": {
                    "execute_command": "high",  # Debug commands can be risky
                    "read_file": "low",
                    "search_files": "low"
                }
            },

            OperatingMode.REVIEW: {
                "allowed_categories": ["file_read", "communication", "analysis"],
                "denied_tools": {"write_to_file", "search_and_replace", "insert_content", "execute_command"},
                "risk_modifications": {
                    "read_file": "minimal",
                    "list_files": "minimal",
                    "search_files": "minimal",
                    "list_code_definition_names": "minimal"
                }
            }
        }

        logger.info("🎯 Tool mode filter initialized")

    def get_allowed_tools_for_mode(self, mode: OperatingMode) -> Set[str]:
        """
        Get the set of allowed tools for a specific mode.

        Args:
            mode: Operating mode

        Returns:
            Set of allowed tool names
        """
        if mode not in self.mode_tool_access:
            logger.warning(f"Unknown mode: {mode}, defaulting to CODE mode")
            mode = OperatingMode.CODE

        mode_config = self.mode_tool_access[mode]
        allowed_categories = mode_config["allowed_categories"]
        denied_tools = mode_config["denied_tools"]

        # Start with all tools from allowed categories
        allowed_tools = set()
        for category in allowed_categories:
            if category in self.tool_categories:
                allowed_tools.update(self.tool_categories[category])

        # Remove explicitly denied tools
        allowed_tools -= denied_tools

        logger.debug(f"Mode {mode.value} allows {len(allowed_tools)} tools: {sorted(allowed_tools)}")
        return allowed_tools

    def is_tool_allowed(self, tool_name: str, mode: OperatingMode) -> bool:
        """
        Check if a specific tool is allowed in the given mode.

        Args:
            tool_name: Name of the tool
            mode: Operating mode

        Returns:
            True if tool is allowed, False otherwise
        """
        allowed_tools = self.get_allowed_tools_for_mode(mode)
        return tool_name in allowed_tools

    def get_modified_risk_level(self, tool_name: str, original_risk: str, mode: OperatingMode) -> str:
        """
        Get modified risk level for a tool in the given mode.

        Args:
            tool_name: Name of the tool
            original_risk: Original risk level
            mode: Operating mode

        Returns:
            Modified risk level (or original if no modification)
        """
        if mode not in self.mode_tool_access:
            return original_risk

        risk_modifications = self.mode_tool_access[mode]["risk_modifications"]
        return risk_modifications.get(tool_name, original_risk)

    def filter_tool_call(self, tool_name: str, parameters: Dict[str, Any], mode: OperatingMode) -> Dict[str, Any]:
        """
        Filter and validate a tool call for the given mode.

        Args:
            tool_name: Name of the tool
            parameters: Tool parameters
            mode: Operating mode

        Returns:
            Dict with filtering result: {"allowed": bool, "reason": str, "modified_risk": str}
        """
        if not self.is_tool_allowed(tool_name, mode):
            return {
                "allowed": False,
                "reason": f"Tool '{tool_name}' is not available in {mode.value} mode",
                "modified_risk": None
            }

        # Tool is allowed, check for any parameter restrictions based on mode
        parameter_restrictions = self._get_parameter_restrictions(tool_name, mode)

        if parameter_restrictions:
            violation = self._check_parameter_restrictions(parameters, parameter_restrictions)
            if violation:
                return {
                    "allowed": False,
                    "reason": f"Parameter restriction violated in {mode.value} mode: {violation}",
                    "modified_risk": None
                }

        # Get modified risk level
        original_risk = self._get_default_risk_level(tool_name)
        modified_risk = self.get_modified_risk_level(tool_name, original_risk, mode)

        return {
            "allowed": True,
            "reason": f"Tool allowed in {mode.value} mode",
            "modified_risk": modified_risk
        }

    def _get_parameter_restrictions(self, tool_name: str, mode: OperatingMode) -> Dict[str, Any]:
        """Get parameter restrictions for a tool in the given mode."""
        # Define mode-specific parameter restrictions
        restrictions = {
            OperatingMode.ASK: {
                "read_file": {
                    "max_file_size": 50000,  # Limit file size in ask mode
                },
                "search_files": {
                    "max_results": 20,  # Limit search results
                }
            },
            OperatingMode.ARCHITECT: {
                "read_file": {
                    "allowed_extensions": [".py", ".js", ".ts", ".java", ".go", ".rs", ".md", ".json", ".yaml", ".yml"],
                },
                "list_files": {
                    "max_depth": 3,  # Limit directory traversal depth
                }
            },
            OperatingMode.DEBUG: {
                "execute_command": {
                    "allowed_commands": ["ls", "cat", "grep", "find", "ps", "top", "df", "free", "uname"],  # Safe debug commands only
                }
            }
        }

        return restrictions.get(mode, {}).get(tool_name, {})

    def _check_parameter_restrictions(self, parameters: Dict[str, Any], restrictions: Dict[str, Any]) -> str:
        """Check if parameters violate mode restrictions."""
        for restriction, limit in restrictions.items():
            if restriction == "max_file_size":
                # Would need file size checking logic
                pass
            elif restriction == "max_results":
                if "limit" in parameters and parameters["limit"] > limit:
                    return f"Result limit {parameters['limit']} exceeds mode maximum {limit}"
            elif restriction == "allowed_extensions":
                if "path" in parameters:
                    file_path = parameters["path"]
                    if not any(file_path.endswith(ext) for ext in limit):
                        return f"File extension not allowed in this mode"
            elif restriction == "max_depth":
                if "recursive" in parameters and parameters["recursive"] and "depth" in parameters:
                    if parameters["depth"] > limit:
                        return f"Directory depth {parameters['depth']} exceeds mode maximum {limit}"
            elif restriction == "allowed_commands":
                if "command" in parameters:
                    command = parameters["command"].split()[0]  # Get base command
                    if command not in limit:
                        return f"Command '{command}' not allowed in this mode"

        return None  # No violations

    def _get_default_risk_level(self, tool_name: str) -> str:
        """Get default risk level for a tool."""
        # Default risk levels
        risk_levels = {
            "read_file": "low",
            "list_files": "low",
            "search_files": "low",
            "list_code_definition_names": "low",
            "write_to_file": "high",
            "search_and_replace": "high",
            "insert_content": "medium",
            "execute_command": "high",
            "attempt_completion": "minimal",
            "ask_followup_question": "minimal",
            "update_todo_list": "low"
        }

        return risk_levels.get(tool_name, "medium")

    def get_mode_description(self, mode: OperatingMode) -> str:
        """Get human-readable description of a mode."""
        descriptions = {
            OperatingMode.CODE: "Full coding assistant with all tools available",
            OperatingMode.ASK: "Question answering with limited file reading capabilities",
            OperatingMode.ARCHITECT: "System design and architecture analysis (read-only)",
            OperatingMode.DEBUG: "Debugging mode with diagnostic tools (no file writing)",
            OperatingMode.REVIEW: "Code review mode with analysis tools (read-only)"
        }

        return descriptions.get(mode, "Unknown mode")

    def get_available_modes(self) -> List[Dict[str, str]]:
        """Get list of all available modes with descriptions."""
        return [
            {
                "mode": mode.value,
                "description": self.get_mode_description(mode),
                "tool_count": len(self.get_allowed_tools_for_mode(mode))
            }
            for mode in OperatingMode
        ]