"""
Base AI provider interface with streaming and tool support.
Provides unified interface for multiple LLM providers.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, AsyncIterator, Optional
from dataclasses import dataclass
from enum import Enum


class ProviderStatus(Enum):
    """Provider health status."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class HealthCheckResult:
    """Result of provider health check."""
    status: ProviderStatus
    latency_ms: Optional[float] = None
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = None


@dataclass
class GenerationRequest:
    """Request for AI generation."""
    messages: List[Dict[str, str]]
    model: Optional[str] = None
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    stream: bool = True


@dataclass
class GenerationResponse:
    """Response from AI generation."""
    content: str
    model: str
    usage: Dict[str, int] = None
    metadata: Dict[str, Any] = None


class AIProvider(ABC):
    """Abstract base class for AI providers."""

    def __init__(self, name: str, api_key: str, base_url: str, model: str):
        self.name = name
        self.api_key = api_key
        self.base_url = base_url
        self.model = model

    @abstractmethod
    async def stream_completion(self, request: GenerationRequest) -> AsyncIterator[str]:
        """Stream completion response."""
        pass

    @abstractmethod
    async def generate_completion(self, request: GenerationRequest) -> GenerationResponse:
        """Generate non-streaming completion."""
        pass

    @abstractmethod
    async def health_check(self) -> HealthCheckResult:
        """Check provider health."""
        pass

    @abstractmethod
    async def validate_tool_call(self, tool_call: Dict[str, Any]) -> bool:
        """Validate tool call format."""
        pass

    async def close(self) -> None:
        """Close provider resources."""
        pass

    def get_supported_models(self) -> List[str]:
        """Get list of supported models."""
        return [self.model]

    def get_capabilities(self) -> Dict[str, Any]:
        """Get provider capabilities."""
        return {
            "streaming": True,
            "tool_calling": True,
            "max_tokens": 4096
        }