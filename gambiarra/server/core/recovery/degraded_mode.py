"""
Degraded mode operation system.
Allows the system to continue operating with reduced functionality when components fail.
"""

import logging
import time
from typing import Dict, Any, Set, Optional, Callable, List
from dataclasses import dataclass
from enum import Enum

from ..events.bus import get_event_bus, EventTypes, publish_event

logger = logging.getLogger(__name__)


class DegradationLevel(Enum):
    """Levels of system degradation."""
    NORMAL = "normal"           # Full functionality
    LIMITED = "limited"         # Some features disabled
    ESSENTIAL = "essential"     # Only core features
    EMERGENCY = "emergency"     # Minimal functionality


class ComponentType(Enum):
    """Types of system components."""
    AI_PROVIDER = "ai_provider"
    DATABASE = "database"
    FILE_SYSTEM = "file_system"
    NETWORK = "network"
    TOOL_SYSTEM = "tool_system"
    SESSION_MANAGER = "session_manager"
    EVENT_BUS = "event_bus"


@dataclass
class ComponentStatus:
    """Status of a system component."""
    name: str
    component_type: ComponentType
    is_healthy: bool
    last_check: float
    failure_count: int = 0
    error_message: Optional[str] = None


@dataclass
class DegradationRule:
    """Rule for determining when to enter degraded mode."""
    component_types: Set[ComponentType]
    min_failures: int
    degradation_level: DegradationLevel
    description: str


class DegradedModeManager:
    """Manages system degradation and recovery."""

    def __init__(self):
        self.current_level = DegradationLevel.NORMAL
        self.components: Dict[str, ComponentStatus] = {}
        self.degradation_rules: List[DegradationRule] = []
        self.disabled_features: Set[str] = set()
        self.event_bus = get_event_bus()

        # Initialize default degradation rules
        self._initialize_default_rules()

    def _initialize_default_rules(self) -> None:
        """Initialize default degradation rules."""
        self.degradation_rules = [
            # AI Provider failures
            DegradationRule(
                component_types={ComponentType.AI_PROVIDER},
                min_failures=1,
                degradation_level=DegradationLevel.LIMITED,
                description="AI provider unavailable - basic file operations only"
            ),

            # Multiple component failures
            DegradationRule(
                component_types={ComponentType.AI_PROVIDER, ComponentType.DATABASE},
                min_failures=2,
                degradation_level=DegradationLevel.ESSENTIAL,
                description="Multiple critical components failed"
            ),

            # Event bus failure
            DegradationRule(
                component_types={ComponentType.EVENT_BUS},
                min_failures=1,
                degradation_level=DegradationLevel.LIMITED,
                description="Event system unavailable - reduced coordination"
            ),

            # Emergency level - most systems down
            DegradationRule(
                component_types={ComponentType.AI_PROVIDER, ComponentType.DATABASE, ComponentType.NETWORK},
                min_failures=3,
                degradation_level=DegradationLevel.EMERGENCY,
                description="System in emergency mode - minimal functionality"
            )
        ]

    def register_component(self,
                          name: str,
                          component_type: ComponentType,
                          health_check: Optional[Callable] = None) -> None:
        """Register a component for monitoring."""
        self.components[name] = ComponentStatus(
            name=name,
            component_type=component_type,
            is_healthy=True,
            last_check=time.time()
        )

        logger.info(f"Registered component for degraded mode monitoring: {name}")

    async def report_component_failure(self, component_name: str, error: str) -> None:
        """Report a component failure."""
        if component_name not in self.components:
            logger.warning(f"Unknown component reported failure: {component_name}")
            return

        component = self.components[component_name]
        component.is_healthy = False
        component.failure_count += 1
        component.error_message = error
        component.last_check = time.time()

        logger.warning(f"Component failure reported: {component_name} - {error}")

        # Publish component failure event
        await publish_event(
            event_type="component.failure",
            data={
                "component_name": component_name,
                "component_type": component.component_type.value,
                "error": error,
                "failure_count": component.failure_count
            },
            source="degraded_mode_manager"
        )

        # Check if we need to change degradation level
        await self._evaluate_degradation_level()

    async def report_component_recovery(self, component_name: str) -> None:
        """Report a component recovery."""
        if component_name not in self.components:
            logger.warning(f"Unknown component reported recovery: {component_name}")
            return

        component = self.components[component_name]
        component.is_healthy = True
        component.error_message = None
        component.last_check = time.time()

        logger.info(f"Component recovered: {component_name}")

        # Publish component recovery event
        await publish_event(
            event_type="component.recovery",
            data={
                "component_name": component_name,
                "component_type": component.component_type.value
            },
            source="degraded_mode_manager"
        )

        # Check if we can improve degradation level
        await self._evaluate_degradation_level()

    async def _evaluate_degradation_level(self) -> None:
        """Evaluate and update system degradation level."""
        # Count failures by component type
        failure_counts = {}
        for component in self.components.values():
            if not component.is_healthy:
                comp_type = component.component_type
                failure_counts[comp_type] = failure_counts.get(comp_type, 0) + 1

        # Find the highest applicable degradation level
        new_level = DegradationLevel.NORMAL
        applicable_rule = None

        for rule in sorted(self.degradation_rules, key=lambda r: r.degradation_level.value, reverse=True):
            failed_types = set()
            for comp_type in rule.component_types:
                if failure_counts.get(comp_type, 0) >= rule.min_failures:
                    failed_types.add(comp_type)

            # Check if rule conditions are met
            if len(failed_types) >= len(rule.component_types):
                new_level = rule.degradation_level
                applicable_rule = rule
                break

        # Update degradation level if changed
        if new_level != self.current_level:
            await self._change_degradation_level(new_level, applicable_rule)

    async def _change_degradation_level(self, new_level: DegradationLevel, rule: Optional[DegradationRule]) -> None:
        """Change system degradation level."""
        old_level = self.current_level
        self.current_level = new_level

        # Update disabled features based on new level
        self._update_disabled_features()

        reason = rule.description if rule else "Manual override"
        logger.warning(f"Degradation level changed: {old_level.value} -> {new_level.value} ({reason})")

        # Publish degradation level change event
        await publish_event(
            event_type="system.degradation_changed",
            data={
                "old_level": old_level.value,
                "new_level": new_level.value,
                "reason": reason,
                "disabled_features": list(self.disabled_features)
            },
            source="degraded_mode_manager"
        )

    def _update_disabled_features(self) -> None:
        """Update the set of disabled features based on current degradation level."""
        self.disabled_features.clear()

        if self.current_level == DegradationLevel.LIMITED:
            self.disabled_features.update([
                "ai_conversation",
                "complex_workflows",
                "background_tasks"
            ])

        elif self.current_level == DegradationLevel.ESSENTIAL:
            self.disabled_features.update([
                "ai_conversation",
                "complex_workflows",
                "background_tasks",
                "file_analysis",
                "code_generation",
                "advanced_search"
            ])

        elif self.current_level == DegradationLevel.EMERGENCY:
            self.disabled_features.update([
                "ai_conversation",
                "complex_workflows",
                "background_tasks",
                "file_analysis",
                "code_generation",
                "advanced_search",
                "session_persistence",
                "context_tracking"
            ])

    def is_feature_available(self, feature_name: str) -> bool:
        """Check if a feature is available in current degradation level."""
        return feature_name not in self.disabled_features

    def get_available_features(self) -> List[str]:
        """Get list of currently available features."""
        all_features = [
            "basic_file_operations",
            "ai_conversation",
            "complex_workflows",
            "background_tasks",
            "file_analysis",
            "code_generation",
            "advanced_search",
            "session_persistence",
            "context_tracking"
        ]

        return [feature for feature in all_features if self.is_feature_available(feature)]

    def force_degradation_level(self, level: DegradationLevel, reason: str = "Manual override") -> None:
        """Manually force a degradation level."""
        asyncio.create_task(self._change_degradation_level(level, None))

    def get_system_status(self) -> Dict[str, Any]:
        """Get comprehensive system status."""
        healthy_components = sum(1 for c in self.components.values() if c.is_healthy)
        total_components = len(self.components)

        component_status = {}
        for name, component in self.components.items():
            component_status[name] = {
                "type": component.component_type.value,
                "healthy": component.is_healthy,
                "failure_count": component.failure_count,
                "last_check": component.last_check,
                "error": component.error_message
            }

        return {
            "degradation_level": self.current_level.value,
            "health_percentage": (healthy_components / total_components * 100) if total_components > 0 else 100,
            "available_features": self.get_available_features(),
            "disabled_features": list(self.disabled_features),
            "components": component_status,
            "summary": {
                "total_components": total_components,
                "healthy_components": healthy_components,
                "failed_components": total_components - healthy_components
            }
        }

    async def health_check_all_components(self) -> None:
        """Perform health checks on all registered components."""
        for component_name, component in self.components.items():
            # This would typically call component-specific health check functions
            # For now, just update the last check time
            component.last_check = time.time()

    def add_degradation_rule(self, rule: DegradationRule) -> None:
        """Add a custom degradation rule."""
        self.degradation_rules.append(rule)
        logger.info(f"Added degradation rule: {rule.description}")


# Global degraded mode manager
_degraded_mode_manager = DegradedModeManager()


def get_degraded_mode_manager() -> DegradedModeManager:
    """Get the global degraded mode manager."""
    return _degraded_mode_manager


def require_feature(feature_name: str):
    """Decorator to check if a feature is available before execution."""
    def decorator(func):
        async def async_wrapper(*args, **kwargs):
            if not _degraded_mode_manager.is_feature_available(feature_name):
                raise RuntimeError(f"Feature '{feature_name}' is not available in current degradation level")
            return await func(*args, **kwargs)

        def sync_wrapper(*args, **kwargs):
            if not _degraded_mode_manager.is_feature_available(feature_name):
                raise RuntimeError(f"Feature '{feature_name}' is not available in current degradation level")
            return func(*args, **kwargs)

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator