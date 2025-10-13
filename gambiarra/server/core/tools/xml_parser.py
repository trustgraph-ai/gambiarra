"""
Robust XML parser for tool calls using xml.etree.ElementTree.

Replaces fragile regex-based parsing with proper XML handling.
This module provides safe, reliable parsing of AI-generated tool calls
in XML format with comprehensive error handling and validation.
"""

import xml.etree.ElementTree as ET
from typing import Dict, Any, Optional
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ParseResult:
    """Result of XML parsing operation."""
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    error_location: Optional[tuple] = None  # (line, column)


class ToolXMLParser:
    """
    Robust XML parser for tool calls using xml.etree.ElementTree.

    This parser replaces the previous regex-based implementation with
    proper XML parsing that handles:
    - Nested elements
    - CDATA sections
    - Proper error reporting
    - Schema validation

    Example:
        parser = ToolXMLParser()
        result = parser.parse_tool_call(xml_string)
        if result.success:
            tool_name = result.data['tool_name']
            parameters = result.data['parameters']
    """

    def parse_tool_call(self, xml_content: str) -> ParseResult:
        """
        Parse XML tool call into structured parameters.

        Args:
            xml_content: XML string from AI

        Returns:
            ParseResult with success status and parsed data or error

        Example:
            >>> parser = ToolXMLParser()
            >>> xml = '''
            ... <read_file>
            ... <args>
            ... <path>test.py</path>
            ... </args>
            ... </read_file>
            ... '''
            >>> result = parser.parse_tool_call(xml)
            >>> result.success
            True
            >>> result.data['tool_name']
            'read_file'
        """
        try:
            # Clean up the XML content
            xml_content = xml_content.strip()

            # Wrap in root element if not already wrapped
            if not xml_content.startswith('<?xml'):
                xml_content = f'<root>{xml_content}</root>'

            # Parse XML
            root = ET.fromstring(xml_content)

            # Extract tool element (unwrap root if we added it)
            tool_element = root if root.tag != 'root' else root[0]
            tool_name = tool_element.tag

            # Find args element
            args_element = tool_element.find('args')
            if args_element is None:
                return ParseResult(
                    success=False,
                    error=f"No <args> element found in <{tool_name}>"
                )

            # Recursively parse parameters
            parameters = self._parse_element(args_element)

            return ParseResult(
                success=True,
                data={
                    'tool_name': tool_name,
                    'parameters': parameters
                }
            )

        except ET.ParseError as e:
            logger.error(f"XML parse error: {e}")
            return ParseResult(
                success=False,
                error=f"Invalid XML structure: {e}",
                error_location=(e.position[0], e.position[1]) if hasattr(e, 'position') else None
            )
        except Exception as e:
            logger.error(f"Unexpected error parsing XML: {e}", exc_info=True)
            return ParseResult(
                success=False,
                error=f"Parse error: {str(e)}"
            )

    def _parse_element(self, element: ET.Element) -> Any:
        """
        Recursively parse XML element into Python data structure.

        Handles:
        - Simple text content (leaf nodes)
        - Nested elements (converted to dict)
        - CDATA sections
        - Multiple elements with same name (converted to list)

        Args:
            element: XML element to parse

        Returns:
            Parsed value (str, dict, or list)
        """
        # Check if element has children
        children = list(element)

        if not children:
            # Leaf node - return text content
            text = element.text or ""
            return text.strip()

        # Has children - parse as dict
        result = {}

        for child in children:
            child_name = child.tag
            child_value = self._parse_element(child)

            # Handle multiple elements with same name
            if child_name in result:
                # Convert to list on second occurrence
                if not isinstance(result[child_name], list):
                    result[child_name] = [result[child_name]]
                result[child_name].append(child_value)
            else:
                result[child_name] = child_value

        return result

    def validate_against_schema(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        schema: Dict[str, Any]
    ) -> ParseResult:
        """
        Validate parsed parameters against tool schema.

        Args:
            tool_name: Name of the tool
            parameters: Parsed parameters
            schema: Expected parameter schema with structure:
                {
                    'required': ['param1', 'param2'],
                    'parameters': {
                        'param1': {'type': 'string', 'description': '...'},
                        'param2': {'type': 'integer'}
                    }
                }

        Returns:
            ParseResult indicating validation success/failure

        Example:
            >>> schema = {
            ...     'required': ['path'],
            ...     'parameters': {
            ...         'path': {'type': 'string'},
            ...         'line_count': {'type': 'integer'}
            ...     }
            ... }
            >>> parser.validate_against_schema('write_file', params, schema)
        """
        errors = []

        # Check required parameters
        required = schema.get('required', [])
        for param in required:
            if param not in parameters:
                errors.append(f"Missing required parameter: {param}")

        # Check parameter types
        param_types = schema.get('parameters', {})
        for param, value in parameters.items():
            if param in param_types:
                expected_type = param_types[param].get('type')
                if expected_type and not self._check_type(value, expected_type):
                    errors.append(
                        f"Parameter '{param}' has wrong type: "
                        f"expected {expected_type}, got {type(value).__name__}"
                    )

        if errors:
            return ParseResult(
                success=False,
                error=f"Validation failed for {tool_name}: " + "; ".join(errors)
            )

        return ParseResult(success=True, data=parameters)

    def _check_type(self, value: Any, expected_type: str) -> bool:
        """
        Check if value matches expected type.

        Args:
            value: Value to check
            expected_type: Expected type string ('string', 'integer', etc.)

        Returns:
            True if type matches, False otherwise
        """
        type_map = {
            'string': str,
            'integer': int,
            'number': (int, float),
            'boolean': bool,
            'object': dict,
            'array': list
        }

        expected = type_map.get(expected_type)
        if expected is None:
            # Unknown type, skip validation
            logger.warning(f"Unknown type in schema: {expected_type}")
            return True

        return isinstance(value, expected)

    def format_error_message(self, xml_content: str, error: str, location: Optional[tuple] = None) -> str:
        """
        Format a user-friendly error message with context.

        Args:
            xml_content: Original XML content
            error: Error message
            location: Optional (line, column) tuple

        Returns:
            Formatted error message with context
        """
        lines = xml_content.split('\n')

        message = f"XML Parse Error: {error}\n\n"

        if location:
            line_num, col_num = location
            if 0 <= line_num - 1 < len(lines):
                message += f"Line {line_num}:\n"
                message += f"  {lines[line_num - 1]}\n"
                message += f"  {' ' * (col_num - 1)}^\n"
        else:
            # Show first few lines of XML for context
            message += "XML content (first 5 lines):\n"
            for i, line in enumerate(lines[:5], 1):
                message += f"  {i}: {line}\n"

        return message
