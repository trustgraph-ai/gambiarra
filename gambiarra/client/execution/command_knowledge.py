"""
Command Knowledge Base for intelligent command execution.

This module contains knowledge about common commands, their behavior,
requirements, and potential issues. It enables pre-execution validation
and intelligent handling of interactive commands.

Key capabilities:
- Detect commands that require interactive input
- Identify preconditions (e.g., empty directory requirements)
- Suggest non-interactive alternatives
- Estimate execution time and risk level
"""

import re
import os
import shutil
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path

from gambiarra.server.core.protocol.execution_messages import (
    CommandRiskLevel,
    ValidationIssue,
    ValidationIssueType
)


@dataclass
class CommandPattern:
    """Represents a known command pattern with its characteristics."""

    pattern: str  # Regex pattern to match the command
    name: str  # Human-readable name
    risk_level: CommandRiskLevel
    is_interactive: bool = False
    requires_empty_dir: bool = False
    typical_duration: int = 30  # seconds
    non_interactive_flags: Optional[List[str]] = None
    preconditions: Optional[List[str]] = None  # List of precondition checks
    known_prompts: Optional[Dict[str, str]] = None  # prompt -> suggested response


# Command Knowledge Base
COMMAND_PATTERNS = [
    # === npm/npx commands ===
    CommandPattern(
        pattern=r"^npm\s+create\s+vite",
        name="npm create vite",
        risk_level=CommandRiskLevel.LOW,
        is_interactive=True,
        requires_empty_dir=False,
        typical_duration=60,
        non_interactive_flags=["--yes", "-y"],
        known_prompts={
            "? Select a framework": "React",
            "? Select a variant": "TypeScript",
            "? Package name": "my-app",
            "? Overwrite": "no"
        }
    ),
    CommandPattern(
        pattern=r"^npx\s+create-",
        name="npx create-* (project generators)",
        risk_level=CommandRiskLevel.LOW,
        is_interactive=True,
        requires_empty_dir=False,
        typical_duration=120,
        non_interactive_flags=["--yes", "-y", "--use-npm"],
        known_prompts={
            "? Would you like to use TypeScript": "Yes",
            "? Would you like to use ESLint": "Yes",
            "Ok to proceed": "y"
        }
    ),
    CommandPattern(
        pattern=r"^npm\s+install",
        name="npm install",
        risk_level=CommandRiskLevel.LOW,
        is_interactive=False,
        typical_duration=90,
        non_interactive_flags=["--yes", "-y"]
    ),
    CommandPattern(
        pattern=r"^npm\s+init",
        name="npm init",
        risk_level=CommandRiskLevel.LOW,
        is_interactive=True,
        typical_duration=30,
        non_interactive_flags=["--yes", "-y"]
    ),

    # === Python commands ===
    CommandPattern(
        pattern=r"^pip\s+install",
        name="pip install",
        risk_level=CommandRiskLevel.LOW,
        is_interactive=False,
        typical_duration=60,
        non_interactive_flags=["--yes", "-y"]
    ),
    CommandPattern(
        pattern=r"^python\s+-m\s+venv",
        name="python venv creation",
        risk_level=CommandRiskLevel.LOW,
        is_interactive=False,
        typical_duration=30
    ),
    CommandPattern(
        pattern=r"^poetry\s+init",
        name="poetry init",
        risk_level=CommandRiskLevel.LOW,
        is_interactive=True,
        typical_duration=30,
        non_interactive_flags=["--no-interaction", "-n"]
    ),

    # === System package managers ===
    CommandPattern(
        pattern=r"^apt-get\s+install",
        name="apt-get install",
        risk_level=CommandRiskLevel.MEDIUM,
        is_interactive=True,
        typical_duration=120,
        non_interactive_flags=["-y", "--assume-yes"]
    ),
    CommandPattern(
        pattern=r"^yum\s+install",
        name="yum install",
        risk_level=CommandRiskLevel.MEDIUM,
        is_interactive=True,
        typical_duration=120,
        non_interactive_flags=["-y", "--assumeyes"]
    ),

    # === Git commands ===
    CommandPattern(
        pattern=r"^git\s+clone",
        name="git clone",
        risk_level=CommandRiskLevel.LOW,
        is_interactive=False,
        typical_duration=60
    ),
    CommandPattern(
        pattern=r"^git\s+pull",
        name="git pull",
        risk_level=CommandRiskLevel.LOW,
        is_interactive=False,
        typical_duration=30
    ),
    CommandPattern(
        pattern=r"^git\s+push",
        name="git push",
        risk_level=CommandRiskLevel.MEDIUM,
        is_interactive=False,
        typical_duration=30
    ),
    CommandPattern(
        pattern=r"^git\s+commit",
        name="git commit",
        risk_level=CommandRiskLevel.LOW,
        is_interactive=False,
        typical_duration=5
    ),

    # === Build commands ===
    CommandPattern(
        pattern=r"^npm\s+run\s+build",
        name="npm run build",
        risk_level=CommandRiskLevel.LOW,
        is_interactive=False,
        typical_duration=120
    ),
    CommandPattern(
        pattern=r"^npm\s+run\s+dev",
        name="npm run dev (development server)",
        risk_level=CommandRiskLevel.LOW,
        is_interactive=False,
        typical_duration=999999  # Long-running
    ),
    CommandPattern(
        pattern=r"^npm\s+(test|run\s+test)",
        name="npm test",
        risk_level=CommandRiskLevel.LOW,
        is_interactive=False,
        typical_duration=60
    ),

    # === Docker commands ===
    CommandPattern(
        pattern=r"^docker\s+build",
        name="docker build",
        risk_level=CommandRiskLevel.MEDIUM,
        is_interactive=False,
        typical_duration=300
    ),
    CommandPattern(
        pattern=r"^docker\s+run",
        name="docker run",
        risk_level=CommandRiskLevel.MEDIUM,
        is_interactive=False,
        typical_duration=999999  # Can be long-running
    ),

    # === Destructive commands ===
    CommandPattern(
        pattern=r"^rm\s+-rf",
        name="rm -rf (recursive delete)",
        risk_level=CommandRiskLevel.CRITICAL,
        is_interactive=False,
        typical_duration=10
    ),
    CommandPattern(
        pattern=r"^sudo",
        name="sudo (elevated privileges)",
        risk_level=CommandRiskLevel.HIGH,
        is_interactive=True,  # May prompt for password
        typical_duration=30
    ),
]


class CommandKnowledgeBase:
    """
    Knowledge base for command validation and intelligence.

    Provides pre-execution validation, risk assessment, and suggestions
    for safer command execution.
    """

    def __init__(self):
        """Initialize the command knowledge base."""
        self.patterns = COMMAND_PATTERNS

    def analyze_command(
        self,
        command: str,
        cwd: Optional[str] = None,
        intent: Optional[str] = None
    ) -> Tuple[CommandRiskLevel, List[ValidationIssue], Optional[str]]:
        """
        Analyze a command and return risk level, issues, and suggestions.

        Args:
            command: The command to analyze
            cwd: Current working directory
            intent: Optional description of what the command should accomplish

        Returns:
            Tuple of (risk_level, issues, suggested_command)
        """
        # Find matching pattern
        pattern = self._find_pattern(command)

        if pattern:
            risk_level = pattern.risk_level
            issues = []
            suggested_command = None

            # Check for interactive prompts
            if pattern.is_interactive:
                issue = self._check_interactive_command(command, pattern)
                if issue:
                    issues.append(issue)
                    suggested_command = self._suggest_non_interactive(command, pattern)

            # Check directory requirements
            if pattern.requires_empty_dir and cwd:
                issue = self._check_directory_empty(cwd)
                if issue:
                    issues.append(issue)

            # Check preconditions
            if pattern.preconditions:
                precondition_issues = self._check_preconditions(
                    pattern.preconditions, cwd
                )
                issues.extend(precondition_issues)

            # Special validation for specific commands
            issues.extend(self._special_validations(command, cwd, intent))

            return risk_level, issues, suggested_command
        else:
            # Unknown command - conservative risk assessment
            return self._analyze_unknown_command(command)

    def _find_pattern(self, command: str) -> Optional[CommandPattern]:
        """Find matching command pattern."""
        for pattern in self.patterns:
            if re.match(pattern.pattern, command.strip()):
                return pattern
        return None

    def _check_interactive_command(
        self,
        command: str,
        pattern: CommandPattern
    ) -> Optional[ValidationIssue]:
        """Check if command has interactive flags."""
        if pattern.non_interactive_flags:
            # Check if any non-interactive flag is already present
            for flag in pattern.non_interactive_flags:
                if flag in command:
                    return None  # Already has non-interactive flag

        return ValidationIssue(
            issue_type=ValidationIssueType.INTERACTIVE_PROMPT,
            severity="warning",
            message=f"Command '{pattern.name}' may prompt for interactive input",
            suggested_fix=f"Add non-interactive flag: {pattern.non_interactive_flags[0] if pattern.non_interactive_flags else 'N/A'}",
            can_auto_fix=bool(pattern.non_interactive_flags)
        )

    def _suggest_non_interactive(
        self,
        command: str,
        pattern: CommandPattern
    ) -> Optional[str]:
        """Suggest a non-interactive version of the command."""
        if not pattern.non_interactive_flags:
            return None

        # Add the first non-interactive flag
        flag = pattern.non_interactive_flags[0]

        # Special case for npm create vite
        if "npm create vite" in command or "npx create-vite" in command:
            # Extract project name if present
            parts = command.split()
            project_name = "my-app"
            if len(parts) > 3:
                project_name = parts[3]

            return f'printf "n\\n" | npm create vite@latest {project_name} -- --template react-ts'

        # Default: append flag
        return f"{command} {flag}"

    def _check_directory_empty(self, cwd: str) -> Optional[ValidationIssue]:
        """Check if directory is empty when required."""
        try:
            path = Path(cwd)
            if not path.exists():
                return None  # Directory doesn't exist yet

            if any(path.iterdir()):
                return ValidationIssue(
                    issue_type=ValidationIssueType.DIRECTORY_NOT_EMPTY,
                    severity="error",
                    message=f"Directory '{cwd}' is not empty, but command requires empty directory",
                    suggested_fix="Use a different directory or clear the current one"
                )
        except (OSError, PermissionError):
            pass

        return None

    def _check_preconditions(
        self,
        preconditions: List[str],
        cwd: Optional[str]
    ) -> List[ValidationIssue]:
        """Check command preconditions."""
        issues = []

        for precondition in preconditions:
            if precondition == "node_installed":
                if not shutil.which("node"):
                    issues.append(ValidationIssue(
                        issue_type=ValidationIssueType.MISSING_DEPENDENCY,
                        severity="error",
                        message="Node.js is not installed",
                        suggested_fix="Install Node.js first"
                    ))
            elif precondition == "npm_installed":
                if not shutil.which("npm"):
                    issues.append(ValidationIssue(
                        issue_type=ValidationIssueType.MISSING_DEPENDENCY,
                        severity="error",
                        message="npm is not installed",
                        suggested_fix="Install npm first"
                    ))
            elif precondition == "git_installed":
                if not shutil.which("git"):
                    issues.append(ValidationIssue(
                        issue_type=ValidationIssueType.MISSING_DEPENDENCY,
                        severity="error",
                        message="Git is not installed",
                        suggested_fix="Install Git first"
                    ))

        return issues

    def _special_validations(
        self,
        command: str,
        cwd: Optional[str],
        intent: Optional[str]
    ) -> List[ValidationIssue]:
        """Perform special validations for specific commands."""
        issues = []

        # Validate npm create vite with current directory
        if "npm create vite" in command and cwd:
            # Check if trying to create in current directory
            if ". " in command or " ." in command:
                if any(Path(cwd).iterdir()):
                    issues.append(ValidationIssue(
                        issue_type=ValidationIssueType.DIRECTORY_NOT_EMPTY,
                        severity="error",
                        message="Cannot create Vite project in current directory - directory is not empty",
                        suggested_fix="Create in a subdirectory like 'my-app' instead of '.'"
                    ))

        # Validate rm -rf patterns
        if "rm -rf" in command:
            # Check for dangerous patterns
            dangerous_patterns = ["/", "~", "*", ".", ".."]
            for pattern in dangerous_patterns:
                if pattern in command:
                    issues.append(ValidationIssue(
                        issue_type=ValidationIssueType.UNSAFE_OPERATION,
                        severity="error",
                        message=f"Dangerous rm -rf pattern detected: '{pattern}'",
                        suggested_fix="Be more specific with the path"
                    ))

        return issues

    def _analyze_unknown_command(
        self,
        command: str
    ) -> Tuple[CommandRiskLevel, List[ValidationIssue], Optional[str]]:
        """Analyze an unknown command conservatively."""
        # Default to MEDIUM risk for unknown commands
        risk_level = CommandRiskLevel.MEDIUM

        # Check for known dangerous patterns
        if any(pattern in command for pattern in ["rm", "del", "format", "mkfs"]):
            risk_level = CommandRiskLevel.HIGH

        if "sudo" in command:
            risk_level = CommandRiskLevel.HIGH

        issues = [
            ValidationIssue(
                issue_type=ValidationIssueType.UNKNOWN,
                severity="info",
                message="Unknown command - cannot predict behavior",
                suggested_fix="Verify command is safe before execution"
            )
        ]

        return risk_level, issues, None

    def estimate_duration(self, command: str) -> int:
        """
        Estimate command execution duration in seconds.

        Args:
            command: Command to estimate

        Returns:
            Estimated duration in seconds
        """
        pattern = self._find_pattern(command)
        if pattern:
            return pattern.typical_duration

        # Default estimate for unknown commands
        return 60

    def is_long_running(self, command: str) -> bool:
        """
        Check if command is expected to be long-running.

        Args:
            command: Command to check

        Returns:
            True if command is long-running (dev servers, watchers, etc.)
        """
        long_running_keywords = [
            "run dev",
            "run start",
            "serve",
            "watch",
            "--watch",
            "daemon"
        ]

        return any(keyword in command.lower() for keyword in long_running_keywords)
