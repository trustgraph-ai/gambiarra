"""
AI Provider Manager - orchestrates multiple AI providers.
Manages multiple AI providers with failover and load balancing.
"""

import logging
from typing import Dict, List, Any, Optional
import asyncio

from .base import AIProvider, GenerationRequest, HealthCheckResult, ProviderStatus
from .test import TestAIProvider
from .openai import OpenAIProvider

# Optional TrustGraph import
try:
    from .trustgraph import TrustGraphProvider
    TRUSTGRAPH_AVAILABLE = True
except ImportError:
    TRUSTGRAPH_AVAILABLE = False

logger = logging.getLogger(__name__)


class AIProviderManager:
    """Manages multiple AI providers with failover and load balancing."""

    def __init__(self, default_provider: str = "test"):
        self.providers: Dict[str, AIProvider] = {}
        self.default_provider = default_provider
        self._health_cache: Dict[str, HealthCheckResult] = {}
        self._cache_ttl = 300  # 5 minutes

    async def initialize(self,
                        openai_api_key: Optional[str] = None,
                        trustgraph_api_key: Optional[str] = None,
                        trustgraph_base_url: Optional[str] = None) -> None:
        """Initialize available providers."""

        # Always add test provider
        self.providers["test"] = TestAIProvider()
        logger.info("✅ Test provider initialized")

        # Initialize OpenAI provider if API key provided
        if openai_api_key:
            self.providers["openai"] = OpenAIProvider(api_key=openai_api_key)
            logger.info("✅ OpenAI provider initialized")

        # Initialize TrustGraph provider if available and configured
        if TRUSTGRAPH_AVAILABLE and trustgraph_api_key and trustgraph_base_url:
            self.providers["trustgraph"] = TrustGraphProvider(
                api_key=trustgraph_api_key,
                base_url=trustgraph_base_url
            )
            logger.info("✅ TrustGraph provider initialized")

        # Validate default provider exists
        if self.default_provider not in self.providers:
            logger.warning(f"Default provider '{self.default_provider}' not available, falling back to 'test'")
            self.default_provider = "test"

    def get_provider(self, name: Optional[str] = None) -> AIProvider:
        """Get provider by name or default."""
        provider_name = name or self.default_provider

        provider = self.providers.get(provider_name)
        if not provider:
            # Fallback to any available provider
            if self.providers:
                provider_name = list(self.providers.keys())[0]
                provider = self.providers[provider_name]
                logger.warning(f"Provider '{name}' not found, using '{provider_name}'")
            else:
                raise ValueError("No AI providers available")

        return provider

    def available_providers(self) -> List[str]:
        """Get list of available provider names."""
        return list(self.providers.keys())

    async def health_check(self, provider_name: Optional[str] = None) -> Dict[str, HealthCheckResult]:
        """Check health of providers."""
        if provider_name:
            # Check specific provider
            provider = self.providers.get(provider_name)
            if not provider:
                return {provider_name: HealthCheckResult(
                    status=ProviderStatus.UNKNOWN,
                    error_message="Provider not found"
                )}

            result = await provider.health_check()
            self._health_cache[provider_name] = result
            return {provider_name: result}

        # Check all providers
        results = {}
        tasks = []

        for name, provider in self.providers.items():
            tasks.append(self._check_provider_health(name, provider))

        health_results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, (name, _) in enumerate(self.providers.items()):
            result = health_results[i]
            if isinstance(result, Exception):
                result = HealthCheckResult(
                    status=ProviderStatus.UNHEALTHY,
                    error_message=str(result)
                )
            results[name] = result
            self._health_cache[name] = result

        return results

    async def _check_provider_health(self, name: str, provider: AIProvider) -> HealthCheckResult:
        """Check individual provider health."""
        try:
            return await provider.health_check()
        except Exception as e:
            logger.error(f"Health check failed for {name}: {e}")
            return HealthCheckResult(
                status=ProviderStatus.UNHEALTHY,
                error_message=str(e)
            )

    async def get_healthy_provider(self, preferred: Optional[str] = None) -> Optional[AIProvider]:
        """Get a healthy provider, preferring the specified one."""
        # Try preferred provider first
        if preferred and preferred in self.providers:
            health = await self.health_check(preferred)
            if health[preferred].status == ProviderStatus.HEALTHY:
                return self.providers[preferred]

        # Try default provider
        if self.default_provider in self.providers:
            health = await self.health_check(self.default_provider)
            if health[self.default_provider].status == ProviderStatus.HEALTHY:
                return self.providers[self.default_provider]

        # Try any healthy provider
        health_results = await self.health_check()
        for name, result in health_results.items():
            if result.status == ProviderStatus.HEALTHY:
                return self.providers[name]

        return None

    def get_provider_info(self, name: Optional[str] = None) -> Dict[str, Any]:
        """Get information about a provider."""
        provider = self.get_provider(name)
        health = self._health_cache.get(provider.name, HealthCheckResult(status=ProviderStatus.UNKNOWN))

        return {
            "name": provider.name,
            "model": provider.model,
            "status": health.status.value,
            "latency_ms": health.latency_ms,
            "capabilities": provider.get_capabilities(),
            "supported_models": provider.get_supported_models()
        }

    async def close_all(self) -> None:
        """Close all provider connections."""
        for provider in self.providers.values():
            try:
                await provider.close()
            except Exception as e:
                logger.error(f"Error closing provider {provider.name}: {e}")

        self.providers.clear()
        self._health_cache.clear()

    def set_default_provider(self, name: str) -> None:
        """Set the default provider."""
        if name not in self.providers:
            raise ValueError(f"Provider '{name}' is not available")
        self.default_provider = name
        logger.info(f"Default provider set to: {name}")

    def get_provider_stats(self) -> Dict[str, Any]:
        """Get statistics about all providers."""
        stats = {
            "total_providers": len(self.providers),
            "default_provider": self.default_provider,
            "providers": {}
        }

        for name, provider in self.providers.items():
            health = self._health_cache.get(name, HealthCheckResult(status=ProviderStatus.UNKNOWN))
            stats["providers"][name] = {
                "status": health.status.value,
                "latency_ms": health.latency_ms,
                "error": health.error_message
            }

        return stats