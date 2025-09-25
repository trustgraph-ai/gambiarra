"""
Base plugin interface and framework.
Enables dynamic tool loading and extensibility for plugin architecture.
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Type
from dataclasses import dataclass
from enum import Enum


class PluginType(Enum):
    """Types of plugins supported by the system."""
    TOOL = "tool"
    PROVIDER = "provider"
    WORKFLOW_STEP = "workflow_step"
    EVENT_HANDLER = "event_handler"
    CONTEXT_ANALYZER = "context_analyzer"


class PluginStatus(Enum):
    """Plugin status states."""
    LOADED = "loaded"
    ACTIVE = "active"
    DISABLED = "disabled"
    ERROR = "error"


@dataclass
class PluginVersion:
    """Plugin version information."""
    major: int
    minor: int
    patch: int
    pre_release: Optional[str] = None

    def __str__(self) -> str:
        version = f"{self.major}.{self.minor}.{self.patch}"
        if self.pre_release:
            version += f"-{self.pre_release}"
        return version

    def is_compatible(self, other: 'PluginVersion') -> bool:
        """Check if this version is compatible with another."""
        # Simple semantic versioning compatibility
        if self.major != other.major:
            return False
        return self.minor >= other.minor


@dataclass
class PluginMetadata:
    """Plugin metadata and information."""
    name: str
    description: str
    version: PluginVersion
    author: str
    plugin_type: PluginType

    # Dependencies
    dependencies: List[str]
    min_system_version: Optional[PluginVersion] = None
    max_system_version: Optional[PluginVersion] = None

    # Configuration
    config_schema: Optional[Dict[str, Any]] = None
    permissions: List[str] = None

    def __post_init__(self):
        if self.permissions is None:
            self.permissions = []


class Plugin(ABC):
    """Abstract base class for all plugins."""

    def __init__(self, metadata: PluginMetadata):
        self.metadata = metadata
        self.status = PluginStatus.LOADED
        self.config: Dict[str, Any] = {}
        self.logger = logging.getLogger(f"plugin.{metadata.name}")

    @abstractmethod
    async def initialize(self, config: Dict[str, Any]) -> bool:
        """Initialize the plugin with configuration."""
        pass

    @abstractmethod
    async def cleanup(self) -> None:
        """Clean up plugin resources."""
        pass

    @abstractmethod
    def get_capabilities(self) -> Dict[str, Any]:
        """Get plugin capabilities."""
        pass

    async def validate_config(self, config: Dict[str, Any]) -> bool:
        """Validate plugin configuration."""
        if not self.metadata.config_schema:
            return True

        # Basic validation - could be enhanced with jsonschema
        required_fields = self.metadata.config_schema.get("required", [])
        for field in required_fields:
            if field not in config:
                self.logger.error(f"Missing required config field: {field}")
                return False

        return True

    def set_status(self, status: PluginStatus) -> None:
        """Set plugin status."""
        old_status = self.status
        self.status = status
        self.logger.info(f"Plugin status changed: {old_status.value} -> {status.value}")

    def get_info(self) -> Dict[str, Any]:
        """Get plugin information."""
        return {
            "name": self.metadata.name,
            "description": self.metadata.description,
            "version": str(self.metadata.version),
            "author": self.metadata.author,
            "type": self.metadata.plugin_type.value,
            "status": self.status.value,
            "dependencies": self.metadata.dependencies,
            "capabilities": self.get_capabilities()
        }


class ToolPlugin(Plugin):
    """Base class for tool plugins."""

    def __init__(self, metadata: PluginMetadata):
        super().__init__(metadata)
        if metadata.plugin_type != PluginType.TOOL:
            raise ValueError("ToolPlugin requires plugin_type=TOOL")

    @abstractmethod
    async def execute_tool(self, tool_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool provided by this plugin."""
        pass

    @abstractmethod
    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """Get definitions of tools provided by this plugin."""
        pass

    def get_capabilities(self) -> Dict[str, Any]:
        """Get tool plugin capabilities."""
        return {
            "tools": [tool["name"] for tool in self.get_tool_definitions()],
            "tool_count": len(self.get_tool_definitions())
        }


class ProviderPlugin(Plugin):
    """Base class for AI provider plugins."""

    def __init__(self, metadata: PluginMetadata):
        super().__init__(metadata)
        if metadata.plugin_type != PluginType.PROVIDER:
            raise ValueError("ProviderPlugin requires plugin_type=PROVIDER")

    @abstractmethod
    async def generate_completion(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """Generate completion using this provider."""
        pass

    @abstractmethod
    async def health_check(self) -> Dict[str, Any]:
        """Check provider health."""
        pass

    def get_capabilities(self) -> Dict[str, Any]:
        """Get provider plugin capabilities."""
        return {
            "streaming": False,
            "tool_calling": False,
            "max_tokens": 4096
        }


class WorkflowStepPlugin(Plugin):
    """Base class for workflow step plugins."""

    def __init__(self, metadata: PluginMetadata):
        super().__init__(metadata)
        if metadata.plugin_type != PluginType.WORKFLOW_STEP:
            raise ValueError("WorkflowStepPlugin requires plugin_type=WORKFLOW_STEP")

    @abstractmethod
    async def execute_step(self, step_config: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a workflow step."""
        pass

    @abstractmethod
    def get_step_definition(self) -> Dict[str, Any]:
        """Get workflow step definition."""
        pass

    def get_capabilities(self) -> Dict[str, Any]:
        """Get workflow step plugin capabilities."""
        step_def = self.get_step_definition()
        return {
            "step_type": step_def.get("type"),
            "parameters": step_def.get("parameters", {}),
            "async": True
        }


class PluginInterface:
    """Interface for plugin system integration."""

    @staticmethod
    def create_metadata(name: str,
                       version: str,
                       plugin_type: PluginType,
                       description: str = "",
                       author: str = "Unknown",
                       dependencies: List[str] = None) -> PluginMetadata:
        """Helper to create plugin metadata."""
        version_parts = version.split(".")
        if len(version_parts) < 3:
            raise ValueError("Version must be in format major.minor.patch")

        return PluginMetadata(
            name=name,
            description=description,
            version=PluginVersion(
                major=int(version_parts[0]),
                minor=int(version_parts[1]),
                patch=int(version_parts[2])
            ),
            author=author,
            plugin_type=plugin_type,
            dependencies=dependencies or []
        )

    @staticmethod
    def validate_plugin_class(plugin_class: Type[Plugin]) -> bool:
        """Validate that a class implements the Plugin interface correctly."""
        required_methods = ["initialize", "cleanup", "get_capabilities"]

        for method in required_methods:
            if not hasattr(plugin_class, method):
                return False
            if not callable(getattr(plugin_class, method)):
                return False

        return True