# Gambiarra Technical Specification v2.0
## Implementation of REVIEW.md Findings

**Document Version:** 2.0
**Status:** PROPOSED
**Based on:** REVIEW.md Comprehensive Technical Review
**Target Release:** Q1 2026

---

## Executive Summary

This specification addresses critical gaps and improvements identified in the comprehensive code review (REVIEW.md). It focuses on three major enhancement areas:

1. **Command Execution Intelligence** - Bidirectional communication, pre-execution validation, interactive command handling
2. **Prompt Engineering System** - Template-based prompts, LLM-specific variants, deployment context customization
3. **Critical Fixes** - XML parser replacement, transaction support, enhanced testing

**Overall Goal:** Transform Gambiarra from a strong prototype (3.5/5) to a production-ready enterprise solution (4.5/5).

---

## Table of Contents

1. [Critical Fixes (Immediate)](#1-critical-fixes-immediate)
2. [Command Execution Intelligence](#2-command-execution-intelligence)
3. [Prompt Engineering System](#3-prompt-engineering-system)
4. [Enhanced Context Management](#4-enhanced-context-management)
5. [Transaction & Rollback System](#5-transaction--rollback-system)
6. [Rate Limiting & Cost Control](#6-rate-limiting--cost-control)
7. [Session Persistence](#7-session-persistence)
8. [Testing Infrastructure](#8-testing-infrastructure)
9. [Deployment & Configuration](#9-deployment--configuration)
10. [Migration Strategy](#10-migration-strategy)

---

## 1. Critical Fixes (Immediate)

### 1.1 Replace XML Parser (Priority: 🔴 CRITICAL)

**Problem:** Current regex-based XML parsing is fragile and unsafe.

**Location:** `server/core/tools/parser.py:15-172`

**Solution:**

```python
# NEW: server/core/tools/xml_parser.py
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

    Replaces fragile regex-based parsing with proper XML handling.
    """

    def parse_tool_call(self, xml_content: str) -> ParseResult:
        """
        Parse XML tool call into structured parameters.

        Args:
            xml_content: XML string from AI

        Returns:
            ParseResult with success status and parsed data or error
        """
        try:
            # Wrap in root element if not already wrapped
            if not xml_content.strip().startswith('<?xml'):
                xml_content = f'<root>{xml_content}</root>'

            root = ET.fromstring(xml_content)

            # Extract tool name and parameters
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
                error_location=(e.position[0], e.position[1])
            )
        except Exception as e:
            logger.error(f"Unexpected error parsing XML: {e}")
            return ParseResult(
                success=False,
                error=f"Parse error: {str(e)}"
            )

    def _parse_element(self, element: ET.Element) -> Any:
        """
        Recursively parse XML element into Python data structure.

        Handles:
        - Simple text content
        - Nested elements (converted to dict)
        - CDATA sections
        - Attributes (if present)
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
                # Convert to list
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
            schema: Expected parameter schema

        Returns:
            ParseResult indicating validation success/failure
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
                        f"Parameter {param} has wrong type: "
                        f"expected {expected_type}, got {type(value).__name__}"
                    )

        if errors:
            return ParseResult(
                success=False,
                error=f"Validation failed for {tool_name}: " + "; ".join(errors)
            )

        return ParseResult(success=True, data=parameters)

    def _check_type(self, value: Any, expected_type: str) -> bool:
        """Check if value matches expected type."""
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
            return True  # Unknown type, skip validation

        return isinstance(value, expected)


# Example usage:
"""
parser = ToolXMLParser()

xml = '''
<read_file>
<args>
<file>
<path>src/main.py</path>
</file>
<start_line>10</start_line>
<end_line>20</end_line>
</args>
</read_file>
'''

result = parser.parse_tool_call(xml)
if result.success:
    print(result.data)
    # {
    #   'tool_name': 'read_file',
    #   'parameters': {
    #     'file': {'path': 'src/main.py'},
    #     'start_line': '10',
    #     'end_line': '20'
    #   }
    # }
else:
    print(f"Error: {result.error}")
"""
```

**Testing Requirements:**

```python
# tests/server/core/tools/test_xml_parser.py
import pytest
from gambiarra.server.core.tools.xml_parser import ToolXMLParser


class TestToolXMLParser:
    def test_simple_tool_call(self):
        """Test parsing simple tool with flat parameters."""
        parser = ToolXMLParser()
        xml = """
        <read_file>
        <args>
        <path>test.py</path>
        </args>
        </read_file>
        """

        result = parser.parse_tool_call(xml)
        assert result.success
        assert result.data['tool_name'] == 'read_file'
        assert result.data['parameters']['path'] == 'test.py'

    def test_nested_parameters(self):
        """Test parsing tool with nested parameters."""
        parser = ToolXMLParser()
        xml = """
        <write_to_file>
        <args>
        <file>
        <path>src/main.py</path>
        </file>
        <content>print("hello")</content>
        </args>
        </write_to_file>
        """

        result = parser.parse_tool_call(xml)
        assert result.success
        assert result.data['parameters']['file']['path'] == 'src/main.py'

    def test_cdata_content(self):
        """Test handling of CDATA sections."""
        parser = ToolXMLParser()
        xml = """
        <execute_command>
        <args>
        <command><![CDATA[grep -r "test" | wc -l]]></command>
        </args>
        </execute_command>
        """

        result = parser.parse_tool_call(xml)
        assert result.success
        assert 'grep -r "test"' in result.data['parameters']['command']

    def test_malformed_xml(self):
        """Test error handling for malformed XML."""
        parser = ToolXMLParser()
        xml = "<read_file><args><path>test.py</args></read_file>"  # Missing closing tag

        result = parser.parse_tool_call(xml)
        assert not result.success
        assert "Invalid XML" in result.error
        assert result.error_location is not None

    def test_missing_args_element(self):
        """Test error handling for missing args."""
        parser = ToolXMLParser()
        xml = "<read_file><path>test.py</path></read_file>"

        result = parser.parse_tool_call(xml)
        assert not result.success
        assert "No <args> element" in result.error

    def test_schema_validation(self):
        """Test parameter validation against schema."""
        parser = ToolXMLParser()

        schema = {
            'required': ['path'],
            'parameters': {
                'path': {'type': 'string'},
                'line_count': {'type': 'integer'}
            }
        }

        # Valid parameters
        result = parser.validate_against_schema(
            'write_to_file',
            {'path': 'test.py', 'line_count': 10},
            schema
        )
        assert result.success

        # Missing required parameter
        result = parser.validate_against_schema(
            'write_to_file',
            {'line_count': 10},
            schema
        )
        assert not result.success
        assert "Missing required parameter: path" in result.error
```

**Migration Steps:**

1. Create new `xml_parser.py` module
2. Add comprehensive tests
3. Update `parser.py` to use new parser
4. Run full regression tests
5. Monitor for parsing errors in production
6. Deprecate old regex-based parser after 1 month

**Timeline:** 2-3 days

---

## 2. Command Execution Intelligence

### 2.1 Architecture Overview

**New Component:** `ExecutionManager` - Intelligent command execution with context awareness

```
┌──────────────────────────────────────────────────────────────┐
│                     ExecutionManager                         │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────────┐  ┌──────────────────┐  ┌─────────────┐  │
│  │ Command         │  │ Hang             │  │ Interaction │  │
│  │ Knowledge Base  │  │ Detector         │  │ Handler     │  │
│  │                 │  │                  │  │             │  │
│  │ • Patterns      │  │ • Prompt detect  │  │ • Auto-resp │  │
│  │ • Preconditions │  │ • Timeout logic  │  │ • Server    │  │
│  │ • Non-int flags │  │ • Pattern match  │  │   comm      │  │
│  └─────────────────┘  └──────────────────┘  └─────────────┘  │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │              SmartExecution                            │  │
│  │  • Bidirectional stdin/stdout                          │  │
│  │  • Real-time hang detection                            │  │
│  │  • Progress streaming to server                        │  │
│  │  • Interactive prompt handling                         │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

### 2.2 Bidirectional Execution Protocol

**New WebSocket Message Types:**

```python
# server/core/protocol/execution_messages.py
from enum import Enum
from dataclasses import dataclass
from typing import Optional, List, Dict, Any


class ExecutionMessageType(Enum):
    """WebSocket message types for command execution."""

    # Client → Server
    EXECUTION_PROGRESS = "execution_progress"
    EXECUTION_INPUT_REQUIRED = "execution_input_required"
    EXECUTION_STATE_CHANGE = "execution_state_change"
    EXECUTION_PREFLIGHT_FAILED = "execution_preflight_failed"

    # Server → Client
    EXECUTION_PROVIDE_INPUT = "execution_provide_input"
    EXECUTION_CANCEL = "execution_cancel"
    EXECUTION_ADJUST_TIMEOUT = "execution_adjust_timeout"


@dataclass
class ExecutionProgressMessage:
    """Progress update during command execution."""
    execution_id: str
    stream: str  # "stdout" or "stderr"
    content: str
    timestamp: float
    line_number: Optional[int] = None


@dataclass
class ExecutionInputRequiredMessage:
    """Command requires user input."""
    execution_id: str
    prompt: str
    detected_options: List[str]
    timeout_seconds: float
    context: Dict[str, Any]
    suggested_response: Optional[str] = None


@dataclass
class ExecutionProvideInputMessage:
    """Server provides input to command."""
    execution_id: str
    input: str
    source: str  # "ai_decision", "user_input", "default_rule"


@dataclass
class ExecutionPreflightFailedMessage:
    """Pre-execution validation failed."""
    execution_id: str
    reason: str
    message: str
    suggested_fixes: List[str]
    require_user_decision: bool
    context: Dict[str, Any]
```

### 2.3 Command Knowledge Base

```python
# client/execution/command_knowledge.py
from dataclasses import dataclass
from typing import List, Dict, Optional, Callable
import re


@dataclass
class CommandPattern:
    """Pattern definition for known command types."""
    pattern: str
    needs_args: List[str]
    interactive_by_default: bool
    non_interactive_flags: List[str]
    preconditions: Dict[str, bool]
    expected_prompts: List[Dict[str, str]]
    typical_duration: float  # seconds
    requires_network: bool = False
    opens_editor: bool = False


class CommandKnowledgeBase:
    """
    Knowledge base of common commands and their behavior.

    Used for:
    - Pre-execution validation
    - Automatic flag addition
    - Timeout adjustment
    - Interactive prompt detection
    """

    def __init__(self):
        self.patterns: Dict[str, CommandPattern] = {}
        self._initialize_patterns()

    def _initialize_patterns(self):
        """Initialize patterns for common commands."""

        # npm/npx patterns
        self.patterns['npx_create'] = CommandPattern(
            pattern=r'^npx\s+create-',
            needs_args=['app_name'],
            interactive_by_default=True,
            non_interactive_flags=['--yes', '--template', '--use-npm'],
            preconditions={'directory_must_not_exist': True},
            expected_prompts=[
                {
                    'pattern': r'What.*template',
                    'default': 'default'
                },
                {
                    'pattern': r'Would you like to use TypeScript',
                    'default': 'yes'
                }
            ],
            typical_duration=120.0,  # 2 minutes
            requires_network=True
        )

        self.patterns['npm_init'] = CommandPattern(
            pattern=r'^npm\s+init\s*$',
            needs_args=[],
            interactive_by_default=True,
            non_interactive_flags=['-y', '--yes'],
            preconditions={'package_json_must_not_exist': True},
            expected_prompts=[
                {'pattern': r'package name:', 'default': 'my-package'},
                {'pattern': r'version:', 'default': '1.0.0'},
                {'pattern': r'description:', 'default': ''},
            ],
            typical_duration=5.0
        )

        self.patterns['npm_install'] = CommandPattern(
            pattern=r'^npm\s+install',
            needs_args=[],
            interactive_by_default=False,
            non_interactive_flags=[],
            preconditions={'package_json_must_exist': True},
            expected_prompts=[],
            typical_duration=60.0,
            requires_network=True
        )

        # Git patterns
        self.patterns['git_commit_no_message'] = CommandPattern(
            pattern=r'^git\s+commit\s*$',
            needs_args=['message'],
            interactive_by_default=True,
            non_interactive_flags=['-m'],
            preconditions={'must_have_staged_changes': True},
            expected_prompts=[],
            typical_duration=5.0,
            opens_editor=True
        )

        # Build tools
        self.patterns['cargo_build'] = CommandPattern(
            pattern=r'^cargo\s+build',
            needs_args=[],
            interactive_by_default=False,
            non_interactive_flags=[],
            preconditions={},
            expected_prompts=[],
            typical_duration=300.0,  # 5 minutes
            requires_network=False
        )

        # Python patterns
        self.patterns['pip_install'] = CommandPattern(
            pattern=r'^pip\s+install',
            needs_args=[],
            interactive_by_default=False,
            non_interactive_flags=[],
            preconditions={},
            expected_prompts=[],
            typical_duration=30.0,
            requires_network=True
        )

    def analyze_command(
        self,
        command: str,
        context: 'ExecutionContext'
    ) -> 'CommandAnalysis':
        """
        Analyze command before execution.

        Returns analysis including:
        - Whether command is safe to execute
        - Required modifications
        - Expected prompts
        - Precondition failures
        """
        # Find matching pattern
        pattern = self._find_pattern(command)

        if not pattern:
            return CommandAnalysis(
                safe_to_execute=True,
                command=command,
                pattern=None
            )

        # Check preconditions
        precondition_failures = self._check_preconditions(
            pattern,
            context
        )

        if precondition_failures:
            return CommandAnalysis(
                safe_to_execute=False,
                likely_to_fail=True,
                failure_reason=precondition_failures[0],
                suggested_fixes=self._suggest_fixes(
                    command,
                    pattern,
                    precondition_failures
                ),
                pattern=pattern
            )

        # Check if command needs modification
        needs_modification = False
        modified_command = command

        if pattern.interactive_by_default:
            if not self._has_non_interactive_flags(command, pattern):
                needs_modification = True
                modified_command = self._add_non_interactive_flags(
                    command,
                    pattern
                )

        # Check if command is missing required args
        if pattern.needs_args:
            missing_args = self._find_missing_args(command, pattern)
            if missing_args:
                return CommandAnalysis(
                    safe_to_execute=False,
                    likely_to_fail=True,
                    failure_reason=f"Missing required arguments: {missing_args}",
                    suggested_fixes=[
                        f"Add missing arguments to command"
                    ],
                    pattern=pattern
                )

        return CommandAnalysis(
            safe_to_execute=True,
            needs_modification=needs_modification,
            suggested_command=modified_command if needs_modification else None,
            expected_prompts=pattern.expected_prompts,
            typical_duration=pattern.typical_duration,
            requires_network=pattern.requires_network,
            opens_editor=pattern.opens_editor,
            pattern=pattern
        )

    def _find_pattern(self, command: str) -> Optional[CommandPattern]:
        """Find matching pattern for command."""
        for pattern_name, pattern in self.patterns.items():
            if re.match(pattern.pattern, command.strip()):
                return pattern
        return None

    def _check_preconditions(
        self,
        pattern: CommandPattern,
        context: 'ExecutionContext'
    ) -> List[str]:
        """Check if all preconditions are met."""
        failures = []

        for condition, required in pattern.preconditions.items():
            checker = getattr(self, f'_check_{condition}', None)
            if checker:
                result = checker(context)
                if result != required:
                    failures.append(condition)

        return failures

    def _check_directory_must_not_exist(
        self,
        context: 'ExecutionContext'
    ) -> bool:
        """Check if target directory doesn't exist."""
        # Extract directory name from command
        # This is command-specific logic
        import os
        # For npx create commands, extract app name
        parts = context.command.split()
        if len(parts) >= 3:
            app_name = parts[2]
            return not os.path.exists(
                os.path.join(context.cwd, app_name)
            )
        return True

    def _check_package_json_must_exist(
        self,
        context: 'ExecutionContext'
    ) -> bool:
        """Check if package.json exists."""
        import os
        return os.path.exists(
            os.path.join(context.cwd, 'package.json')
        )

    def _check_must_have_staged_changes(
        self,
        context: 'ExecutionContext'
    ) -> bool:
        """Check if git has staged changes."""
        import subprocess
        try:
            result = subprocess.run(
                ['git', 'diff', '--cached', '--quiet'],
                cwd=context.cwd,
                capture_output=True
            )
            # Returns 1 if there are changes
            return result.returncode == 1
        except:
            return False

    def _suggest_fixes(
        self,
        command: str,
        pattern: CommandPattern,
        failures: List[str]
    ) -> List[str]:
        """Suggest fixes for precondition failures."""
        fixes = []

        for failure in failures:
            if failure == 'directory_must_not_exist':
                # Extract app name
                parts = command.split()
                if len(parts) >= 3:
                    app_name = parts[2]
                    fixes.append(f"rm -rf {app_name} && {command}")
                    fixes.append(f"{command.replace(app_name, app_name + '-new')}")

            elif failure == 'package_json_must_exist':
                fixes.append(f"npm init -y && {command}")

            elif failure == 'must_have_staged_changes':
                fixes.append("git add . && " + command)

        return fixes

    def _has_non_interactive_flags(
        self,
        command: str,
        pattern: CommandPattern
    ) -> bool:
        """Check if command has non-interactive flags."""
        for flag in pattern.non_interactive_flags:
            if flag in command:
                return True
        return False

    def _add_non_interactive_flags(
        self,
        command: str,
        pattern: CommandPattern
    ) -> str:
        """Add non-interactive flags to command."""
        # Choose most appropriate flag
        if pattern.non_interactive_flags:
            flag = pattern.non_interactive_flags[0]
            return f"{command} {flag}"
        return command

    def _find_missing_args(
        self,
        command: str,
        pattern: CommandPattern
    ) -> List[str]:
        """Find missing required arguments."""
        # This is pattern-specific
        # For now, just check if command has enough parts
        parts = command.split()
        if pattern.needs_args and len(parts) < 3:
            return pattern.needs_args
        return []


@dataclass
class ExecutionContext:
    """Context for command execution."""
    command: str
    cwd: str
    env: Dict[str, str]
    user: str


@dataclass
class CommandAnalysis:
    """Result of command analysis."""
    safe_to_execute: bool
    command: str
    pattern: Optional[CommandPattern] = None
    likely_to_fail: bool = False
    failure_reason: Optional[str] = None
    suggested_fixes: List[str] = None
    needs_modification: bool = False
    suggested_command: Optional[str] = None
    expected_prompts: List[Dict[str, str]] = None
    typical_duration: float = 60.0
    requires_network: bool = False
    opens_editor: bool = False
```

### 2.4 Interactive Execution Handler

```python
# client/execution/smart_execution.py
import asyncio
import re
from typing import Optional, Dict, Any
from dataclasses import dataclass


@dataclass
class HangType:
    """Type of hang detected."""
    NORMAL = "normal"
    INTERACTIVE_PROMPT = "interactive_prompt"
    LEGITIMATE_LONG_OPERATION = "legitimate_long_operation"
    POSSIBLY_HUNG = "possibly_hung"


class HangDetector:
    """Detect and classify command hangs."""

    def __init__(self):
        # Patterns indicating interactive prompts
        self.prompt_patterns = [
            r'.*\?\s*$',                    # "? " (inquirer)
            r'.*\[Y/n\]\s*$',              # [Y/n]
            r'.*\[y/N\]\s*$',              # [y/N]
            r'.*:\s*$',                     # "Enter name: "
            r'.*\(y/N\)\s*$',              # (y/N)
            r'.*password.*:\s*$',           # Password
            r'.*continue\?.*$',             # Continue?
        ]

        # Patterns indicating legitimate long operations
        self.long_op_patterns = [
            r'Compiling',
            r'Building',
            r'Downloading',
            r'Installing',
            r'\d+%',                        # Progress
            r'Fetching',
        ]

    def analyze_hang(
        self,
        last_output: str,
        silence_duration: float,
        command: str
    ) -> str:
        """Determine why command appears hung."""

        # Check for interactive prompt patterns
        for pattern in self.prompt_patterns:
            if re.search(pattern, last_output, re.MULTILINE):
                return HangType.INTERACTIVE_PROMPT

        # Check for legitimate long operations
        for pattern in self.long_op_patterns:
            if re.search(pattern, last_output, re.MULTILINE):
                # Long operations can be silent for up to 5 minutes
                if silence_duration < 300:
                    return HangType.LEGITIMATE_LONG_OPERATION

        # Check command-specific timeouts
        if 'cargo build' in command or 'npm install' in command:
            if silence_duration < 300:
                return HangType.LEGITIMATE_LONG_OPERATION

        # No output for extended period
        if silence_duration > 60:
            return HangType.POSSIBLY_HUNG

        return HangType.NORMAL


class SmartExecution:
    """Execute command with intelligent monitoring."""

    def __init__(
        self,
        command: str,
        cwd: str,
        hang_detector: HangDetector,
        interaction_handler: 'InteractionHandler',
        execution_channel: 'ExecutionChannel'
    ):
        self.command = command
        self.cwd = cwd
        self.hang_detector = hang_detector
        self.interaction_handler = interaction_handler
        self.channel = execution_channel
        self.process = None
        self.start_time = None
        self.last_output_time = None

    async def run_with_monitoring(self) -> 'ExecutionResult':
        """Run command with real-time monitoring and interaction."""

        import shlex
        cmd_parts = shlex.split(self.command)

        self.process = await asyncio.create_subprocess_exec(
            *cmd_parts,
            cwd=self.cwd,
            stdin=asyncio.subprocess.PIPE,    # ✨ Bidirectional
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=self._get_safe_environment()
        )

        self.start_time = asyncio.get_event_loop().time()
        self.last_output_time = self.start_time

        stdout_buffer = []
        stderr_buffer = []

        async def monitor_stdout():
            """Monitor and handle stdout."""
            while True:
                try:
                    # Read with short timeout
                    line = await asyncio.wait_for(
                        self.process.stdout.readline(),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    # Check for hang
                    await self._check_for_hang(stdout_buffer)
                    continue

                if not line:
                    break

                line_str = line.decode('utf-8', errors='replace')
                stdout_buffer.append(line_str)
                self.last_output_time = asyncio.get_event_loop().time()

                # Stream to server
                await self.channel.send_progress('stdout', line_str)

                # Check if this looks like a prompt
                if self._is_interactive_prompt(line_str):
                    await self._handle_interactive_prompt(
                        ''.join(stdout_buffer[-3:])
                    )

        async def monitor_stderr():
            """Monitor stderr."""
            while True:
                try:
                    line = await asyncio.wait_for(
                        self.process.stderr.readline(),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue

                if not line:
                    break

                line_str = line.decode('utf-8', errors='replace')
                stderr_buffer.append(line_str)
                self.last_output_time = asyncio.get_event_loop().time()

                await self.channel.send_progress('stderr', line_str)

        # Run both monitors concurrently
        await asyncio.gather(
            monitor_stdout(),
            monitor_stderr(),
            self.process.wait()
        )

        return ExecutionResult(
            exit_code=self.process.returncode,
            stdout=''.join(stdout_buffer),
            stderr=''.join(stderr_buffer),
            duration=asyncio.get_event_loop().time() - self.start_time
        )

    async def _check_for_hang(self, output_buffer: list):
        """Check if command is hung."""
        current_time = asyncio.get_event_loop().time()
        silence_duration = current_time - self.last_output_time

        last_output = ''.join(output_buffer[-10:])

        hang_type = self.hang_detector.analyze_hang(
            last_output,
            silence_duration,
            self.command
        )

        if hang_type == HangType.INTERACTIVE_PROMPT:
            # Detected interactive prompt
            await self._handle_interactive_prompt(last_output)

        elif hang_type == HangType.POSSIBLY_HUNG:
            # Kill process
            self.process.kill()
            raise ExecutionHungError(
                f"Command hung after {silence_duration:.0f}s of silence"
            )

    def _is_interactive_prompt(self, line: str) -> bool:
        """Check if line looks like an interactive prompt."""
        prompt_indicators = ['?', ':', '[Y/n]', '[y/N]', '(y/N)']
        return any(ind in line for ind in prompt_indicators)

    async def _handle_interactive_prompt(self, prompt_text: str):
        """Handle interactive prompt."""
        # Request input from server
        response = await self.interaction_handler.handle_prompt(
            prompt_text,
            self.channel
        )

        # Provide input to process
        if response:
            self.process.stdin.write(f"{response}\n".encode())
            await self.process.stdin.drain()

    def _get_safe_environment(self) -> Dict[str, str]:
        """Get safe environment for execution."""
        import os
        return {
            "PATH": os.environ.get("PATH", ""),
            "HOME": os.environ.get("HOME", ""),
            "CI": "true",
            "NPM_CONFIG_YES": "true",
            "DEBIAN_FRONTEND": "noninteractive",
        }


@dataclass
class ExecutionResult:
    """Result of command execution."""
    exit_code: int
    stdout: str
    stderr: str
    duration: float


class ExecutionHungError(Exception):
    """Raised when command is detected as hung."""
    pass
```

**Timeline:** 2-3 weeks

---

## 3. Prompt Engineering System

### 3.1 Architecture

```
gambiarra/
├── prompts/
│   ├── templates/              # ✨ NEW - Jinja2 templates
│   │   ├── base.j2
│   │   ├── claude.j2
│   │   ├── gpt4.j2
│   │   ├── gemini.j2
│   │   └── opensource.j2
│   ├── contexts/              # ✨ NEW - Deployment contexts
│   │   ├── enterprise.yaml
│   │   ├── personal.yaml
│   │   ├── cicd.yaml
│   │   └── education.yaml
│   ├── overrides/             # ✨ NEW - User customizations
│   │   └── custom.yaml
│   └── engine/                # ✨ NEW - Template engine
│       ├── __init__.py
│       ├── template_engine.py
│       └── filters.py
```

### 3.2 Template Engine Implementation

```python
# server/prompts/engine/template_engine.py
from jinja2 import Environment, FileSystemLoader, select_autoescape
import yaml
import os
from typing import Dict, Any, Optional
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class PromptTemplateEngine:
    """
    Flexible prompt template engine using Jinja2.

    Features:
    - LLM-specific template variants
    - Deployment context customization
    - User overrides
    - Dynamic section inclusion
    - TrustGraph integration (optional)
    """

    def __init__(
        self,
        template_dir: str,
        context_dir: str,
        override_dir: Optional[str] = None
    ):
        self.template_dir = Path(template_dir)
        self.context_dir = Path(context_dir)
        self.override_dir = Path(override_dir) if override_dir else None

        # Initialize Jinja2 environment
        self.env = Environment(
            loader=FileSystemLoader(str(self.template_dir)),
            autoescape=select_autoescape(),
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True
        )

        # Register custom filters
        self._register_filters()

        logger.info(
            f"Prompt template engine initialized: "
            f"templates={self.template_dir}, contexts={self.context_dir}"
        )

    def _register_filters(self):
        """Register custom Jinja2 filters."""
        from .filters import (
            format_tool_xml,
            format_tool_json,
            format_tool_markdown,
            emphasize_for_llm
        )

        self.env.filters['format_tool_xml'] = format_tool_xml
        self.env.filters['format_tool_json'] = format_tool_json
        self.env.filters['format_tool_markdown'] = format_tool_markdown
        self.env.filters['emphasize'] = emphasize_for_llm

    def generate_prompt(
        self,
        llm_type: str,
        deployment_context: str,
        mode: str = "code",
        cwd: str = "/workspace",
        tools: list = None,
        overrides: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Generate customized prompt for specific LLM and context.

        Args:
            llm_type: LLM type (claude, gpt4, gemini, opensource)
            deployment_context: Deployment context (enterprise, personal, etc.)
            mode: Operating mode (code, debug, architect, etc.)
            cwd: Current working directory
            tools: Available tools
            overrides: User-specific overrides

        Returns:
            Rendered prompt string
        """
        # Load base context
        context = self._load_base_context()

        # Load deployment-specific context
        deployment_ctx = self._load_deployment_context(deployment_context)
        context.update(deployment_ctx)

        # Add runtime variables
        context.update({
            'llm_type': llm_type,
            'mode': mode,
            'cwd': cwd,
            'tools': tools or [],
            'deployment_context': deployment_context,
        })

        # Apply user overrides
        if overrides:
            context = self._apply_overrides(context, overrides)

        # Load user custom overrides from file
        if self.override_dir:
            file_overrides = self._load_user_overrides()
            if file_overrides:
                context = self._apply_overrides(context, file_overrides)

        # Select template based on LLM type
        template_name = f"{llm_type}.j2"

        if not self._template_exists(template_name):
            logger.warning(
                f"Template {template_name} not found, using base.j2"
            )
            template_name = "base.j2"

        template = self.env.get_template(template_name)

        # Render prompt
        prompt = template.render(**context)

        logger.debug(
            f"Generated prompt: llm={llm_type}, "
            f"context={deployment_context}, length={len(prompt)}"
        )

        return prompt

    def _load_base_context(self) -> Dict[str, Any]:
        """Load base context with default values."""
        return {
            'rules': {
                'critical': [],
                'important': [],
                'optional': []
            },
            'tools': [],
            'capabilities': [],
            'examples': [],
            'system': {
                'os': 'Linux',
                'shell': '/bin/bash'
            }
        }

    def _load_deployment_context(self, context_name: str) -> Dict[str, Any]:
        """Load deployment context from YAML file."""
        context_file = self.context_dir / f"{context_name}.yaml"

        if not context_file.exists():
            logger.warning(
                f"Deployment context {context_name} not found, "
                f"using defaults"
            )
            return {}

        with open(context_file, 'r') as f:
            return yaml.safe_load(f) or {}

    def _load_user_overrides(self) -> Optional[Dict[str, Any]]:
        """Load user overrides from custom.yaml."""
        if not self.override_dir:
            return None

        override_file = self.override_dir / "custom.yaml"

        if not override_file.exists():
            return None

        with open(override_file, 'r') as f:
            return yaml.safe_load(f) or {}

    def _apply_overrides(
        self,
        context: Dict[str, Any],
        overrides: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Apply overrides to context (deep merge)."""

        def deep_merge(base: dict, override: dict) -> dict:
            """Deep merge override into base."""
            result = base.copy()

            for key, value in override.items():
                if (key in result and
                    isinstance(result[key], dict) and
                    isinstance(value, dict)):
                    result[key] = deep_merge(result[key], value)
                else:
                    result[key] = value

            return result

        return deep_merge(context, overrides)

    def _template_exists(self, template_name: str) -> bool:
        """Check if template file exists."""
        return (self.template_dir / template_name).exists()

    def list_available_templates(self) -> list:
        """List all available template files."""
        return [
            f.stem for f in self.template_dir.glob("*.j2")
        ]

    def list_available_contexts(self) -> list:
        """List all available deployment contexts."""
        return [
            f.stem for f in self.context_dir.glob("*.yaml")
        ]
```

### 3.3 Template Examples

**Claude Template (claude.j2):**

```jinja2
You are Gambiarra, an AI coding assistant with a secure client-server architecture.

<instructions>
{%- if mode == "code" %}
Your goal is to help users write, modify, and understand code efficiently.
{%- elif mode == "debug" %}
Your goal is to identify and fix bugs in the user's code systematically.
{%- elif mode == "architect" %}
Your goal is to design system architecture and plan implementation strategies.
{%- endif %}

Follow this methodology:
1. Analyze the task in <thinking> tags before taking action
2. Break down complex tasks into clear, sequential steps
3. Use tools one at a time, waiting for results before proceeding
4. Provide clear explanations of your reasoning
</instructions>

<tools>
{%- for tool in tools %}
{{ tool | format_tool_xml }}
{%- endfor %}
</tools>

<rules>
<critical_rules>
{%- for rule in rules.critical %}
{{ rule | emphasize(llm_type) }}
{%- endfor %}
</critical_rules>

{%- if deployment_context == "enterprise" and security is defined %}
<security_constraints>
{%- for constraint in security.constraints %}
- {{ constraint }}
{%- endfor %}

<allowed_domains>
{%- for domain in security.allowed_domains %}
- {{ domain }}
{%- endfor %}
</allowed_domains>

<forbidden_commands>
{%- for cmd in security.forbidden_commands %}
- {{ cmd }}
{%- endfor %}
</forbidden_commands>
</security_constraints>
{%- endif %}

{%- if command_execution_rules is defined %}
<command_execution_rules>
{%- for rule in command_execution_rules %}
{{ rule }}
{%- endfor %}
</command_execution_rules>
{%- endif %}
</rules>

{%- if examples and examples|length > 0 %}
<examples>
{%- for example in examples %}
{{ example }}
{%- endfor %}
</examples>
{%- endif %}

<system_info>
Operating System: {{ system.os }}
Current Directory: {{ cwd }}
Shell: {{ system.shell }}
{%- if deployment_context %}
Deployment Context: {{ deployment_context }}
{%- endif %}
</system_info>

{%- if custom_sections is defined %}
{%- for section in custom_sections %}
<{{ section.name | lower | replace(' ', '_') }}>
{{ section.content }}
</{{ section.name | lower | replace(' ', '_') }}>
{%- endfor %}
{%- endif %}
```

**GPT-4 Template (gpt4.j2):**

```jinja2
You are Gambiarra, an AI coding assistant with a secure client-server architecture.

## Your Role

{%- if mode == "code" %}
Help users write, modify, and understand code efficiently.
{%- elif mode == "debug" %}
Identify and fix bugs in the user's code systematically.
{%- elif mode == "architect" %}
Design system architecture and plan implementation strategies.
{%- endif %}

## Methodology

1. Analyze the task step-by-step
2. Break down complex tasks into clear steps
3. Use tools one at a time
4. Wait for results before proceeding
5. Provide clear explanations

## Available Tools

{%- for tool in tools %}
{{ tool | format_tool_json }}
{%- endfor %}

## Critical Rules

{%- for rule in rules.critical %}
**IMPORTANT:** {{ rule }}
{%- endfor %}

{%- if deployment_context == "enterprise" and security is defined %}

## Security Constraints

**Allowed Domains:**
{%- for domain in security.allowed_domains %}
- {{ domain }}
{%- endfor %}

**Forbidden Commands:**
{%- for cmd in security.forbidden_commands %}
- `{{ cmd }}`
{%- endfor %}

{%- for constraint in security.constraints %}
- {{ constraint }}
{%- endfor %}
{%- endif %}

## System Information

- **OS:** {{ system.os }}
- **Current Directory:** `{{ cwd }}`
- **Shell:** {{ system.shell }}
{%- if deployment_context %}
- **Context:** {{ deployment_context }}
{%- endif %}
```

### 3.4 Deployment Context Examples

**Enterprise Context (enterprise.yaml):**

```yaml
deployment_context: enterprise

rules:
  critical:
    - Never access external URLs without approval
    - Always sanitize user inputs before processing
    - Log all file modifications to audit trail
    - Never execute sudo or privileged commands
    - Use only approved package registries

  important:
    - Verify code changes don't introduce security vulnerabilities
    - Follow company coding standards and style guides
    - Include error handling in all operations
    - Document all significant changes

security:
  constraints:
    - "All code changes must include audit comments"
    - "Sensitive data must be encrypted at rest and in transit"
    - "Follow PCI-DSS guidelines for payment processing code"
    - "No credentials or secrets in code or logs"
    - "All external dependencies must be approved"

  allowed_domains:
    - "npmjs.com"
    - "pypi.org"
    - "github.com"
    - "company-internal-registry.example.com"

  forbidden_commands:
    - "curl"
    - "wget"
    - "ssh"
    - "scp"
    - "sudo"
    - "docker run"

behavior:
  auto_approve: false
  require_explanation: true
  require_tests: true
  compliance_mode: true
  verbose_logging: true

command_execution_rules:
  - "All commands must be non-interactive"
  - "Network access requires explicit approval"
  - "File modifications require audit logging"
  - "Dangerous operations require manager approval"

custom_sections:
  - name: "Company Coding Standards"
    content: |
      Follow these company-specific standards:
      - Use TypeScript for all new JavaScript code
      - API endpoints must follow REST conventions
      - All functions must have JSDoc comments
      - Error handling must use centralized error service
      - Security review required for authentication code
```

**Personal Context (personal.yaml):**

```yaml
deployment_context: personal

rules:
  critical:
    - Execute commands in non-interactive mode
    - Use one tool at a time
    - Wait for results before proceeding

  important:
    - Prefer modern best practices
    - Write clean, readable code
    - Include helpful comments

behavior:
  auto_approve: true
  require_explanation: false
  compliance_mode: false
  concise_responses: true
  allow_experiments: true

custom_sections:
  - name: "Personal Preferences"
    content: |
      My preferences:
      - Use functional programming patterns when appropriate
      - Prefer Rust for systems programming
      - Use pytest for Python testing
      - Keep explanations concise unless I ask for details
```

**CI/CD Context (cicd.yaml):**

```yaml
deployment_context: cicd

rules:
  critical:
    - ALL commands must be non-interactive
    - Use default values for all prompts
    - Fail fast on any errors
    - No user interaction allowed
    - Deterministic behavior required

  important:
    - Minimize output verbosity
    - Use parallel operations when possible
    - Cache dependencies when appropriate
    - Clean up resources after execution

behavior:
  auto_approve: true
  require_explanation: false
  fail_fast: true
  deterministic: true
  no_prompts: true

command_execution_rules:
  - "Always use --yes or -y flags"
  - "Set CI=true environment variable"
  - "Use npm ci instead of npm install"
  - "Disable progress bars and animations"
  - "Use --quiet or --silent flags"

system:
  timeout: 600  # 10 minutes max
  max_retries: 3
  parallel_jobs: 4
```

### 3.5 Custom Filters

```python
# server/prompts/engine/filters.py
from typing import Dict, Any


def format_tool_xml(tool: Dict[str, Any]) -> str:
    """Format tool description for XML-based LLMs (Claude)."""
    name = tool.get('name', 'unknown')
    description = tool.get('description', '')
    parameters = tool.get('parameters', {})

    xml = f"""
## {name}
Description: {description}

Parameters:
"""

    for param_name, param_info in parameters.items():
        required = param_info.get('required', False)
        param_desc = param_info.get('description', '')
        req_str = "(required)" if required else "(optional)"

        xml += f"- {param_name}: {req_str} {param_desc}\n"

    if 'example' in tool:
        xml += f"\nExample:\n```xml\n{tool['example']}\n```\n"

    return xml


def format_tool_json(tool: Dict[str, Any]) -> str:
    """Format tool description for JSON-based LLMs (GPT-4)."""
    import json

    name = tool.get('name', 'unknown')
    description = tool.get('description', '')
    parameters = tool.get('parameters', {})

    json_schema = {
        "name": name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }

    for param_name, param_info in parameters.items():
        json_schema["parameters"]["properties"][param_name] = {
            "type": param_info.get('type', 'string'),
            "description": param_info.get('description', '')
        }

        if param_info.get('required', False):
            json_schema["parameters"]["required"].append(param_name)

    return f"### {name}\n```json\n{json.dumps(json_schema, indent=2)}\n```"


def format_tool_markdown(tool: Dict[str, Any]) -> str:
    """Format tool description in markdown (for display)."""
    name = tool.get('name', 'unknown')
    description = tool.get('description', '')
    parameters = tool.get('parameters', {})

    md = f"### {name}\n\n{description}\n\n**Parameters:**\n\n"

    for param_name, param_info in parameters.items():
        required = param_info.get('required', False)
        param_desc = param_info.get('description', '')
        req_str = "**required**" if required else "*optional*"

        md += f"- `{param_name}` ({req_str}): {param_desc}\n"

    return md


def emphasize_for_llm(text: str, llm_type: str) -> str:
    """Add LLM-specific emphasis markers."""
    if llm_type == "claude":
        return f"<important>{text}</important>"
    elif llm_type == "gpt4":
        return f"**IMPORTANT:** {text}"
    elif llm_type == "gemini":
        return f"⚠️ **CRITICAL:** {text}"
    else:
        return f"⚠️ {text.upper()}"
```

### 3.6 Integration with Server

```python
# server/main.py (updated)
from gambiarra.server.prompts.engine.template_engine import PromptTemplateEngine
from gambiarra.server.config import Config


class GambiarraServer:
    def __init__(self, config: Config):
        self.config = config

        # Initialize prompt engine
        self.prompt_engine = PromptTemplateEngine(
            template_dir=config.prompt_template_dir,
            context_dir=config.prompt_context_dir,
            override_dir=config.prompt_override_dir
        )

        # ... rest of initialization

    async def get_system_prompt(self, session: Session) -> str:
        """Generate system prompt for session."""

        # Determine LLM type from provider
        llm_type = self._get_llm_type(self.ai_provider)

        # Get deployment context from config or session
        deployment_context = (
            session.config.deployment_context or
            self.config.default_deployment_context
        )

        # Generate prompt
        prompt = self.prompt_engine.generate_prompt(
            llm_type=llm_type,
            deployment_context=deployment_context,
            mode=session.config.operating_mode,
            cwd=session.config.working_directory,
            tools=self.tool_registry.get_all_tool_descriptions(),
            overrides=session.config.prompt_overrides
        )

        return prompt

    def _get_llm_type(self, provider) -> str:
        """Determine LLM type from provider."""
        provider_name = provider.__class__.__name__.lower()

        if 'claude' in provider_name or 'anthropic' in provider_name:
            return 'claude'
        elif 'openai' in provider_name or 'gpt' in provider_name:
            return 'gpt4'
        elif 'gemini' in provider_name or 'google' in provider_name:
            return 'gemini'
        else:
            return 'base'
```

**Timeline:** 1-2 weeks

---

## 4. Enhanced Context Management

### 4.1 Semantic File Selection

```python
# client/context/semantic_context_manager.py
from typing import List, Dict, Any, Optional
import numpy as np
from dataclasses import dataclass


@dataclass
class FileRelevance:
    """Relevance score for a file."""
    path: str
    relevance_score: float
    reasons: List[str]
    last_modified: float
    size: int


class SemanticContextManager:
    """
    Manages context with semantic understanding.

    Features:
    - Embedding-based file selection
    - Relevance scoring
    - Automatic context pruning
    - Smart file prioritization
    """

    def __init__(self, max_tokens: int = 100000):
        self.max_tokens = max_tokens
        self.file_embeddings: Dict[str, np.ndarray] = {}
        self.file_metadata: Dict[str, Dict[str, Any]] = {}
        self.current_context: List[str] = []

    async def select_relevant_files(
        self,
        query: str,
        workspace_files: List[str],
        max_files: int = 50
    ) -> List[FileRelevance]:
        """
        Select most relevant files for query using embeddings.

        Args:
            query: User query or task description
            workspace_files: All files in workspace
            max_files: Maximum files to return

        Returns:
            List of FileRelevance sorted by relevance
        """
        # Generate query embedding
        query_embedding = await self._get_embedding(query)

        # Score all files
        scored_files = []

        for file_path in workspace_files:
            # Get or compute file embedding
            file_embedding = await self._get_file_embedding(file_path)

            # Compute similarity
            similarity = self._cosine_similarity(
                query_embedding,
                file_embedding
            )

            # Adjust score based on other factors
            adjusted_score = self._adjust_relevance_score(
                file_path,
                similarity
            )

            reasons = self._explain_relevance(
                file_path,
                similarity,
                adjusted_score
            )

            metadata = self.file_metadata.get(file_path, {})

            scored_files.append(FileRelevance(
                path=file_path,
                relevance_score=adjusted_score,
                reasons=reasons,
                last_modified=metadata.get('modified', 0),
                size=metadata.get('size', 0)
            ))

        # Sort by relevance
        scored_files.sort(key=lambda x: x.relevance_score, reverse=True)

        return scored_files[:max_files]

    async def _get_embedding(self, text: str) -> np.ndarray:
        """Get embedding for text."""
        # TODO: Integrate with embedding service
        # For now, use simple TF-IDF or similar
        pass

    async def _get_file_embedding(self, file_path: str) -> np.ndarray:
        """Get or compute embedding for file."""
        if file_path in self.file_embeddings:
            return self.file_embeddings[file_path]

        # Read file and compute embedding
        # Cache result
        pass

    def _cosine_similarity(
        self,
        vec1: np.ndarray,
        vec2: np.ndarray
    ) -> float:
        """Compute cosine similarity between vectors."""
        return float(np.dot(vec1, vec2) / (
            np.linalg.norm(vec1) * np.linalg.norm(vec2)
        ))

    def _adjust_relevance_score(
        self,
        file_path: str,
        base_score: float
    ) -> float:
        """Adjust relevance score based on file characteristics."""
        score = base_score

        # Boost recently modified files
        if file_path in self.file_metadata:
            age_days = self._get_file_age_days(file_path)
            if age_days < 7:
                score *= 1.2  # Recent files more relevant

        # Boost files already in context
        if file_path in self.current_context:
            score *= 1.5

        # Penalize very large files
        if self.file_metadata.get(file_path, {}).get('size', 0) > 100000:
            score *= 0.8

        # Boost important file types
        if file_path.endswith(('.py', '.js', '.ts', '.java')):
            score *= 1.1

        # Penalize generated/build files
        if any(p in file_path for p in ['node_modules', 'dist', 'build', '.git']):
            score *= 0.1

        return score

    def _explain_relevance(
        self,
        file_path: str,
        similarity: float,
        adjusted_score: float
    ) -> List[str]:
        """Explain why file is relevant."""
        reasons = []

        if similarity > 0.7:
            reasons.append("High semantic similarity to query")

        if file_path in self.current_context:
            reasons.append("Already in context")

        age_days = self._get_file_age_days(file_path)
        if age_days < 7:
            reasons.append(f"Recently modified ({age_days} days ago)")

        return reasons

    def _get_file_age_days(self, file_path: str) -> float:
        """Get file age in days."""
        import time
        modified = self.file_metadata.get(file_path, {}).get('modified', 0)
        return (time.time() - modified) / 86400
```

**Timeline:** 1 week

---

## 5. Transaction & Rollback System

```python
# client/tools/transaction_manager.py
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum
import asyncio
import shutil
import tempfile
from pathlib import Path


class TransactionState(Enum):
    """Transaction states."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMMITTED = "committed"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


@dataclass
class TransactionOperation:
    """Single operation in a transaction."""
    operation_type: str  # write, delete, move
    target_path: str
    backup_path: Optional[str] = None
    content: Optional[str] = None
    metadata: Dict[str, Any] = None


class TransactionManager:
    """
    Manages atomic multi-file operations with rollback support.

    Usage:
        async with TransactionManager() as txn:
            await txn.write_file('a.txt', 'content a')
            await txn.write_file('b.txt', 'content b')
            await txn.commit()
        # Auto-rollback on exception
    """

    def __init__(self):
        self.state = TransactionState.PENDING
        self.operations: List[TransactionOperation] = []
        self.backup_dir = None

    async def __aenter__(self):
        """Start transaction."""
        self.state = TransactionState.IN_PROGRESS
        self.backup_dir = tempfile.mkdtemp(prefix='gambiarra_txn_')
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """End transaction (commit or rollback)."""
        if exc_type is not None:
            # Exception occurred, rollback
            await self.rollback()
            return False  # Re-raise exception

        if self.state == TransactionState.IN_PROGRESS:
            # Auto-commit if not manually committed
            await self.commit()

        # Cleanup backup directory
        if self.backup_dir:
            shutil.rmtree(self.backup_dir, ignore_errors=True)

        return True

    async def write_file(
        self,
        path: str,
        content: str,
        metadata: Dict[str, Any] = None
    ):
        """Add file write to transaction."""
        if self.state != TransactionState.IN_PROGRESS:
            raise TransactionError("Transaction not in progress")

        # Create backup if file exists
        backup_path = None
        if Path(path).exists():
            backup_path = Path(self.backup_dir) / Path(path).name
            shutil.copy2(path, backup_path)

        self.operations.append(TransactionOperation(
            operation_type='write',
            target_path=path,
            backup_path=str(backup_path) if backup_path else None,
            content=content,
            metadata=metadata or {}
        ))

    async def delete_file(self, path: str):
        """Add file deletion to transaction."""
        if self.state != TransactionState.IN_PROGRESS:
            raise TransactionError("Transaction not in progress")

        # Create backup
        backup_path = None
        if Path(path).exists():
            backup_path = Path(self.backup_dir) / Path(path).name
            shutil.copy2(path, backup_path)

        self.operations.append(TransactionOperation(
            operation_type='delete',
            target_path=path,
            backup_path=str(backup_path) if backup_path else None
        ))

    async def commit(self):
        """Commit all operations."""
        if self.state != TransactionState.IN_PROGRESS:
            raise TransactionError(f"Cannot commit in state {self.state}")

        try:
            # Execute all operations
            for op in self.operations:
                await self._execute_operation(op)

            self.state = TransactionState.COMMITTED

        except Exception as e:
            # Rollback on failure
            await self.rollback()
            raise TransactionError(f"Commit failed: {e}")

    async def rollback(self):
        """Rollback all operations."""
        if self.state == TransactionState.ROLLED_BACK:
            return  # Already rolled back

        # Restore all backups
        for op in reversed(self.operations):
            try:
                await self._restore_backup(op)
            except Exception as e:
                # Log but continue rollback
                import logging
                logging.error(f"Error during rollback: {e}")

        self.state = TransactionState.ROLLED_BACK

    async def _execute_operation(self, op: TransactionOperation):
        """Execute single operation."""
        if op.operation_type == 'write':
            # Write file
            async with aiofiles.open(op.target_path, 'w') as f:
                await f.write(op.content)

        elif op.operation_type == 'delete':
            # Delete file
            Path(op.target_path).unlink()

    async def _restore_backup(self, op: TransactionOperation):
        """Restore file from backup."""
        if op.backup_path and Path(op.backup_path).exists():
            shutil.copy2(op.backup_path, op.target_path)

        elif op.operation_type == 'write' and not op.backup_path:
            # File was created by transaction, remove it
            if Path(op.target_path).exists():
                Path(op.target_path).unlink()


class TransactionError(Exception):
    """Transaction-related error."""
    pass


# Example usage:
"""
async def refactor_multiple_files():
    async with TransactionManager() as txn:
        # These operations are atomic
        await txn.write_file('a.py', 'new content a')
        await txn.write_file('b.py', 'new content b')
        await txn.write_file('c.py', 'new content c')

        # If any operation fails, all are rolled back
        await txn.commit()
"""
```

**Timeline:** 3-5 days

---

## 6. Rate Limiting & Cost Control

```python
# server/ai_integration/rate_limiter.py
import asyncio
import time
from typing import Dict, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Rate limit configuration."""
    requests_per_minute: int = 60
    tokens_per_minute: int = 150000
    daily_cost_limit_usd: float = 50.0


class RateLimiter:
    """
    Token bucket rate limiter with cost tracking.

    Features:
    - Request rate limiting
    - Token rate limiting
    - Cost tracking
    - Per-session limits
    """

    def __init__(self, config: RateLimitConfig):
        self.config = config
        self.request_tokens = config.requests_per_minute
        self.token_tokens = config.tokens_per_minute
        self.last_refill = time.time()
        self.lock = asyncio.Lock()

        # Cost tracking
        self.daily_cost = 0.0
        self.cost_reset_time = self._get_next_midnight()

    async def acquire(
        self,
        estimated_tokens: int = 0
    ) -> bool:
        """
        Acquire permission to make request.

        Args:
            estimated_tokens: Estimated token count

        Returns:
            True if allowed, False if rate limited

        Raises:
            CostLimitExceeded if daily cost limit reached
        """
        async with self.lock:
            # Refill tokens if needed
            await self._refill_tokens()

            # Check cost limit
            if self.daily_cost >= self.config.daily_cost_limit_usd:
                raise CostLimitExceeded(
                    f"Daily cost limit reached: ${self.daily_cost:.2f}"
                )

            # Check if we have enough tokens
            if self.request_tokens < 1:
                return False

            if estimated_tokens > 0 and self.token_tokens < estimated_tokens:
                return False

            # Consume tokens
            self.request_tokens -= 1
            if estimated_tokens > 0:
                self.token_tokens -= estimated_tokens

            return True

    async def _refill_tokens(self):
        """Refill tokens based on time elapsed."""
        now = time.time()
        elapsed = now - self.last_refill

        if elapsed < 1.0:
            return  # Less than 1 second, don't refill

        # Refill request tokens
        refill_amount = (elapsed / 60.0) * self.config.requests_per_minute
        self.request_tokens = min(
            self.config.requests_per_minute,
            self.request_tokens + refill_amount
        )

        # Refill token tokens
        token_refill = (elapsed / 60.0) * self.config.tokens_per_minute
        self.token_tokens = min(
            self.config.tokens_per_minute,
            self.token_tokens + token_refill
        )

        self.last_refill = now

        # Reset daily cost if needed
        if now >= self.cost_reset_time:
            self.daily_cost = 0.0
            self.cost_reset_time = self._get_next_midnight()
            logger.info("Daily cost limit reset")

    def track_cost(self, cost_usd: float):
        """Track API call cost."""
        self.daily_cost += cost_usd
        logger.debug(f"Cost tracked: ${cost_usd:.4f}, total: ${self.daily_cost:.2f}")

    def _get_next_midnight(self) -> float:
        """Get timestamp of next midnight."""
        import datetime
        tomorrow = datetime.date.today() + datetime.timedelta(days=1)
        midnight = datetime.datetime.combine(tomorrow, datetime.time.min)
        return midnight.timestamp()

    def get_stats(self) -> Dict:
        """Get rate limiter statistics."""
        return {
            "requests_available": int(self.request_tokens),
            "tokens_available": int(self.token_tokens),
            "daily_cost": self.daily_cost,
            "cost_limit": self.config.daily_cost_limit_usd,
            "cost_remaining": self.config.daily_cost_limit_usd - self.daily_cost
        }


class CostLimitExceeded(Exception):
    """Raised when daily cost limit is exceeded."""
    pass
```

**Timeline:** 2-3 days

---

## 7. Session Persistence

```python
# server/session/persistence.py
import json
import pickle
from typing import Optional, Dict, Any
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class SessionPersistence:
    """
    Persist sessions to disk for recovery after restart.

    Features:
    - JSON serialization for metadata
    - Pickle for complex objects
    - Automatic cleanup of old sessions
    - Session recovery on reconnection
    """

    def __init__(self, storage_dir: str):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    async def save_session(
        self,
        session_id: str,
        session: 'Session'
    ):
        """Save session to disk."""
        try:
            session_file = self.storage_dir / f"{session_id}.json"

            # Serialize session
            data = {
                'session_id': session.session_id,
                'connection_id': session.connection_id,
                'created_at': session.created_at,
                'last_activity': session.last_activity,
                'config': {
                    'working_directory': session.config.working_directory,
                    'auto_approve_reads': session.config.auto_approve_reads,
                    'operating_mode': session.config.operating_mode
                },
                'messages': [
                    {
                        'role': msg.role,
                        'content': msg.content,
                        'timestamp': msg.timestamp
                    }
                    for msg in session.messages
                ],
                'context_files': session.context_files
            }

            # Write to disk
            with open(session_file, 'w') as f:
                json.dump(data, f, indent=2)

            logger.debug(f"Saved session {session_id}")

        except Exception as e:
            logger.error(f"Failed to save session {session_id}: {e}")

    async def load_session(
        self,
        session_id: str
    ) -> Optional[Dict[str, Any]]:
        """Load session from disk."""
        try:
            session_file = self.storage_dir / f"{session_id}.json"

            if not session_file.exists():
                return None

            with open(session_file, 'r') as f:
                data = json.load(f)

            logger.debug(f"Loaded session {session_id}")
            return data

        except Exception as e:
            logger.error(f"Failed to load session {session_id}: {e}")
            return None

    async def delete_session(self, session_id: str):
        """Delete session from disk."""
        try:
            session_file = self.storage_dir / f"{session_id}.json"
            if session_file.exists():
                session_file.unlink()
            logger.debug(f"Deleted session {session_id}")
        except Exception as e:
            logger.error(f"Failed to delete session {session_id}: {e}")
```

**Timeline:** 2-3 days

---

## 8. Testing Infrastructure

### 8.1 Test Coverage Goals

```
Component                      Current    Target
-----------------------------------------------
XML Parser                     0%         95%
Path Validator                 0%         100%
Command Filter                 0%         95%
Security (all)                 0%         95%
Tool Execution                 20%        90%
Client-Server Protocol         0%         85%
Circuit Breaker                0%         90%
Error Recovery                 0%         85%
Session Management             0%         80%
Prompt Template Engine         0%         90%
Command Execution Manager      0%         90%
-----------------------------------------------
Overall                        ~5%        90%
```

### 8.2 Test Structure

```
tests/
├── unit/
│   ├── server/
│   │   ├── core/
│   │   │   ├── tools/
│   │   │   │   ├── test_xml_parser.py       # ✨ NEW
│   │   │   │   ├── test_tool_registry.py
│   │   │   │   └── test_validator.py
│   │   │   └── recovery/
│   │   │       ├── test_circuit_breaker.py  # ✨ NEW
│   │   │       └── test_error_recovery.py   # ✨ NEW
│   │   └── prompts/
│   │       └── engine/
│   │           ├── test_template_engine.py  # ✨ NEW
│   │           └── test_filters.py          # ✨ NEW
│   └── client/
│       ├── security/
│       │   ├── test_path_validator.py       # ✨ NEW
│       │   ├── test_command_filter.py       # ✨ NEW
│       │   └── test_approval_manager.py     # ✨ NEW
│       ├── execution/
│       │   ├── test_command_knowledge.py    # ✨ NEW
│       │   ├── test_hang_detector.py        # ✨ NEW
│       │   └── test_smart_execution.py      # ✨ NEW
│       └── tools/
│           ├── test_file_ops.py
│           ├── test_command_ops.py
│           └── test_transaction_manager.py  # ✨ NEW
├── integration/
│   ├── test_client_server.py               # ✨ NEW
│   ├── test_websocket_protocol.py          # ✨ NEW
│   ├── test_execution_flow.py              # ✨ NEW
│   └── test_prompt_generation.py           # ✨ NEW
├── security/
│   ├── test_path_traversal.py              # ✨ NEW
│   ├── test_command_injection.py           # ✨ NEW
│   └── test_fuzzing.py                     # ✨ NEW
└── e2e/
    ├── test_complete_workflow.py           # ✨ NEW
    └── test_error_scenarios.py             # ✨ NEW
```

**Timeline:** 2 weeks

---

## 9. Deployment & Configuration

### 9.1 Configuration File

```yaml
# config.yaml
server:
  host: "0.0.0.0"
  port: 8765
  log_level: "INFO"

  # Session management
  session:
    timeout_seconds: 3600
    cleanup_interval: 300
    max_concurrent: 100
    persistence_enabled: true
    persistence_dir: "./data/sessions"

  # AI Provider
  ai_provider:
    type: "openai"  # openai, trustgraph, test
    model: "gpt-4"
    api_key: "${OPENAI_API_KEY}"
    base_url: null

    # Rate limiting
    rate_limit:
      requests_per_minute: 60
      tokens_per_minute: 150000
      daily_cost_limit_usd: 50.0

  # Prompt system
  prompts:
    provider: "local"  # local or trustgraph

    # Local templates
    local:
      template_dir: "./prompts/templates"
      context_dir: "./prompts/contexts"
      override_dir: "./prompts/overrides"
      default_context: "personal"

    # TrustGraph integration (optional)
    trustgraph:
      enabled: false
      url: "https://trustgraph.example.com"
      api_key: "${TRUSTGRAPH_API_KEY}"
      template_namespace: "gambiarra"

  # Error handling
  error_recovery:
    max_error_history: 1000
    circuit_breaker:
      failure_threshold: 5
      success_threshold: 3
      timeout_seconds: 60.0

client:
  server_url: "ws://localhost:8765"

  # Security
  security:
    workspace_root: "."
    ignore_file: ".gambiarraignore"
    permissive_mode: false

    # Command filter
    command_filter:
      enabled: true
      allow_sudo: false

    # Approval
    approval:
      auto_approve_reads: true
      auto_approve_low_risk: true
      mistake_limit: 3
      max_consecutive_auto_approvals: 10

  # Command execution
  execution:
    default_timeout: 60
    inactivity_timeout: 30
    max_output_lines: 10000

    # Command knowledge base
    knowledge_base:
      enabled: true
      pre_execution_validation: true
      auto_add_non_interactive_flags: true

  # Context management
  context:
    max_tracked_files: 200
    max_tokens: 100000
    semantic_selection: true

  # Transactions
  transactions:
    enabled: true
    auto_backup: true
    backup_dir: "./backups"
```

### 9.2 Environment Variables

```bash
# .env
OPENAI_API_KEY=sk-...
TRUSTGRAPH_API_KEY=tg-...
GAMBIARRA_CONFIG_FILE=./config.yaml
GAMBIARRA_LOG_LEVEL=INFO
```

**Timeline:** 3-5 days

---

## 10. Migration Strategy

### 10.1 Phase 1: Critical Fixes (Week 1-2)

**Priority:** 🔴 CRITICAL

1. Replace XML parser with ElementTree
2. Add basic test suite for parser
3. Test with existing prompts
4. Monitor for issues

**Success Criteria:**
- All existing tool calls parse correctly
- No regressions in functionality
- 95% test coverage for parser

### 10.2 Phase 2: Command Execution (Week 3-5)

**Priority:** 🔴 HIGH

1. Implement CommandKnowledgeBase
2. Add bidirectional execution protocol
3. Update client command execution
4. Add HangDetector
5. Test with common commands (npm, git, cargo)

**Success Criteria:**
- npx create-* commands work
- npm install doesn't hang
- git commit requires -m flag
- 90% test coverage

### 10.3 Phase 3: Prompt Engineering (Week 6-7)

**Priority:** 🔴 HIGH

1. Create template directory structure
2. Implement PromptTemplateEngine
3. Create templates for Claude, GPT-4
4. Create deployment contexts
5. Integrate with server
6. Migration guide for existing prompts

**Success Criteria:**
- Templates work for all AI providers
- Deployment contexts apply correctly
- Users can customize prompts
- 90% test coverage

### 10.4 Phase 4: Enhancements (Week 8-10)

**Priority:** 🟡 MEDIUM

1. Transaction support
2. Rate limiting
3. Session persistence
4. Enhanced context management

**Success Criteria:**
- Multi-file operations are atomic
- Rate limits prevent overuse
- Sessions survive restarts
- Context selection is intelligent

### 10.5 Phase 5: Testing & Documentation (Week 11-12)

**Priority:** 🟡 MEDIUM

1. Comprehensive test suite
2. Security testing
3. Load testing
4. Documentation updates
5. Deployment guides

**Success Criteria:**
- 90% overall test coverage
- Security vulnerabilities addressed
- Can handle 100 concurrent sessions
- Documentation complete

---

## 11. Success Metrics

### 11.1 Technical Metrics

| Metric | Current | Target | Timeline |
|--------|---------|--------|----------|
| Test Coverage | ~5% | 90% | 12 weeks |
| Command Success Rate | ~40% | 95% | 5 weeks |
| Prompt Customizability | 0% | 100% | 7 weeks |
| Security Vulnerabilities | Unknown | 0 Critical | 12 weeks |
| Parser Reliability | ~80% | 99.9% | 2 weeks |

### 11.2 User Experience Metrics

| Metric | Current | Target |
|--------|---------|--------|
| npx create-* success rate | ~20% | 95% |
| npm install hang rate | ~30% | <1% |
| Manual intervention required | ~40% | <5% |
| Time to customize prompts | N/A (code change) | <10 min (YAML edit) |
| Multi-file operation consistency | ~60% | 99% |

---

## 12. Risks & Mitigation

### 12.1 Technical Risks

**Risk:** XML parser replacement breaks existing deployments
- **Mitigation:** Comprehensive testing, gradual rollout, fallback option

**Risk:** Command execution changes cause regressions
- **Mitigation:** Feature flag, extensive testing, monitoring

**Risk:** Prompt template system is too complex for users
- **Mitigation:** Good defaults, clear documentation, examples

### 12.2 Timeline Risks

**Risk:** Implementation takes longer than estimated
- **Mitigation:** Prioritize critical fixes, phase remaining features

**Risk:** Testing uncovers major issues
- **Mitigation:** Allocate buffer time, continuous testing during development

---

## 13. Conclusion

This technical specification addresses the critical gaps identified in REVIEW.md and provides a clear path to transform Gambiarra from a 3.5/5 prototype to a 4.5/5 production-ready enterprise solution.

**Key Improvements:**
1. ✅ Robust XML parsing
2. ✅ Intelligent command execution with interactive handling
3. ✅ Flexible prompt engineering system
4. ✅ Transaction support for atomic operations
5. ✅ Rate limiting and cost control
6. ✅ Comprehensive testing infrastructure

**Total Estimated Timeline:** 12 weeks

**After implementation, Gambiarra will be:**
- Production-ready for enterprise deployments
- Able to handle complex interactive workflows
- Customizable for different LLMs and contexts
- Reliable with proper error handling and recovery
- Well-tested with >90% coverage

---

**Document End**

*Generated based on REVIEW.md findings*
*Date: October 2025*
*Version: 2.0 PROPOSED*
