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

from gambiarra.server.websocket_handler import WebSocketManager
from gambiarra.server.ai_integration.providers import AIProviderManager
from gambiarra.server.session.manager import SessionManager
from gambiarra.server.tools.mode_filter import ToolModeFilter, OperatingMode
from gambiarra.server.error_handling import ErrorRecoveryManager, ErrorCategory, ErrorSeverity
from gambiarra.server.config import ServerConfig

# New modular components
from gambiarra.server.core.tools.parser import ToolCallParser
from gambiarra.server.core.tools.registry import get_tool_registry
from gambiarra.server.core.tools.validator import validate_xml_tool_call
from gambiarra.server.core.session.context import get_context_manager
from gambiarra.server.core.events.bus import get_event_bus, EventTypes, publish_event
from gambiarra.server.core.task.manager import get_task_manager
from gambiarra.server.core.task.handlers import register_all_handlers
from gambiarra.server.core.recovery.degraded_mode import get_degraded_mode_manager, ComponentType
from gambiarra.server.core.performance.connection_pool import get_connection_pool_manager
from gambiarra.server.core.performance.request_batcher import get_batcher_manager

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
# Note: ai_provider_manager will be initialized after command line args are processed
ai_provider_manager = None
tool_mode_filter = ToolModeFilter()
error_recovery_manager = ErrorRecoveryManager()

# New modular managers
context_manager = get_context_manager()
tool_registry = get_tool_registry()
event_bus = get_event_bus()
task_manager = get_task_manager()
degraded_mode_manager = get_degraded_mode_manager()
connection_pool_manager = get_connection_pool_manager()
batcher_manager = get_batcher_manager()

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

    # Start event-driven components
    await event_bus.start()
    await task_manager.start()

    # Register event handlers
    register_all_handlers()

    # Initialize degraded mode monitoring
    degraded_mode_manager.register_component("ai_provider", ComponentType.AI_PROVIDER)
    degraded_mode_manager.register_component("event_bus", ComponentType.EVENT_BUS)
    degraded_mode_manager.register_component("session_manager", ComponentType.SESSION_MANAGER)
    degraded_mode_manager.register_component("websocket_manager", ComponentType.NETWORK)

    # Start performance managers
    await connection_pool_manager.start_all()
    await batcher_manager.start_all()

    # Publish system startup event
    await publish_event(
        event_type=EventTypes.SYSTEM_STARTUP,
        data={"server_version": "1.0.0", "providers": list(ai_provider_manager.available_providers())},
        source="server_main"
    )

    logger.info("✅ Event-driven architecture initialized")
    logger.info("✅ Degraded mode monitoring enabled")
    logger.info("✅ Performance optimization features started")

    yield

    # Cleanup
    logger.info("🛑 Shutting down Gambiarra Server...")

    # Publish system shutdown event
    await publish_event(
        event_type=EventTypes.SYSTEM_SHUTDOWN,
        data={"reason": "server_shutdown"},
        source="server_main"
    )

    # Stop event-driven components
    await task_manager.stop()
    await event_bus.stop()

    # Stop performance managers
    await connection_pool_manager.stop_all()
    await batcher_manager.stop_all()

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
            "active_sessions": session_manager.active_session_count(),
            "degradation_level": degraded_mode_manager.current_level.value,
            "available_features": degraded_mode_manager.get_available_features()
        }
    }

@app.get("/health")
async def health_check():
    """Detailed health check for monitoring."""
    ai_status = await ai_provider_manager.health_check()

    # Check system health including degraded mode
    system_status = degraded_mode_manager.get_system_status()

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
        },
        "system": system_status,
        "performance": {
            "connection_pools": connection_pool_manager.get_all_stats(),
            "request_batchers": batcher_manager.get_all_stats()
        }
    }

@app.get("/sessions")
async def list_sessions():
    """List active sessions (for debugging)."""
    return {
        "active_sessions": session_manager.list_sessions(),
        "count": session_manager.active_session_count()
    }

@app.get("/modes")
async def get_available_modes():
    """Get available operating modes."""
    return {
        "available_modes": tool_mode_filter.get_available_modes(),
        "default_mode": "code"
    }

@app.get("/sessions/{session_id}/mode")
async def get_session_mode(session_id: str):
    """Get operating mode for a specific session."""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "session_id": session_id,
        "operating_mode": session.config.operating_mode,
        "mode_description": tool_mode_filter.get_mode_description(OperatingMode(session.config.operating_mode))
    }

@app.post("/sessions/{session_id}/mode")
async def set_session_mode(session_id: str, request: dict):
    """Set operating mode for a specific session."""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    new_mode = request.get("mode")
    if not new_mode:
        raise HTTPException(status_code=400, detail="Mode is required")

    try:
        operating_mode = OperatingMode(new_mode)
    except ValueError:
        available_modes = [mode.value for mode in OperatingMode]
        raise HTTPException(
            status_code=400,
            detail=f"Invalid mode '{new_mode}'. Available modes: {available_modes}"
        )

    # Update session mode
    session.config.operating_mode = new_mode
    logger.info(f"🎯 Session {session_id} mode changed to {new_mode}")

    return {
        "session_id": session_id,
        "old_mode": session.config.operating_mode,
        "new_mode": new_mode,
        "mode_description": tool_mode_filter.get_mode_description(operating_mode),
        "allowed_tools": list(tool_mode_filter.get_allowed_tools_for_mode(operating_mode))
    }

@app.get("/errors/stats")
async def get_error_statistics():
    """Get error statistics for monitoring."""
    return error_recovery_manager.get_error_statistics()

@app.get("/errors/recent")
async def get_recent_errors(count: int = 10):
    """Get recent errors for debugging."""
    return {
        "recent_errors": error_recovery_manager.get_recent_errors(count),
        "count": count
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
            try:
                # Receive message from client
                data = await websocket.receive_text()
                message = json.loads(data)
            except json.JSONDecodeError as e:
                # Handle malformed JSON
                await error_recovery_manager.handle_error(
                    e,
                    ErrorCategory.VALIDATION,
                    ErrorSeverity.LOW,
                    {"connection_id": connection_id, "raw_data": data}
                )
                continue

            logger.info(f"📨 Received from {connection_id}: {message.get('type', 'unknown')}")

            try:
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

            except Exception as handler_error:
                # Log the exact error with full traceback for debugging
                import traceback
                logger.error(f"❌ Detailed error in message processing: {handler_error}")
                logger.error(f"📍 Full traceback:\n{traceback.format_exc()}")

                # Report component failure for degraded mode monitoring
                await degraded_mode_manager.report_component_failure(
                    "websocket_manager",
                    f"Message processing error: {handler_error}"
                )

                # Handle errors in message processing
                recovery_result = await error_recovery_manager.handle_error(
                    handler_error,
                    ErrorCategory.SESSION,
                    ErrorSeverity.MEDIUM,
                    {
                        "connection_id": connection_id,
                        "session_id": session_id,
                        "message_type": message.get("type", "unknown"),
                        "websocket": websocket
                    },
                    session_id=session_id
                )

                # Send error response to client
                error_response = {
                    "type": "error",
                    "error": {
                        "code": "MESSAGE_PROCESSING_ERROR",
                        "message": str(handler_error),
                        "recovery_attempted": recovery_result.get("recovered", False)
                    }
                }

                try:
                    await websocket.send_text(json.dumps(error_response))
                except:
                    # WebSocket might be closed, log and break
                    logger.error(f"❌ Failed to send error response to {connection_id}")
                    break

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
            "available_tools": tool_registry.list_tools()
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

    # Publish session creation event
    await publish_event(
        event_type=EventTypes.SESSION_CREATED,
        data={
            "connection_id": connection_id,
            "working_directory": config.get("working_directory", "."),
            "config": config
        },
        source="session_manager",
        session_id=session_id
    )

    logger.info(f"🎯 Created session {session_id} for connection {connection_id}")
    return session_id

async def handle_user_message(session_id: str, message: Dict[str, Any]) -> None:
    """Handle user message - processes with AI and may trigger tool calls."""
    session = session_manager.get_session(session_id)
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

        # Generate system prompt with tool descriptions
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

        # Report AI provider failure for degraded mode monitoring
        await degraded_mode_manager.report_component_failure(
            "ai_provider",
            f"AI processing error: {e}"
        )

        # Handle error with recovery manager
        recovery_result = await error_recovery_manager.handle_error(
            e,
            ErrorCategory.AI_PROVIDER,
            ErrorSeverity.HIGH,
            {
                "session_id": session_id,
                "provider": ai_provider_manager.default_provider,
                "message_count": len(messages) if 'messages' in locals() else 0
            },
            session_id=session_id
        )

        # Send error to client
        websocket = websocket_manager.get_websocket(session.connection_id)
        if websocket:
            await websocket.send_text(json.dumps({
                "type": "error",
                "error": {
                    "code": "AI_PROCESSING_ERROR",
                    "message": str(e),
                    "recovery_attempted": recovery_result.get("recovered", False)
                }
            }))

async def generate_system_prompt(session) -> str:
    """Generate system prompt with tool descriptions using modular approach."""
    from gambiarra.server.prompts.system import generate_system_prompt

    # Get current working directory from session or default
    cwd = getattr(session, 'cwd', '/workspace')

    # Generate modular prompt
    return generate_system_prompt(cwd=cwd, mode="code")

def parse_tool_calls(content: str) -> list:
    """Parse XML tool calls from AI response content."""
    import re

    # Simple XML tool call parser
    tool_pattern = r'<(\w+)>(.*?)</\1>'
    matches = re.findall(tool_pattern, content, re.DOTALL)

    tool_calls = []

    for tool_name, tool_content in matches:
        if tool_name in tool_registry.list_tools():
            # Validate XML format first
            validation_result = validate_xml_tool_call(f"<{tool_name}>{tool_content}</{tool_name}>")

            if not validation_result.is_valid:
                logger.warning(f"⚠️ Invalid XML format for {tool_name}: {validation_result.errors}")
                continue

            # Parse parameters from XML content using new parser
            params = ToolCallParser.parse_xml_parameters(tool_content)

            # Validate tool call against registry
            try:
                tool_registry.validate_tool_call(tool_name, params)
                tool_calls.append({
                    "name": tool_name,
                    "parameters": params
                })
            except Exception as e:
                logger.warning(f"⚠️ Tool validation failed for {tool_name}: {e}")
                continue

    return tool_calls

# XML parser function removed - now using modular ToolCallParser

def wrap_tool_parameters_for_client(tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Wrap tool parameters in the format expected by the client."""
    # All tools now use nested args structure for consistency

    if tool_name == "read_file":
        # Special nested structure: args.file.path
        return {
            "args": {
                "file": {
                    "path": params.get("path", "")
                }
            }
        }

    # All other tools use standard nested args structure
    return {
        "args": params
    }


async def request_tool_approval(session_id: str, tool_call: dict, websocket: WebSocket):
    """Request user approval for tool execution."""
    request_id = str(uuid.uuid4())

    # Get session to check operating mode
    session = session_manager.get_session(session_id)
    if not session:
        logger.error(f"❌ Session {session_id} not found for tool approval")
        return

    # Get operating mode from session
    operating_mode_str = session.config.operating_mode
    try:
        operating_mode = OperatingMode(operating_mode_str)
    except ValueError:
        logger.warning(f"Unknown operating mode '{operating_mode_str}', defaulting to CODE")
        operating_mode = OperatingMode.CODE

    # Wrap parameters for client format
    wrapped_params = wrap_tool_parameters_for_client(tool_call["name"], tool_call["parameters"])

    # Apply mode-based filtering
    filter_result = tool_mode_filter.filter_tool_call(
        tool_call["name"],
        wrapped_params,
        operating_mode
    )

    if not filter_result["allowed"]:
        # Tool is blocked by mode filter - send error to client
        error_response = {
            "type": "tool_approval_response",
            "session_id": session_id,
            "request_id": request_id,
            "decision": "denied",
            "feedback": f"Tool blocked by {operating_mode_str} mode: {filter_result['reason']}",
            "modified_parameters": {}
        }
        await websocket.send_text(json.dumps(error_response))
        return

    # Store the tool call for later execution
    pending_tool_requests[request_id] = tool_call

    # Get risk level (potentially modified by mode)
    original_risk = get_tool_risk_level(tool_call["name"])
    final_risk = filter_result["modified_risk"] or original_risk

    approval_request = {
        "type": "tool_approval_request",
        "session_id": session_id,
        "request_id": request_id,
        "tool": {
            "name": tool_call["name"],
            "parameters": wrapped_params,  # Use wrapped parameters for client
            "description": f"Execute {tool_call['name']} tool (mode: {operating_mode_str})",
            "risk_level": final_risk,
            "requires_approval": True
        }
    }

    await websocket.send_text(json.dumps(approval_request))
    logger.info(f"🔐 Requested approval for {tool_call['name']} in session {session_id}")

def format_tool_result_for_ai(result: Dict[str, Any]) -> str:
    """Format tool result in a way AI can understand and act on."""
    if result.get("status") != "success":
        return f"Tool failed: {result.get('error', 'Unknown error')}"

    data = result.get("data", {}) or {}
    metadata = result.get("metadata", {}) or {}

    # Format based on what kind of operation was performed
    if "files" in data and "directories" in data:
        # list_files result
        files = data["files"]
        directories = data["directories"]

        if not files and not directories:
            return "No files or directories found in the workspace."

        result_parts = []

        if directories:
            dir_names = [d.get("name", "unknown") for d in directories]
            result_parts.append(f"Directories: {', '.join(dir_names)}")

        if files:
            file_list = []
            for file_info in files:
                name = file_info.get("name", "unknown")
                size = file_info.get("size", 0)
                file_list.append(f"{name} ({size} bytes)")
            result_parts.append(f"Files: {', '.join(file_list)}")

        return "Tool result: " + "; ".join(result_parts)

    elif metadata.get("operation") == "file_created":
        # write_to_file result
        path = metadata.get("path", "unknown")
        bytes_written = metadata.get("bytes_written", 0)
        return f"Tool result: Created file {path} ({bytes_written} bytes)"

    elif metadata.get("operation") == "file_updated":
        # write_to_file update result
        path = metadata.get("path", "unknown")
        bytes_written = metadata.get("bytes_written", 0)
        return f"Tool result: Updated file {path} ({bytes_written} bytes)"

    elif "content" in data:
        # read_file result
        content = str(data["content"])
        path = metadata.get("path", "unknown file")
        return f"Tool result: Read {path} ({len(content)} chars). Content: {content[:200]}..."

    elif "output" in data:
        # execute_command result
        output = str(data["output"])
        command = metadata.get("command", "unknown command")
        return f"Tool result: Executed '{command}'. Output: {output[:300]}"

    else:
        # Generic result
        return f"Tool result: Operation completed successfully. Data: {str(data)[:100]}"

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

        # Wrap parameters for client format
        wrapped_params = wrap_tool_parameters_for_client(tool_call["name"], tool_call["parameters"])

        return {
            "type": "execute_tool",
            "session_id": session_id,
            "execution_id": execution_id,
            "tool": {
                "name": tool_call["name"],
                "parameters": wrapped_params
            }
        }
    else:
        # Get tool info for better denial message
        tool_call = pending_tool_requests.get(request_id)
        tool_name = tool_call.get("name", "unknown") if tool_call else "unknown"
        feedback = message.get("feedback", "Tool execution denied by user")

        # Remove from pending even if denied
        pending_tool_requests.pop(request_id, None)

        # Feed the denial back into the AI conversation
        await _handle_tool_denial_for_ai(session_id, tool_name, feedback)

        return {
            "type": "tool_denied",
            "session_id": session_id,
            "request_id": request_id,
            "tool_name": tool_name,
            "reason": feedback
        }

async def _handle_tool_denial_for_ai(session_id: str, tool_name: str, feedback: str) -> None:
    """Handle tool denial by feeding the information back into the AI conversation."""
    try:
        session = session_manager.get_session(session_id)
        if not session:
            logger.error(f"❌ Session {session_id} not found for tool denial handling")
            return

        # Create a tool result indicating denial
        denial_result = {
            "status": "error",
            "error": {
                "code": "TOOL_DENIED",
                "message": f"Tool '{tool_name}' was denied by the user: {feedback}"
            },
            "data": None,
            "metadata": {
                "tool_name": tool_name,
                "denial_reason": feedback,
                "denied_at": time.time()
            }
        }

        # Add the denial as a message to the conversation for AI to process
        denial_message = f"Tool result: The '{tool_name}' tool was denied by the user. Reason: {feedback}. Please acknowledge this and consider alternative approaches."
        await session.add_message("assistant", denial_message)

        logger.info(f"✅ Tool denial added to conversation")

        # Continue the agentic loop to let AI handle the denial
        await process_ai_response(session_id, session)

    except Exception as e:
        logger.error(f"❌ Error handling tool denial for AI: {e}")


async def handle_tool_result(session_id: str, message: Dict[str, Any]) -> Dict[str, Any]:
    """Handle tool execution result from client."""
    result = message["result"]
    execution_id = message["execution_id"]

    logger.info(f"🛠️ Tool result received for execution {execution_id}: {result['status']}")

    # Add tool result to session for automatic agentic loop
    session = session_manager.get_session(session_id)
    if session:
        # Add a detailed tool result that AI can understand and act on
        tool_summary = format_tool_result_for_ai(result)
        await session.add_message("assistant", tool_summary)

        logger.info(f"✅ Tool result added to conversation")
        logger.info(f"🔍 Current conversation has {len(session.messages)} messages")

        # Continue agentic loop until attempt_completion or no more tools
        # Safety limit to prevent infinite loops
        recent_tool_count = sum(1 for msg in session.messages[-10:] if msg.role == "assistant" and msg.content and "Tool result:" in (msg.content or ""))

        if recent_tool_count < 10:  # Increased safety limit
            logger.info(f"🤖 Continuing agentic loop (tool #{recent_tool_count + 1})")
            await process_ai_response(session_id, session)
        else:
            logger.info(f"🛑 Safety limit reached (tool count: {recent_tool_count})")

    return {
        "type": "tool_result_received",
        "session_id": session_id,
        "execution_id": execution_id,
        "status": "processed"
    }

def main():
    """Main entry point for the Gambiarra server."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Gambiarra Server - AI-powered coding assistant server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  gambiarra-server                    # Start server with default settings
  gambiarra-server --host 0.0.0.0    # Start server on all interfaces
  gambiarra-server --port 9000       # Start server on port 9000
  gambiarra-server --provider openai # Use OpenAI as default provider

Environment variables:
  GAMBIARRA_HOST                      # Server host (default: localhost)
  GAMBIARRA_PORT                      # Server port (default: 8000)
  GAMBIARRA_AI_PROVIDER               # AI provider (default: test)
  OPENAI_API_KEY                      # OpenAI API key (for OpenAI provider)
  GAMBIARRA_TRUSTGRAPH_URL            # TrustGraph server URL
  GAMBIARRA_TRUSTGRAPH_FLOW           # TrustGraph flow ID
        """
    )

    parser.add_argument(
        "--host",
        default=config.host,
        help=f"Host to bind server to (default: {config.host}, use 0.0.0.0 for all interfaces)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=config.port,
        help=f"Port to bind server to (default: {config.port})"
    )
    parser.add_argument(
        "--provider",
        choices=["test", "openai", "trustgraph"],
        default=config.ai_provider,
        help=f"Default AI provider (default: {config.ai_provider})"
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default=config.log_level,
        help=f"Logging level (default: {config.log_level})"
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development"
    )

    args = parser.parse_args()

    # Update config with command line arguments
    # Convert 'localhost' to '127.0.0.1' to avoid IPv6 binding issues
    config.host = '127.0.0.1' if args.host == 'localhost' else args.host
    config.port = args.port
    config.ai_provider = args.provider
    config.log_level = args.log_level

    # Initialize AI provider manager with the correct provider from command line
    global ai_provider_manager
    ai_provider_manager = AIProviderManager(default_provider=config.ai_provider)

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
        reload=args.reload
    )


if __name__ == "__main__":
    main()