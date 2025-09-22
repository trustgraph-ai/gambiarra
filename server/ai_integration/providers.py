"""
AI Provider integration for Gambiarra.
Supports multiple LLM providers with unified interface.
"""

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Any, AsyncIterator, Optional
import aiohttp

logger = logging.getLogger(__name__)


class AIProvider(ABC):
    """Abstract base class for AI providers."""

    def __init__(self, api_key: str, base_url: str, model: str):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model

    @abstractmethod
    async def stream_completion(self, messages: List[Dict[str, str]]) -> AsyncIterator[str]:
        """Stream completion response."""
        pass

    @abstractmethod
    async def health_check(self) -> Dict[str, Any]:
        """Check provider health."""
        pass


class TestAIProvider(AIProvider):
    """Test AI provider that connects to our dummy server."""

    def __init__(self, api_key: str = "test-key", base_url: str = "http://localhost:8001/v1", model: str = "gpt-4"):
        super().__init__(api_key, base_url, model)
        self.session = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if not self.session:
            self.session = aiohttp.ClientSession()
        return self.session

    async def stream_completion(self, messages: List[Dict[str, str]]) -> AsyncIterator[str]:
        """Stream completion from test provider."""
        session = await self._get_session()

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "temperature": 0.1
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
                    raise Exception(f"AI provider error {response.status}: {error_text}")

                async for line in response.content:
                    line_str = line.decode('utf-8').strip()

                    if not line_str:
                        continue

                    if line_str.startswith("data: "):
                        data_str = line_str[6:]  # Remove "data: " prefix

                        if data_str == "[DONE]":
                            break

                        try:
                            data = json.loads(data_str)
                            choices = data.get("choices", [])

                            if choices and "delta" in choices[0]:
                                content = choices[0]["delta"].get("content", "")
                                if content:
                                    yield content

                        except json.JSONDecodeError:
                            logger.warning(f"Failed to parse JSON: {data_str}")
                            continue

        except Exception as e:
            logger.error(f"❌ Test AI provider error: {e}")
            yield f"Error communicating with AI provider: {e}"

    async def health_check(self) -> Dict[str, Any]:
        """Check test provider health."""
        session = await self._get_session()

        try:
            async with session.get(f"{self.base_url.replace('/v1', '')}/health") as response:
                if response.status == 200:
                    health_data = await response.json()
                    return {
                        "status": "healthy",
                        "provider": "test",
                        "details": health_data
                    }
                else:
                    return {
                        "status": "unhealthy",
                        "provider": "test",
                        "error": f"HTTP {response.status}"
                    }

        except Exception as e:
            return {
                "status": "unhealthy",
                "provider": "test",
                "error": str(e)
            }

    async def close(self):
        """Close HTTP session."""
        if self.session:
            await self.session.close()


class OpenAIProvider(AIProvider):
    """OpenAI API provider."""

    def __init__(self, api_key: str, base_url: str = "https://api.openai.com/v1", model: str = "gpt-4"):
        super().__init__(api_key, base_url, model)
        self.session = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if not self.session:
            self.session = aiohttp.ClientSession()
        return self.session

    async def stream_completion(self, messages: List[Dict[str, str]]) -> AsyncIterator[str]:
        """Stream completion from OpenAI."""
        session = await self._get_session()

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "temperature": 0.1
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
                    line_str = line.decode('utf-8').strip()

                    if not line_str or not line_str.startswith("data: "):
                        continue

                    data_str = line_str[6:]  # Remove "data: " prefix

                    if data_str == "[DONE]":
                        break

                    try:
                        data = json.loads(data_str)
                        choices = data.get("choices", [])

                        if choices and "delta" in choices[0]:
                            content = choices[0]["delta"].get("content", "")
                            if content:
                                yield content

                    except json.JSONDecodeError:
                        continue

        except Exception as e:
            logger.error(f"❌ OpenAI provider error: {e}")
            yield f"Error communicating with OpenAI: {e}"

    async def health_check(self) -> Dict[str, Any]:
        """Check OpenAI health."""
        session = await self._get_session()

        try:
            async with session.get(
                f"{self.base_url}/models",
                headers={"Authorization": f"Bearer {self.api_key}"}
            ) as response:
                if response.status == 200:
                    return {
                        "status": "healthy",
                        "provider": "openai"
                    }
                else:
                    return {
                        "status": "unhealthy",
                        "provider": "openai",
                        "error": f"HTTP {response.status}"
                    }

        except Exception as e:
            return {
                "status": "unhealthy",
                "provider": "openai",
                "error": str(e)
            }

    async def close(self):
        """Close HTTP session."""
        if self.session:
            await self.session.close()


class AIProviderManager:
    """Manages multiple AI providers."""

    def __init__(self):
        self.providers: Dict[str, AIProvider] = {}
        self.default_provider = "test"

    async def initialize(self):
        """Initialize AI providers."""
        # Initialize test provider (always available)
        self.providers["test"] = TestAIProvider()

        logger.info("✅ AI providers initialized")

    def add_provider(self, name: str, provider: AIProvider):
        """Add a new provider."""
        self.providers[name] = provider
        logger.info(f"➕ Added AI provider: {name}")

    def get_provider(self, name: str = None) -> AIProvider:
        """Get AI provider by name."""
        provider_name = name or self.default_provider

        if provider_name not in self.providers:
            logger.warning(f"❌ Provider {provider_name} not found, using {self.default_provider}")
            provider_name = self.default_provider

        return self.providers[provider_name]

    def available_providers(self) -> List[str]:
        """Get list of available providers."""
        return list(self.providers.keys())

    async def health_check(self) -> Dict[str, Any]:
        """Check health of all providers."""
        health_results = {}

        for name, provider in self.providers.items():
            try:
                health_results[name] = await provider.health_check()
            except Exception as e:
                health_results[name] = {
                    "status": "error",
                    "provider": name,
                    "error": str(e)
                }

        return health_results

    async def close_all(self):
        """Close all provider connections."""
        for provider in self.providers.values():
            try:
                await provider.close()
            except Exception as e:
                logger.error(f"❌ Error closing provider: {e}")

        logger.info("🔌 Closed all AI provider connections")