"""
Execution message protocol for bidirectional server-client communication.

This module defines message types and structures for intelligent command execution,
enabling the server and client to coordinate during command execution with:
- Pre-execution validation requests
- Interactive input handling
- Hang detection and recovery
- Real-time execution status updates

Message Flow:
1. Server requests command execution with validation
2. Client validates and requests clarification if needed
3. Server provides input/decisions
4. Client executes with streaming updates
5. Client reports completion or errors
"""

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Dict, Any, List
from datetime import datetime
import json


class ExecutionMessageType(Enum):
    """Types of execution-related messages."""

    # Server -> Client messages
    EXECUTE_REQUEST = "execute_request"
    VALIDATION_REQUEST = "validation_request"
    INPUT_RESPONSE = "input_response"
    ABORT_REQUEST = "abort_request"

    # Client -> Server messages
    VALIDATION_RESULT = "validation_result"
    INPUT_REQUIRED = "input_required"
    EXECUTION_STARTED = "execution_started"
    EXECUTION_OUTPUT = "execution_output"
    EXECUTION_COMPLETED = "execution_completed"
    EXECUTION_FAILED = "execution_failed"
    HANG_DETECTED = "hang_detected"


class CommandRiskLevel(Enum):
    """Risk levels for command execution."""
    SAFE = "safe"           # Read-only, no side effects
    LOW = "low"             # Minimal risk (e.g., npm install)
    MEDIUM = "medium"       # Moderate risk (e.g., file operations)
    HIGH = "high"           # High risk (e.g., system modifications)
    CRITICAL = "critical"   # Critical risk (e.g., destructive operations)


class ValidationIssueType(Enum):
    """Types of validation issues."""
    INTERACTIVE_PROMPT = "interactive_prompt"
    MISSING_DEPENDENCY = "missing_dependency"
    PRECONDITION_FAILED = "precondition_failed"
    DIRECTORY_NOT_EMPTY = "directory_not_empty"
    UNSAFE_OPERATION = "unsafe_operation"
    TIMEOUT_LIKELY = "timeout_likely"
    UNKNOWN = "unknown"


@dataclass
class ValidationIssue:
    """Represents a validation issue found during pre-execution check."""

    issue_type: ValidationIssueType
    severity: str  # "error", "warning", "info"
    message: str
    suggested_fix: Optional[str] = None
    can_auto_fix: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "issue_type": self.issue_type.value,
            "severity": self.severity,
            "message": self.message,
            "suggested_fix": self.suggested_fix,
            "can_auto_fix": self.can_auto_fix
        }


@dataclass
class ExecuteRequestMessage:
    """
    Server requests command execution from client.

    The server provides the command along with context about what it's
    trying to accomplish, allowing the client to make intelligent decisions.
    """

    command: str
    cwd: Optional[str] = None
    intent: Optional[str] = None  # What the server is trying to accomplish
    timeout: int = 300  # Timeout in seconds
    require_validation: bool = True
    allow_interactive: bool = False
    environment: Optional[Dict[str, str]] = None
    request_id: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class ValidationRequestMessage:
    """Server requests pre-execution validation from client."""

    command: str
    cwd: Optional[str] = None
    intent: Optional[str] = None
    request_id: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class ValidationResultMessage:
    """
    Client responds with validation results.

    Indicates whether the command can be executed safely and what issues
    were found during validation.
    """

    request_id: str
    can_execute: bool
    risk_level: CommandRiskLevel
    issues: List[ValidationIssue] = field(default_factory=list)
    suggested_command: Optional[str] = None  # Alternative safer command
    estimated_duration: Optional[int] = None  # Estimated execution time in seconds
    requires_input: bool = False
    message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "request_id": self.request_id,
            "can_execute": self.can_execute,
            "risk_level": self.risk_level.value,
            "issues": [issue.to_dict() for issue in self.issues],
            "suggested_command": self.suggested_command,
            "estimated_duration": self.estimated_duration,
            "requires_input": self.requires_input,
            "message": self.message
        }


@dataclass
class InputRequiredMessage:
    """
    Client notifies server that the command requires input.

    This allows the server to provide the necessary input or decide
    to abort the command.
    """

    request_id: str
    prompt: str  # The prompt shown by the command
    input_type: str  # "text", "boolean", "choice", "password"
    choices: Optional[List[str]] = None  # For "choice" input type
    default_value: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class InputResponseMessage:
    """Server provides input for an interactive command."""

    request_id: str
    input_value: str
    abort: bool = False  # If true, abort the command instead

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class ExecutionStartedMessage:
    """Client notifies server that execution has started."""

    request_id: str
    command: str
    cwd: str
    pid: Optional[int] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class ExecutionOutputMessage:
    """
    Client streams command output to server.

    Allows the server to monitor execution in real-time and detect issues.
    """

    request_id: str
    output_type: str  # "stdout", "stderr"
    content: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class ExecutionCompletedMessage:
    """Client notifies server that execution completed successfully."""

    request_id: str
    exit_code: int
    stdout: str
    stderr: str
    duration: float  # Execution time in seconds
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class ExecutionFailedMessage:
    """Client notifies server that execution failed."""

    request_id: str
    error: str
    exit_code: Optional[int] = None
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    error_type: str = "execution_error"  # "timeout", "killed", "execution_error"
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class HangDetectedMessage:
    """
    Client notifies server that a hang was detected.

    The server can decide whether to wait, abort, or provide input to resolve.
    """

    request_id: str
    reason: str  # Description of why hang is suspected
    duration: float  # How long the command has been running
    last_output: Optional[str] = None
    suggested_action: str = "abort"  # "abort", "wait", "input"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class AbortRequestMessage:
    """Server requests to abort a running command."""

    request_id: str
    reason: Optional[str] = None
    force: bool = False  # Use SIGKILL instead of SIGTERM

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


class ExecutionMessageProtocol:
    """
    Protocol handler for execution messages.

    Provides serialization/deserialization and validation of execution messages.
    """

    @staticmethod
    def serialize(message: Any) -> str:
        """
        Serialize an execution message to JSON.

        Args:
            message: Any execution message dataclass

        Returns:
            JSON string representation
        """
        if hasattr(message, 'to_dict'):
            data = message.to_dict()
        else:
            data = asdict(message)

        # Add message type
        message_type = message.__class__.__name__.replace('Message', '').lower()
        data['message_type'] = message_type

        return json.dumps(data)

    @staticmethod
    def deserialize(json_str: str) -> Optional[Any]:
        """
        Deserialize a JSON string to an execution message.

        Args:
            json_str: JSON string

        Returns:
            Execution message dataclass instance or None if invalid
        """
        try:
            data = json.loads(json_str)
            message_type = data.get('message_type')

            if not message_type:
                return None

            # Remove message_type from data
            data = {k: v for k, v in data.items() if k != 'message_type'}

            # Map message type to class
            message_classes = {
                'executerequest': ExecuteRequestMessage,
                'validationrequest': ValidationRequestMessage,
                'validationresult': ValidationResultMessage,
                'inputrequired': InputRequiredMessage,
                'inputresponse': InputResponseMessage,
                'executionstarted': ExecutionStartedMessage,
                'executionoutput': ExecutionOutputMessage,
                'executioncompleted': ExecutionCompletedMessage,
                'executionfailed': ExecutionFailedMessage,
                'hangdetected': HangDetectedMessage,
                'abortrequest': AbortRequestMessage
            }

            message_class = message_classes.get(message_type.replace('_', ''))
            if not message_class:
                return None

            # Handle nested objects
            if message_type == 'validation_result' and 'issues' in data:
                issues = []
                for issue_data in data['issues']:
                    issue = ValidationIssue(
                        issue_type=ValidationIssueType(issue_data['issue_type']),
                        severity=issue_data['severity'],
                        message=issue_data['message'],
                        suggested_fix=issue_data.get('suggested_fix'),
                        can_auto_fix=issue_data.get('can_auto_fix', False)
                    )
                    issues.append(issue)
                data['issues'] = issues

                # Convert risk_level string to enum
                if 'risk_level' in data:
                    data['risk_level'] = CommandRiskLevel(data['risk_level'])

            return message_class(**data)

        except (json.JSONDecodeError, TypeError, ValueError, KeyError) as e:
            return None

    @staticmethod
    def create_envelope(message: Any, session_id: str) -> Dict[str, Any]:
        """
        Create a WebSocket message envelope for an execution message.

        Args:
            message: Execution message dataclass
            session_id: Session identifier

        Returns:
            Dictionary suitable for WebSocket transmission
        """
        message_type = message.__class__.__name__.replace('Message', '').lower()

        return {
            "type": "execution_message",
            "session_id": session_id,
            "execution_message_type": message_type,
            "payload": message.to_dict() if hasattr(message, 'to_dict') else asdict(message),
            "timestamp": datetime.now().isoformat()
        }
