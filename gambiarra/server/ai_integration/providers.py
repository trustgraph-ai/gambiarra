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

# Import TrustGraph API
try:
    from trustgraph.api import Api
    TRUSTGRAPH_AVAILABLE = True
except ImportError:
    TRUSTGRAPH_AVAILABLE = False

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


class DummyAIProvider(AIProvider):
    """Dummy AI provider for testing that connects to our test server."""

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


class TrustGraphProvider(AIProvider):
    """TrustGraph API provider."""

    def __init__(self, api_key: str = "", base_url: str = "http://localhost:8088/", model: str = "default"):
        super().__init__(api_key, base_url, model)
        self.session = None
        self.flow_id = model  # Use model as flow ID for TrustGraph

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if not self.session:
            self.session = aiohttp.ClientSession()
        return self.session

    async def stream_completion(self, messages: List[Dict[str, str]]) -> AsyncIterator[str]:
        """Stream completion from TrustGraph."""
        if not TRUSTGRAPH_AVAILABLE:
            yield "Error: TrustGraph API not available. Please install trustgraph package."
            return

        try:
            # Build conversation context for TrustGraph
            system_msg = ""
            conversation_context = []

            logger.info(f"🔍 TrustGraph received {len(messages)} messages")
            for i, msg in enumerate(messages):
                if msg.get("role") == "system":
                    system_msg = msg.get("content", "")
                    logger.debug(f"System message: {system_msg[:100]}...")
                else:
                    role = msg.get("role", "")
                    content = msg.get("content", "")
                    conversation_context.append(f"{role}: {content}")
                    logger.debug(f"Message {i}: {role}: {content[:100]}...")

            # Combine conversation into a single prompt for TrustGraph
            full_prompt = "\n\n".join(conversation_context)
            logger.info(f"🔍 TrustGraph full prompt ({len(full_prompt)} chars): {full_prompt[:200]}...")

            # Create TrustGraph API instance
            api = Api(url=self.base_url)

            # Call text completion with full conversation context
            response = api.flow().id(self.flow_id).text_completion(
                system=system_msg,
                prompt=full_prompt
            )

            # Yield the complete response
            yield response

        except Exception as e:
            logger.error(f"❌ TrustGraph provider error: {e}")
            yield f"Error communicating with TrustGraph: {e}"

    async def health_check(self) -> Dict[str, Any]:
        """Check TrustGraph health."""
        if not TRUSTGRAPH_AVAILABLE:
            return {
                "status": "unavailable",
                "provider": "trustgraph",
                "error": "TrustGraph API not installed"
            }

        try:
            # Simple health check - try to create API instance
            api = Api(url=self.base_url)
            # You could add a simple API call here if TrustGraph has a health endpoint

            return {
                "status": "healthy",
                "provider": "trustgraph",
                "flow_id": self.flow_id
            }

        except Exception as e:
            return {
                "status": "unhealthy",
                "provider": "trustgraph",
                "error": str(e)
            }

    async def close(self):
        """Close HTTP session."""
        if self.session:
            await self.session.close()


class AIProviderManager:
    """Manages multiple AI providers."""

    def __init__(self, default_provider: str = "test"):
        self.providers: Dict[str, AIProvider] = {}
        self.default_provider = default_provider

    async def initialize(self, openai_api_key: str = None, trustgraph_url: str = None, trustgraph_flow: str = None):
        """Initialize AI providers."""
        # Initialize test provider (always available)
        self.providers["test"] = DummyAIProvider()

        # Initialize OpenAI provider if API key provided
        if openai_api_key:
            self.providers["openai"] = OpenAIProvider(api_key=openai_api_key)
            logger.info("✅ OpenAI provider initialized")

        # Initialize TrustGraph provider (always available with default URL)
        trustgraph_url = trustgraph_url or "http://localhost:8088/"
        flow_id = trustgraph_flow or "default"
        self.providers["trustgraph"] = TrustGraphProvider(
            base_url=trustgraph_url,
            model=flow_id
        )
        logger.info(f"✅ TrustGraph provider initialized (URL: {trustgraph_url}, flow: {flow_id})")

        logger.info(f"✅ AI providers initialized: {list(self.providers.keys())}")

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