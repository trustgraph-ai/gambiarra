"""
Client configuration for Gambiarra.
"""

import os
from typing import Optional
from dataclasses import dataclass


@dataclass
class ClientConfig:
    """Client configuration settings."""

    server_url: str = "ws://localhost:8000/ws"
    workspace_root: str = "."

    # Security settings
    auto_approve_reads: bool = True
    command_timeout: int = 30
    max_file_size: int = 10_000_000  # 10MB
    backup_enabled: bool = True

    # UI settings
    interactive_mode: bool = True
    show_tool_output: bool = True
    log_level: str = "INFO"

    def __post_init__(self):
        """Load from environment variables."""

        # Load from environment
        self.server_url = os.getenv("GAMBIARRA_SERVER_URL", self.server_url)
        self.workspace_root = os.getenv("GAMBIARRA_WORKSPACE", self.workspace_root)

        self.auto_approve_reads = os.getenv("GAMBIARRA_AUTO_APPROVE_READS", "true").lower() == "true"
        self.command_timeout = int(os.getenv("GAMBIARRA_COMMAND_TIMEOUT", self.command_timeout))
        self.max_file_size = int(os.getenv("GAMBIARRA_MAX_FILE_SIZE", self.max_file_size))
        self.backup_enabled = os.getenv("GAMBIARRA_BACKUP_ENABLED", "true").lower() == "true"

        self.interactive_mode = os.getenv("GAMBIARRA_INTERACTIVE", "true").lower() == "true"
        self.show_tool_output = os.getenv("GAMBIARRA_SHOW_OUTPUT", "true").lower() == "true"
        self.log_level = os.getenv("GAMBIARRA_LOG_LEVEL", self.log_level)

        # Resolve workspace root to absolute path
        self.workspace_root = os.path.abspath(self.workspace_root)

    @property
    def workspace_name(self) -> str:
        """Get workspace directory name."""
        return os.path.basename(self.workspace_root)


# Global config instance
config = ClientConfig()