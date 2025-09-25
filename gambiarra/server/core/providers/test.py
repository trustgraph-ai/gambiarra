"""
Test AI provider for development and testing.
Connects to mock OpenAI-compatible server.
"""

import asyncio
import json
import logging
import time
from typing import Dict, List, Any, AsyncIterator
import aiohttp

from .base import AIProvider, GenerationRequest, GenerationResponse, HealthCheckResult, ProviderStatus

logger = logging.getLogger(__name__)


class TestAIProvider(AIProvider):
    """Test AI provider that connects to our dummy server."""

    def __init__(self, api_key: str = "test-key", base_url: str = "http://localhost:8001/v1", model: str = "gpt-4"):
        super().__init__("test", api_key, base_url, model)
        self.session = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def stream_completion(self, request: GenerationRequest) -> AsyncIterator[str]:
        """Stream completion from test server."""
        session = await self._get_session()

        payload = {
            "model": request.model or self.model,
            "messages": request.messages,
            "stream": True,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        try:
            async with session.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Test API error {response.status}: {error_text}")

                async for line in response.content:
                    line = line.decode('utf-8').strip()
                    if line.startswith("data: "):
                        data = line[6:]  # Remove "data: " prefix
                        if data == "[DONE]":
                            break

                        try:
                            chunk = json.loads(data)
                            if "choices" in chunk and chunk["choices"]:
                                delta = chunk["choices"][0].get("delta", {})
                                if "content" in delta:
                                    yield delta["content"]
                        except json.JSONDecodeError:
                            continue

        except Exception as e:
            logger.error(f"❌ Test provider error: {e}")
            yield f"Error communicating with test server: {e}"

    async def generate_completion(self, request: GenerationRequest) -> GenerationResponse:
        """Generate non-streaming completion."""
        content_parts = []
        async for chunk in self.stream_completion(request):
            content_parts.append(chunk)

        return GenerationResponse(
            content="".join(content_parts),
            model=request.model or self.model,
            usage={"prompt_tokens": 0, "completion_tokens": len(content_parts)},
            metadata={"provider": "test"}
        )

    async def health_check(self) -> HealthCheckResult:
        """Check test server health."""
        session = await self._get_session()

        try:
            start_time = time.time()
            async with session.get(f"{self.base_url.replace('/v1', '')}/health") as response:
                latency = (time.time() - start_time) * 1000

                if response.status == 200:
                    return HealthCheckResult(
                        status=ProviderStatus.HEALTHY,
                        latency_ms=latency
                    )
                else:
                    return HealthCheckResult(
                        status=ProviderStatus.UNHEALTHY,
                        error_message=f"HTTP {response.status}"
                    )

        except Exception as e:
            return HealthCheckResult(
                status=ProviderStatus.UNHEALTHY,
                error_message=str(e)
            )

    async def validate_tool_call(self, tool_call: Dict[str, Any]) -> bool:
        """Validate tool call format."""
        # Test provider accepts any tool call format
        return True

    async def close(self) -> None:
        """Close HTTP session."""
        if self.session and not self.session.closed:
            await self.session.close()

    def get_capabilities(self) -> Dict[str, Any]:
        """Get test provider capabilities."""
        return {
            "streaming": True,
            "tool_calling": True,
            "max_tokens": 4096,
            "test_mode": True
        }