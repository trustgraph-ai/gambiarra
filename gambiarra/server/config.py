"""
Server configuration for Gambiarra.
"""

import os
from typing import Optional
from dataclasses import dataclass


@dataclass
class ServerConfig:
    """Server configuration settings."""

    host: str = "127.0.0.1"  # Use explicit IPv4 to avoid IPv6 binding issues
    port: int = 8000

    # AI Provider settings
    ai_provider: str = "test"  # test, openai, trustgraph

    # OpenAI settings
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4"

    # TrustGraph settings
    trustgraph_url: Optional[str] = None
    trustgraph_flow: str = "default"

    # Legacy settings (for backward compatibility)
    api_key: Optional[str] = None
    api_base_url: Optional[str] = None
    model: str = "gpt-4"

    # Session management
    max_sessions: int = 100
    session_timeout: int = 3600  # seconds

    # Logging
    log_level: str = "INFO"

    # Security
    enable_cors: bool = True
    allowed_origins: list = None

    def __post_init__(self):
        """Load from environment variables."""

        # Load from environment
        # Convert 'localhost' to '127.0.0.1' to avoid IPv6 binding issues
        env_host = os.getenv("GAMBIARRA_HOST", self.host)
        self.host = '127.0.0.1' if env_host == 'localhost' else env_host
        self.port = int(os.getenv("GAMBIARRA_PORT", self.port))

        self.ai_provider = os.getenv("GAMBIARRA_AI_PROVIDER", self.ai_provider)

        # Load OpenAI settings
        self.openai_api_key = os.getenv("OPENAI_API_KEY", self.openai_api_key)
        self.openai_model = os.getenv("GAMBIARRA_OPENAI_MODEL", self.openai_model)

        # Load TrustGraph settings
        self.trustgraph_url = os.getenv("GAMBIARRA_TRUSTGRAPH_URL", self.trustgraph_url)
        self.trustgraph_flow = os.getenv("GAMBIARRA_TRUSTGRAPH_FLOW", self.trustgraph_flow)

        # Legacy settings (for backward compatibility)
        self.api_key = os.getenv("GAMBIARRA_API_KEY", self.api_key)
        self.api_base_url = os.getenv("GAMBIARRA_API_BASE_URL", self.api_base_url)
        self.model = os.getenv("GAMBIARRA_MODEL", self.model)

        self.max_sessions = int(os.getenv("GAMBIARRA_MAX_SESSIONS", self.max_sessions))
        self.session_timeout = int(os.getenv("GAMBIARRA_SESSION_TIMEOUT", self.session_timeout))

        self.log_level = os.getenv("GAMBIARRA_LOG_LEVEL", self.log_level)

        # Set defaults for legacy compatibility
        if self.ai_provider == "test":
            self.api_base_url = self.api_base_url or "http://localhost:8001/v1"
            self.api_key = self.api_key or "test-key"

        # Set default TrustGraph URL if not specified
        if not self.trustgraph_url:
            self.trustgraph_url = "http://localhost:8088/"

        # Parse allowed origins
        origins_env = os.getenv("GAMBIARRA_ALLOWED_ORIGINS")
        if origins_env:
            self.allowed_origins = [origin.strip() for origin in origins_env.split(",")]
        elif self.allowed_origins is None:
            self.allowed_origins = ["*"]  # Default to allow all in development

    @property
    def websocket_url(self) -> str:
        """Get the WebSocket URL."""
        return f"ws://{self.host}:{self.port}/ws"

    @property
    def http_url(self) -> str:
        """Get the HTTP URL."""
        return f"http://{self.host}:{self.port}"


# Global config instance
config = ServerConfig()