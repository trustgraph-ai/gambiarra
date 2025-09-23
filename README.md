# Gambiarra

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Gambiarra** is an AI-powered coding assistant with a secure client-server architecture, inspired by KiloCode. It features client-side file operations for security and server-side AI orchestration for intelligent code assistance.

> **Gambiarra** is a Brazilian Portuguese term meaning "creative improvised solution" - perfect for an AI that helps you solve coding problems!

## Features

🔒 **Security-First Design**: Client-side file operations with comprehensive security validation
🤖 **AI-Powered**: Server-side AI orchestration with multiple provider support (OpenAI, TrustGraph, Test)
🔌 **Plugin System**: Dynamic tool loading and extensibility
⚡ **High Performance**: Connection pooling, request batching, and fault tolerance
🌐 **Real-time Communication**: WebSocket-based bidirectional communication
🛡️ **Fault Tolerance**: Circuit breakers and graceful degradation
📊 **Event-Driven**: Modern event-driven architecture with task management
🎯 **Tool Management**: Comprehensive tool registry with versioning and validation
🔧 **XML Tool Format**: Comprehensive XML-based tool calling system

## Quick Start

### Installation

```bash
# Install from source (development)
git clone https://github.com/gambiarra-team/gambiarra.git
cd gambiarra
pip install -e .

# Or install from PyPI (when published)
pip install gambiarra
```

### Usage

**Start the server:**
```bash
# Using entry point (recommended)
gambiarra-server

# With custom settings
gambiarra-server --host 0.0.0.0 --port 9000 --provider openai

# Using module invocation
python -m gambiarra.server

# Get help
gambiarra-server --help
```

**Start the client:**
```bash
# Using entry point (recommended)
gambiarra-client

# With custom workspace
gambiarra-client --workspace /path/to/project

# Using module invocation
python -m gambiarra.client

# Get help
gambiarra-client --help
```

**Start the test LLM (for development):**
```bash
# Using entry point (recommended)
gambiarra-test-llm

# With custom settings
gambiarra-test-llm --port 9001 --host localhost

# Using module invocation
python -m gambiarra.test_llm

# Get help
gambiarra-test-llm --help
```

## Architecture Overview

```
┌─────────────────┐    WebSocket     ┌─────────────────┐    HTTP      ┌─────────────────┐
│                 │ ◄────────────► │                 │ ◄─────────► │                 │
│  Gambiarra      │                │  Gambiarra      │             │  AI Provider    │
│  Client         │                │  Server         │             │  (OpenAI/Test)  │
│                 │                │                 │             │                 │
│ • File Ops      │                │ • AI Orchestr.  │             │ • LLM Responses │
│ • Security      │                │ • Tool Parsing  │             │ • Tool Calls    │
│ • Tool Exec     │                │ • Sessions      │             │ • Streaming     │
│ • Approvals     │                │ • WebSockets    │             │                 │
└─────────────────┘                └─────────────────┘             └─────────────────┘
```

## Features

### 🔧 Client-Side Tools

All tools execute locally on the client for security:

- **File Operations**: `read_file`, `write_to_file`, `search_files`, `list_files`
- **Code Editing**: `insert_content`, `search_and_replace`
- **Command Execution**: `execute_command` with security filtering
- **Git Operations**: `git_operation` for repository management

### 🛡️ Security Features

- **Path Validation**: Prevents directory traversal attacks
- **Command Filtering**: Whitelist/blacklist for shell commands
- **Workspace Isolation**: All operations restricted to project directory
- **User Approval**: Interactive confirmation for risky operations
- **File Backups**: Automatic backup before modifications

### 🧠 AI Integration

- **Multiple Providers**: OpenAI, Anthropic, Google (extensible)
- **Streaming Responses**: Real-time AI output with tool parsing
- **Modular Prompts**: Comprehensive prompt system with tool descriptions
- **Tool Orchestration**: XML-based tool call parsing and execution

## Configuration

### Server Configuration

Set environment variables:

```bash
export GAMBIARRA_HOST=localhost
export GAMBIARRA_PORT=8000
export GAMBIARRA_AI_PROVIDER=test  # or openai, anthropic
export GAMBIARRA_API_KEY=your-api-key
export GAMBIARRA_LOG_LEVEL=INFO
```

### Client Configuration

```bash
export GAMBIARRA_SERVER_URL=ws://localhost:8000/ws
export GAMBIARRA_WORKSPACE=/path/to/project
export GAMBIARRA_AUTO_APPROVE_READS=true
export GAMBIARRA_COMMAND_TIMEOUT=30
export GAMBIARRA_LOG_LEVEL=INFO
```

## Command Line Options

### Server Options

```bash
gambiarra-server --help
```

Available options:
- `--host HOST` - Host to bind server to (default: localhost)
- `--port PORT` - Port to bind server to (default: 8000)
- `--provider PROVIDER` - AI provider: test, openai, trustgraph (default: test)
- `--log-level LEVEL` - Logging level: DEBUG, INFO, WARNING, ERROR (default: INFO)
- `--reload` - Enable auto-reload for development

### Client Options

```bash
gambiarra-client --help
```

Available options:
- `--workspace PATH` - Workspace root directory (default: current directory)
- `--server-url URL` - Server WebSocket URL (default: ws://localhost:8000/ws)
- `--auto-approve-reads` - Auto-approve read operations
- `--command-timeout SECONDS` - Command execution timeout
- `--log-level LEVEL` - Logging level

### Test LLM Options

```bash
gambiarra-test-llm --help
```

Available options:
- `--host HOST` - Host to bind server to (default: 0.0.0.0)
- `--port PORT` - Port to bind server to (default: 8001)
- `--log-level LEVEL` - Logging level: debug, info, warning, error (default: info)
- `--reload` - Enable auto-reload for development

## Module Invocation

You can also run components using Python's module system:

```bash
# Show package information
python -m gambiarra

# Start components
python -m gambiarra.server
python -m gambiarra.client
python -m gambiarra.test_llm
```

## Usage Examples

### Basic File Operations

The AI can read, write, and search files:

```
User: "Read the main.py file and tell me what it does"
AI: I'll read the file for you.

<read_file>
<args>
<file>
<path>main.py</path>
</file>
</args>
</read_file>

[Client executes read_file tool locally]

Based on the file contents, this is a Python script that...
```

### Command Execution

Execute shell commands with security:

```
User: "Run the tests"
AI: I'll run the test suite for you.

<execute_command>
<command>python -m pytest</command>
<cwd>.</cwd>
</execute_command>

[Client shows approval prompt]
🔐 APPROVAL REQUEST
Tool: execute_command
Risk Level: high
Description: Execute execute_command tool
Parameters: {"command": "python -m pytest", "cwd": "."}

Approve? (y/n/m for modify): y

[Client executes command locally and streams output]
```

## Security Model

### Path Security

- All file paths validated against workspace root
- `.gambiarraignore` patterns respected
- No access outside project directory
- Symbolic link traversal protection

### Command Security

- Comprehensive command filtering
- Dangerous patterns blocked (e.g., `rm -rf /`)
- Whitelist of safe development commands
- User approval required for high-risk operations

### Approval Workflow

- Configurable approval policies
- Auto-approval for low-risk read operations
- Required approval for write operations and commands
- Complete audit trail of all approvals

## Development

### Project Structure

```
gambiarra/
├── TECH-SPEC.md              # Complete technical specification
├── README.md                 # This file
├── requirements.txt          # Dependencies
├── server/                   # AI orchestration server
│   ├── main.py              # FastAPI server entry point
│   ├── websocket_handler.py # WebSocket management
│   ├── ai_integration/      # AI provider integration
│   └── session/             # Session management
├── client/                   # Secure client implementation
│   ├── main.py              # Client entry point
│   ├── tools/               # Tool implementations
│   └── security/            # Security components
├── test-llm/                # OpenAI-compatible test server
│   └── main.py              # Dummy LLM for testing
└── tests/                   # Integration tests
```

### Running Tests

```bash
# Install test dependencies
pip install pytest pytest-asyncio

# Run tests
pytest tests/
```

### Adding New Tools

1. Create tool class inheriting from `BaseTool`
2. Implement `execute()` method
3. Register in `client/main.py`
4. Add to server's available tools list

### Adding New AI Providers

1. Create provider class inheriting from `AIProvider`
2. Implement `stream_completion()` method
3. Register in `server/ai_integration/providers.py`

## Troubleshooting

### Connection Issues

```bash
# Check if server is running
curl http://localhost:8000/health

# Check WebSocket connection
wscat -c ws://localhost:8000/ws
```

### Tool Execution Issues

- Verify workspace path is correct
- Check file permissions
- Review `.gambiarraignore` patterns
- Enable debug logging: `--debug`

### AI Provider Issues

- Verify API key is set
- Check network connectivity
- Try test provider first: `GAMBIARRA_AI_PROVIDER=test`

## Contributing

1. Fork the repository
2. Create feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit pull request

## License

MIT License - see LICENSE file for details.

## Acknowledgments

- Inspired by [KiloCode](https://github.com/Kilo-Org/kiloocode), Roo-Code
  and Cline.
- Built with FastAPI, WebSockets, and asyncio
- Brazilian references are deliberate 🇧🇷
