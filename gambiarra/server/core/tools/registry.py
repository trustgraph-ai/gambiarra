"""
Tool registry for dynamic tool management.
Provides comprehensive tool registry and validation.
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from enum import Enum


class ToolRiskLevel(Enum):
    """Tool risk levels for approval workflows."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class ToolDefinition:
    """Definition of a tool and its capabilities."""
    name: str
    description: str
    parameters: Dict[str, Any]
    risk_level: ToolRiskLevel
    requires_approval: bool
    xml_format: str


class ToolValidationError(Exception):
    """Raised when tool validation fails."""
    pass


class ToolRegistry:
    """Registry for managing available tools and their definitions."""

    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}
        self._initialize_default_tools()

    def _initialize_default_tools(self) -> None:
        """Initialize registry with default tool set."""

        # File operations
        self.register_tool(ToolDefinition(
            name="read_file",
            description="Read and view the contents of a file",
            parameters={
                "path": {"type": "string", "required": True, "description": "File path to read"}
            },
            risk_level=ToolRiskLevel.LOW,
            requires_approval=False,
            xml_format="<read_file><args><file><path>{path}</path></file></args></read_file>"
        ))

        self.register_tool(ToolDefinition(
            name="write_to_file",
            description="Write content to a file",
            parameters={
                "path": {"type": "string", "required": True, "description": "File path to write"},
                "content": {"type": "string", "required": True, "description": "Content to write"},
                "line_count": {"type": "integer", "required": True, "description": "Expected line count"}
            },
            risk_level=ToolRiskLevel.HIGH,
            requires_approval=True,
            xml_format="<write_to_file><path>{path}</path><content>{content}</content><line_count>{line_count}</line_count></write_to_file>"
        ))

        self.register_tool(ToolDefinition(
            name="list_files",
            description="List files and directories in a directory",
            parameters={
                "path": {"type": "string", "required": True, "description": "Directory path to list"},
                "recursive": {"type": "boolean", "required": False, "description": "Whether to list recursively"}
            },
            risk_level=ToolRiskLevel.LOW,
            requires_approval=False,
            xml_format="<list_files><path>{path}</path><recursive>{recursive}</recursive></list_files>"
        ))

        self.register_tool(ToolDefinition(
            name="search_files",
            description="Search for text patterns within files using regex",
            parameters={
                "path": {"type": "string", "required": True, "description": "Directory to search"},
                "regex": {"type": "string", "required": True, "description": "Regex pattern to search"},
                "file_pattern": {"type": "string", "required": False, "description": "File pattern filter"}
            },
            risk_level=ToolRiskLevel.LOW,
            requires_approval=False,
            xml_format="<search_files><path>{path}</path><regex>{regex}</regex><file_pattern>{file_pattern}</file_pattern></search_files>"
        ))

        self.register_tool(ToolDefinition(
            name="execute_command",
            description="Execute a command in the terminal",
            parameters={
                "command": {"type": "string", "required": True, "description": "Command to execute"}
            },
            risk_level=ToolRiskLevel.HIGH,
            requires_approval=True,
            xml_format="<execute_command><command>{command}</command></execute_command>"
        ))

        self.register_tool(ToolDefinition(
            name="search_and_replace",
            description="Find and replace text in a file",
            parameters={
                "path": {"type": "string", "required": True, "description": "File path"},
                "search": {"type": "string", "required": True, "description": "Text to search for"},
                "replace": {"type": "string", "required": True, "description": "Replacement text"}
            },
            risk_level=ToolRiskLevel.MEDIUM,
            requires_approval=True,
            xml_format="<search_and_replace><path>{path}</path><search>{search}</search><replace>{replace}</replace></search_and_replace>"
        ))

        self.register_tool(ToolDefinition(
            name="insert_content",
            description="Insert content at a specific line in a file",
            parameters={
                "path": {"type": "string", "required": True, "description": "File path"},
                "line_number": {"type": "integer", "required": True, "description": "Line number to insert at"},
                "content": {"type": "string", "required": True, "description": "Content to insert"}
            },
            risk_level=ToolRiskLevel.MEDIUM,
            requires_approval=True,
            xml_format="<insert_content><path>{path}</path><line_number>{line_number}</line_number><content>{content}</content></insert_content>"
        ))

        # Code analysis
        self.register_tool(ToolDefinition(
            name="list_code_definition_names",
            description="Get an overview of code definitions in a source file",
            parameters={
                "path": {"type": "string", "required": True, "description": "Source file path"}
            },
            risk_level=ToolRiskLevel.LOW,
            requires_approval=False,
            xml_format="<list_code_definition_names><path>{path}</path></list_code_definition_names>"
        ))

        # Workflow management
        self.register_tool(ToolDefinition(
            name="attempt_completion",
            description="Signal that a task has been completed",
            parameters={
                "result": {"type": "string", "required": True, "description": "Description of what was accomplished"}
            },
            risk_level=ToolRiskLevel.LOW,
            requires_approval=False,
            xml_format="<attempt_completion><result>{result}</result></attempt_completion>"
        ))

        self.register_tool(ToolDefinition(
            name="ask_followup_question",
            description="Ask the user a follow-up question for clarification",
            parameters={
                "question": {"type": "string", "required": True, "description": "Question to ask"}
            },
            risk_level=ToolRiskLevel.LOW,
            requires_approval=False,
            xml_format="<ask_followup_question><question>{question}</question></ask_followup_question>"
        ))

        self.register_tool(ToolDefinition(
            name="update_todo_list",
            description="Create or update a todo list to track progress",
            parameters={
                "todos": {"type": "string", "required": True, "description": "Todo list in markdown format"}
            },
            risk_level=ToolRiskLevel.LOW,
            requires_approval=False,
            xml_format="<update_todo_list><todos>{todos}</todos></update_todo_list>"
        ))

    def register_tool(self, tool: ToolDefinition) -> None:
        """Register a new tool in the registry."""
        self._tools[tool.name] = tool

    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        """Get tool definition by name."""
        return self._tools.get(name)

    def list_tools(self) -> List[str]:
        """Get list of all registered tool names."""
        return list(self._tools.keys())

    def get_available_tools(self) -> List[str]:
        """Get list of available tool names (alias for compatibility)."""
        return self.list_tools()

    def validate_tool_call(self, tool_name: str, parameters: Dict[str, Any]) -> bool:
        """Validate a tool call against its definition."""
        tool = self.get_tool(tool_name)
        if not tool:
            raise ToolValidationError(f"Unknown tool: {tool_name}")

        # Check required parameters
        for param_name, param_def in tool.parameters.items():
            if param_def.get("required", False) and param_name not in parameters:
                raise ToolValidationError(f"Missing required parameter '{param_name}' for tool '{tool_name}'")

        # Check parameter types
        for param_name, param_value in parameters.items():
            if param_name in tool.parameters:
                param_def = tool.parameters[param_name]
                expected_type = param_def.get("type")

                if expected_type == "string" and not isinstance(param_value, str):
                    raise ToolValidationError(f"Parameter '{param_name}' must be a string")
                elif expected_type == "integer" and not isinstance(param_value, int):
                    raise ToolValidationError(f"Parameter '{param_name}' must be an integer")
                elif expected_type == "boolean" and not isinstance(param_value, bool):
                    raise ToolValidationError(f"Parameter '{param_name}' must be a boolean")

        return True

    def get_tool_description(self, tool_name: str) -> Optional[str]:
        """Get tool description for prompts."""
        tool = self.get_tool(tool_name)
        return tool.description if tool else None

    def requires_approval(self, tool_name: str) -> bool:
        """Check if tool requires user approval."""
        tool = self.get_tool(tool_name)
        return tool.requires_approval if tool else True

    def get_risk_level(self, tool_name: str) -> Optional[ToolRiskLevel]:
        """Get tool risk level."""
        tool = self.get_tool(tool_name)
        return tool.risk_level if tool else None


# Global registry instance
_tool_registry = ToolRegistry()


def get_tool_registry() -> ToolRegistry:
    """Get the global tool registry instance."""
    return _tool_registry