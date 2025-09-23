"""
Tool versioning and compatibility system.
Manages tool versions and ensures compatibility across updates.
"""

import logging
import json
import hashlib
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class CompatibilityLevel(Enum):
    """Compatibility levels between tool versions."""
    COMPATIBLE = "compatible"           # Fully compatible
    MINOR_BREAKING = "minor_breaking"   # Some parameters changed
    MAJOR_BREAKING = "major_breaking"   # Significant changes
    INCOMPATIBLE = "incompatible"       # Complete incompatibility


@dataclass
class ToolParameter:
    """Tool parameter definition."""
    name: str
    type: str
    required: bool = False
    default: Any = None
    description: str = ""


@dataclass
class ToolVersion:
    """Tool version information."""
    name: str
    version: str
    description: str
    parameters: List[ToolParameter]
    capabilities: List[str]
    deprecated: bool = False
    deprecation_message: Optional[str] = None

    # Compatibility information
    compatible_versions: List[str] = None
    breaking_changes: List[str] = None

    # Metadata
    created_at: str = ""
    checksum: str = ""

    def __post_init__(self):
        if self.compatible_versions is None:
            self.compatible_versions = []
        if self.breaking_changes is None:
            self.breaking_changes = []


class ToolVersionManager:
    """Manages tool versions and compatibility."""

    def __init__(self, registry_path: str = "tool_versions.json"):
        self.registry_path = Path(registry_path)
        self.versions: Dict[str, List[ToolVersion]] = {}
        self.current_versions: Dict[str, str] = {}
        self.compatibility_cache: Dict[str, Dict[str, CompatibilityLevel]] = {}

        self._load_registry()

    def _load_registry(self) -> None:
        """Load tool versions from registry file."""
        if not self.registry_path.exists():
            logger.info("No tool version registry found, starting fresh")
            return

        try:
            with open(self.registry_path, 'r') as f:
                data = json.load(f)

            for tool_name, versions_data in data.get("versions", {}).items():
                self.versions[tool_name] = []
                for version_data in versions_data:
                    # Convert parameter dicts back to ToolParameter objects
                    parameters = [
                        ToolParameter(**param_data)
                        for param_data in version_data.get("parameters", [])
                    ]
                    version_data["parameters"] = parameters

                    version = ToolVersion(**version_data)
                    self.versions[tool_name].append(version)

            self.current_versions = data.get("current_versions", {})

            logger.info(f"Loaded {len(self.versions)} tool versions from registry")

        except Exception as e:
            logger.error(f"Error loading tool version registry: {e}")

    def _save_registry(self) -> None:
        """Save tool versions to registry file."""
        try:
            # Convert to serializable format
            data = {
                "versions": {},
                "current_versions": self.current_versions
            }

            for tool_name, versions in self.versions.items():
                data["versions"][tool_name] = []
                for version in versions:
                    version_dict = asdict(version)
                    # Convert ToolParameter objects to dicts
                    version_dict["parameters"] = [
                        asdict(param) for param in version.parameters
                    ]
                    data["versions"][tool_name].append(version_dict)

            self.registry_path.parent.mkdir(exist_ok=True)
            with open(self.registry_path, 'w') as f:
                json.dump(data, f, indent=2)

            logger.debug(f"Saved tool version registry to {self.registry_path}")

        except Exception as e:
            logger.error(f"Error saving tool version registry: {e}")

    def register_tool_version(self, tool_version: ToolVersion) -> None:
        """Register a new tool version."""
        tool_name = tool_version.name

        # Calculate checksum for version
        version_str = json.dumps(asdict(tool_version), sort_keys=True)
        tool_version.checksum = hashlib.sha256(version_str.encode()).hexdigest()[:12]

        if tool_name not in self.versions:
            self.versions[tool_name] = []

        # Check if this exact version already exists
        existing_version = self.get_tool_version(tool_name, tool_version.version)
        if existing_version:
            if existing_version.checksum == tool_version.checksum:
                logger.debug(f"Tool version {tool_name} v{tool_version.version} already registered")
                return
            else:
                logger.warning(f"Tool version {tool_name} v{tool_version.version} checksum mismatch")

        self.versions[tool_name].append(tool_version)

        # Set as current version if it's the first or a newer version
        if tool_name not in self.current_versions or self._is_newer_version(tool_version.version, self.current_versions[tool_name]):
            self.current_versions[tool_name] = tool_version.version

        # Clear compatibility cache for this tool
        self.compatibility_cache.pop(tool_name, None)

        self._save_registry()
        logger.info(f"Registered tool version: {tool_name} v{tool_version.version}")

    def get_tool_version(self, tool_name: str, version: str) -> Optional[ToolVersion]:
        """Get specific tool version."""
        if tool_name not in self.versions:
            return None

        for tool_version in self.versions[tool_name]:
            if tool_version.version == version:
                return tool_version

        return None

    def get_current_version(self, tool_name: str) -> Optional[ToolVersion]:
        """Get current version of a tool."""
        if tool_name not in self.current_versions:
            return None

        return self.get_tool_version(tool_name, self.current_versions[tool_name])

    def get_all_versions(self, tool_name: str) -> List[ToolVersion]:
        """Get all versions of a tool."""
        return self.versions.get(tool_name, [])

    def set_current_version(self, tool_name: str, version: str) -> bool:
        """Set the current version of a tool."""
        if not self.get_tool_version(tool_name, version):
            logger.error(f"Cannot set current version: {tool_name} v{version} not found")
            return False

        self.current_versions[tool_name] = version
        self._save_registry()
        logger.info(f"Set current version: {tool_name} v{version}")
        return True

    def check_compatibility(self, tool_name: str, from_version: str, to_version: str) -> CompatibilityLevel:
        """Check compatibility between two tool versions."""
        cache_key = f"{from_version}->{to_version}"

        if tool_name in self.compatibility_cache and cache_key in self.compatibility_cache[tool_name]:
            return self.compatibility_cache[tool_name][cache_key]

        from_tool = self.get_tool_version(tool_name, from_version)
        to_tool = self.get_tool_version(tool_name, to_version)

        if not from_tool or not to_tool:
            compatibility = CompatibilityLevel.INCOMPATIBLE
        else:
            compatibility = self._analyze_compatibility(from_tool, to_tool)

        # Cache result
        if tool_name not in self.compatibility_cache:
            self.compatibility_cache[tool_name] = {}
        self.compatibility_cache[tool_name][cache_key] = compatibility

        return compatibility

    def _analyze_compatibility(self, from_version: ToolVersion, to_version: ToolVersion) -> CompatibilityLevel:
        """Analyze compatibility between two tool versions."""
        # Check if versions are explicitly marked as compatible
        if to_version.version in from_version.compatible_versions:
            return CompatibilityLevel.COMPATIBLE

        # Check parameter compatibility
        from_params = {p.name: p for p in from_version.parameters}
        to_params = {p.name: p for p in to_version.parameters}

        # Check for removed required parameters
        for param_name, param in from_params.items():
            if param.required and param_name not in to_params:
                return CompatibilityLevel.MAJOR_BREAKING

        # Check for new required parameters without defaults
        for param_name, param in to_params.items():
            if param.required and param.default is None and param_name not in from_params:
                return CompatibilityLevel.MAJOR_BREAKING

        # Check for type changes in existing parameters
        minor_changes = False
        for param_name in from_params:
            if param_name in to_params:
                from_param = from_params[param_name]
                to_param = to_params[param_name]

                if from_param.type != to_param.type:
                    return CompatibilityLevel.MAJOR_BREAKING

                if from_param.required != to_param.required:
                    minor_changes = True

        # Check capabilities
        from_caps = set(from_version.capabilities)
        to_caps = set(to_version.capabilities)

        if not from_caps.issubset(to_caps):
            # Some capabilities were removed
            return CompatibilityLevel.MINOR_BREAKING

        if minor_changes or len(to_caps - from_caps) > 0:
            # Minor changes or new capabilities
            return CompatibilityLevel.MINOR_BREAKING

        return CompatibilityLevel.COMPATIBLE

    def _is_newer_version(self, version1: str, version2: str) -> bool:
        """Check if version1 is newer than version2."""
        # Simple semantic versioning comparison
        try:
            v1_parts = [int(x) for x in version1.split('.')]
            v2_parts = [int(x) for x in version2.split('.')]

            # Pad shorter version with zeros
            max_len = max(len(v1_parts), len(v2_parts))
            v1_parts.extend([0] * (max_len - len(v1_parts)))
            v2_parts.extend([0] * (max_len - len(v2_parts)))

            return v1_parts > v2_parts

        except ValueError:
            # Fall back to string comparison if not numeric
            return version1 > version2

    def deprecate_version(self, tool_name: str, version: str, message: str) -> bool:
        """Mark a tool version as deprecated."""
        tool_version = self.get_tool_version(tool_name, version)
        if not tool_version:
            return False

        tool_version.deprecated = True
        tool_version.deprecation_message = message

        self._save_registry()
        logger.info(f"Deprecated tool version: {tool_name} v{version}")
        return True

    def get_deprecated_versions(self) -> List[tuple]:
        """Get all deprecated tool versions."""
        deprecated = []
        for tool_name, versions in self.versions.items():
            for version in versions:
                if version.deprecated:
                    deprecated.append((tool_name, version.version, version.deprecation_message))
        return deprecated

    def validate_tool_call(self, tool_name: str, version: str, parameters: Dict[str, Any]) -> tuple[bool, List[str]]:
        """Validate a tool call against a specific version."""
        tool_version = self.get_tool_version(tool_name, version)
        if not tool_version:
            return False, [f"Tool {tool_name} version {version} not found"]

        errors = []

        # Check for missing required parameters
        tool_params = {p.name: p for p in tool_version.parameters}
        for param in tool_version.parameters:
            if param.required and param.name not in parameters:
                if param.default is None:
                    errors.append(f"Missing required parameter: {param.name}")

        # Check for unknown parameters
        for param_name in parameters:
            if param_name not in tool_params:
                errors.append(f"Unknown parameter: {param_name}")

        # Type validation would go here (simplified for now)

        return len(errors) == 0, errors

    def get_migration_path(self, tool_name: str, from_version: str, to_version: str) -> Optional[List[str]]:
        """Get migration path between tool versions."""
        if not self.get_tool_version(tool_name, from_version) or not self.get_tool_version(tool_name, to_version):
            return None

        # Simple direct migration for now
        compatibility = self.check_compatibility(tool_name, from_version, to_version)

        if compatibility == CompatibilityLevel.INCOMPATIBLE:
            return None

        return [from_version, to_version]

    def get_stats(self) -> Dict[str, Any]:
        """Get tool versioning statistics."""
        total_tools = len(self.versions)
        total_versions = sum(len(versions) for versions in self.versions.values())
        deprecated_count = sum(
            1 for versions in self.versions.values()
            for version in versions if version.deprecated
        )

        return {
            "total_tools": total_tools,
            "total_versions": total_versions,
            "deprecated_versions": deprecated_count,
            "tools": list(self.versions.keys()),
            "current_versions": dict(self.current_versions)
        }


# Global version manager
_version_manager = ToolVersionManager()


def get_version_manager() -> ToolVersionManager:
    """Get the global tool version manager."""
    return _version_manager


def register_tool_version(name: str, version: str, description: str,
                         parameters: List[ToolParameter], capabilities: List[str]) -> None:
    """Helper function to register a tool version."""
    import time

    tool_version = ToolVersion(
        name=name,
        version=version,
        description=description,
        parameters=parameters,
        capabilities=capabilities,
        created_at=str(int(time.time()))
    )

    _version_manager.register_tool_version(tool_version)


def version_compatible(tool_name: str, required_version: str, available_version: str) -> bool:
    """Check if available version is compatible with required version."""
    compatibility = _version_manager.check_compatibility(tool_name, required_version, available_version)
    return compatibility in [CompatibilityLevel.COMPATIBLE, CompatibilityLevel.MINOR_BREAKING]