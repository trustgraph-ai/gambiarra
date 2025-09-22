#!/usr/bin/env python3
"""
Gambiarra Server - Main FastAPI application with WebSocket support.
Handles AI orchestration and tool coordination for secure coding assistance.
"""

import asyncio
import json
import logging
import uuid
import time
from contextlib import asynccontextmanager
from typing import Dict, Any
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from server.websocket_handler import WebSocketManager
from server.ai_integration.providers import AIProviderManager
from server.session.manager import SessionManager
from server.config import ServerConfig

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global config and managers
config = ServerConfig()
websocket_manager = WebSocketManager()
session_manager = SessionManager()
ai_provider_manager = AIProviderManager(default_provider=config.ai_provider)

# Store pending tool requests
pending_tool_requests = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    logger.info("🚀 Starting Gambiarra Server...")

    # Initialize AI providers with configuration
    await ai_provider_manager.initialize(
        openai_api_key=config.openai_api_key,
        trustgraph_url=config.trustgraph_url,
        trustgraph_flow=config.trustgraph_flow
    )
    logger.info("✅ AI providers initialized")

    yield

    # Cleanup
    logger.info("🛑 Shutting down Gambiarra Server...")
    await websocket_manager.disconnect_all()
    await session_manager.cleanup_all()
    logger.info("✅ Cleanup completed")

# Create FastAPI app
app = FastAPI(
    title="Gambiarra Server",
    description="AI-powered coding assistant with client-side file operations",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    """Health check and service information."""
    return {
        "service": "Gambiarra Server",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "websocket": "/ws",
            "health": "/health",
            "sessions": "/sessions"
        },
        "features": {
            "ai_providers": list(ai_provider_manager.available_providers()),
            "websocket_connections": websocket_manager.connection_count(),
            "active_sessions": session_manager.active_session_count()
        }
    }

@app.get("/health")
async def health_check():
    """Detailed health check for monitoring."""
    ai_status = await ai_provider_manager.health_check()

    return {
        "status": "healthy",
        "services": {
            "websocket_manager": "running",
            "session_manager": "running",
            "ai_providers": ai_status
        },
        "metrics": {
            "websocket_connections": websocket_manager.connection_count(),
            "active_sessions": session_manager.active_session_count(),
            "total_sessions": session_manager.total_session_count()
        }
    }

@app.get("/sessions")
async def list_sessions():
    """List active sessions (for debugging)."""
    return {
        "active_sessions": session_manager.list_sessions(),
        "count": session_manager.active_session_count()
    }

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Main WebSocket endpoint for client connections."""
    connection_id = str(uuid.uuid4())

    try:
        # Accept connection
        await websocket.accept()
        logger.info(f"🔌 New WebSocket connection: {connection_id}")

        # Register connection
        await websocket_manager.connect(connection_id, websocket)

        # Handle connection lifecycle
        await handle_websocket_connection(connection_id, websocket)

    except WebSocketDisconnect:
        logger.info(f"🔌 WebSocket disconnected: {connection_id}")
    except Exception as e:
        logger.error(f"❌ WebSocket error for {connection_id}: {e}")
    finally:
        # Cleanup
        await websocket_manager.disconnect(connection_id)
        await session_manager.cleanup_session(connection_id)

async def handle_websocket_connection(connection_id: str, websocket: WebSocket):
    """Handle the full lifecycle of a WebSocket connection."""
    session_id = None

    try:
        while True:
            # Receive message from client
            data = await websocket.receive_text()
            message = json.loads(data)

            logger.info(f"📨 Received from {connection_id}: {message.get('type', 'unknown')}")

            # Route message based on type
            if message["type"] == "connect":
                response = await handle_connect(connection_id, message)

            elif message["type"] == "create_session":
                session_id = await handle_create_session(connection_id, message)
                response = {"type": "session_created", "session_id": session_id, "status": "ready"}

            elif message["type"] == "user_message":
                if not session_id:
                    raise ValueError("No active session")
                response = await handle_user_message(session_id, message)

            elif message["type"] == "tool_approval_response":
                if not session_id:
                    raise ValueError("No active session")
                response = await handle_tool_approval(session_id, message)
                # The response from handle_tool_approval should be sent immediately
                if response:
                    await websocket.send_text(json.dumps(response))
                    response = None  # Don't send again

            elif message["type"] == "tool_result":
                if not session_id:
                    raise ValueError("No active session")
                response = await handle_tool_result(session_id, message)

            else:
                response = {
                    "type": "error",
                    "error": {
                        "code": "UNKNOWN_MESSAGE_TYPE",
                        "message": f"Unknown message type: {message['type']}"
                    }
                }

            # Send response if not already handled by streaming
            if response:
                await websocket.send_text(json.dumps(response))

    except WebSocketDisconnect:
        raise
    except json.JSONDecodeError:
        await websocket.send_text(json.dumps({
            "type": "error",
            "error": {
                "code": "INVALID_JSON",
                "message": "Invalid JSON in message"
            }
        }))
    except Exception as e:
        logger.error(f"❌ Error handling message: {e}")
        await websocket.send_text(json.dumps({
            "type": "error",
            "error": {
                "code": "INTERNAL_ERROR",
                "message": str(e)
            }
        }))

async def handle_connect(connection_id: str, message: Dict[str, Any]) -> Dict[str, Any]:
    """Handle initial connection message."""
    return {
        "type": "connected",
        "connection_id": connection_id,
        "server_info": {
            "version": "1.0.0",
            "supported_providers": list(ai_provider_manager.available_providers()),
            "available_tools": [
                "read_file", "write_to_file", "search_files", "list_files",
                "insert_content", "search_and_replace", "execute_command",
                "list_code_definition_names", "attempt_completion",
                "ask_followup_question", "update_todo_list"
            ]
        }
    }

async def handle_create_session(connection_id: str, message: Dict[str, Any]) -> str:
    """Handle session creation."""
    config = message.get("config", {})

    # Create new session
    session_id = await session_manager.create_session(
        connection_id=connection_id,
        config=config
    )

    logger.info(f"🎯 Created session {session_id} for connection {connection_id}")
    return session_id

async def handle_user_message(session_id: str, message: Dict[str, Any]) -> None:
    """Handle user message - processes with AI and may trigger tool calls."""
    session = await session_manager.get_session(session_id)
    if not session:
        raise ValueError(f"Session {session_id} not found")

    user_content = message["message"]["content"]
    images = message["message"].get("images", [])

    logger.info(f"💬 Processing user message in session {session_id}")

    # Add user message to conversation
    await session.add_message("user", user_content, images)

    # Process with AI provider
    await process_ai_response(session_id, session)

    return None  # Response handled by streaming

async def process_ai_response(session_id: str, session):
    """Process AI response with streaming and tool call parsing."""
    try:
        # Get AI provider (server-configured)
        provider = ai_provider_manager.get_provider()

        # Generate system prompt (KiloCode compatible)
        system_prompt = await generate_system_prompt(session)

        # Get conversation messages
        messages = await session.get_messages()

        # Add system prompt
        full_messages = [{"role": "system", "content": system_prompt}] + messages

        # Stream AI response
        websocket = websocket_manager.get_websocket(session.connection_id)
        if not websocket:
            raise ValueError("WebSocket connection lost")

        response_content = ""

        async for chunk in provider.stream_completion(full_messages):
            # Send chunk to client
            await websocket.send_text(json.dumps({
                "type": "ai_response_chunk",
                "session_id": session_id,
                "chunk": {
                    "content": chunk,
                    "is_complete": False
                }
            }))

            response_content += chunk

        # Parse for tool calls
        tool_calls = parse_tool_calls(response_content)

        if tool_calls:
            logger.info(f"🛠️ Found {len(tool_calls)} tool calls in AI response")

            # Request approval for each tool
            for tool_call in tool_calls:
                await request_tool_approval(session_id, tool_call, websocket)

        # Add AI response to conversation
        await session.add_message("assistant", response_content)

        # Send completion signal
        await websocket.send_text(json.dumps({
            "type": "ai_response_chunk",
            "session_id": session_id,
            "chunk": {
                "content": "",
                "is_complete": True
            }
        }))

    except Exception as e:
        logger.error(f"❌ Error processing AI response: {e}")
        # Send error to client
        websocket = websocket_manager.get_websocket(session.connection_id)
        if websocket:
            await websocket.send_text(json.dumps({
                "type": "error",
                "error": {
                    "code": "AI_PROCESSING_ERROR",
                    "message": str(e)
                }
            }))

async def generate_system_prompt(session) -> str:
    """Generate KiloCode-compatible system prompt."""
    # This is a simplified version - in full implementation,
    # this would use the KiloCode prompt system from PROMPTS.json

    prompt = """You are Gambiarra, an AI coding assistant. You have access to tools for file operations, code analysis, and system commands.

Available tools (use XML format):
- <read_file><args><file><path>filename</path></file></args></read_file>
- <write_to_file><path>filename</path><content>file content</content><line_count>number</line_count></write_to_file>
- <search_files><path>directory</path><regex>pattern</regex><file_pattern>*.py</file_pattern></search_files>
- <execute_command><command>shell command</command><cwd>directory</cwd></execute_command>
- <list_files><path>directory</path><recursive>true/false</recursive></list_files>

Always use tools to understand the codebase before making changes. Be helpful and thorough."""

    return prompt

def parse_tool_calls(content: str) -> list:
    """Parse XML tool calls from AI response content."""
    import re

    # Simple XML tool call parser
    tool_pattern = r'<(\w+)>(.*?)</\1>'
    matches = re.findall(tool_pattern, content, re.DOTALL)

    tool_calls = []
    for tool_name, tool_content in matches:
        if tool_name in ["read_file", "write_to_file", "search_files", "execute_command", "list_files", "search_and_replace"]:
            # Parse parameters from XML content
            params = parse_xml_parameters(tool_content)
            tool_calls.append({
                "name": tool_name,
                "parameters": params
            })

    return tool_calls

def parse_xml_parameters(xml_content: str) -> dict:
    """Parse parameters from XML tool content."""
    import re

    params = {}

    # Extract path
    path_match = re.search(r'<path>(.*?)</path>', xml_content)
    if path_match:
        params["path"] = path_match.group(1)

    # Extract other common parameters
    content_match = re.search(r'<content>(.*?)</content>', xml_content, re.DOTALL)
    if content_match:
        params["content"] = content_match.group(1)

    regex_match = re.search(r'<regex>(.*?)</regex>', xml_content)
    if regex_match:
        params["regex"] = regex_match.group(1)

    command_match = re.search(r'<command>(.*?)</command>', xml_content)
    if command_match:
        params["command"] = command_match.group(1)

    # Extract search and replace parameters
    search_match = re.search(r'<search>(.*?)</search>', xml_content, re.DOTALL)
    if search_match:
        params["search"] = search_match.group(1)

    replace_match = re.search(r'<replace>(.*?)</replace>', xml_content, re.DOTALL)
    if replace_match:
        params["replace"] = replace_match.group(1)

    return params

async def request_tool_approval(session_id: str, tool_call: dict, websocket: WebSocket):
    """Request user approval for tool execution."""
    request_id = str(uuid.uuid4())

    # Store the tool call for later execution
    pending_tool_requests[request_id] = tool_call

    approval_request = {
        "type": "tool_approval_request",
        "session_id": session_id,
        "request_id": request_id,
        "tool": {
            "name": tool_call["name"],
            "parameters": tool_call["parameters"],
            "description": f"Execute {tool_call['name']} tool",
            "risk_level": get_tool_risk_level(tool_call["name"]),
            "requires_approval": True
        }
    }

    await websocket.send_text(json.dumps(approval_request))
    logger.info(f"🔐 Requested approval for {tool_call['name']} in session {session_id}")

def get_tool_risk_level(tool_name: str) -> str:
    """Determine risk level for tool."""
    high_risk = ["write_to_file", "execute_command"]
    medium_risk = ["search_and_replace", "insert_content"]

    if tool_name in high_risk:
        return "high"
    elif tool_name in medium_risk:
        return "medium"
    else:
        return "low"

async def handle_tool_approval(session_id: str, message: Dict[str, Any]) -> Dict[str, Any]:
    """Handle tool approval response from client."""
    decision = message["decision"]
    request_id = message["request_id"]

    logger.info(f"🔐 Tool approval {decision} for request {request_id}")

    if decision == "approved":
        # Retrieve the stored tool request
        tool_call = pending_tool_requests.get(request_id)
        if not tool_call:
            logger.error(f"❌ No pending tool request found for {request_id}")
            return {
                "type": "error",
                "error": {
                    "code": "TOOL_REQUEST_NOT_FOUND",
                    "message": f"No pending tool request for {request_id}"
                }
            }

        # Remove from pending
        pending_tool_requests.pop(request_id, None)

        execution_id = str(uuid.uuid4())

        return {
            "type": "execute_tool",
            "session_id": session_id,
            "execution_id": execution_id,
            "tool": {
                "name": tool_call["name"],
                "parameters": tool_call["parameters"]
            }
        }
    else:
        # Remove from pending even if denied
        pending_tool_requests.pop(request_id, None)

        return {
            "type": "tool_denied",
            "session_id": session_id,
            "request_id": request_id,
            "message": "Tool execution denied by user"
        }

async def handle_tool_result(session_id: str, message: Dict[str, Any]) -> Dict[str, Any]:
    """Handle tool execution result from client."""
    result = message["result"]
    execution_id = message["execution_id"]

    logger.info(f"🛠️ Tool result received for execution {execution_id}: {result['status']}")

    # Add tool result to session
    session = await session_manager.get_session(session_id)
    if session:
        await session.add_tool_result(execution_id, result)

    return {
        "type": "tool_result_received",
        "session_id": session_id,
        "execution_id": execution_id,
        "status": "processed"
    }

if __name__ == "__main__":
    print("🚀 Starting Gambiarra Server...")
    print(f"📍 WebSocket endpoint: ws://{config.host}:{config.port}/ws")
    print(f"🌐 Health check: http://{config.host}:{config.port}/health")
    print(f"🤖 Default AI provider: {config.ai_provider}")

    # Show available providers based on configuration
    available_providers = ["test", "trustgraph"]  # Both always available
    if config.openai_api_key:
        available_providers.append("openai")
    print(f"🔌 Available providers: {', '.join(available_providers)}")

    print("🔧 Configure your Gambiarra client to connect to this server")

    uvicorn.run(
        app,
        host=config.host,
        port=config.port,
        log_level=config.log_level.lower(),
        reload=False
    )