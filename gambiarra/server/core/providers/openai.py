"""
OpenAI provider implementation.
Supports OpenAI API and compatible services.
"""

import json
import logging
import time
from typing import Dict, List, Any, AsyncIterator
import aiohttp

from .base import AIProvider, GenerationRequest, GenerationResponse, HealthCheckResult, ProviderStatus

logger = logging.getLogger(__name__)


class OpenAIProvider(AIProvider):
    """OpenAI API provider."""

    def __init__(self, api_key: str, base_url: str = "https://api.openai.com/v1", model: str = "gpt-4"):
        super().__init__("openai", api_key, base_url, model)
        self.session = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def stream_completion(self, request: GenerationRequest) -> AsyncIterator[str]:
        """Stream completion from OpenAI."""
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
                    raise Exception(f"OpenAI API error {response.status}: {error_text}")

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
            logger.error(f"❌ OpenAI provider error: {e}")
            yield f"Error communicating with OpenAI: {e}"

    async def generate_completion(self, request: GenerationRequest) -> GenerationResponse:
        """Generate non-streaming completion."""
        session = await self._get_session()

        payload = {
            "model": request.model or self.model,
            "messages": request.messages,
            "stream": False,
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
                    raise Exception(f"OpenAI API error {response.status}: {error_text}")

                result = await response.json()
                choice = result["choices"][0]

                return GenerationResponse(
                    content=choice["message"]["content"],
                    model=result["model"],
                    usage=result.get("usage", {}),
                    metadata={"provider": "openai"}
                )

        except Exception as e:
            logger.error(f"❌ OpenAI provider error: {e}")
            raise

    async def health_check(self) -> HealthCheckResult:
        """Check OpenAI health."""
        session = await self._get_session()

        try:
            start_time = time.time()
            # Use models endpoint for health check
            async with session.get(
                f"{self.base_url}/models",
                headers={"Authorization": f"Bearer {self.api_key}"}
            ) as response:
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
        # OpenAI expects specific tool call format
        required_fields = ["name", "parameters"]
        return all(field in tool_call for field in required_fields)

    async def close(self) -> None:
        """Close HTTP session."""
        if self.session and not self.session.closed:
            await self.session.close()

    def get_supported_models(self) -> List[str]:
        """Get supported OpenAI models."""
        return [
            "gpt-4",
            "gpt-4-turbo",
            "gpt-3.5-turbo",
            "gpt-4o",
            "gpt-4o-mini"
        ]

    def get_capabilities(self) -> Dict[str, Any]:
        """Get OpenAI provider capabilities."""
        return {
            "streaming": True,
            "tool_calling": True,
            "max_tokens": 128000,  # GPT-4 context window
            "vision": True,
            "json_mode": True
        }