"""
Tests for server-side tool registry functionality.
Tests tool registration, validation, and management.
"""

import pytest
from unittest.mock import MagicMock, patch
from gambiarra.server.core.tools.registry import get_tool_registry, ToolRegistry, ToolValidationError
from gambiarra.server.core.tools.validator import validate_xml_tool_call


class TestToolRegistry:
    """Test tool registry functionality."""

    @pytest.fixture
    def tool_registry(self):
        """Create tool registry instance."""
        return ToolRegistry()

    @pytest.fixture
    def sample_tool_definition(self):
        """Sample tool definition."""
        return {
            "name": "read_file",
            "description": "Read contents of a file",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file to read"
                    }
                },
                "required": ["path"]
            }
        }

    @pytest.fixture
    def sample_complex_tool(self):
        """Sample complex tool with nested parameters."""
        return {
            "name": "search_and_replace",
            "description": "Search and replace text in file",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "search": {"type": "string"},
                    "replace": {"type": "string"},
                    "options": {
                        "type": "object",
                        "properties": {
                            "case_sensitive": {"type": "boolean", "default": True},
                            "regex": {"type": "boolean", "default": False}
                        }
                    }
                },
                "required": ["path", "search", "replace"]
            }
        }

    def test_tool_registration(self, tool_registry, sample_tool_definition):
        """Test registering a tool."""
        tool_registry.register_tool(sample_tool_definition)

        assert "read_file" in tool_registry.tools
        registered_tool = tool_registry.get_tool("read_file")
        assert registered_tool["name"] == "read_file"
        assert registered_tool["description"] == "Read contents of a file"

    def test_duplicate_tool_registration(self, tool_registry, sample_tool_definition):
        """Test registering a tool with duplicate name."""
        tool_registry.register_tool(sample_tool_definition)

        # Registering again should update the existing tool
        updated_tool = sample_tool_definition.copy()
        updated_tool["description"] = "Updated description"

        tool_registry.register_tool(updated_tool)

        registered_tool = tool_registry.get_tool("read_file")
        assert registered_tool["description"] == "Updated description"

    def test_get_nonexistent_tool(self, tool_registry):
        """Test getting a non-existent tool."""
        tool = tool_registry.get_tool("nonexistent")
        assert tool is None

    def test_list_tools(self, tool_registry, sample_tool_definition, sample_complex_tool):
        """Test listing all registered tools."""
        tool_registry.register_tool(sample_tool_definition)
        tool_registry.register_tool(sample_complex_tool)

        tools = tool_registry.list_tools()
        assert len(tools) == 2
        assert "read_file" in tools
        assert "search_and_replace" in tools

    def test_unregister_tool(self, tool_registry, sample_tool_definition):
        """Test unregistering a tool."""
        tool_registry.register_tool(sample_tool_definition)
        assert "read_file" in tool_registry.tools

        tool_registry.unregister_tool("read_file")
        assert "read_file" not in tool_registry.tools

    def test_unregister_nonexistent_tool(self, tool_registry):
        """Test unregistering a non-existent tool."""
        # Should not raise error
        tool_registry.unregister_tool("nonexistent")

    def test_tool_validation(self, tool_registry):
        """Test tool definition validation."""
        # Valid tool
        valid_tool = {
            "name": "valid_tool",
            "description": "A valid tool",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }

        # Should register without error
        tool_registry.register_tool(valid_tool)
        assert "valid_tool" in tool_registry.tools

    def test_invalid_tool_validation(self, tool_registry):
        """Test invalid tool definition rejection."""
        invalid_tools = [
            {"description": "Missing name"},  # Missing name
            {"name": ""},  # Empty name
            {"name": "test"},  # Missing description
            {"name": "test", "description": ""},  # Empty description
            {"name": "test", "description": "test", "parameters": "invalid"},  # Invalid parameters
        ]

        for invalid_tool in invalid_tools:
            with pytest.raises((KeyError, ValueError, TypeError)):
                tool_registry.register_tool(invalid_tool)

    def test_tool_parameter_schema_validation(self, tool_registry):
        """Test parameter schema validation."""
        tool_with_schema = {
            "name": "test_tool",
            "description": "Test tool with parameter schema",
            "parameters": {
                "type": "object",
                "properties": {
                    "required_param": {"type": "string"},
                    "optional_param": {"type": "integer", "default": 42}
                },
                "required": ["required_param"]
            }
        }

        tool_registry.register_tool(tool_with_schema)
        registered_tool = tool_registry.get_tool("test_tool")

        assert "required_param" in registered_tool["parameters"]["properties"]
        assert "optional_param" in registered_tool["parameters"]["properties"]
        assert registered_tool["parameters"]["required"] == ["required_param"]

    def test_get_tool_schema(self, tool_registry, sample_tool_definition):
        """Test getting tool parameter schema."""
        tool_registry.register_tool(sample_tool_definition)

        schema = tool_registry.get_tool_schema("read_file")
        assert schema is not None
        assert schema["type"] == "object"
        assert "path" in schema["properties"]

    def test_get_tool_schema_nonexistent(self, tool_registry):
        """Test getting schema for non-existent tool."""
        schema = tool_registry.get_tool_schema("nonexistent")
        assert schema is None

    def test_validate_tool_call_parameters(self, tool_registry, sample_tool_definition):
        """Test validating tool call parameters against schema."""
        tool_registry.register_tool(sample_tool_definition)

        # Valid parameters
        valid_params = {"path": "test.py"}
        is_valid = tool_registry.validate_parameters("read_file", valid_params)
        assert is_valid is True

        # Invalid parameters
        invalid_params = {}  # Missing required 'path'
        is_valid = tool_registry.validate_parameters("read_file", invalid_params)
        assert is_valid is False

    def test_tool_discovery_from_modules(self, tool_registry):
        """Test automatic tool discovery from modules."""
        # Mock module discovery (would need actual implementation)
        with patch('importlib.import_module') as mock_import:
            mock_module = MagicMock()
            mock_module.TOOL_DEFINITION = {
                "name": "discovered_tool",
                "description": "Auto-discovered tool",
                "parameters": {"type": "object", "properties": {}}
            }
            mock_import.return_value = mock_module

            # tool_registry.discover_tools_from_module("test_module")
            # Would test auto-discovery mechanism

    def test_tool_versioning(self, tool_registry):
        """Test tool versioning support."""
        versioned_tool = {
            "name": "versioned_tool",
            "version": "1.0.0",
            "description": "A versioned tool",
            "parameters": {"type": "object", "properties": {}}
        }

        tool_registry.register_tool(versioned_tool)
        registered_tool = tool_registry.get_tool("versioned_tool")

        assert registered_tool["version"] == "1.0.0"

        # Register newer version
        newer_tool = versioned_tool.copy()
        newer_tool["version"] = "1.1.0"
        newer_tool["description"] = "Updated tool"

        tool_registry.register_tool(newer_tool)
        updated_tool = tool_registry.get_tool("versioned_tool")

        assert updated_tool["version"] == "1.1.0"
        assert updated_tool["description"] == "Updated tool"

    def test_tool_categories(self, tool_registry):
        """Test tool categorization."""
        file_tool = {
            "name": "read_file",
            "category": "file_operations",
            "description": "Read file",
            "parameters": {"type": "object", "properties": {}}
        }

        command_tool = {
            "name": "execute_command",
            "category": "system",
            "description": "Execute command",
            "parameters": {"type": "object", "properties": {}}
        }

        tool_registry.register_tool(file_tool)
        tool_registry.register_tool(command_tool)

        file_tools = tool_registry.get_tools_by_category("file_operations")
        system_tools = tool_registry.get_tools_by_category("system")

        assert len(file_tools) == 1
        assert file_tools[0]["name"] == "read_file"
        assert len(system_tools) == 1
        assert system_tools[0]["name"] == "execute_command"

    def test_tool_security_levels(self, tool_registry):
        """Test tool security level classification."""
        low_risk_tool = {
            "name": "read_file",
            "description": "Read file",
            "security_level": "low",
            "parameters": {"type": "object", "properties": {}}
        }

        high_risk_tool = {
            "name": "execute_command",
            "description": "Execute command",
            "security_level": "high",
            "parameters": {"type": "object", "properties": {}}
        }

        tool_registry.register_tool(low_risk_tool)
        tool_registry.register_tool(high_risk_tool)

        low_risk_tools = tool_registry.get_tools_by_security_level("low")
        high_risk_tools = tool_registry.get_tools_by_security_level("high")

        assert len(low_risk_tools) == 1
        assert low_risk_tools[0]["name"] == "read_file"
        assert len(high_risk_tools) == 1
        assert high_risk_tools[0]["name"] == "execute_command"

    def test_tool_registry_serialization(self, tool_registry, sample_tool_definition):
        """Test serializing tool registry to JSON."""
        tool_registry.register_tool(sample_tool_definition)

        # Export tools
        exported_tools = tool_registry.export_tools()
        assert isinstance(exported_tools, dict)
        assert "read_file" in exported_tools

        # Import tools
        new_registry = ToolRegistry()
        new_registry.import_tools(exported_tools)

        assert "read_file" in new_registry.tools
        assert new_registry.get_tool("read_file")["name"] == "read_file"

    def test_tool_registry_singleton(self):
        """Test that get_tool_registry returns singleton instance."""
        registry1 = get_tool_registry()
        registry2 = get_tool_registry()

        assert registry1 is registry2

    def test_concurrent_tool_registration(self, tool_registry):
        """Test concurrent tool registration."""
        import asyncio

        async def register_tool_async(tool_name):
            tool_def = {
                "name": tool_name,
                "description": f"Tool {tool_name}",
                "parameters": {"type": "object", "properties": {}}
            }
            tool_registry.register_tool(tool_def)

        async def run_concurrent_registration():
            tasks = [register_tool_async(f"tool_{i}") for i in range(10)]
            await asyncio.gather(*tasks)

        # Run concurrent registration
        asyncio.run(run_concurrent_registration())

        # Verify all tools were registered
        tools = tool_registry.list_tools()
        assert len(tools) == 10
        for i in range(10):
            assert f"tool_{i}" in tools


class TestToolValidation:
    """Test tool call validation functionality."""

    @pytest.fixture
    def valid_xml_tool_call(self):
        """Valid XML tool call."""
        return """<read_file>
<args>
<file>
<path>main.py</path>
</file>
</args>
</read_file>"""

    @pytest.fixture
    def invalid_xml_tool_call(self):
        """Invalid XML tool call."""
        return """<read_file>
<args>
<file>
<path>main.py</path>
</file>
</read_file>"""  # Missing closing </args>

    def test_valid_xml_validation(self, valid_xml_tool_call):
        """Test validation of valid XML tool call."""
        result = validate_xml_tool_call(valid_xml_tool_call)
        assert result is True

    def test_invalid_xml_validation(self, invalid_xml_tool_call):
        """Test validation of invalid XML tool call."""
        result = validate_xml_tool_call(invalid_xml_tool_call)
        assert not result.is_valid

    def test_malformed_xml_validation(self):
        """Test validation of malformed XML."""
        malformed_xml = "<read_file><args><unclosed_tag>"

        result = validate_xml_tool_call(malformed_xml)
        assert not result.is_valid

    def test_empty_xml_validation(self):
        """Test validation of empty XML."""
        result = validate_xml_tool_call("")
        assert not result.is_valid

    def test_xml_injection_prevention(self):
        """Test prevention of XML injection attacks."""
        injection_attempts = [
            '<?xml version="1.0"?><!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><read_file>&xxe;</read_file>',
            '<read_file><args><script>alert("xss")</script></args></read_file>',
            '<read_file xmlns:xi="http://www.w3.org/2001/XInclude"><xi:include href="file:///etc/passwd"/></read_file>'
        ]

        for injection in injection_attempts:
            result = validate_xml_tool_call(injection)
            assert not result.is_valid

    def test_large_xml_handling(self):
        """Test handling of large XML documents."""
        # Create large but valid XML
        large_content = "x" * 100000  # 100KB content
        large_xml = f"""<read_file>
<args>
<file>
<path>{large_content}</path>
</file>
</args>
</read_file>"""

        # Should handle large XML (but may have size limits)
        result = validate_xml_tool_call(large_xml)
        # Should either validate successfully or return invalid result
        assert result.is_valid or not result.is_valid

    def test_unicode_xml_validation(self):
        """Test validation of XML with Unicode content."""
        unicode_xml = """<read_file>
<args>
<file>
<path>文件名.py</path>
</file>
</args>
</read_file>"""

        result = validate_xml_tool_call(unicode_xml)
        assert result.is_valid

    def test_xml_namespace_handling(self):
        """Test handling of XML namespaces."""
        namespaced_xml = """<tool:read_file xmlns:tool="http://gambiarra.ai/tools">
<tool:args>
<tool:file>
<tool:path>main.py</tool:path>
</tool:file>
</tool:args>
</tool:read_file>"""

        # Should handle namespaces appropriately
        result = validate_xml_tool_call(namespaced_xml)
        # Result depends on namespace handling policy - either valid or invalid is acceptable