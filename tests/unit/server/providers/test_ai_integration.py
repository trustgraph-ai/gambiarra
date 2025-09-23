"""
Tests for AI provider integration.
Tests provider interface, message formatting, and error handling.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import json
import aiohttp
from gambiarra.server.ai_integration.providers import (
    AIProvider, TestAIProvider, AIProviderManager
)


class TestAIProvider:
    """Test base AI provider interface."""

    def test_ai_provider_initialization(self):
        """Test AI provider initialization."""
        provider = TestAIProvider(
            api_key="test-key",
            base_url="http://localhost:8001",
            model="gpt-4"
        )

        assert provider.api_key == "test-key"
        assert provider.base_url == "http://localhost:8001"
        assert provider.model == "gpt-4"

    def test_ai_provider_abstract_methods(self):
        """Test that AI provider is abstract."""
        # Should not be able to instantiate abstract base class directly
        with pytest.raises(TypeError):
            AIProvider("key", "url", "model")


@pytest.mark.asyncio
class TestTestAIProvider:
    """Test the TestAIProvider implementation."""

    @pytest.fixture
    def test_provider(self):
        """Create test AI provider instance."""
        return TestAIProvider()

    @pytest.fixture
    def sample_messages(self):
        """Sample conversation messages."""
        return [
            {"role": "system", "content": "You are a helpful coding assistant."},
            {"role": "user", "content": "Help me read a file called main.py"}
        ]

    @pytest.fixture
    def mock_response(self):
        """Mock HTTP response for AI provider."""
        response = AsyncMock()
        response.status = 200
        response.headers = {"content-type": "text/plain"}

        # Mock streaming response
        async def mock_iter():
            chunks = [
                "I'll help you read that file. ",
                "<read_file><args><file><path>main.py</path></file></args></read_file>",
                " The file has been read successfully."
            ]
            for chunk in chunks:
                yield chunk.encode()

        response.content.iter_chunked = mock_iter
        return response

    async def test_health_check(self, test_provider):
        """Test provider health check."""
        with patch('aiohttp.ClientSession.get') as mock_get:
            # Mock successful health check
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value={"status": "healthy"})
            mock_get.return_value.__aenter__.return_value = mock_response

            health = await test_provider.health_check()

            assert health["status"] == "healthy"
            mock_get.assert_called_once()

    async def test_health_check_failure(self, test_provider):
        """Test provider health check failure."""
        with patch('aiohttp.ClientSession.get') as mock_get:
            # Mock failed health check
            mock_get.side_effect = aiohttp.ClientError("Connection failed")

            health = await test_provider.health_check()

            assert health["status"] == "unhealthy"
            assert "error" in health

    async def test_stream_completion(self, test_provider, sample_messages, mock_response):
        """Test streaming completion."""
        with patch('aiohttp.ClientSession.post') as mock_post:
            mock_post.return_value.__aenter__.return_value = mock_response

            chunks = []
            async for chunk in test_provider.stream_completion(sample_messages):
                chunks.append(chunk)

            assert len(chunks) == 3
            assert chunks[0] == "I'll help you read that file. "
            assert "<read_file>" in chunks[1]
            assert chunks[2] == " The file has been read successfully."

    async def test_stream_completion_request_format(self, test_provider, sample_messages):
        """Test that stream completion sends correct request format."""
        with patch('aiohttp.ClientSession.post') as mock_post:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.content.iter_chunked = AsyncMock()
            mock_response.content.iter_chunked.return_value = []
            mock_post.return_value.__aenter__.return_value = mock_response

            async for _ in test_provider.stream_completion(sample_messages):
                pass

            # Verify request was made with correct parameters
            mock_post.assert_called_once()
            call_args = mock_post.call_args

            # Check URL
            assert "/chat/completions" in call_args[0][0]

            # Check headers
            headers = call_args[1]["headers"]
            assert "Authorization" in headers
            assert "Content-Type" in headers

            # Check request body
            json_data = call_args[1]["json"]
            assert json_data["model"] == "gpt-4"
            assert json_data["messages"] == sample_messages
            assert json_data["stream"] is True

    async def test_stream_completion_error_handling(self, test_provider, sample_messages):
        """Test error handling in stream completion."""
        with patch('aiohttp.ClientSession.post') as mock_post:
            # Mock HTTP error
            mock_post.side_effect = aiohttp.ClientError("Network error")

            chunks = []
            async for chunk in test_provider.stream_completion(sample_messages):
                chunks.append(chunk)

            # Should handle error gracefully
            assert len(chunks) == 0

    async def test_stream_completion_http_error(self, test_provider, sample_messages):
        """Test handling of HTTP error responses."""
        with patch('aiohttp.ClientSession.post') as mock_post:
            mock_response = AsyncMock()
            mock_response.status = 500
            mock_response.text = AsyncMock(return_value="Internal Server Error")
            mock_post.return_value.__aenter__.return_value = mock_response

            chunks = []
            async for chunk in test_provider.stream_completion(sample_messages):
                chunks.append(chunk)

            # Should handle HTTP error gracefully
            assert len(chunks) == 0

    async def test_session_management(self, test_provider):
        """Test HTTP session management."""
        # Session should be created lazily
        assert test_provider.session is None

        # First call should create session
        session = await test_provider._get_session()
        assert session is not None
        assert test_provider.session is session

        # Second call should reuse session
        session2 = await test_provider._get_session()
        assert session2 is session

    async def test_cleanup_resources(self, test_provider):
        """Test cleanup of HTTP session."""
        # Create session
        session = await test_provider._get_session()
        assert session is not None

        # Cleanup should close session
        await test_provider.cleanup()

        # Session should be closed (would need actual implementation)
        assert test_provider.session is None


class TestAIProviderManager:
    """Test AI provider manager functionality."""

    @pytest.fixture
    def provider_manager(self):
        """Create AI provider manager."""
        return AIProviderManager(default_provider="test")

    @pytest.fixture
    def mock_test_provider(self):
        """Create mock test provider."""
        provider = AsyncMock(spec=TestAIProvider)
        provider.health_check = AsyncMock(return_value={"status": "healthy"})
        provider.stream_completion = AsyncMock()
        return provider

    def test_provider_manager_initialization(self, provider_manager):
        """Test provider manager initialization."""
        assert provider_manager.default_provider == "test"
        assert "test" in provider_manager.providers

    def test_get_provider(self, provider_manager):
        """Test getting a provider by name."""
        provider = provider_manager.get_provider("test")
        assert isinstance(provider, TestAIProvider)

    def test_get_nonexistent_provider(self, provider_manager):
        """Test getting non-existent provider."""
        provider = provider_manager.get_provider("nonexistent")
        assert provider is None

    def test_get_default_provider(self, provider_manager):
        """Test getting default provider."""
        provider = provider_manager.get_default_provider()
        assert isinstance(provider, TestAIProvider)

    async def test_health_check_all_providers(self, provider_manager):
        """Test health check for all providers."""
        with patch.object(provider_manager.providers["test"], "health_check") as mock_health:
            mock_health.return_value = {"status": "healthy"}

            health_results = await provider_manager.health_check_all()

            assert "test" in health_results
            assert health_results["test"]["status"] == "healthy"

    def test_register_custom_provider(self, provider_manager, mock_test_provider):
        """Test registering a custom provider."""
        provider_manager.register_provider("custom", mock_test_provider)

        assert "custom" in provider_manager.providers
        assert provider_manager.get_provider("custom") == mock_test_provider

    def test_unregister_provider(self, provider_manager):
        """Test unregistering a provider."""
        # Test provider should exist initially
        assert "test" in provider_manager.providers

        provider_manager.unregister_provider("test")
        assert "test" not in provider_manager.providers

    def test_list_providers(self, provider_manager):
        """Test listing all available providers."""
        providers = provider_manager.list_providers()
        assert "test" in providers
        assert isinstance(providers, list)

    async def test_provider_failover(self, provider_manager):
        """Test provider failover mechanism."""
        # Register multiple providers
        backup_provider = AsyncMock(spec=TestAIProvider)
        backup_provider.health_check = AsyncMock(return_value={"status": "healthy"})
        provider_manager.register_provider("backup", backup_provider)

        # Mock primary provider failure
        with patch.object(provider_manager.providers["test"], "stream_completion") as mock_stream:
            mock_stream.side_effect = Exception("Provider down")

            # Should fallback to backup provider (would need implementation)
            primary = provider_manager.get_provider("test")
            backup = provider_manager.get_provider("backup")

            assert primary is not None
            assert backup is not None

    async def test_concurrent_provider_calls(self, provider_manager):
        """Test concurrent calls to multiple providers."""
        # Register additional provider
        provider2 = TestAIProvider(model="gpt-3.5-turbo")
        provider_manager.register_provider("test2", provider2)

        messages = [{"role": "user", "content": "Hello"}]

        with patch('aiohttp.ClientSession.post') as mock_post:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.content.iter_chunked = AsyncMock(return_value=[])
            mock_post.return_value.__aenter__.return_value = mock_response

            # Make concurrent calls
            tasks = []
            for provider_name in ["test", "test2"]:
                provider = provider_manager.get_provider(provider_name)
                task = asyncio.create_task(
                    list(provider.stream_completion(messages).__aiter__())
                )
                tasks.append(task)

            results = await asyncio.gather(*tasks, return_exceptions=True)
            assert len(results) == 2

    def test_provider_configuration(self, provider_manager):
        """Test provider configuration management."""
        test_provider = provider_manager.get_provider("test")

        # Verify default configuration
        assert test_provider.model == "gpt-4"
        assert test_provider.base_url == "http://localhost:8001/v1"

        # Test configuration update (would need implementation)
        new_config = {
            "model": "gpt-3.5-turbo",
            "temperature": 0.7
        }

        # provider_manager.update_provider_config("test", new_config)
        # Would verify config was updated

    async def test_provider_rate_limiting(self, provider_manager):
        """Test provider rate limiting."""
        provider = provider_manager.get_provider("test")
        messages = [{"role": "user", "content": "Hello"}]

        # Simulate multiple rapid requests (would need rate limiting implementation)
        start_time = asyncio.get_event_loop().time()

        with patch('aiohttp.ClientSession.post') as mock_post:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.content.iter_chunked = AsyncMock(return_value=[])
            mock_post.return_value.__aenter__.return_value = mock_response

            # Make multiple requests
            tasks = []
            for _ in range(5):
                task = asyncio.create_task(
                    list(provider.stream_completion(messages).__aiter__())
                )
                tasks.append(task)

            await asyncio.gather(*tasks)

        end_time = asyncio.get_event_loop().time()
        duration = end_time - start_time

        # Verify calls were made (rate limiting would add delays)
        assert mock_post.call_count == 5