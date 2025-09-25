"""
Shared test configuration and fixtures for Gambiarra test suite.
"""

import pytest
import tempfile
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any

# Test data
SAMPLE_WORKSPACE_FILES = {
    "main.py": "print('Hello, Gambiarra!')\n",
    "src/utils.py": "def helper():\n    return 'test'\n",
    "README.md": "# Test Project\n",
    ".gambiarraignore": "*.pyc\n__pycache__/\n.env\n"
}

SAMPLE_TOOL_CALLS = {
    "read_file_nested": """<read_file>
<args>
<file>
<path>main.py</path>
</file>
</args>
</read_file>""",

    "write_to_file_nested": """<write_to_file>
<args>
<path>new_file.py</path>
<content>print('Created by test')</content>
<line_count>1</line_count>
</args>
</write_to_file>""",

    "list_files_nested": """<list_files>
<args>
<path>.</path>
<recursive>true</recursive>
</args>
</list_files>"""
}

SAMPLE_AI_RESPONSES = {
    "simple_response": {
        "content": "I'll help you read that file.",
        "tool_calls": []
    },

    "with_tool_call": {
        "content": "I'll read the main.py file for you.",
        "tool_calls": [
            {
                "name": "read_file",
                "parameters": {"path": "main.py"}
            }
        ]
    }
}


@pytest.fixture
def temp_workspace():
    """Create a temporary workspace with sample files."""
    with tempfile.TemporaryDirectory() as temp_dir:
        workspace = Path(temp_dir)

        # Create sample files
        for file_path, content in SAMPLE_WORKSPACE_FILES.items():
            file_full_path = workspace / file_path
            file_full_path.parent.mkdir(parents=True, exist_ok=True)
            file_full_path.write_text(content)

        yield workspace


@pytest.fixture
def mock_websocket():
    """Mock WebSocket for testing client-server communication."""
    websocket = AsyncMock()
    websocket.send = AsyncMock()
    websocket.recv = AsyncMock()
    websocket.send_text = AsyncMock()
    websocket.receive_text = AsyncMock()
    return websocket


@pytest.fixture
def mock_ai_provider():
    """Mock AI provider for testing server responses."""
    provider = AsyncMock()

    async def mock_stream_completion(messages, **kwargs):
        """Mock streaming completion that yields test responses."""
        yield {
            "type": "content",
            "content": "I'll help you with that."
        }
        yield {
            "type": "tool_call",
            "name": "read_file",
            "parameters": {"path": "test.py"}
        }
        yield {
            "type": "complete"
        }

    provider.stream_completion = mock_stream_completion
    provider.validate_tool_call = AsyncMock(return_value=True)
    return provider


@pytest.fixture
def mock_session():
    """Mock session for server testing."""
    session = MagicMock()
    session.id = "test-session-123"
    session.messages = []
    session.config = MagicMock()
    session.config.working_directory = "/tmp/test"
    session.config.ai_provider = "test"

    async def mock_add_message(role, content):
        session.messages.append(MagicMock(role=role, content=content))

    session.add_message = AsyncMock(side_effect=mock_add_message)
    session.add_tool_result = MagicMock()
    return session


@pytest.fixture
def sample_tool_calls():
    """Sample XML tool calls for testing."""
    return SAMPLE_TOOL_CALLS


@pytest.fixture
def sample_ai_responses():
    """Sample AI responses for testing."""
    return SAMPLE_AI_RESPONSES


@pytest.fixture
def mock_security_manager():
    """Mock security manager for client testing."""
    security = MagicMock()
    security.validate_path = MagicMock(return_value="/safe/path")
    security.is_command_allowed = MagicMock(return_value=True)
    security.track_file_read = MagicMock()
    return security


@pytest.fixture
def mock_approval_manager():
    """Mock approval manager for client testing."""
    manager = AsyncMock()

    # Mock approval response
    approval_response = MagicMock()
    approval_response.decision.value = "approved"
    approval_response.feedback = "Auto-approved for testing"
    approval_response.modified_parameters = {}

    manager.request_approval = AsyncMock(return_value=approval_response)
    return manager


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# Test markers
def pytest_configure(config):
    """Configure custom pytest markers."""
    config.addinivalue_line(
        "markers", "security: mark test as security-related"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as integration test"
    )
    config.addinivalue_line(
        "markers", "unit: mark test as unit test"
    )


# Helper functions for tests
def create_mock_tool_result(status="success", data=None, error=None):
    """Create a mock tool execution result."""
    return {
        "status": status,
        "data": data,
        "error": error,
        "metadata": {
            "execution_time": 0.1,
            "timestamp": "2023-01-01T00:00:00Z"
        }
    }


def create_mock_websocket_message(msg_type, **kwargs):
    """Create a mock WebSocket message."""
    return {
        "type": msg_type,
        "timestamp": "2023-01-01T00:00:00Z",
        **kwargs
    }


# Pytest configuration
pytest_plugins = ["pytest_asyncio"]