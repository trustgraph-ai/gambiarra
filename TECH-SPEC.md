# Gambiarra Technical Specification

## Executive Summary

Gambiarra has become a "sprawling mess" with fundamental architectural problems. This document proposes a comprehensive refactoring strategy inspired by KiloCode's proven architecture to address critical issues including format inconsistencies, monolithic design, and missing features.

## Current Problems

### 1. Format Inconsistencies
- **Critical Issue**: server/main.py XML parser doesn't match server/prompts/tools.py specification
- **Master Specification**: server/prompts/tools.py defines nested XML structure:
  ```xml
  <read_file>
  <args>
  <file>
  <path>src/main.py</path>
  </file>
  </args>
  </read_file>
  ```
- **Broken Implementation**: server/main.py only parses flat structure: `<path>...</path>`
- **Impact**: Tool validation failures, parameter extraction errors

### 2. Monolithic Architecture
- **server/main.py**: 800+ lines mixing WebSocket handling, AI orchestration, tool parsing, session management
- **Lack of Separation**: No clear boundaries between concerns
- **Maintainability**: Single file responsible for too many responsibilities

## Target Architecture

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

### Core Components

#### 1. Task Management System
```python
# server/core/task/manager.py
class TaskManager:
    async def create_task(self, request: TaskRequest) -> TaskResult
    async def execute_workflow(self, workflow: Workflow) -> WorkflowResult
```

#### 2. Tool Plugin System
```python
# server/core/tools/registry.py
class ToolRegistry:
    def register_tool(self, tool: Tool) -> None
    def get_tool(self, name: str) -> Tool
    def validate_tool_call(self, call: ToolCall) -> ValidationResult
```

#### 3. AI Provider Abstraction
```python
# server/core/providers/base.py
class AIProvider:
    async def generate_response(self, request: GenerationRequest) -> Response
    async def validate_tool_call(self, call: ToolCall) -> bool
```

#### 4. Event System
```python
# server/core/events/bus.py
class EventBus:
    def subscribe(self, event_type: str, handler: Callable) -> None
    async def publish(self, event: Event) -> None
```

## Three-Phase Refactoring Strategy

### Phase 1: Foundation (Week 1-2)
**Goal**: Extract core services from monolithic server/main.py

1. **Create Core Directory Structure**
   ```
   server/
   ├── core/
   │   ├── tools/
   │   │   ├── registry.py
   │   │   ├── parser.py     # Fix XML parsing to match specification
   │   │   └── validator.py
   │   ├── providers/
   │   │   ├── base.py
   │   │   ├── openai.py
   │   │   └── trustgraph.py
   │   ├── session/
   │   │   ├── manager.py    # Already exists
   │   │   └── context.py
   │   └── events/
   │       └── bus.py
   ```

2. **Extract Tool Management**
   - Move XML parsing logic to `server/core/tools/parser.py`
   - Fix parser to match master specification in server/prompts/tools.py
   - Create tool registry for dynamic tool loading
   - Implement validation to prevent format drift

3. **Extract Provider Management**
   - Move AI provider logic to separate modules
   - Implement provider interface for extensibility

**Acceptance Criteria**:
- ✅ XML parser matches master specification
- ✅ Tool calls execute successfully
- ✅ Provider switching works
- ✅ Format drift prevention in place

### Phase 2: Workflow Engine (Week 3-4)
**Goal**: Implement task-centric workflow system

1. **Task Management System**
   ```python
   # server/core/task/
   ├── manager.py      # Task orchestration
   ├── workflow.py     # Workflow definitions
   ├── executor.py     # Task execution engine
   └── state.py        # Task state management
   ```

2. **Event-Driven Architecture**
   - Implement event bus for component communication
   - Add event handlers for task lifecycle
   - Enable async task processing

3. **Context Management**
   - Rich conversation context tracking
   - File dependency analysis
   - Memory optimization strategies

**Acceptance Criteria**:
- ✅ Tasks can be created and executed
- ✅ Workflow engine handles complex multi-step operations
- ✅ Events properly propagate between components
- ✅ Context management prevents stale data issues

### Phase 3: Advanced Features (Week 5-6)
**Goal**: Implement missing features

1. **Plugin System**
   - Dynamic tool loading
   - Tool versioning and compatibility
   - Custom tool development framework

2. **Advanced Error Recovery**
   - Circuit breaker patterns
   - Automatic retry strategies
   - Degraded mode operation

3. **Performance Optimization**
   - Connection pooling
   - Request batching
   - Caching strategies

**Acceptance Criteria**:
- ✅ Custom tools can be added without code changes
- ✅ System gracefully handles failures
- ✅ Performance matches or exceeds current implementation

## Success Metrics

1. **Functional**
   - ✅ All existing functionality preserved
   - ✅ XML parser matches specification
   - ✅ No tool execution failures

2. **Architectural**
   - ✅ Clear separation of concerns
   - ✅ Modular, testable components
   - ✅ Extensible plugin architecture

3. **Operational**
   - ✅ Improved error handling and recovery
   - ✅ Better logging and monitoring
   - ✅ Easier deployment and maintenance

