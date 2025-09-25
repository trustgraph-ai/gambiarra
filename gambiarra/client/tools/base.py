"""
Base classes and interfaces for Gambiarra client-side tools.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class ToolResult:
    """Result of a tool execution."""
    status: str  # "success" or "error"
    data: Any = None
    metadata: Dict[str, Any] = None
    error: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

    @classmethod
    def success(cls, data: Any = None, metadata: Dict[str, Any] = None) -> "ToolResult":
        """Create a successful result."""
        return cls(status="success", data=data, metadata=metadata or {})

    @classmethod
    def create_error(cls, code: str, message: str, details: Dict[str, Any] = None) -> "ToolResult":
        """Create an error result."""
        return cls(
            status="error",
            error={
                "code": code,
                "message": message,
                "details": details or {}
            }
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "status": self.status,
            "data": self.data,
            "metadata": self.metadata,
            "error": self.error
        }


class BaseTool(ABC):
    """Base class for all client-side tools."""

    def __init__(self, security_manager):
        self.security_manager = security_manager

    @property
    @abstractmethod
    def name(self) -> str:
        """Tool name."""
        pass

    @property
    @abstractmethod
    def risk_level(self) -> str:
        """Risk level: low, medium, high."""
        pass

    @abstractmethod
    async def execute(self, parameters: Dict[str, Any]) -> ToolResult:
        """Execute the tool with given parameters."""
        pass

    def validate_parameters(self, parameters: Dict[str, Any], required: list, optional: list = None) -> None:
        """Validate tool parameters."""
        optional = optional or []

        # Check required parameters
        for param in required:
            if param not in parameters:
                raise ValueError(f"Missing required parameter: {param}")

        # Check for unknown parameters
        all_params = set(required + optional)
        provided_params = set(parameters.keys())
        unknown_params = provided_params - all_params

        if unknown_params:
            logger.warning(f"Unknown parameters for {self.name}: {unknown_params}")

    async def pre_execute(self, parameters: Dict[str, Any]) -> None:
        """Pre-execution hook for validation and setup."""
        pass

    async def post_execute(self, result: ToolResult, parameters: Dict[str, Any]) -> ToolResult:
        """Post-execution hook for cleanup and result processing."""
        return result


class FileOperationTool(BaseTool):
    """Base class for file operation tools."""

    def validate_path(self, path: str) -> str:
        """Validate and resolve file path."""
        return self.security_manager.validate_path(path)

    async def pre_execute(self, parameters: Dict[str, Any]) -> None:
        """Validate file paths in parameters."""
        await super().pre_execute(parameters)

        # Validate path parameter if present
        if "path" in parameters:
            parameters["path"] = self.validate_path(parameters["path"])


class CommandExecutionTool(BaseTool):
    """Base class for command execution tools."""

    def validate_command(self, command: str) -> bool:
        """Validate command is allowed."""
        return self.security_manager.is_command_allowed(command)

    async def pre_execute(self, parameters: Dict[str, Any]) -> None:
        """Validate command in parameters."""
        await super().pre_execute(parameters)

        # Validate command parameter if present
        if "command" in parameters:
            if not self.validate_command(parameters["command"]):
                raise ValueError(f"Command blocked by security policy: {parameters['command']}")


class ToolManager:
    """Manages all client-side tools."""

    def __init__(self, security_manager):
        self.security_manager = security_manager
        self.tools: Dict[str, BaseTool] = {}

    def register_tool(self, tool: BaseTool) -> None:
        """Register a tool."""
        self.tools[tool.name] = tool
        logger.info(f"🔧 Registered tool: {tool.name}")

    def get_tool(self, name: str) -> Optional[BaseTool]:
        """Get tool by name."""
        return self.tools.get(name)

    def list_tools(self) -> list:
        """List all available tools."""
        return list(self.tools.keys())

    async def execute_tool(self, name: str, parameters: Dict[str, Any]) -> ToolResult:
        """Execute a tool with given parameters."""
        tool = self.get_tool(name)
        if not tool:
            return ToolResult.create_error(
                "TOOL_NOT_FOUND",
                f"Tool '{name}' not found",
                {"available_tools": self.list_tools()}
            )

        try:
            # Unwrap nested args structure for tool execution
            unwrapped_params = self._unwrap_parameters(name, parameters)

            # Pre-execution
            await tool.pre_execute(unwrapped_params)

            # Execute
            logger.info(f"🔧 Executing tool: {name}")
            result = await tool.execute(unwrapped_params)

            # Post-execution
            result = await tool.post_execute(result, unwrapped_params)

            logger.info(f"✅ Tool {name} completed: {result.status}")
            return result

        except Exception as e:
            logger.error(f"❌ Tool {name} failed: {e}")
            return ToolResult.create_error(
                "TOOL_EXECUTION_ERROR",
                str(e),
                {"tool": name, "parameters": parameters}
            )

    def _unwrap_parameters(self, tool_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Unwrap nested args structure to flat parameters for tool execution."""
        if "args" not in parameters:
            # Already in flat format, return as-is
            return parameters

        args = parameters["args"]

        if tool_name == "read_file":
            # Special case: read_file has args.file.path structure
            if isinstance(args, dict) and "file" in args:
                file_params = args["file"]
                if isinstance(file_params, dict) and "path" in file_params:
                    return {"path": file_params["path"]}
            # Fallback to flat args
            return args
        else:
            # Standard nested args: return the args content
            return args