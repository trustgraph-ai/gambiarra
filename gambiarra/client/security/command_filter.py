"""
Command security filter for Gambiarra client.
Implements whitelist/blacklist for shell command execution.
"""

import re
import shlex
from typing import List, Dict, Set
import logging

logger = logging.getLogger(__name__)


class CommandFilter:
    """Filters and validates shell commands for security."""

    def __init__(self):
        self.blocked_commands: List[re.Pattern] = []
        self.allowed_commands: List[re.Pattern] = []
        self.blocked_patterns: List[re.Pattern] = []
        self.dangerous_chars: Set[str] = set()

        self._initialize_security_rules()

    def _initialize_security_rules(self) -> None:
        """Initialize command security rules."""

        # Dangerous command patterns (blocked)
        blocked_patterns = [
            # System destruction
            r'rm\s+(-rf?|--recursive|--force).*/',
            r'dd\s+if=/dev/(zero|random)',
            r'mkfs\.',
            r'fdisk',
            r'parted',

            # Fork bombs and infinite loops
            r':\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:',  # Fork bomb
            r'while\s+true.*do',
            r'for\s*\(\(\s*;\s*;\s*\)\)',

            # Network/remote execution
            r'curl.*\|\s*(sh|bash|python)',
            r'wget.*\|\s*(sh|bash|python)',
            r'nc\s+.*-e',
            r'netcat\s+.*-e',

            # Privilege escalation
            r'sudo\s+(rm|dd|mkfs|fdisk)',
            r'su\s+-',

            # Process manipulation
            r'kill\s+-9\s+1',  # Kill init
            r'killall\s+-9',

            # File system manipulation
            r'chmod\s+777\s+/',
            r'chown\s+.*:.*\s+/',

            # Dangerous redirections
            r'>\s*/dev/sd[a-z]',
            r'>\s*/dev/null\s*&',

            # Code injection attempts
            r'eval\s+\$\(',
            r'`.*`',  # Command substitution
            r'\$\(.*\)',  # Command substitution
        ]

        self.blocked_patterns = [re.compile(pattern, re.IGNORECASE) for pattern in blocked_patterns]

        # Allowed command patterns (whitelist)
        allowed_patterns = [
            # Basic file operations
            r'^ls(\s|$)',
            r'^cat\s+',
            r'^head\s+',
            r'^tail\s+',
            r'^grep\s+',
            r'^find\s+',
            r'^pwd(\s|$)',
            r'^cd\s+',
            r'^echo\s+',
            r'^mkdir\s+',
            r'^touch\s+',
            r'^cp\s+',
            r'^mv\s+',
            r'^rm\s+[^-]',  # rm without dangerous flags

            # Development tools
            r'^python\s+',
            r'^python3\s+',
            r'^node\s+',
            r'^npm\s+(install|test|run|build|start)',
            r'^yarn\s+(install|test|run|build|start)',
            r'^pip\s+(install|list|show)',
            r'^cargo\s+(new|build|test|run|check|init)',
            r'^go\s+(build|test|run|mod)',
            r'^gcc\s+',
            r'^clang\s+',
            r'^make\s+(build|test|clean)',
            r'^tsc(\s|$)',
            r'^eslint\s+',
            r'^prettier\s+',

            # Git operations
            r'^git\s+(status|add|commit|push|pull|fetch|checkout|branch|log|diff|show|reset|stash)',

            # System information
            r'^uname(\s|$)',
            r'^whoami(\s|$)',
            r'^date(\s|$)',
            r'^uptime(\s|$)',
            r'^ps\s+',
            r'^top(\s|$)',
            r'^htop(\s|$)',
            r'^df(\s|$)',
            r'^free(\s|$)',

            # Text processing
            r'^sort\s+',
            r'^uniq\s+',
            r'^awk\s+',
            r'^sed\s+',
            r'^cut\s+',
            r'^wc\s+',

            # Compression
            r'^tar\s+',
            r'^zip\s+',
            r'^unzip\s+',
            r'^gzip\s+',
            r'^gunzip\s+',
        ]

        self.allowed_commands = [re.compile(pattern, re.IGNORECASE) for pattern in allowed_patterns]

        # Dangerous characters that require extra scrutiny
        self.dangerous_chars = {
            ';', '|', '&', '`', '$', '>', '<', '*', '?', '[', ']', '(', ')', '{', '}'
        }

        logger.info(f"🔒 Initialized command filter with {len(self.blocked_patterns)} blocked patterns and {len(self.allowed_commands)} allowed patterns")

    def is_command_allowed(self, command: str) -> bool:
        """Check if command is allowed to execute."""
        try:
            # Clean and normalize command
            cleaned_command = command.strip()

            if not cleaned_command:
                return False

            # Check for blocked patterns first
            for pattern in self.blocked_patterns:
                if pattern.search(cleaned_command):
                    logger.warning(f"🚫 Command blocked by pattern: {pattern.pattern}")
                    return False

            # Check for dangerous character combinations
            if self._has_dangerous_patterns(cleaned_command):
                logger.warning(f"🚫 Command blocked due to dangerous patterns")
                return False

            # Check whitelist
            for pattern in self.allowed_commands:
                if pattern.match(cleaned_command):
                    logger.debug(f"✅ Command allowed by pattern: {pattern.pattern}")
                    return True

            # If no whitelist match, check if it's a simple safe command
            if self._is_simple_safe_command(cleaned_command):
                logger.debug(f"✅ Command allowed as simple safe command")
                return True

            logger.warning(f"🚫 Command not in whitelist: {cleaned_command[:50]}...")
            return False

        except Exception as e:
            logger.error(f"❌ Error checking command: {e}")
            return False

    def _has_dangerous_patterns(self, command: str) -> bool:
        """Check for dangerous character patterns."""

        # Multiple command separators
        if command.count(';') > 1 or command.count('|') > 2:
            return True

        # Command substitution
        if '`' in command or '$(' in command:
            return True

        # Dangerous redirections
        if re.search(r'>\s*/dev/', command) or re.search(r'>\s*/proc/', command):
            return True

        # Multiple ampersands (background processes)
        if command.count('&') > 1:
            return True

        # Suspicious environment variable usage
        if re.search(r'\$\{.*\}', command) or re.search(r'\$[A-Z_]+', command):
            suspicious_vars = ['PATH', 'LD_LIBRARY_PATH', 'HOME', 'SHELL']
            for var in suspicious_vars:
                if f'${var}' in command:
                    return True

        return False

    def _is_simple_safe_command(self, command: str) -> bool:
        """Check if command is a simple, safe command."""
        try:
            # Parse command
            parts = shlex.split(command)
            if not parts:
                return False

            base_command = parts[0]

            # List of absolutely safe commands
            safe_commands = {
                'ls', 'pwd', 'whoami', 'date', 'uptime', 'uname',
                'echo', 'cat', 'head', 'tail', 'wc', 'sort', 'uniq'
            }

            if base_command in safe_commands:
                # Additional check: no dangerous arguments
                args = ' '.join(parts[1:])
                if not any(char in args for char in self.dangerous_chars):
                    return True

            return False

        except ValueError:
            # Command has unmatched quotes or other parsing errors
            return False

    def get_command_risk_level(self, command: str) -> str:
        """Get risk level for a command."""
        if not self.is_command_allowed(command):
            return "blocked"

        # Check for high-risk patterns
        high_risk_patterns = [
            r'rm\s+',
            r'sudo\s+',
            r'chmod\s+',
            r'chown\s+',
            r'npm\s+install',
            r'pip\s+install',
        ]

        for pattern in high_risk_patterns:
            if re.search(pattern, command, re.IGNORECASE):
                return "high"

        # Check for medium-risk patterns
        medium_risk_patterns = [
            r'git\s+(push|pull|checkout)',
            r'cargo\s+build',
            r'npm\s+run',
            r'python\s+',
        ]

        for pattern in medium_risk_patterns:
            if re.search(pattern, command, re.IGNORECASE):
                return "medium"

        return "low"

    def suggest_alternative(self, blocked_command: str) -> List[str]:
        """Suggest alternative commands for blocked ones."""
        suggestions = []

        # Common dangerous command alternatives
        alternatives = {
            r'rm\s+-rf\s+/': ['Use specific file paths instead of root directory'],
            r'sudo\s+': ['Run without sudo if possible', 'Use specific user permissions'],
            r'curl.*\|\s*sh': ['Download file first, then inspect before running'],
            r'dd\s+': ['Use cp for file copying', 'Use specific backup tools'],
        }

        for pattern, alts in alternatives.items():
            if re.search(pattern, blocked_command, re.IGNORECASE):
                suggestions.extend(alts)

        if not suggestions:
            suggestions = [
                'Check if the command is necessary',
                'Use a more specific, safer alternative',
                'Run the command in a controlled environment'
            ]

        return suggestions

    def add_allowed_pattern(self, pattern: str) -> None:
        """Add a new allowed command pattern."""
        try:
            compiled_pattern = re.compile(pattern, re.IGNORECASE)
            self.allowed_commands.append(compiled_pattern)
            logger.info(f"➕ Added allowed command pattern: {pattern}")
        except re.error as e:
            logger.error(f"❌ Invalid regex pattern: {pattern} - {e}")

    def add_blocked_pattern(self, pattern: str) -> None:
        """Add a new blocked command pattern."""
        try:
            compiled_pattern = re.compile(pattern, re.IGNORECASE)
            self.blocked_patterns.append(compiled_pattern)
            logger.info(f"🚫 Added blocked command pattern: {pattern}")
        except re.error as e:
            logger.error(f"❌ Invalid regex pattern: {pattern} - {e}")

    def get_filter_stats(self) -> Dict[str, int]:
        """Get statistics about the command filter."""
        return {
            "allowed_patterns": len(self.allowed_commands),
            "blocked_patterns": len(self.blocked_patterns),
            "dangerous_chars": len(self.dangerous_chars)
        }