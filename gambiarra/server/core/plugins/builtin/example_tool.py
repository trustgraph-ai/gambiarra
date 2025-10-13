"""
Example tool plugin demonstrating the plugin system.
Shows how to create a custom tool plugin.
"""

from typing import Dict, Any, List
from gambiarra.server.core.plugins.base import ToolPlugin, PluginInterface, PluginType


class ExampleToolPlugin(ToolPlugin):
    """Example tool plugin that provides utility functions."""

    def __init__(self, metadata):
        super().__init__(metadata)

    async def initialize(self, config: Dict[str, Any]) -> bool:
        """Initialize the example tool plugin."""
        self.config = config
        self.logger.info("Example tool plugin initialized")
        return True

    async def cleanup(self) -> None:
        """Clean up plugin resources."""
        self.logger.info("Example tool plugin cleaned up")

    async def execute_tool(self, tool_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool provided by this plugin."""
        if tool_name == "echo":
            return await self._execute_echo(parameters)
        elif tool_name == "calculate":
            return await self._execute_calculate(parameters)
        else:
            return {
                "success": False,
                "error": f"Unknown tool: {tool_name}"
            }

    async def _execute_echo(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Echo tool that returns the input message."""
        message = parameters.get("message", "")
        return {
            "success": True,
            "data": {
                "echo": message,
                "length": len(message)
            }
        }

    async def _execute_calculate(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Simple calculator tool."""
        try:
            operation = parameters.get("operation")
            a = float(parameters.get("a", 0))
            b = float(parameters.get("b", 0))

            if operation == "add":
                result = a + b
            elif operation == "subtract":
                result = a - b
            elif operation == "multiply":
                result = a * b
            elif operation == "divide":
                if b == 0:
                    return {"success": False, "error": "Division by zero"}
                result = a / b
            else:
                return {"success": False, "error": f"Unknown operation: {operation}"}

            return {
                "success": True,
                "data": {
                    "result": result,
                    "operation": operation,
                    "operands": [a, b]
                }
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """Get definitions of tools provided by this plugin."""
        return [
            {
                "name": "echo",
                "description": "Echo back a message with its length",
                "parameters": {
                    "message": {
                        "type": "string",
                        "required": True,
                        "description": "Message to echo"
                    }
                },
                "returns": {
                    "echo": "string",
                    "length": "integer"
                }
            },
            {
                "name": "calculate",
                "description": "Perform basic arithmetic operations",
                "parameters": {
                    "operation": {
                        "type": "string",
                        "required": True,
                        "enum": ["add", "subtract", "multiply", "divide"],
                        "description": "Arithmetic operation to perform"
                    },
                    "a": {
                        "type": "number",
                        "required": True,
                        "description": "First operand"
                    },
                    "b": {
                        "type": "number",
                        "required": True,
                        "description": "Second operand"
                    }
                },
                "returns": {
                    "result": "number",
                    "operation": "string",
                    "operands": "array"
                }
            }
        ]


# Plugin factory function
def create_plugin():
    """Create and return the plugin instance."""
    metadata = PluginInterface.create_metadata(
        name="example_tool",
        version="1.0.0",
        plugin_type=PluginType.TOOL,
        description="Example tool plugin with echo and calculator functions",
        author="Gambiarra Team"
    )
    return ExampleToolPlugin(metadata)