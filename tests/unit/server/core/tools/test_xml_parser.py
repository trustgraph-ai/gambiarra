"""
Comprehensive test suite for the XML parser module.

Tests cover:
- Simple and nested parameter parsing
- CDATA handling
- Error cases (malformed XML, missing elements)
- Schema validation
- Edge cases
"""

import pytest
from gambiarra.server.core.tools.xml_parser import ToolXMLParser, ParseResult


class TestToolXMLParser:
    """Test suite for ToolXMLParser class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.parser = ToolXMLParser()

    def test_simple_tool_call(self):
        """Test parsing simple tool with flat parameters."""
        xml = """
        <read_file>
        <args>
        <path>test.py</path>
        </args>
        </read_file>
        """

        result = self.parser.parse_tool_call(xml)

        assert result.success
        assert result.data['tool_name'] == 'read_file'
        assert result.data['parameters']['path'] == 'test.py'
        assert result.error is None

    def test_nested_parameters(self):
        """Test parsing tool with nested parameters."""
        xml = """
        <write_to_file>
        <args>
        <file>
        <path>src/main.py</path>
        </file>
        <content>print("hello")</content>
        <line_count>1</line_count>
        </args>
        </write_to_file>
        """

        result = self.parser.parse_tool_call(xml)

        assert result.success
        assert result.data['tool_name'] == 'write_to_file'
        assert result.data['parameters']['file']['path'] == 'src/main.py'
        assert result.data['parameters']['content'] == 'print("hello")'
        assert result.data['parameters']['line_count'] == '1'

    def test_deeply_nested_parameters(self):
        """Test parsing with deeply nested structure."""
        xml = """
        <complex_tool>
        <args>
        <level1>
        <level2>
        <level3>deep_value</level3>
        </level2>
        </level1>
        </args>
        </complex_tool>
        """

        result = self.parser.parse_tool_call(xml)

        assert result.success
        assert result.data['parameters']['level1']['level2']['level3'] == 'deep_value'

    def test_multiple_same_name_elements(self):
        """Test handling of multiple elements with the same name (converted to list)."""
        xml = """
        <list_files>
        <args>
        <path>src</path>
        <path>tests</path>
        <path>docs</path>
        </args>
        </list_files>
        """

        result = self.parser.parse_tool_call(xml)

        assert result.success
        assert isinstance(result.data['parameters']['path'], list)
        assert len(result.data['parameters']['path']) == 3
        assert 'src' in result.data['parameters']['path']
        assert 'tests' in result.data['parameters']['path']
        assert 'docs' in result.data['parameters']['path']

    def test_cdata_content(self):
        """Test handling of CDATA sections."""
        xml = """
        <execute_command>
        <args>
        <command><![CDATA[grep -r "test" | wc -l]]></command>
        </args>
        </execute_command>
        """

        result = self.parser.parse_tool_call(xml)

        assert result.success
        assert 'grep -r "test"' in result.data['parameters']['command']
        assert '|' in result.data['parameters']['command']

    def test_special_characters_in_content(self):
        """Test handling of special XML characters."""
        xml = """
        <write_to_file>
        <args>
        <content>if x &lt; 5 &amp;&amp; y &gt; 10:</content>
        </args>
        </write_to_file>
        """

        result = self.parser.parse_tool_call(xml)

        assert result.success
        # ElementTree automatically unescapes XML entities
        assert '<' in result.data['parameters']['content'] or '&lt;' in result.data['parameters']['content']

    def test_empty_parameter(self):
        """Test handling of empty parameter values."""
        xml = """
        <search_files>
        <args>
        <path></path>
        <pattern>*.py</pattern>
        </args>
        </search_files>
        """

        result = self.parser.parse_tool_call(xml)

        assert result.success
        assert result.data['parameters']['path'] == ''
        assert result.data['parameters']['pattern'] == '*.py'

    def test_whitespace_handling(self):
        """Test that leading/trailing whitespace is properly stripped."""
        xml = """
        <read_file>
        <args>
        <path>
            test.py
        </path>
        </args>
        </read_file>
        """

        result = self.parser.parse_tool_call(xml)

        assert result.success
        assert result.data['parameters']['path'] == 'test.py'

    def test_malformed_xml_missing_closing_tag(self):
        """Test error handling for malformed XML with missing closing tag."""
        xml = """
        <read_file>
        <args>
        <path>test.py</args>
        </read_file>
        """

        result = self.parser.parse_tool_call(xml)

        assert not result.success
        assert result.error is not None
        assert 'Invalid XML' in result.error or 'mismatched tag' in result.error.lower()

    def test_malformed_xml_unclosed_tag(self):
        """Test error handling for unclosed tags."""
        xml = """
        <read_file>
        <args>
        <path>test.py
        </args>
        </read_file>
        """

        result = self.parser.parse_tool_call(xml)

        assert not result.success
        assert result.error is not None

    def test_missing_args_element(self):
        """Test error handling for missing <args> element."""
        xml = """
        <read_file>
        <path>test.py</path>
        </read_file>
        """

        result = self.parser.parse_tool_call(xml)

        assert not result.success
        assert 'No <args> element' in result.error

    def test_empty_xml(self):
        """Test error handling for empty XML."""
        xml = ""

        result = self.parser.parse_tool_call(xml)

        assert not result.success
        assert result.error is not None

    def test_invalid_xml_syntax(self):
        """Test error handling for completely invalid XML."""
        xml = "not xml at all"

        result = self.parser.parse_tool_call(xml)

        assert not result.success
        assert result.error is not None

    def test_xml_with_declaration(self):
        """Test handling of XML with declaration."""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <read_file>
        <args>
        <path>test.py</path>
        </args>
        </read_file>
        """

        result = self.parser.parse_tool_call(xml)

        assert result.success
        assert result.data['tool_name'] == 'read_file'


class TestSchemaValidation:
    """Test suite for schema validation functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.parser = ToolXMLParser()

    def test_valid_parameters_pass_validation(self):
        """Test that valid parameters pass schema validation."""
        schema = {
            'required': ['path'],
            'parameters': {
                'path': {'type': 'string'},
                'line_count': {'type': 'integer'}
            }
        }

        parameters = {
            'path': 'test.py',
            'line_count': 10
        }

        result = self.parser.validate_against_schema(
            'write_to_file',
            parameters,
            schema
        )

        assert result.success

    def test_missing_required_parameter(self):
        """Test validation fails for missing required parameter."""
        schema = {
            'required': ['path', 'content'],
            'parameters': {
                'path': {'type': 'string'},
                'content': {'type': 'string'}
            }
        }

        parameters = {
            'path': 'test.py'
            # Missing 'content'
        }

        result = self.parser.validate_against_schema(
            'write_to_file',
            parameters,
            schema
        )

        assert not result.success
        assert 'Missing required parameter: content' in result.error

    def test_wrong_parameter_type(self):
        """Test validation fails for wrong parameter type."""
        schema = {
            'required': ['line_count'],
            'parameters': {
                'line_count': {'type': 'integer'}
            }
        }

        parameters = {
            'line_count': 'not an integer'
        }

        result = self.parser.validate_against_schema(
            'tool',
            parameters,
            schema
        )

        assert not result.success
        assert 'wrong type' in result.error
        assert 'line_count' in result.error

    def test_optional_parameters_allowed(self):
        """Test that optional parameters don't cause validation failure."""
        schema = {
            'required': ['path'],
            'parameters': {
                'path': {'type': 'string'},
                'optional_param': {'type': 'string'}
            }
        }

        parameters = {
            'path': 'test.py'
            # optional_param not provided
        }

        result = self.parser.validate_against_schema(
            'tool',
            parameters,
            schema
        )

        assert result.success

    def test_extra_parameters_allowed(self):
        """Test that extra parameters not in schema are allowed."""
        schema = {
            'required': ['path'],
            'parameters': {
                'path': {'type': 'string'}
            }
        }

        parameters = {
            'path': 'test.py',
            'extra_param': 'extra_value'
        }

        result = self.parser.validate_against_schema(
            'tool',
            parameters,
            schema
        )

        assert result.success

    def test_number_type_accepts_int_and_float(self):
        """Test that 'number' type accepts both int and float."""
        schema = {
            'required': ['value'],
            'parameters': {
                'value': {'type': 'number'}
            }
        }

        # Test with integer
        result = self.parser.validate_against_schema(
            'tool',
            {'value': 42},
            schema
        )
        assert result.success

        # Test with float
        result = self.parser.validate_against_schema(
            'tool',
            {'value': 42.5},
            schema
        )
        assert result.success

    def test_array_type_validation(self):
        """Test validation of array/list types."""
        schema = {
            'required': ['items'],
            'parameters': {
                'items': {'type': 'array'}
            }
        }

        parameters = {
            'items': ['item1', 'item2', 'item3']
        }

        result = self.parser.validate_against_schema(
            'tool',
            parameters,
            schema
        )

        assert result.success

    def test_object_type_validation(self):
        """Test validation of object/dict types."""
        schema = {
            'required': ['config'],
            'parameters': {
                'config': {'type': 'object'}
            }
        }

        parameters = {
            'config': {'key1': 'value1', 'key2': 'value2'}
        }

        result = self.parser.validate_against_schema(
            'tool',
            parameters,
            schema
        )

        assert result.success


class TestErrorFormatting:
    """Test suite for error message formatting."""

    def setup_method(self):
        """Set up test fixtures."""
        self.parser = ToolXMLParser()

    def test_format_error_with_location(self):
        """Test error formatting with line/column location."""
        xml_content = "<read_file>\n<args>\n<path>test.py</args>\n</read_file>"
        error = "Mismatched tag"
        location = (3, 5)

        formatted = self.parser.format_error_message(xml_content, error, location)

        assert "XML Parse Error" in formatted
        assert "Mismatched tag" in formatted
        assert "Line 3" in formatted

    def test_format_error_without_location(self):
        """Test error formatting without specific location."""
        xml_content = "<read_file>\n<args>\n<path>test.py</path>\n</args>\n</read_file>"
        error = "General error"

        formatted = self.parser.format_error_message(xml_content, error, None)

        assert "XML Parse Error" in formatted
        assert "General error" in formatted
        assert "XML content" in formatted


class TestRealWorldExamples:
    """Test suite with real-world XML examples from actual tool calls."""

    def setup_method(self):
        """Set up test fixtures."""
        self.parser = ToolXMLParser()

    def test_read_file_with_line_range(self):
        """Test real-world read_file call with line range."""
        xml = """
        <read_file>
        <args>
        <file>
        <path>src/main.py</path>
        </file>
        <start_line>10</start_line>
        <end_line>20</end_line>
        </args>
        </read_file>
        """

        result = self.parser.parse_tool_call(xml)

        assert result.success
        assert result.data['parameters']['file']['path'] == 'src/main.py'
        assert result.data['parameters']['start_line'] == '10'
        assert result.data['parameters']['end_line'] == '20'

    def test_write_to_file_with_content(self):
        """Test real-world write_to_file call."""
        xml = """
        <write_to_file>
        <args>
        <file>
        <path>test.py</path>
        </file>
        <content>def hello():
    print("world")
</content>
        <line_count>2</line_count>
        </args>
        </write_to_file>
        """

        result = self.parser.parse_tool_call(xml)

        assert result.success
        assert 'def hello():' in result.data['parameters']['content']
        assert 'print("world")' in result.data['parameters']['content']

    def test_execute_command(self):
        """Test real-world execute_command call."""
        xml = """
        <execute_command>
        <args>
        <command>npm install express</command>
        <cwd>.</cwd>
        </args>
        </execute_command>
        """

        result = self.parser.parse_tool_call(xml)

        assert result.success
        assert result.data['parameters']['command'] == 'npm install express'
        assert result.data['parameters']['cwd'] == '.'

    def test_search_and_replace(self):
        """Test real-world search_and_replace call."""
        xml = """
        <search_and_replace>
        <args>
        <file>
        <path>src/config.py</path>
        </file>
        <search>DEBUG = True</search>
        <replace>DEBUG = False</replace>
        </args>
        </search_and_replace>
        """

        result = self.parser.parse_tool_call(xml)

        assert result.success
        assert result.data['parameters']['search'] == 'DEBUG = True'
        assert result.data['parameters']['replace'] == 'DEBUG = False'
