# Gambiarra Test Suite

This directory contains the complete test suite for Gambiarra, following the testing strategy defined in [TEST-STRATEGY.md](../TEST-STRATEGY.md).

## Structure

```
tests/
├── unit/                      # Unit tests (60% of test suite)
│   ├── client/               # Client-side component tests
│   │   ├── tools/           # Individual tool implementations
│   │   ├── security/        # Security component tests (CRITICAL)
│   │   └── context/         # Context management tests
│   ├── server/              # Server-side component tests
│   │   ├── core/           # Core server logic
│   │   ├── providers/      # AI provider tests
│   │   └── tools/          # Server-side tool logic
│   └── test_llm/           # Test LLM server tests
├── integration/              # Integration tests (30% of test suite)
│   ├── client_server/      # Full communication tests
│   ├── workflows/          # Complete workflow tests
│   └── security/           # Security integration tests
├── fixtures/                 # Test data and fixtures
│   ├── ai_responses/       # Sample AI responses
│   ├── tool_calls/         # Sample XML tool calls
│   └── conversations/      # Sample conversation flows
├── conftest.py              # Shared fixtures and configuration
└── README.md               # This file
```

## Running Tests

### Quick Start

```bash
# Install test dependencies
pip install pytest pytest-asyncio pytest-cov

# Run all tests
pytest

# Or use the test runner
python run_tests.py
```

### Test Categories

```bash
# Run unit tests only (fast)
pytest tests/unit/
python run_tests.py --category unit

# Run integration tests
pytest tests/integration/
python run_tests.py --category integration

# Run security tests only (CRITICAL)
pytest -m security
python run_tests.py --category security

# Run fast tests (excludes slow-running tests)
pytest -m "not slow"
python run_tests.py --category fast
```

### With Coverage

```bash
# Generate coverage report
pytest --cov=gambiarra --cov-report=html

# Use test runner with coverage
python run_tests.py --coverage
```

## Test Markers

- `@pytest.mark.security` - Security-related tests (MUST pass)
- `@pytest.mark.slow` - Slow-running tests (may be skipped in CI)
- `@pytest.mark.integration` - Integration tests
- `@pytest.mark.unit` - Unit tests

## Security Test Requirements

Security tests are **CRITICAL** and must have 100% pass rate:

- **Path validation tests** - Prevent directory traversal attacks
- **Command filtering tests** - Block dangerous shell commands
- **XML parsing tests** - Prevent injection attacks
- **Parameter validation tests** - Ensure input sanitization

## Key Test Fixtures

Available in `conftest.py`:

- `temp_workspace` - Temporary workspace with sample files
- `mock_websocket` - Mock WebSocket for client-server tests
- `mock_ai_provider` - Mock AI provider with test responses
- `mock_security_manager` - Mock security components
- `sample_tool_calls` - XML tool call examples
- `sample_ai_responses` - AI response examples

## Writing New Tests

### Unit Test Example

```python
import pytest
from gambiarra.client.tools.file_ops import ReadFileTool

@pytest.mark.unit
class TestReadFileTool:
    def test_tool_initialization(self, mock_security_manager):
        tool = ReadFileTool(mock_security_manager)
        assert tool.name == "read_file"

    @pytest.mark.asyncio
    async def test_file_reading(self, mock_security_manager, temp_workspace):
        tool = ReadFileTool(mock_security_manager)
        # Test implementation...
```

### Security Test Example

```python
import pytest
from gambiarra.client.security.path_validator import PathValidator

@pytest.mark.security
class TestPathValidator:
    def test_directory_traversal_prevention(self, temp_workspace):
        validator = PathValidator(temp_workspace)

        with pytest.raises(ValueError, match="Path traversal detected"):
            validator.validate_path("../etc/passwd")
```

### Integration Test Example

```python
import pytest

@pytest.mark.integration
@pytest.mark.asyncio
class TestClientServerFlow:
    async def test_tool_execution_flow(self, mock_websocket):
        # Test complete client-server communication...
```

## Test Data Management

### Fixtures Location

- **AI Responses**: `fixtures/ai_responses/sample_responses.json`
- **Tool Calls**: `fixtures/tool_calls/valid_calls.xml`
- **Conversations**: `fixtures/conversations/` (for complex scenarios)

### Adding Test Data

1. Add sample data to appropriate fixture files
2. Load in tests using fixture functions
3. Keep test data realistic but minimal

## Continuous Integration

### Required Test Coverage

- **Overall**: Minimum 80%
- **Security components**: 100% (enforced)
- **Core tool parsing**: 95%
- **Client-server communication**: 90%

### CI Test Commands

```bash
# Fast CI run (excludes slow tests)
pytest tests/unit/ tests/integration/ -x --tb=short -m "not slow"

# Full CI run with coverage
pytest --cov=gambiarra --cov-fail-under=80 --cov-report=xml
```

## Troubleshooting

### Common Issues

1. **Import Errors**: Ensure Gambiarra is installed in development mode
   ```bash
   pip install -e .
   ```

2. **Async Test Failures**: Make sure to use `@pytest.mark.asyncio`

3. **Fixture Not Found**: Check `conftest.py` and ensure proper imports

4. **Path Issues**: Run tests from project root directory

### Debug Mode

```bash
# Verbose output with debug info
pytest -v -s --tb=long

# Run single test file
pytest tests/unit/client/security/test_path_validator.py -v

# Run specific test
pytest tests/unit/client/security/test_path_validator.py::TestPathValidator::test_directory_traversal_prevention -v
```

## Contributing Test Code

When adding new features to Gambiarra:

1. **Write security tests first** for any security-related code
2. **Aim for high coverage** of new functionality
3. **Use existing fixtures** and patterns
4. **Add integration tests** for complete workflows
5. **Update this README** if adding new test categories

## Test Philosophy

- **Security First**: Security tests are non-negotiable
- **Fast Feedback**: Unit tests should run quickly
- **Real Scenarios**: Integration tests should reflect actual usage
- **Comprehensive Coverage**: Test success paths, error paths, and edge cases
- **Maintainable**: Tests should be easy to understand and modify