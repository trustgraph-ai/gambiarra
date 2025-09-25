"""
Plugin manager for dynamic loading and management.
Handles plugin lifecycle, dependencies, and registration.
"""

import asyncio
import importlib
import importlib.util
import logging
import os
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional, Type, Set
import json
import traceback

from .base import Plugin, PluginMetadata, PluginType, PluginStatus, PluginVersion
from ..events.bus import get_event_bus, EventTypes, publish_event

logger = logging.getLogger(__name__)


class PluginLoadError(Exception):
    """Raised when a plugin fails to load."""
    pass


class PluginDependencyError(Exception):
    """Raised when plugin dependencies cannot be resolved."""
    pass


class PluginManager:
    """Manages plugin loading, dependencies, and lifecycle."""

    def __init__(self, plugin_directories: List[str] = None):
        self.plugins: Dict[str, Plugin] = {}
        self.plugin_directories = plugin_directories or []
        self.dependency_graph: Dict[str, Set[str]] = {}
        self.event_bus = get_event_bus()

    def list_loaded_plugins(self) -> Dict[str, Dict[str, Any]]:
        """Get information about all loaded plugins."""
        return {
            name: {
                "metadata": plugin.metadata.__dict__,
                "status": plugin.status.value,
                "type": plugin.metadata.plugin_type.value
            }
            for name, plugin in self.plugins.items()
        }

    def get_stats(self) -> Dict[str, Any]:
        """Get plugin manager statistics."""
        total_plugins = len(self.plugins)
        active_plugins = sum(1 for p in self.plugins.values() if p.status == PluginStatus.ACTIVE)
        failed_plugins = sum(1 for p in self.plugins.values() if p.status == PluginStatus.ERROR)

        return {
            "loaded_plugins": total_plugins,
            "active_plugins": active_plugins,
            "failed_loads": failed_plugins,
            "plugin_directories": self.plugin_directories
        }

    async def initialize(self) -> None:
        """Initialize the plugin manager."""
        logger.info("🔌 Initializing plugin manager...")

        # Add default plugin directories
        if not self.plugin_directories:
            self.plugin_directories = [
                "server/plugins",
                "server/core/plugins/builtin"
            ]

        # Create plugin directories if they don't exist
        for directory in self.plugin_directories:
            Path(directory).mkdir(parents=True, exist_ok=True)

        logger.info(f"Plugin directories: {self.plugin_directories}")

    async def scan_and_load_plugins(self) -> None:
        """Scan directories and load all valid plugins."""
        plugin_manifests = await self._scan_plugin_manifests()

        # Sort by dependencies
        load_order = self._resolve_load_order(plugin_manifests)

        loaded_count = 0
        for plugin_name in load_order:
            try:
                manifest = plugin_manifests[plugin_name]
                await self._load_plugin_from_manifest(manifest)
                loaded_count += 1
            except Exception as e:
                logger.error(f"Failed to load plugin {plugin_name}: {e}")

        logger.info(f"🔌 Loaded {loaded_count}/{len(plugin_manifests)} plugins")

    async def _scan_plugin_manifests(self) -> Dict[str, Dict[str, Any]]:
        """Scan for plugin manifest files."""
        manifests = {}

        for directory in self.plugin_directories:
            dir_path = Path(directory)
            if not dir_path.exists():
                continue

            # Look for plugin.json files
            for manifest_file in dir_path.rglob("plugin.json"):
                try:
                    with open(manifest_file, 'r') as f:
                        manifest = json.load(f)

                    # Validate manifest
                    if self._validate_manifest(manifest):
                        plugin_name = manifest["name"]
                        manifest["_directory"] = str(manifest_file.parent)
                        manifests[plugin_name] = manifest
                        logger.debug(f"Found plugin manifest: {plugin_name}")

                except Exception as e:
                    logger.error(f"Error reading manifest {manifest_file}: {e}")

        return manifests

    def _validate_manifest(self, manifest: Dict[str, Any]) -> bool:
        """Validate plugin manifest structure."""
        required_fields = ["name", "version", "type", "entry_point"]

        for field in required_fields:
            if field not in manifest:
                logger.error(f"Manifest missing required field: {field}")
                return False

        # Validate plugin type
        try:
            PluginType(manifest["type"])
        except ValueError:
            logger.error(f"Invalid plugin type: {manifest['type']}")
            return False

        return True

    def _resolve_load_order(self, manifests: Dict[str, Dict[str, Any]]) -> List[str]:
        """Resolve plugin load order based on dependencies."""
        # Simple topological sort
        graph = {}
        for name, manifest in manifests.items():
            dependencies = manifest.get("dependencies", [])
            graph[name] = set(dep for dep in dependencies if dep in manifests)

        # Kahn's algorithm for topological sorting
        in_degree = {name: 0 for name in graph}
        for name, deps in graph.items():
            for dep in deps:
                in_degree[name] += 1

        queue = [name for name, degree in in_degree.items() if degree == 0]
        result = []

        while queue:
            current = queue.pop(0)
            result.append(current)

            for name, deps in graph.items():
                if current in deps:
                    in_degree[name] -= 1
                    if in_degree[name] == 0:
                        queue.append(name)

        if len(result) != len(manifests):
            # Circular dependency detected
            missing = set(manifests.keys()) - set(result)
            raise PluginDependencyError(f"Circular dependency detected in plugins: {missing}")

        return result

    async def _load_plugin_from_manifest(self, manifest: Dict[str, Any]) -> None:
        """Load a plugin from its manifest."""
        plugin_name = manifest["name"]
        plugin_dir = manifest["_directory"]
        entry_point = manifest["entry_point"]

        try:
            # Add plugin directory to Python path
            if plugin_dir not in sys.path:
                sys.path.insert(0, plugin_dir)

            # Import the plugin module
            module_name = entry_point.split('.')[0]
            spec = importlib.util.spec_from_file_location(
                module_name,
                os.path.join(plugin_dir, f"{module_name}.py")
            )

            if spec is None or spec.loader is None:
                raise PluginLoadError(f"Could not load plugin module: {entry_point}")

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Get plugin class
            class_name = entry_point.split('.')[-1]
            if not hasattr(module, class_name):
                raise PluginLoadError(f"Plugin class {class_name} not found in module")

            plugin_class = getattr(module, class_name)

            # Create plugin metadata
            metadata = self._create_metadata_from_manifest(manifest)

            # Instantiate plugin
            plugin = plugin_class(metadata)

            # Initialize plugin
            config = manifest.get("config", {})
            if await plugin.initialize(config):
                plugin.set_status(PluginStatus.ACTIVE)
                self.plugins[plugin_name] = plugin

                # Publish plugin loaded event
                await publish_event(
                    event_type="plugin.loaded",
                    data={
                        "plugin_name": plugin_name,
                        "plugin_type": manifest["type"],
                        "version": manifest["version"]
                    },
                    source="plugin_manager"
                )

                logger.info(f"🔌 Loaded plugin: {plugin_name} v{manifest['version']}")
            else:
                raise PluginLoadError(f"Plugin initialization failed: {plugin_name}")

        except Exception as e:
            logger.error(f"Failed to load plugin {plugin_name}: {e}")
            logger.error(traceback.format_exc())
            raise PluginLoadError(f"Plugin load error: {e}")

    def _create_metadata_from_manifest(self, manifest: Dict[str, Any]) -> PluginMetadata:
        """Create PluginMetadata from manifest."""
        version_str = manifest["version"]
        version_parts = version_str.split(".")

        return PluginMetadata(
            name=manifest["name"],
            description=manifest.get("description", ""),
            version=PluginVersion(
                major=int(version_parts[0]),
                minor=int(version_parts[1]),
                patch=int(version_parts[2])
            ),
            author=manifest.get("author", "Unknown"),
            plugin_type=PluginType(manifest["type"]),
            dependencies=manifest.get("dependencies", []),
            config_schema=manifest.get("config_schema"),
            permissions=manifest.get("permissions", [])
        )

    def get_plugin(self, name: str) -> Optional[Plugin]:
        """Get a plugin by name."""
        return self.plugins.get(name)

    def get_plugins_by_type(self, plugin_type: PluginType) -> List[Plugin]:
        """Get all plugins of a specific type."""
        return [
            plugin for plugin in self.plugins.values()
            if plugin.metadata.plugin_type == plugin_type
        ]

    def list_plugins(self) -> List[Dict[str, Any]]:
        """List all loaded plugins."""
        return [plugin.get_info() for plugin in self.plugins.values()]

    async def enable_plugin(self, name: str) -> bool:
        """Enable a plugin."""
        plugin = self.get_plugin(name)
        if not plugin:
            return False

        if plugin.status == PluginStatus.DISABLED:
            plugin.set_status(PluginStatus.ACTIVE)
            await publish_event(
                event_type="plugin.enabled",
                data={"plugin_name": name},
                source="plugin_manager"
            )
            logger.info(f"🔌 Enabled plugin: {name}")
            return True

        return False

    async def disable_plugin(self, name: str) -> bool:
        """Disable a plugin."""
        plugin = self.get_plugin(name)
        if not plugin:
            return False

        if plugin.status == PluginStatus.ACTIVE:
            plugin.set_status(PluginStatus.DISABLED)
            await publish_event(
                event_type="plugin.disabled",
                data={"plugin_name": name},
                source="plugin_manager"
            )
            logger.info(f"🔌 Disabled plugin: {name}")
            return True

        return False

    async def unload_plugin(self, name: str) -> bool:
        """Unload a plugin."""
        plugin = self.get_plugin(name)
        if not plugin:
            return False

        try:
            await plugin.cleanup()
            del self.plugins[name]

            await publish_event(
                event_type="plugin.unloaded",
                data={"plugin_name": name},
                source="plugin_manager"
            )

            logger.info(f"🔌 Unloaded plugin: {name}")
            return True

        except Exception as e:
            logger.error(f"Error unloading plugin {name}: {e}")
            return False

    async def reload_plugin(self, name: str) -> bool:
        """Reload a plugin."""
        if name not in self.plugins:
            return False

        # Store plugin info before unloading
        plugin = self.plugins[name]
        plugin_dir = getattr(plugin, "_directory", None)

        # Unload the plugin
        await self.unload_plugin(name)

        # Re-scan and load
        try:
            await self.scan_and_load_plugins()
            return name in self.plugins
        except Exception as e:
            logger.error(f"Failed to reload plugin {name}: {e}")
            return False

    async def cleanup_all(self) -> None:
        """Clean up all plugins."""
        logger.info("🔌 Cleaning up all plugins...")

        for plugin_name in list(self.plugins.keys()):
            await self.unload_plugin(plugin_name)

        self.plugins.clear()
        logger.info("🔌 All plugins cleaned up")

    def get_stats(self) -> Dict[str, Any]:
        """Get plugin manager statistics."""
        stats = {
            "total_plugins": len(self.plugins),
            "by_type": {},
            "by_status": {}
        }

        for plugin in self.plugins.values():
            plugin_type = plugin.metadata.plugin_type.value
            status = plugin.status.value

            stats["by_type"][plugin_type] = stats["by_type"].get(plugin_type, 0) + 1
            stats["by_status"][status] = stats["by_status"].get(status, 0) + 1

        return stats


# Global plugin manager instance
_plugin_manager = PluginManager()


def get_plugin_manager() -> PluginManager:
    """Get the global plugin manager instance."""
    return _plugin_manager