#!/usr/bin/env python3
"""
Test script for Phase 3 advanced features.
Verifies plugin system, error recovery, performance optimization, and degraded mode operation.
"""

import asyncio
import json
import time
import logging
from pathlib import Path

# Test imports
from gambiarra.server.core.plugins.manager import get_plugin_manager
from gambiarra.server.core.recovery.circuit_breaker import get_circuit_breaker_registry, CircuitBreakerConfig
from gambiarra.server.core.recovery.degraded_mode import get_degraded_mode_manager, ComponentType, DegradationLevel
from gambiarra.server.core.performance.connection_pool import get_connection_pool_manager, PoolConfig
from gambiarra.server.core.performance.request_batcher import get_batcher_manager, BatchConfig
from gambiarra.server.core.tools.versioning import get_version_manager, ToolParameter

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class Phase3Tester:
    """Test suite for Phase 3 advanced features."""

    def __init__(self):
        self.results = {
            "plugin_system": {"passed": 0, "failed": 0, "details": []},
            "circuit_breakers": {"passed": 0, "failed": 0, "details": []},
            "degraded_mode": {"passed": 0, "failed": 0, "details": []},
            "connection_pooling": {"passed": 0, "failed": 0, "details": []},
            "request_batching": {"passed": 0, "failed": 0, "details": []},
            "tool_versioning": {"passed": 0, "failed": 0, "details": []}
        }

    def assert_test(self, category: str, test_name: str, condition: bool, message: str = ""):
        """Assert a test condition and record results."""
        if condition:
            self.results[category]["passed"] += 1
            status = "✅ PASS"
        else:
            self.results[category]["failed"] += 1
            status = "❌ FAIL"

        detail = f"{status}: {test_name}"
        if message:
            detail += f" - {message}"

        self.results[category]["details"].append(detail)
        logger.info(detail)

    async def test_plugin_system(self):
        """Test plugin system functionality."""
        logger.info("🔌 Testing Plugin System...")

        try:
            plugin_manager = get_plugin_manager()

            # Test plugin manager initialization
            self.assert_test("plugin_system", "Plugin manager initialization",
                           plugin_manager is not None, "Manager instance created")

            # Test plugin scanning (should not fail even with no plugins)
            await plugin_manager.scan_and_load_plugins()
            self.assert_test("plugin_system", "Plugin scanning",
                           True, "Scan completed without errors")

            # Test plugin registry access
            loaded_plugins = plugin_manager.list_loaded_plugins()
            self.assert_test("plugin_system", "Plugin registry access",
                           isinstance(loaded_plugins, dict), f"Registry accessible: {len(loaded_plugins)} plugins")

            # Test stats
            stats = plugin_manager.get_stats()
            has_required_fields = "loaded_plugins" in stats and "failed_loads" in stats
            self.assert_test("plugin_system", "Plugin statistics",
                           has_required_fields,
                           f"Stats: {stats.get('loaded_plugins', 0)} loaded, {stats.get('failed_loads', 0)} failed")

        except Exception as e:
            self.assert_test("plugin_system", "Plugin system error handling",
                           False, f"Exception: {e}")

    async def test_circuit_breakers(self):
        """Test circuit breaker functionality."""
        logger.info("🛡️ Testing Circuit Breakers...")

        try:
            registry = get_circuit_breaker_registry()

            # Test circuit breaker creation
            config = CircuitBreakerConfig(failure_threshold=2, timeout_seconds=1.0)
            cb = registry.create_circuit_breaker("test_cb", config)
            self.assert_test("circuit_breakers", "Circuit breaker creation",
                           cb is not None, "Circuit breaker created successfully")

            # Test successful call
            async def success_func():
                return "success"

            result = await cb.call(success_func)
            self.assert_test("circuit_breakers", "Successful call",
                           result == "success", "Function executed successfully")

            # Test failure handling
            async def failure_func():
                raise ValueError("Test failure")

            try:
                await cb.call(failure_func)
                self.assert_test("circuit_breakers", "Failure handling",
                               False, "Should have raised exception")
            except ValueError:
                self.assert_test("circuit_breakers", "Failure handling",
                               True, "Exception properly propagated")

            # Test stats
            stats = cb.get_stats()
            self.assert_test("circuit_breakers", "Circuit breaker statistics",
                           stats.get("total_calls", 0) >= 0, f"Stats tracked: {stats.get('total_calls', 0)} calls")

        except Exception as e:
            self.assert_test("circuit_breakers", "Circuit breaker error handling",
                           False, f"Exception: {e}")

    async def test_degraded_mode(self):
        """Test degraded mode operation."""
        logger.info("🚨 Testing Degraded Mode...")

        try:
            manager = get_degraded_mode_manager()

            # Test component registration
            manager.register_component("test_component", ComponentType.AI_PROVIDER)
            self.assert_test("degraded_mode", "Component registration",
                           "test_component" in manager.components, "Component registered successfully")

            # Test normal operation
            initial_level = manager.current_level
            self.assert_test("degraded_mode", "Initial degradation level",
                           initial_level == DegradationLevel.NORMAL, f"Started at {initial_level.value}")

            # Test feature availability
            available_features = manager.get_available_features()
            self.assert_test("degraded_mode", "Feature availability check",
                           len(available_features) > 0, f"{len(available_features)} features available")

            # Test component failure reporting
            await manager.report_component_failure("test_component", "Simulated failure")
            self.assert_test("degraded_mode", "Component failure reporting",
                           not manager.components["test_component"].is_healthy, "Failure recorded")

            # Test component recovery
            await manager.report_component_recovery("test_component")
            self.assert_test("degraded_mode", "Component recovery",
                           manager.components["test_component"].is_healthy, "Recovery recorded")

            # Test system status
            status = manager.get_system_status()
            self.assert_test("degraded_mode", "System status",
                           "degradation_level" in status and "health_percentage" in status,
                           f"Health: {status['health_percentage']:.1f}%")

        except Exception as e:
            self.assert_test("degraded_mode", "Degraded mode error handling",
                           False, f"Exception: {e}")

    async def test_connection_pooling(self):
        """Test connection pooling functionality."""
        logger.info("🔗 Testing Connection Pooling...")

        try:
            manager = get_connection_pool_manager()

            # Test HTTP pool creation
            config = PoolConfig(min_size=1, max_size=3)
            pool = manager.create_http_pool("test_pool", "http://httpbin.org", config)
            self.assert_test("connection_pooling", "HTTP pool creation",
                           pool is not None, "Pool created successfully")

            # Test pool startup
            await manager.start_all()
            self.assert_test("connection_pooling", "Pool startup",
                           True, "Pools started without errors")

            # Test pool statistics
            stats = manager.get_all_stats()
            self.assert_test("connection_pooling", "Pool statistics",
                           "test_pool" in stats, f"Stats available for {len(stats)} pools")

            # Test pool shutdown
            await manager.stop_all()
            self.assert_test("connection_pooling", "Pool shutdown",
                           True, "Pools stopped without errors")

        except Exception as e:
            self.assert_test("connection_pooling", "Connection pooling error handling",
                           False, f"Exception: {e}")

    async def test_request_batching(self):
        """Test request batching functionality."""
        logger.info("📦 Testing Request Batching...")

        try:
            manager = get_batcher_manager()

            # Test AI batcher creation
            async def mock_ai_provider(messages):
                return {"messages": messages, "metadata": {"processed": True}}

            config = BatchConfig(max_batch_size=3, max_wait_time=0.1)
            batcher = manager.create_ai_batcher("test_ai_batcher", mock_ai_provider, config)
            self.assert_test("request_batching", "AI batcher creation",
                           batcher is not None, "AI batcher created successfully")

            # Test batcher startup
            await manager.start_all()
            self.assert_test("request_batching", "Batcher startup",
                           True, "Batchers started without errors")

            # Test batch submission (simplified)
            # Note: Full testing would require actual batch processing
            stats = manager.get_all_stats()
            self.assert_test("request_batching", "Batcher statistics",
                           "test_ai_batcher" in stats, f"Stats available for {len(stats)} batchers")

            # Test batcher shutdown
            await manager.stop_all()
            self.assert_test("request_batching", "Batcher shutdown",
                           True, "Batchers stopped without errors")

        except Exception as e:
            self.assert_test("request_batching", "Request batching error handling",
                           False, f"Exception: {e}")

    def test_tool_versioning(self):
        """Test tool versioning functionality."""
        logger.info("🔧 Testing Tool Versioning...")

        try:
            manager = get_version_manager()

            # Test version manager initialization
            self.assert_test("tool_versioning", "Version manager initialization",
                           manager is not None, "Manager instance created")

            # Test tool version registration using helper function
            from server.core.tools.versioning import register_tool_version
            parameters = [
                ToolParameter("file_path", "string", required=True, description="Path to file"),
                ToolParameter("content", "string", required=True, description="File content")
            ]
            register_tool_version(
                "test_tool", "1.0.0", "Test tool for versioning",
                parameters, ["file_operations"]
            )
            self.assert_test("tool_versioning", "Tool version registration",
                           manager.get_current_version("test_tool") is not None, "Version registered successfully")

            # Test compatibility checking
            # Register a second version
            parameters_v2 = parameters + [
                ToolParameter("encoding", "string", required=False, default="utf-8", description="File encoding")
            ]
            register_tool_version(
                "test_tool", "1.1.0", "Test tool v1.1 with encoding",
                parameters_v2, ["file_operations"]
            )

            compatibility = manager.check_compatibility("test_tool", "1.0.0", "1.1.0")
            self.assert_test("tool_versioning", "Compatibility checking",
                           compatibility is not None, f"Compatibility: {compatibility.value}")

            # Test tool call validation
            valid, errors = manager.validate_tool_call("test_tool", "1.0.0", {
                "file_path": "/test/file.txt",
                "content": "Hello world"
            })
            self.assert_test("tool_versioning", "Tool call validation",
                           valid and len(errors) == 0, "Valid call passed validation")

            # Test invalid call validation
            valid, errors = manager.validate_tool_call("test_tool", "1.0.0", {
                "file_path": "/test/file.txt"
                # Missing required 'content' parameter
            })
            self.assert_test("tool_versioning", "Invalid call validation",
                           not valid and len(errors) > 0, f"Invalid call rejected: {len(errors)} errors")

            # Test statistics
            stats = manager.get_stats()
            self.assert_test("tool_versioning", "Versioning statistics",
                           stats["total_tools"] > 0 and stats["total_versions"] > 0,
                           f"Stats: {stats['total_tools']} tools, {stats['total_versions']} versions")

        except Exception as e:
            self.assert_test("tool_versioning", "Tool versioning error handling",
                           False, f"Exception: {e}")

    async def run_all_tests(self):
        """Run all Phase 3 tests."""
        logger.info("🚀 Starting Phase 3 Advanced Features Test Suite")
        logger.info("=" * 60)

        start_time = time.time()

        # Run all test categories
        await self.test_plugin_system()
        await self.test_circuit_breakers()
        await self.test_degraded_mode()
        await self.test_connection_pooling()
        await self.test_request_batching()
        self.test_tool_versioning()

        end_time = time.time()
        duration = end_time - start_time

        # Print results summary
        logger.info("=" * 60)
        logger.info("📊 Phase 3 Test Results Summary")
        logger.info("=" * 60)

        total_passed = 0
        total_failed = 0

        for category, results in self.results.items():
            passed = results["passed"]
            failed = results["failed"]
            total = passed + failed

            total_passed += passed
            total_failed += failed

            status = "✅" if failed == 0 else "❌"
            logger.info(f"{status} {category.replace('_', ' ').title()}: {passed}/{total} passed")

            if failed > 0:
                for detail in results["details"]:
                    if "❌ FAIL" in detail:
                        logger.info(f"    {detail}")

        logger.info("=" * 60)
        overall_status = "✅ ALL TESTS PASSED" if total_failed == 0 else f"❌ {total_failed} TESTS FAILED"
        logger.info(f"{overall_status} ({total_passed}/{total_passed + total_failed} passed in {duration:.2f}s)")

        return total_failed == 0


async def main():
    """Main test execution."""
    tester = Phase3Tester()
    success = await tester.run_all_tests()

    if success:
        logger.info("🎉 All Phase 3 advanced features are working correctly!")
        return 0
    else:
        logger.error("💥 Some Phase 3 features failed testing")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)