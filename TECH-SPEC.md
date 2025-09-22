# Gambiarra Technical Specification

## Overview

Gambiarra is a Python-based implementation of a headless AI coding assistant inspired by KiloCode. It provides a client-server architecture where all file operations are performed client-side for security, while the server handles AI orchestration and tool coordination.

**Name Origin**: "Gambiarra" is a Brazilian Portuguese term referring to creative, improvised solutions - fitting for an AI coding assistant that helps developers solve complex problems.

## Architecture Components

### 1. Server (`gambiarra/server/`)
- **WebSocket Server**: Real-time bidirectional communication
- **AI Provider Integration**: OpenAI, Anthropic, Google, etc.
- **Prompt System**: KiloCode-compatible prompt generation
- **Tool Orchestration**: XML-based tool call parsing and workflow management
- **Session Management**: Multi-user concurrent sessions

### 2. Client (`gambiarra/client/`)
- **File Operations**: Secure local file system access
- **Command Execution**: Sandboxed shell command execution
- **Tool Implementation**: All KiloCode tools implemented client-side
- **Security Manager**: Path validation, command filtering, approval workflows
- **WebSocket Client**: Real-time server communication

### 3. Test LLM (`gambiarra/test-llm/`)
- **OpenAI API Mock**: Compatible dummy server for testing
- **Predictable Responses**: Deterministic outputs for validation
- **Tool Call Simulation**: XML-based tool invocation testing

## Core Features

### Tool System (Client-Side)
Based on KiloCode's 25+ tools, implemented securely on client:

#### File Operations
- `read_file`: Read file contents with optional line ranges
- `write_to_file`: Create/overwrite files with backup support
- `search_files`: Regex search across multiple files
- `list_files`: Directory listing with recursive support
- `insert_content`: Add content at specific line positions
- `search_and_replace`: Find/replace with regex support

#### Code Analysis
- `list_code_definition_names`: Extract function/class definitions
- `codebase_search`: Semantic search across entire codebase

#### System Operations
- `execute_command`: Secure shell command execution
- `git_operations`: Repository management commands

#### Workflow Management
- `attempt_completion`: Signal task completion
- `ask_followup_question`: Request user clarification
- `update_todo_list`: Task tracking and progress management

### AI Integration (Server-Side)
- **Prompt Generation**: KiloCode-compatible system prompts
- **Streaming Responses**: Real-time AI output with tool parsing
- **Provider Abstraction**: Multiple LLM provider support
- **Context Management**: Conversation history and token optimization

### Security Architecture
- **Path Validation**: Prevent directory traversal attacks
- **Command Filtering**: Whitelist/blacklist for shell commands
- **User Approval**: Interactive tool execution approval
- **Workspace Isolation**: Operations restricted to project directory

## Technology Stack

### Server Dependencies
```python
# Core server
fastapi>=0.104.0          # Modern async web framework
websockets>=12.0          # WebSocket support
uvicorn>=0.24.0           # ASGI server

# AI Integration
openai>=1.0.0            # OpenAI API client
anthropic>=0.7.0         # Anthropic API client
google-generativeai>=0.3.0  # Google AI client

# Utilities
pydantic>=2.5.0          # Data validation
aiofiles>=23.2.1         # Async file operations
python-dotenv>=1.0.0     # Environment variable management
```

### Client Dependencies
```python
# Core client
websockets>=12.0          # WebSocket communication
asyncio                   # Async operations
pathlib                   # Path manipulation

# File Operations
aiofiles>=23.2.1         # Async file I/O
watchdog>=3.0.0          # File system monitoring
gitpython>=3.1.40        # Git operations

# Security
fnmatch                   # Pattern matching for .kilocodeignore
subprocess               # Secure command execution

# Code Analysis
tree-sitter>=0.20.0     # Syntax tree parsing
tree-sitter-python       # Python language support
tree-sitter-javascript   # JavaScript language support
tree-sitter-typescript   # TypeScript language support
```

### Test LLM Dependencies
```python
# Mock server
fastapi>=0.104.0         # API framework
uvicorn>=0.24.0          # Server runtime
```

## Message Protocol

### WebSocket Communication

#### Connection Handshake
```json
{
  "type": "connect",
  "protocol_version": "1.0",
  "client_info": {
    "platform": "python",
    "version": "1.0.0",
    "capabilities": ["file_operations", "command_execution"]
  }
}
```

#### Tool Approval Request
```json
{
  "type": "tool_approval_request",
  "request_id": "uuid",
  "tool": {
    "name": "write_to_file",
    "parameters": {
      "path": "src/main.py",
      "content": "print('hello world')"
    },
    "description": "Create a simple Python hello world script",
    "risk_level": "medium",
    "requires_approval": true
  }
}
```

#### Tool Execution
```json
{
  "type": "execute_tool",
  "execution_id": "uuid",
  "tool": {
    "name": "read_file",
    "parameters": {
      "path": "src/config.py",
      "line_range": [1, 50]
    }
  }
}
```

#### Tool Result
```json
{
  "type": "tool_result",
  "execution_id": "uuid",
  "result": {
    "status": "success",
    "data": "# Configuration file\nDEBUG = True\n...",
    "metadata": {
      "file_size": 1024,
      "line_count": 45,
      "read_lines": "1-50"
    }
  }
}
```

## Implementation Plan

### Phase 1: Core Infrastructure
1. **Test LLM Server**: OpenAI-compatible mock for development
2. **Basic WebSocket Server**: Connection handling and message routing
3. **Simple Client**: File read/write operations
4. **Integration Test**: End-to-end tool execution

### Phase 2: Tool Implementation
1. **File Operations**: Complete set of file manipulation tools
2. **Command Execution**: Secure shell command support
3. **Security Manager**: Path validation and command filtering
4. **Approval System**: Interactive user confirmation

### Phase 3: AI Integration
1. **Prompt System**: KiloCode-compatible prompt generation
2. **Tool Parsing**: XML tool call extraction from AI responses
3. **Multiple Providers**: OpenAI, Anthropic, Google support
4. **Streaming**: Real-time response processing

### Phase 4: Advanced Features
1. **Code Analysis**: AST parsing and semantic search
2. **Git Integration**: Repository operations
3. **Context Management**: Smart file inclusion
4. **Performance Optimization**: Concurrent operations

### Phase 5: Production Ready
1. **Error Handling**: Comprehensive error recovery
2. **Logging**: Detailed operation tracking
3. **Configuration**: Flexible deployment options
4. **Documentation**: User and developer guides

## Directory Structure

```
gambiarra/
├── TECH-SPEC.md              # This document
├── README.md                 # User guide and setup
├── requirements.txt          # Combined dependencies
├── server/
│   ├── __init__.py
│   ├── main.py              # FastAPI server entry point
│   ├── websocket_handler.py # WebSocket connection management
│   ├── ai_integration/
│   │   ├── __init__.py
│   │   ├── providers.py     # LLM provider implementations
│   │   ├── prompts.py       # KiloCode prompt system
│   │   └── tool_parser.py   # XML tool call parsing
│   ├── session/
│   │   ├── __init__.py
│   │   ├── manager.py       # Session state management
│   │   └── conversation.py  # Message history handling
│   └── config.py            # Server configuration
├── client/
│   ├── __init__.py
│   ├── main.py              # Client entry point
│   ├── websocket_client.py  # Server communication
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── base.py          # Tool interface
│   │   ├── file_ops.py      # File operation tools
│   │   ├── command_ops.py   # Command execution tools
│   │   └── code_analysis.py # Code analysis tools
│   ├── security/
│   │   ├── __init__.py
│   │   ├── path_validator.py # Path traversal protection
│   │   ├── command_filter.py # Command security
│   │   └── approval_manager.py # User approval workflows
│   └── config.py            # Client configuration
├── test-llm/
│   ├── __init__.py
│   ├── main.py              # OpenAI mock server
│   ├── responses.py         # Predefined test responses
│   └── tool_responses.py    # Tool call simulation
└── tests/
    ├── test_integration.py   # End-to-end tests
    ├── test_server.py        # Server unit tests
    ├── test_client.py        # Client unit tests
    └── test_tools.py         # Tool implementation tests
```

## Security Considerations

### Client-Side Security
- **Workspace Containment**: All operations restricted to project directory
- **Path Traversal Protection**: Absolute path validation
- **Command Filtering**: Dangerous command detection and blocking
- **User Approval**: Interactive confirmation for risky operations
- **File Backup**: Automatic backup creation before modifications

### Server-Side Security
- **No File Access**: Server never touches local file system
- **Session Isolation**: Each client session completely isolated
- **API Key Management**: Secure credential handling
- **Rate Limiting**: Prevent abuse of AI providers
- **Input Validation**: All messages validated against schemas

### Communication Security
- **WebSocket Encryption**: TLS/SSL for production deployments
- **Message Validation**: JSON schema validation
- **Authentication**: Token-based client authentication
- **Audit Logging**: Complete operation history

## Configuration

### Server Configuration
```python
# server/config.py
class ServerConfig:
    host: str = "localhost"
    port: int = 8000
    ai_provider: str = "openai"  # openai, anthropic, google
    api_key: str = None
    max_sessions: int = 100
    session_timeout: int = 3600
    log_level: str = "INFO"
```

### Client Configuration
```python
# client/config.py
class ClientConfig:
    server_url: str = "ws://localhost:8000/ws"
    workspace_root: str = "."
    auto_approve_reads: bool = True
    command_timeout: int = 30
    max_file_size: int = 10_000_000  # 10MB
    backup_enabled: bool = True
```

## Error Handling Strategy

### Client Errors
- **File Not Found**: Suggest similar files, offer to create
- **Permission Denied**: Clear explanation, suggest fixes
- **Command Failed**: Show error output, suggest alternatives
- **Path Traversal**: Block with security warning

### Server Errors
- **AI Provider Error**: Automatic retry with exponential backoff
- **Rate Limiting**: Queue requests, inform user of delays
- **Network Error**: Graceful degradation, offline mode
- **Session Timeout**: Automatic reconnection with state recovery

### Recovery Mechanisms
- **Automatic Retry**: Transient failures with backoff
- **Graceful Degradation**: Core functionality when AI unavailable
- **State Persistence**: Session recovery after disconnection
- **Backup Restoration**: Undo operations when things go wrong

## Testing Strategy

### Unit Tests
- **Tool Functions**: Each tool tested in isolation
- **Security Components**: Path validation, command filtering
- **Message Parsing**: Protocol message validation
- **AI Integration**: Mock provider responses

### Integration Tests
- **End-to-End**: Client → Server → Mock LLM → Client
- **Tool Workflows**: Multi-step tool execution chains
- **Error Scenarios**: Network failures, permission errors
- **Security**: Attempted attacks and boundary conditions

### Performance Tests
- **Concurrent Sessions**: Multiple client connections
- **Large Files**: Memory usage and streaming
- **Command Execution**: Long-running operations
- **WebSocket Load**: Message throughput and latency

This specification provides the foundation for building Gambiarra as a production-ready, secure, and scalable AI coding assistant that preserves the power of KiloCode while enabling flexible deployment scenarios.