# Gambiarra Technical Specification

## Overview

Gambiarra is an AI-powered coding assistant with a secure client-server architecture. It features client-side file operations for security and server-side AI orchestration for intelligent code assistance using XML-based tool calling.

## Architecture

### System Architecture
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

### Layered Architecture
```
┌─────────────────────────────────────────┐
│             API Layer                   │  WebSocket handlers, HTTP endpoints
├─────────────────────────────────────────┤
│          Business Logic Layer           │  Task orchestration, workflow engine
├─────────────────────────────────────────┤
│           Service Layer                 │  AI providers, tool execution, sessions
├─────────────────────────────────────────┤
│          Infrastructure Layer           │  Database, file system, networking
└─────────────────────────────────────────┘
```

## Core Components

### 1. Client-Side Security Architecture

**Path Validation**: All file operations are validated against workspace boundaries using comprehensive path security checks.

**Command Filtering**: Shell commands are filtered through configurable whitelists and blacklists for security.

**User Approval System**: Interactive confirmation system for potentially risky operations with risk-level classification.

**File Context Tracking**: Intelligent tracking of file modifications and dependencies for context-aware operations.

### 2. Server-Side AI Orchestration

**Session Management**: Persistent sessions with configurable timeouts and state management.

**AI Provider Abstraction**: Pluggable AI provider system supporting OpenAI, TrustGraph, and custom implementations.

**Tool Registry**: Dynamic tool loading and validation system with comprehensive parameter checking.

**Event-Driven Architecture**: Async message dispatch and component communication through event bus.

### 3. Tool System

#### XML-Based Tool Format
All tools use structured XML format for consistent parsing and validation:

```xml
<tool_name>
<args>
<parameter>value</parameter>
<nested_parameter>
<sub_parameter>nested_value</sub_parameter>
</nested_parameter>
</args>
</tool_name>
```

#### Available Tools

**File Operations**:
- `read_file` - Read file contents with optional line ranges
- `write_to_file` - Create or overwrite files with content validation
- `list_files` - Directory listing with recursive options
- `search_files` - Pattern-based file search with regex support

**Code Operations**:
- `search_and_replace` - Find and replace text in files
- `insert_content` - Insert content at specific line numbers
- `list_code_definition_names` - Extract function/class definitions

**System Operations**:
- `execute_command` - Secure shell command execution
- `attempt_completion` - Task completion signaling
- `ask_followup_question` - Interactive user queries
- `update_todo_list` - Task progress tracking

## Security Model

### Client-Side Security

**Workspace Isolation**: All operations restricted to designated project directory with no external access.

**Path Traversal Protection**: Comprehensive validation prevents directory traversal attacks and symlink exploitation.

**Ignore Patterns**: Support for `.gambiarraignore` files to exclude sensitive files from operations.

**Command Security**: Multi-layer command filtering with dangerous pattern detection and user confirmation.

### Server-Side Security

**Parameter Validation**: All tool parameters validated against strict schemas before execution.

**Format Consistency**: XML format validation prevents parser drift and ensures reliable tool execution.

**Session Security**: Secure session management with timeout handling and proper cleanup.

## Data Flow

### 1. Tool Execution Flow
1. AI generates XML tool call following specification
2. Server parses and validates XML structure
3. Server wraps parameters in nested format for client
4. Client validates parameters and requests user approval if needed
5. Client unwraps parameters and executes tool locally
6. Results sent back through WebSocket for AI processing

### 2. Message Flow
1. User sends message to client
2. Client establishes WebSocket connection to server
3. Server processes message with AI provider
4. AI generates response with tool calls
5. Tool calls executed on client with approval workflow
6. Results aggregated and presented to user

## Configuration

### Server Configuration
- Host/port binding with IPv4/IPv6 support
- AI provider selection (test, OpenAI, TrustGraph)
- Session management parameters
- Logging and monitoring configuration
- CORS and security settings

### Client Configuration
- Server connection settings
- Workspace directory configuration
- Auto-approval policies for trusted operations
- Command timeout settings
- Security policy configuration

## Extensibility

### Plugin Architecture
- Dynamic tool loading through registry system
- Tool versioning and compatibility checking
- Custom tool development framework
- Event-driven plugin communication

### AI Provider Integration
- Abstract provider interface for consistent integration
- Streaming response support
- Tool call validation and formatting
- Error handling and retry strategies

### Event System
- Pub/sub event architecture for component decoupling
- Task lifecycle events
- Error and recovery events
- Performance monitoring events

## Performance Characteristics

### Scalability
- Connection pooling for multiple concurrent sessions
- Request batching for efficiency
- Memory-optimized conversation context management
- Configurable session limits and cleanup

### Reliability
- Circuit breaker patterns for fault tolerance
- Automatic retry with exponential backoff
- Graceful degradation during failures
- Comprehensive error recovery mechanisms

### Monitoring
- Structured logging with configurable levels
- Performance metrics and timing
- Error tracking and analysis
- Resource usage monitoring

## Development and Deployment

### Package Structure
```
gambiarra/
├── server/              # AI orchestration server
│   ├── main.py         # FastAPI server entry point
│   ├── core/           # Core business logic
│   ├── prompts/        # System prompts and tool specifications
│   └── tools/          # Tool management and filtering
├── client/             # Secure client implementation
│   ├── main.py        # Client entry point
│   ├── tools/         # Tool implementations
│   └── security/      # Security components
└── test_llm/          # Development test server
    └── main.py        # Mock LLM for testing
```

### Entry Points
- `gambiarra-server` - Start AI orchestration server
- `gambiarra-client` - Start secure client
- `gambiarra-test-llm` - Start development test LLM
- Module invocation: `python -m gambiarra.{component}`

### Dependencies
- **Server**: FastAPI, WebSockets, asyncio, aiofiles
- **Client**: WebSocket client, aiofiles, security libraries
- **Test LLM**: FastAPI, streaming response handling
- **Common**: Pydantic for validation, structured logging