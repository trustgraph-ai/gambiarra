"""
XML tool call parser that matches the master specification.
Handles both flat and nested XML structures according to server/prompts/tools.py.
"""

import re
import html
from typing import Dict, Any, Optional


class ToolCallParser:
    """Parses XML tool calls according to master specification."""

    @staticmethod
    def parse_xml_parameters(xml_content: str) -> Dict[str, Any]:
        """Parse parameters from XML tool content according to master specification."""

        def unescape_content(content: str) -> str:
            """Unescape HTML entities in content."""
            if content:
                return html.unescape(content)
            return content

        params = {}

        # Determine tool type from root element
        tool_type = ToolCallParser._extract_tool_type(xml_content)

        if not tool_type:
            # Fallback to legacy flat parsing for backward compatibility
            return ToolCallParser._parse_flat_structure(xml_content, unescape_content)

        # Parse according to master specification - all tools now use nested args structure
        if tool_type == "read_file":
            # Nested structure: <read_file><args><file><path>...</path></file></args></read_file>
            path_match = re.search(r'<args>.*?<file>.*?<path>(.*?)</path>.*?</file>.*?</args>', xml_content, re.DOTALL)
            if path_match:
                params["path"] = unescape_content(path_match.group(1).strip())

        elif tool_type in ["write_to_file", "search_and_replace", "insert_content", "list_code_definition_names", "list_files", "search_files"]:
            # Nested structure with args wrapper: <tool><args><path>...</path></args></tool>
            path_match = re.search(r'<args>.*?<path>(.*?)</path>.*?</args>', xml_content, re.DOTALL)
            if path_match:
                params["path"] = unescape_content(path_match.group(1).strip())

        # Extract tool-specific parameters
        ToolCallParser._extract_tool_parameters(tool_type, xml_content, params, unescape_content)

        return params

    @staticmethod
    def _extract_tool_type(xml_content: str) -> Optional[str]:
        """Extract tool type from XML content."""
        tool_types = [
            "read_file", "write_to_file", "list_files", "search_files",
            "execute_command", "search_and_replace", "insert_content",
            "list_code_definition_names", "attempt_completion",
            "ask_followup_question", "update_todo_list"
        ]

        for tool in tool_types:
            if f"<{tool}>" in xml_content or f"<{tool} " in xml_content:
                return tool

        return None

    @staticmethod
    def _extract_tool_parameters(tool_type: str, xml_content: str, params: Dict[str, Any], unescape_func) -> None:
        """Extract tool-specific parameters from nested args structure."""

        # All tools now use nested args structure, so search within <args> tags
        if tool_type == "write_to_file":
            content_match = re.search(r'<args>.*?<content>(.*?)</content>.*?</args>', xml_content, re.DOTALL)
            if content_match:
                params["content"] = unescape_func(content_match.group(1))

            line_count_match = re.search(r'<args>.*?<line_count>(\d+)</line_count>.*?</args>', xml_content, re.DOTALL)
            if line_count_match:
                params["line_count"] = int(line_count_match.group(1))

        elif tool_type == "search_files":
            regex_match = re.search(r'<args>.*?<regex>(.*?)</regex>.*?</args>', xml_content, re.DOTALL)
            if regex_match:
                params["regex"] = unescape_func(regex_match.group(1).strip())

            file_pattern_match = re.search(r'<args>.*?<file_pattern>(.*?)</file_pattern>.*?</args>', xml_content, re.DOTALL)
            if file_pattern_match:
                params["file_pattern"] = unescape_func(file_pattern_match.group(1).strip())

        elif tool_type == "list_files":
            recursive_match = re.search(r'<args>.*?<recursive>(true|false)</recursive>.*?</args>', xml_content, re.DOTALL)
            if recursive_match:
                params["recursive"] = recursive_match.group(1) == "true"

        elif tool_type == "execute_command":
            command_match = re.search(r'<args>.*?<command>(.*?)</command>.*?</args>', xml_content, re.DOTALL)
            if command_match:
                params["command"] = unescape_func(command_match.group(1).strip())

        elif tool_type == "search_and_replace":
            search_match = re.search(r'<args>.*?<search>(.*?)</search>.*?</args>', xml_content, re.DOTALL)
            if search_match:
                params["search"] = unescape_func(search_match.group(1))

            replace_match = re.search(r'<args>.*?<replace>(.*?)</replace>.*?</args>', xml_content, re.DOTALL)
            if replace_match:
                params["replace"] = unescape_func(replace_match.group(1))

        elif tool_type == "insert_content":
            line_number_match = re.search(r'<args>.*?<line_number>(\d+)</line_number>.*?</args>', xml_content, re.DOTALL)
            if line_number_match:
                params["line_number"] = int(line_number_match.group(1))

            content_match = re.search(r'<args>.*?<content>(.*?)</content>.*?</args>', xml_content, re.DOTALL)
            if content_match:
                params["content"] = unescape_func(content_match.group(1))

        elif tool_type == "ask_followup_question":
            question_match = re.search(r'<args>.*?<question>(.*?)</question>.*?</args>', xml_content, re.DOTALL)
            if question_match:
                params["question"] = unescape_func(question_match.group(1))

        elif tool_type == "attempt_completion":
            result_match = re.search(r'<args>.*?<result>(.*?)</result>.*?</args>', xml_content, re.DOTALL)
            if result_match:
                params["result"] = unescape_func(result_match.group(1))

        elif tool_type == "update_todo_list":
            todos_match = re.search(r'<args>.*?<todos>(.*?)</todos>.*?</args>', xml_content, re.DOTALL)
            if todos_match:
                params["todos"] = unescape_func(todos_match.group(1))

    @staticmethod
    def _parse_flat_structure(xml_content: str, unescape_func) -> Dict[str, Any]:
        """Fallback parsing for flat XML structure (legacy compatibility)."""
        params = {}

        # Extract common parameters using flat structure
        patterns = {
            "path": r'<path>(.*?)</path>',
            "content": r'<content>(.*?)</content>',
            "regex": r'<regex>(.*?)</regex>',
            "command": r'<command>(.*?)</command>',
            "search": r'<search>(.*?)</search>',
            "replace": r'<replace>(.*?)</replace>',
            "line_count": r'<line_count>(\d+)</line_count>',
            "line_number": r'<line_number>(\d+)</line_number>',
            "recursive": r'<recursive>(true|false)</recursive>',
            "file_pattern": r'<file_pattern>(.*?)</file_pattern>',
            "question": r'<question>(.*?)</question>',
            "result": r'<result>(.*?)</result>',
            "todos": r'<todos>(.*?)</todos>'
        }

        for param_name, pattern in patterns.items():
            flags = re.DOTALL if param_name in ["content", "search", "replace", "question", "result", "todos"] else 0
            match = re.search(pattern, xml_content, flags)
            if match:
                value = match.group(1)
                if param_name in ["line_number", "line_count"]:
                    params[param_name] = int(value)
                elif param_name == "recursive":
                    params[param_name] = value == "true"
                else:
                    params[param_name] = unescape_func(value.strip() if value else "")

        return params


def parse_xml_parameters(xml_content: str) -> Dict[str, Any]:
    """Legacy function for backward compatibility."""
    return ToolCallParser.parse_xml_parameters(xml_content)