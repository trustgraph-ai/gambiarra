"""
Format validation to prevent client/server drift.
Ensures XML tool calls match the master specification.
"""

import re
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

from .registry import get_tool_registry, ToolValidationError


@dataclass
class ValidationResult:
    """Result of XML format validation."""
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    parsed_tool: Optional[str] = None
    parsed_parameters: Optional[Dict[str, Any]] = None


class XMLFormatValidator:
    """Validates XML tool calls against master specification."""

    def __init__(self):
        self.registry = get_tool_registry()

    def validate_xml_format(self, xml_content: str) -> ValidationResult:
        """Validate XML format against master specification."""
        errors = []
        warnings = []

        # Basic XML structure validation
        if not xml_content.strip():
            errors.append("Empty XML content")
            return ValidationResult(is_valid=False, errors=errors, warnings=warnings)

        # Extract tool name
        tool_name = self._extract_tool_name(xml_content)
        if not tool_name:
            errors.append("Could not identify tool type from XML")
            return ValidationResult(is_valid=False, errors=errors, warnings=warnings)

        # Check if tool exists in registry
        tool_def = self.registry.get_tool(tool_name)
        if not tool_def:
            errors.append(f"Unknown tool: {tool_name}")
            return ValidationResult(is_valid=False, errors=errors, warnings=warnings)

        # Validate XML structure against expected format
        structure_errors = self._validate_xml_structure(xml_content, tool_name)
        errors.extend(structure_errors)

        # Parse parameters
        try:
            from .parser import ToolCallParser
            parsed_params = ToolCallParser.parse_xml_parameters(xml_content)

            # Validate parameters against tool definition
            param_errors = self._validate_parameters(tool_name, parsed_params)
            errors.extend(param_errors)

        except Exception as e:
            errors.append(f"Failed to parse parameters: {str(e)}")
            parsed_params = None

        # Check for common issues
        format_warnings = self._check_format_issues(xml_content, tool_name)
        warnings.extend(format_warnings)

        is_valid = len(errors) == 0

        return ValidationResult(
            is_valid=is_valid,
            errors=errors,
            warnings=warnings,
            parsed_tool=tool_name,
            parsed_parameters=parsed_params if is_valid else None
        )

    def _extract_tool_name(self, xml_content: str) -> Optional[str]:
        """Extract tool name from XML content."""
        # Look for opening tag
        match = re.search(r'<(\w+)(?:\s|>)', xml_content)
        if match:
            potential_tool = match.group(1)
            if potential_tool in self.registry.list_tools():
                return potential_tool

        return None

    def _validate_xml_structure(self, xml_content: str, tool_name: str) -> List[str]:
        """Validate XML structure against expected format."""
        errors = []

        # Check for properly closed tags
        if f"<{tool_name}>" in xml_content and f"</{tool_name}>" not in xml_content:
            errors.append(f"Missing closing tag for <{tool_name}>")

        # Tool-specific structure validation - all tools now use nested args structure
        if tool_name == "read_file":
            # Should have nested structure: <read_file><args><file><path>...</path></file></args></read_file>
            if "<args>" not in xml_content:
                errors.append("read_file missing <args> element")
            elif "<file>" not in xml_content:
                errors.append("read_file missing <file> element within <args>")
            elif not re.search(r'<args>.*<file>.*<path>.*</path>.*</file>.*</args>', xml_content, re.DOTALL):
                errors.append("read_file has incorrect nested structure")

        elif tool_name in ["write_to_file", "list_files", "search_files", "execute_command",
                          "search_and_replace", "insert_content", "list_code_definition_names",
                          "attempt_completion", "ask_followup_question", "update_todo_list"]:
            # All tools now require nested args structure
            if "<args>" not in xml_content:
                errors.append(f"{tool_name} missing <args> element")

        return errors

    def _validate_parameters(self, tool_name: str, parameters: Dict[str, Any]) -> List[str]:
        """Validate parameters against tool definition."""
        errors = []

        try:
            self.registry.validate_tool_call(tool_name, parameters)
        except ToolValidationError as e:
            errors.append(str(e))

        return errors

    def _check_format_issues(self, xml_content: str, tool_name: str) -> List[str]:
        """Check for common format issues that could cause drift."""
        warnings = []

        # Check for extra whitespace in parameter values
        param_matches = re.findall(r'<(\w+)>\s*(.*?)\s*</\1>', xml_content, re.DOTALL)
        for param_name, param_value in param_matches:
            if param_value != param_value.strip():
                warnings.append(f"Parameter '{param_name}' has extra whitespace")

        # Check for HTML entities that might not be properly escaped
        if '&' in xml_content and not re.search(r'&(?:amp|lt|gt|quot|apos);', xml_content):
            warnings.append("Unescaped ampersand found - may cause parsing issues")

        # Check for inconsistent boolean format
        bool_matches = re.findall(r'<recursive>(.*?)</recursive>', xml_content)
        for bool_value in bool_matches:
            if bool_value not in ['true', 'false']:
                warnings.append(f"Non-standard boolean value: '{bool_value}'")

        return warnings

    def validate_against_specification(self, xml_content: str, expected_tool: str) -> ValidationResult:
        """Validate XML against specific tool specification."""
        result = self.validate_xml_format(xml_content)

        if result.parsed_tool != expected_tool:
            result.errors.append(f"Expected tool '{expected_tool}', got '{result.parsed_tool}'")
            result.is_valid = False

        return result


class FormatDriftDetector:
    """Detects potential format drift between client and server."""

    def __init__(self):
        self.validator = XMLFormatValidator()
        self.seen_formats: Dict[str, List[str]] = {}

    def record_tool_call(self, tool_name: str, xml_content: str) -> None:
        """Record a tool call format for drift detection."""
        if tool_name not in self.seen_formats:
            self.seen_formats[tool_name] = []

        # Normalize XML for comparison
        normalized = self._normalize_xml(xml_content)
        if normalized not in self.seen_formats[tool_name]:
            self.seen_formats[tool_name].append(normalized)

    def detect_drift(self) -> Dict[str, List[str]]:
        """Detect tools with multiple different formats (potential drift)."""
        drift_detected = {}

        for tool_name, formats in self.seen_formats.items():
            if len(formats) > 1:
                drift_detected[tool_name] = formats

        return drift_detected

    def _normalize_xml(self, xml_content: str) -> str:
        """Normalize XML content for comparison."""
        # Remove whitespace variations and parameter values
        normalized = re.sub(r'>\s+<', '><', xml_content.strip())
        # Replace parameter values with placeholders
        normalized = re.sub(r'<(\w+)>.*?</\1>', r'<\1>{value}</\1>', normalized)
        return normalized


# Global instances
_validator = XMLFormatValidator()
_drift_detector = FormatDriftDetector()


def validate_xml_tool_call(xml_content: str) -> ValidationResult:
    """Validate XML tool call format."""
    result = _validator.validate_xml_format(xml_content)

    # Record for drift detection
    if result.parsed_tool:
        _drift_detector.record_tool_call(result.parsed_tool, xml_content)

    return result


def get_format_drift_report() -> Dict[str, List[str]]:
    """Get report of detected format drift."""
    return _drift_detector.detect_drift()