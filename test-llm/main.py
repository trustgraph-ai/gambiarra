#!/usr/bin/env python3
"""
OpenAI-compatible dummy server for testing Gambiarra.
Provides predictable responses with tool call support.
"""

import asyncio
import json
import time
import uuid
from typing import Dict, List, Any, Optional, AsyncIterable
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import uvicorn

app = FastAPI(title="Gambiarra Test LLM", version="1.0.0")

# OpenAI API Models
class Message(BaseModel):
    role: str
    content: str

class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[Message]
    stream: bool = False
    temperature: float = 0.1
    max_tokens: Optional[int] = None

class Usage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

class Choice(BaseModel):
    index: int
    message: Message
    finish_reason: str

class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[Choice]
    usage: Usage

class ChunkChoice(BaseModel):
    index: int
    delta: Dict[str, Any]
    finish_reason: Optional[str] = None

class ChatCompletionChunk(BaseModel):
    id: str
    object: str = "chat.completion.chunk"
    created: int
    model: str
    choices: List[ChunkChoice]

# Predefined responses for testing different scenarios
TEST_RESPONSES = {
    "hello": {
        "response": "Hello! I'm Gambiarra, your AI coding assistant. I can help you with file operations, code analysis, and development tasks. What would you like to work on?",
        "tools": []
    },

    "read_file": {
        "response": "I'll read the file for you. Let me use the read_file tool to examine its contents.",
        "tools": [
            {
                "name": "read_file",
                "parameters": {"path": "src/main.py"}
            }
        ]
    },

    "write_file": {
        "response": "I'll create that file for you. Let me use the write_to_file tool to write the content.",
        "tools": [
            {
                "name": "write_to_file",
                "parameters": {
                    "path": "hello.py",
                    "content": "print('Hello, World!')\n",
                    "line_count": 1
                }
            }
        ]
    },

    "search_files": {
        "response": "I'll search for that pattern across your files using the search_files tool.",
        "tools": [
            {
                "name": "search_files",
                "parameters": {
                    "path": "src",
                    "regex": "function.*export",
                    "file_pattern": "*.py"
                }
            }
        ]
    },

    "execute_command": {
        "response": "I'll run that command for you. Let me use the execute_command tool.",
        "tools": [
            {
                "name": "execute_command",
                "parameters": {
                    "command": "python --version",
                    "cwd": "."
                }
            }
        ]
    },

    "complex_task": {
        "response": "I'll help you implement this feature. Let me start by reading the existing code and then make the necessary changes.",
        "tools": [
            {
                "name": "read_file",
                "parameters": {"path": "src/app.py"}
            },
            {
                "name": "search_files",
                "parameters": {
                    "path": "src",
                    "regex": "class.*App",
                    "file_pattern": "*.py"
                }
            }
        ]
    }
}

def detect_intent(messages: List[Message]) -> str:
    """Detect user intent from message history to return appropriate test response."""
    if not messages:
        return "hello"

    last_message = messages[-1].content.lower()

    if any(word in last_message for word in ["hello", "hi", "start"]):
        return "hello"
    elif any(word in last_message for word in ["read", "show", "display", "content"]):
        return "read_file"
    elif any(word in last_message for word in ["write", "create", "make", "new file"]):
        return "write_file"
    elif any(word in last_message for word in ["search", "find", "grep", "look for"]):
        return "search_files"
    elif any(word in last_message for word in ["run", "execute", "command", "shell"]):
        return "execute_command"
    elif any(word in last_message for word in ["implement", "feature", "complex", "multiple"]):
        return "complex_task"
    else:
        return "hello"

def generate_tool_calls(tools: List[Dict[str, Any]]) -> str:
    """Generate XML tool calls in KiloCode format."""
    if not tools:
        return ""

    tool_calls = []
    for tool in tools:
        name = tool["name"]
        params = tool["parameters"]

        if name == "read_file":
            xml = f"<read_file>\n<args>\n<file>\n<path>{params['path']}</path>\n</file>\n</args>\n</read_file>"
        elif name == "write_to_file":
            xml = f"<write_to_file>\n<path>{params['path']}</path>\n<content>{params['content']}</content>\n<line_count>{params['line_count']}</line_count>\n</write_to_file>"
        elif name == "search_files":
            xml = f"<search_files>\n<path>{params['path']}</path>\n<regex>{params['regex']}</regex>\n<file_pattern>{params['file_pattern']}</file_pattern>\n</search_files>"
        elif name == "execute_command":
            xml = f"<execute_command>\n<command>{params['command']}</command>\n<cwd>{params['cwd']}</cwd>\n</execute_command>"
        else:
            xml = f"<{name}>\n"
            for key, value in params.items():
                xml += f"<{key}>{value}</{key}>\n"
            xml += f"</{name}>"

        tool_calls.append(xml)

    return "\n\n" + "\n\n".join(tool_calls)

def create_response_content(intent: str) -> str:
    """Create complete response content with tool calls."""
    template = TEST_RESPONSES.get(intent, TEST_RESPONSES["hello"])
    response = template["response"]

    if template["tools"]:
        tool_calls = generate_tool_calls(template["tools"])
        response += tool_calls

    return response

async def stream_response(content: str, model: str) -> AsyncIterable[str]:
    """Stream response content chunk by chunk."""
    completion_id = f"chatcmpl-{uuid.uuid4().hex[:8]}"
    created = int(time.time())

    # Split content into words for realistic streaming
    words = content.split()

    for i, word in enumerate(words):
        chunk = ChatCompletionChunk(
            id=completion_id,
            created=created,
            model=model,
            choices=[ChunkChoice(
                index=0,
                delta={"content": word + " " if i < len(words) - 1 else word},
                finish_reason=None
            )]
        )

        yield f"data: {chunk.model_dump_json()}\n\n"
        await asyncio.sleep(0.05)  # Simulate realistic typing speed

    # Send final chunk
    final_chunk = ChatCompletionChunk(
        id=completion_id,
        created=created,
        model=model,
        choices=[ChunkChoice(
            index=0,
            delta={},
            finish_reason="stop"
        )]
    )

    yield f"data: {final_chunk.model_dump_json()}\n\n"
    yield "data: [DONE]\n\n"

@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "ok", "service": "Gambiarra Test LLM", "version": "1.0.0"}

@app.get("/v1/models")
async def list_models():
    """List available models (OpenAI API compatibility)."""
    return {
        "object": "list",
        "data": [
            {
                "id": "gpt-4",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "gambiarra-test"
            },
            {
                "id": "gpt-3.5-turbo",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "gambiarra-test"
            }
        ]
    }

@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    """Handle chat completions (OpenAI API compatibility)."""

    # Detect intent and generate response
    intent = detect_intent(request.messages)
    content = create_response_content(intent)

    print(f"[TEST-LLM] Intent: {intent}")
    print(f"[TEST-LLM] Response length: {len(content)} chars")

    if request.stream:
        # Return streaming response
        return StreamingResponse(
            stream_response(content, request.model),
            media_type="text/plain",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
        )
    else:
        # Return complete response
        completion_id = f"chatcmpl-{uuid.uuid4().hex[:8]}"

        response = ChatCompletionResponse(
            id=completion_id,
            created=int(time.time()),
            model=request.model,
            choices=[Choice(
                index=0,
                message=Message(role="assistant", content=content),
                finish_reason="stop"
            )],
            usage=Usage(
                prompt_tokens=sum(len(msg.content.split()) for msg in request.messages),
                completion_tokens=len(content.split()),
                total_tokens=sum(len(msg.content.split()) for msg in request.messages) + len(content.split())
            )
        )

        return response

@app.get("/health")
async def health_check():
    """Detailed health check for monitoring."""
    return {
        "status": "healthy",
        "timestamp": int(time.time()),
        "service": "gambiarra-test-llm",
        "endpoints": {
            "chat_completions": "/v1/chat/completions",
            "models": "/v1/models"
        },
        "features": {
            "streaming": True,
            "tool_calls": True,
            "multiple_intents": True
        }
    }

if __name__ == "__main__":
    print("🧠 Starting Gambiarra Test LLM Server...")
    print("📍 OpenAI API compatible endpoint: http://localhost:8001")
    print("🔧 Use this as your AI provider for testing Gambiarra")
    print("📖 Supported intents: hello, read_file, write_file, search_files, execute_command, complex_task")

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8001,
        log_level="info"
    )