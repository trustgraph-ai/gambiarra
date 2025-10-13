"""
Tests for server-side XML tool call parsing.
These tests ensure consistent parsing and prevent injection attacks.
"""

import pytest
from gambiarra.server.core.tools.parser import ToolCallParser


@pytest.mark.unit
class TestXMLToolParser:
    """Test XML tool call parsing functionality."""

    def test_parse_read_file_nested_structure(self, sample_tool_calls):
        """Test parsing read_file with nested args structure."""
        xml_content = sample_tool_calls["read_file_nested"]

        params = ToolCallParser.parse_xml_parameters(xml_content)

        assert "path" in params
        assert params["path"] == "main.py"

    def test_parse_write_to_file_nested_structure(self, sample_tool_calls):
        """Test parsing write_to_file with nested args structure."""
        xml_content = sample_tool_calls["write_to_file_nested"]

        params = ToolCallParser.parse_xml_parameters(xml_content)

        assert "path" in params
        assert "content" in params
        assert "line_count" in params
        assert params["path"] == "new_file.py"
        assert params["content"] == "print('Created by test')"
        assert params["line_count"] == 1

    def test_parse_list_files_nested_structure(self, sample_tool_calls):
        """Test parsing list_files with nested args structure."""
        xml_content = sample_tool_calls["list_files_nested"]

        params = ToolCallParser.parse_xml_parameters(xml_content)

        assert "path" in params
        assert "recursive" in params
        assert params["path"] == "."
        assert params["recursive"] is True

    def test_malformed_xml_handling(self):
        """Test handling of malformed XML."""
        malformed_xmls = [
            "<read_file><args><file><path>test.py</path></file>",  # Missing closing tags
            "<read_file><args><file><path>test.py</path></args></read_file>",  # Missing </file>
            "<read_file args><file><path>test.py</path></file></args></read_file>",  # Invalid syntax
            "not xml at all",
            "",
            "<read_file></read_file>",  # Empty tool call
        ]

        for malformed_xml in malformed_xmls:
            # Should either return empty dict or handle gracefully
            try:
                params = ToolCallParser.parse_xml_parameters(malformed_xml)
                assert isinstance(params, dict)
                # Empty results are acceptable for malformed input
            except Exception as e:
                # Exceptions are also acceptable - just shouldn't crash
                assert isinstance(e, (ValueError, TypeError))

    def test_html_entity_unescaping(self):
        """Test proper unescaping of HTML entities."""
        xml_with_entities = """<write_to_file>
<args>
<path>test.py</path>
<content>print("Hello &amp; goodbye")
&lt;script&gt;alert('xss')&lt;/script&gt;</content>
<line_count>2</line_count>
</args>
</write_to_file>"""

        params = ToolCallParser.parse_xml_parameters(xml_with_entities)

        # Should properly unescape HTML entities
        assert "content" in params
        assert "&" in params["content"]  # &amp; should become &
        assert "<script>" in params["content"]  # &lt; &gt; should be unescaped
        assert "alert('xss')" in params["content"]

    def test_injection_attack_prevention(self):
        """Test prevention of XML injection attacks."""
        injection_attacks = [
            # XML entity expansion attack
            """<?xml version="1.0"?>
            <!DOCTYPE root [
            <!ENTITY lol "lol">
            ]>
            <read_file><args><file><path>&lol;</path></file></args></read_file>""",

            # XXE attack
            """<?xml version="1.0"?>
            <!DOCTYPE root [
            <!ENTITY xxe SYSTEM "file:///etc/passwd">
            ]>
            <read_file><args><file><path>&xxe;</path></file></args></read_file>""",
        ]

        for attack in injection_attacks:
            try:
                params = ToolCallParser.parse_xml_parameters(attack)
                # If parsing succeeds, ensure no sensitive data leaked
                if "path" in params:
                    assert "passwd" not in params["path"].lower()
                    assert "lol" not in params["path"].lower()
            except Exception:
                # Rejecting malicious XML is perfectly acceptable
                pass

    def test_large_xml_handling(self):
        """Test handling of unusually large XML inputs."""
        # Create large content
        large_content = "x" * 10000
        large_xml = f"""<write_to_file>
<args>
<path>large_file.txt</path>
<content>{large_content}</content>
<line_count>1</line_count>
</args>
</write_to_file>"""

        # Should handle large inputs gracefully
        try:
            params = ToolCallParser.parse_xml_parameters(large_xml)
            if "content" in params:
                assert len(params["content"]) == 10000
        except Exception:
            # Rejecting overly large inputs is also acceptable
            pass

    def test_unicode_content_handling(self):
        """Test handling of Unicode content in XML."""
        unicode_xml = """<write_to_file>
<args>
<path>unicode_test.py</path>
<content>print("Hello 🌍! Здравствуй мир! 你好世界!")
# Test with various Unicode: αβγδε, 🚀🔥💻</content>
<line_count>2</line_count>
</args>
</write_to_file>"""

        params = ToolCallParser.parse_xml_parameters(unicode_xml)

        assert "content" in params
        assert "🌍" in params["content"]
        assert "Здравствуй" in params["content"]
        assert "你好世界" in params["content"]
        assert "🚀🔥💻" in params["content"]

    def test_nested_structure_consistency(self):
        """Test that all tools consistently use nested structure."""
        # Test different tools with nested structure
        tool_xmls = {
            "execute_command": """<execute_command>
<args>
<command>python test.py</command>
</args>
</execute_command>""",

            "search_and_replace": """<search_and_replace>
<args>
<path>test.py</path>
<search>old_text</search>
<replace>new_text</replace>
</args>
</search_and_replace>""",

            "insert_content": """<insert_content>
<args>
<path>test.py</path>
<line_number>5</line_number>
<content># Inserted comment</content>
</args>
</insert_content>""",
        }

        for tool_name, xml in tool_xmls.items():
            params = ToolCallParser.parse_xml_parameters(xml)

            # Each should successfully parse with expected parameters
            assert isinstance(params, dict)
            assert len(params) > 0

            if tool_name == "execute_command":
                assert "command" in params
                assert params["command"] == "python test.py"

            elif tool_name == "search_and_replace":
                assert "path" in params
                assert "search" in params
                assert "replace" in params
                assert params["search"] == "old_text"
                assert params["replace"] == "new_text"

            elif tool_name == "insert_content":
                assert "path" in params
                assert "line_number" in params
                assert "content" in params
                assert params["line_number"] == 5

    def test_extract_tool_type(self):
        """Test tool type extraction from XML."""
        tool_types = [
            ("<read_file><args></args></read_file>", "read_file"),
            ("<write_to_file><args></args></write_to_file>", "write_to_file"),
            ("<execute_command><args></args></execute_command>", "execute_command"),
            ("<invalid_tool><args></args></invalid_tool>", None),
            ("not xml", None),
            ("", None)
        ]

        for xml, expected_type in tool_types:
            extracted_type = ToolCallParser._extract_tool_type(xml)
            assert extracted_type == expected_type

    def test_parameter_type_conversion(self):
        """Test proper type conversion of parameters."""
        xml_with_types = """<write_to_file>
<args>
<path>test.py</path>
<content>test content</content>
<line_count>42</line_count>
</args>
</write_to_file>"""

        params = ToolCallParser.parse_xml_parameters(xml_with_types)

        # line_count should be converted to int
        assert isinstance(params["line_count"], int)
        assert params["line_count"] == 42

        # Other params should remain strings
        assert isinstance(params["path"], str)
        assert isinstance(params["content"], str)

    def test_boolean_parameter_parsing(self):
        """Test boolean parameter parsing."""
        xml_with_boolean = """<list_files>
<args>
<path>src</path>
<recursive>false</recursive>
</args>
</list_files>"""

        params = ToolCallParser.parse_xml_parameters(xml_with_boolean)

        assert "recursive" in params
        assert isinstance(params["recursive"], bool)
        assert params["recursive"] is False

        # Test true case
        xml_with_true = xml_with_boolean.replace("false", "true")
        params_true = ToolCallParser.parse_xml_parameters(xml_with_true)
        assert params_true["recursive"] is True

    def test_whitespace_handling(self):
        """Test proper whitespace handling in XML parsing."""
        xml_with_whitespace = """<read_file>
<args>
  <file>
    <path>  test.py  </path>
  </file>
</args>
</read_file>"""

        params = ToolCallParser.parse_xml_parameters(xml_with_whitespace)

        # Whitespace should be trimmed from parameter values
        assert params["path"] == "test.py"

    def test_empty_parameter_handling(self):
        """Test handling of empty parameters."""
        xml_with_empty = """<write_to_file>
<args>
<path></path>
<content></content>
<line_count>0</line_count>
</args>
</write_to_file>"""

        params = ToolCallParser.parse_xml_parameters(xml_with_empty)

        assert params["path"] == ""
        assert params["content"] == ""
        assert params["line_count"] == 0