# Testing Strategy for Gambiarra

## Overview

This document outlines the testing strategy for Gambiarra, an AI-powered coding assistant with a secure client-server architecture. The approach focuses on comprehensive testing across all components while maintaining fast execution and reliable results.

## 1. Test Framework: pytest + pytest-asyncio

- **pytest**: Python testing framework with excellent fixture support
- **pytest-asyncio**: Essential for testing async WebSocket and AI provider operations
- **pytest-mock**: For mocking external services and dependencies
- **websockets**: For testing WebSocket client-server communication

## 2. Architecture-Specific Testing

### Client-Side Testing
- **Security Components**: Path validation, command filtering, approval workflows
- **Tool Execution**: File operations, command execution with mocking
- **WebSocket Communication**: Connection handling, message parsing
- **Context Management**: Conversation memory, file context tracking

### Server-Side Testing
- **AI Provider Integration**: OpenAI, TrustGraph, test provider responses
- **Tool Orchestration**: XML parsing, parameter validation, tool registry
- **Session Management**: Session lifecycle, timeout handling
- **WebSocket Handling**: Message routing, streaming responses

### Integration Testing
- **End-to-End Tool Execution**: Full client-server-AI workflow
- **Security Policies**: Approval workflows, command filtering
- **Error Recovery**: Network failures, AI provider errors, tool failures

## 3. Test Categories

### Unit Tests (60%)
- **Tool implementations** - Individual tool logic and parameter validation
- **Security validators** - Path validation, command filtering
- **AI provider adapters** - Request/response formatting, error handling
- **XML parsing** - Tool call parsing and parameter extraction
- **Session management** - Session lifecycle and state management

### Integration Tests (30%)
- **Client-Server communication** - Full WebSocket message flows
- **Tool execution workflows** - Complete tool approval and execution cycles
- **AI conversation flows** - Multi-turn conversations with tool usage
- **Error handling** - Network errors, timeouts, AI failures

### End-to-End Tests (10%)
- **Complete workflows** - User message → AI response → tool execution → result
- **Security scenarios** - Approval workflows, denied operations
- **Real AI provider integration** - Testing with actual AI services (optional)

## 4. Mock Strategy

### What to Mock
- ✅ **AI Provider APIs** - OpenAI, TrustGraph responses
- ✅ **File System Operations** - For security and speed
- ✅ **Network Calls** - External API calls
- ✅ **System Commands** - Shell command execution
- ✅ **WebSocket Connections** - For unit testing

### What NOT to Mock
- ❌ **Core Business Logic** - Tool parsing, validation logic
- ❌ **Internal Data Structures** - Sessions, messages, parameters
- ❌ **Configuration Management** - Config loading and validation
- ❌ **Event System** - Internal message passing

## 5. Test Structure

```
tests/
├── unit/
│   ├── client/
│   │   ├── tools/              # Individual tool tests
│   │   ├── security/           # Security component tests
│   │   └── context/            # Context management tests
│   ├── server/
│   │   ├── core/               # Core server logic tests
│   │   ├── providers/          # AI provider tests
│   │   └── tools/              # Server-side tool tests
│   └── test_llm/               # Test LLM server tests
├── integration/
│   ├── client_server/          # Full communication tests
│   ├── workflows/              # Complete workflow tests
│   └── security/               # Security integration tests
├── fixtures/
│   ├── ai_responses/           # Sample AI responses
│   ├── tool_calls/             # Sample XML tool calls
│   └── conversations/          # Sample conversation flows
└── conftest.py                 # Shared fixtures and configuration
```

## 6. Key Testing Scenarios

### Security Testing
- **Path Traversal Prevention** - Attempts to access files outside workspace
- **Command Injection Prevention** - Malicious command patterns
- **Approval Workflow** - User approval required for risky operations
- **Ignore Patterns** - `.gambiarraignore` file processing

### Tool System Testing
- **XML Parsing** - Valid and invalid tool call formats
- **Parameter Validation** - Required/optional parameters, type checking
- **Nested Arguments** - Complex parameter structures
- **Error Handling** - Malformed XML, missing parameters

### AI Integration Testing
- **Provider Switching** - OpenAI, TrustGraph, test provider
- **Streaming Responses** - Real-time AI response handling
- **Tool Call Generation** - AI generates valid XML tool calls
- **Conversation Context** - Multi-turn conversations with context

### WebSocket Communication Testing
- **Connection Management** - Connect, disconnect, reconnect scenarios
- **Message Types** - All message types handled correctly
- **Error Recovery** - Network failures, timeout handling
- **Concurrent Sessions** - Multiple client sessions

## 7. Test Data Management

### Fixtures and Sample Data
- **AI Response Fixtures** - Realistic AI responses with tool calls
- **Tool Call Examples** - Valid and invalid XML examples
- **File System Mocks** - Realistic directory structures
- **Configuration Samples** - Various configuration scenarios

### Test Databases
- **Session Storage** - In-memory session management for tests
- **Conversation History** - Sample conversation flows
- **Tool Registry** - Test tool configurations

## 8. Mocking Patterns

### AI Provider Mocking
```python
@pytest.fixture
def mock_openai_provider():
    with patch('gambiarra.server.core.providers.openai.OpenAIProvider') as mock:
        mock.stream_completion.return_value = mock_ai_response()
        yield mock
```

### WebSocket Mocking
```python
@pytest.fixture
def mock_websocket():
    websocket = AsyncMock()
    websocket.send_text = AsyncMock()
    websocket.receive_text = AsyncMock()
    return websocket
```

### File System Mocking
```python
@pytest.fixture
def mock_filesystem(tmp_path):
    # Create temporary workspace structure
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return workspace
```

## 9. Running Tests

### Local Development
```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=gambiarra --cov-report=html

# Run specific test categories
pytest tests/unit/
pytest tests/integration/

# Run with specific markers
pytest -m "not slow"
pytest -m "security"
```

### Continuous Integration
```bash
# Fast test suite for CI
pytest tests/unit/ tests/integration/ -x --tb=short

# Full test suite with coverage
pytest --cov=gambiarra --cov-fail-under=80 --cov-report=xml
```

## 10. Performance Testing

### Load Testing
- **Concurrent Sessions** - Multiple clients simultaneously
- **Tool Execution Volume** - High-frequency tool calls
- **Memory Usage** - Long-running sessions with context

### Benchmark Testing
- **Tool Execution Speed** - Individual tool performance
- **XML Parsing Performance** - Large/complex tool calls
- **WebSocket Throughput** - Message processing rates

## 11. Test Quality Guidelines

### Test Isolation
- Each test should be completely independent
- Use fixtures for common setup and teardown
- No shared state between tests
- Deterministic test execution order

### Error Testing
- Test both success and failure paths
- Verify proper error messages and codes
- Test timeout and retry scenarios
- Validate error recovery mechanisms

### Async Testing
- Use `@pytest.mark.asyncio` for async tests
- Properly mock async dependencies
- Test concurrent operations safely
- Handle async context managers correctly

## 12. Security Test Requirements

### Mandatory Security Tests
- **Path validation** must prevent directory traversal
- **Command filtering** must block dangerous commands
- **Parameter validation** must prevent injection attacks
- **Approval workflows** must require user confirmation

### Security Test Coverage
- All security components must have 100% test coverage
- Security tests must include negative test cases
- Security boundary conditions must be thoroughly tested

## 13. AI Provider Test Strategy

### Test Provider Implementation
- Use built-in test LLM for deterministic responses
- Mock realistic AI responses for unit tests
- Test provider failover and error handling
- Validate tool call generation accuracy

### Provider-Specific Testing
- **OpenAI Provider** - API format, rate limiting, errors
- **TrustGraph Provider** - Custom flow handling
- **Test Provider** - Deterministic responses for testing

## Conclusion

This testing strategy ensures comprehensive coverage of Gambiarra's security-first architecture while maintaining fast execution times. The emphasis on security testing, AI integration, and client-server communication reflects the unique challenges of an AI coding assistant with distributed execution.