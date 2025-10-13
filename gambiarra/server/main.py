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
from typing import Dict, Any, Optional
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
from gambiarra.server.prompts.tools import get_available_tools
from gambiarra.server.playbooks import get_playbook_registry, get_playbook_executor
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
ai_provider_manager = AIProviderManager(default_provider=config.ai_provider)
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
    session = await session_manager.get_session(session_id, auto_recover=False)
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
    session = await session_manager.get_session(session_id, auto_recover=False)
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
    session = await session_manager.get_session(session_id, auto_recover=False)
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
        logger.info(f"🤖 Using AI provider: {ai_provider_manager.default_provider}")

        # Generate system prompt with tool descriptions
        system_prompt = await generate_system_prompt(session)
        logger.info(f"📝 Generated system prompt ({len(system_prompt)} chars)")

        # Get conversation messages
        messages = await session.get_messages()
        logger.info(f"💬 Got {len(messages)} conversation messages")

        # Add system prompt
        full_messages = [{"role": "system", "content": system_prompt}] + messages

        # Stream AI response
        websocket = websocket_manager.get_websocket(session.connection_id)
        if not websocket:
            raise ValueError("WebSocket connection lost")

        response_content = ""
        logger.info(f"🔄 Starting to stream completion from {ai_provider_manager.default_provider}...")

        chunk_count = 0
        async for chunk in provider.stream_completion(full_messages):
            chunk_count += 1
            logger.info(f"📦 Received chunk #{chunk_count} ({len(chunk)} chars)")

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

        logger.info(f"✅ Streaming complete. Total chunks: {chunk_count}, total chars: {len(response_content)}")
        logger.info(f"🔍 Full AI response:\n{response_content}")

        # Parse for tool calls
        tool_calls, validation_errors = parse_tool_calls(response_content)

        # Handle validation errors FIRST
        if validation_errors:
            logger.error(f"❌ {len(validation_errors)} tool calls had validation errors")

            # Track validation failures for retry limit
            session = await session_manager.get_session(session_id, auto_recover=False)
            if not hasattr(session, 'tool_validation_failures'):
                session.tool_validation_failures = 0
            session.tool_validation_failures += 1

            # Check retry limit
            MAX_VALIDATION_RETRIES = 3
            if session.tool_validation_failures >= MAX_VALIDATION_RETRIES:
                # Too many validation failures - fail gracefully
                error_summary = f"AI repeatedly generated invalid tool calls after {MAX_VALIDATION_RETRIES} attempts."
                for err in validation_errors:
                    error_summary += f"\n\nLast error for {err['tool_name']}:\n{err['error']}"

                logger.error(f"❌ Task failed after {session.tool_validation_failures} validation errors")

                # Send failure to client
                await websocket.send_json({
                    "type": "task_failed",
                    "session_id": session_id,
                    "error": error_summary,
                    "metadata": {"validation_errors": validation_errors}
                })
                return

            # Format errors for AI
            error_messages = []
            for err in validation_errors:
                error_messages.append(
                    f"ERROR: Tool '{err['tool_name']}' failed validation.\n"
                    f"{err['error']}\n"
                    f"You attempted: {err['attempted_xml']}"
                )

            combined_error = "\n\n".join(error_messages)

            # Add error to session so AI sees it
            await session.add_message("user", f"Tool validation errors (attempt {session.tool_validation_failures}/{MAX_VALIDATION_RETRIES}):\n\n{combined_error}\n\nPlease retry with correct XML format.")

            # If ALL tools failed validation, continue agentic loop for retry
            if not tool_calls:
                logger.info(f"🔄 All tools invalid, continuing loop for AI retry (attempt {session.tool_validation_failures}/{MAX_VALIDATION_RETRIES})")
                # Don't send anything to client yet - let agentic loop continue
                # The loop will call AI again with the error message
                return

            # If there are SOME valid tools, process them (errors already reported above)

        if tool_calls:
            logger.info(f"🛠️ Found {len(tool_calls)} tool calls in AI response")

            # Get list of valid tools for validation
            valid_tools = get_available_tools()

            # Validate and request approval for each tool
            for tool_call in tool_calls:
                tool_name = tool_call.get('name', '')

                # Validate tool name
                if tool_name not in valid_tools:
                    error_msg = f"Unknown tool '{tool_name}'. Valid tools are: {', '.join(valid_tools)}"
                    logger.warning(f"⚠️ Invalid tool requested: {tool_name}")

                    # Send error back to AI immediately
                    error_result = {
                        "status": "error",
                        "error": error_msg,
                        "data": None,
                        "metadata": {"tool_name": tool_name, "valid_tools": valid_tools}
                    }

                    # Add error to session context so AI sees it
                    session = await session_manager.get_session(session_id, auto_recover=False)
                    await session.add_message("system", f"Tool execution error: {error_msg}")

                    # Continue to next tool call
                    continue

                # Handle server-side memory tools
                if tool_name == "store_knowledge":
                    result = await handle_store_knowledge(session_id, tool_call)
                    session = await session_manager.get_session(session_id, auto_recover=False)
                    await session.add_message("user", result)
                    continue
                elif tool_name == "retrieve_knowledge":
                    result = await handle_retrieve_knowledge(session_id, tool_call)
                    session = await session_manager.get_session(session_id, auto_recover=False)
                    await session.add_message("user", result)
                    continue
                elif tool_name == "list_knowledge":
                    result = await handle_list_knowledge(session_id, tool_call)
                    session = await session_manager.get_session(session_id, auto_recover=False)
                    await session.add_message("user", result)
                    continue
                elif tool_name == "create_plan":
                    result = await handle_create_plan(session_id, tool_call)
                    session = await session_manager.get_session(session_id, auto_recover=False)
                    await session.add_message("user", result)
                    continue
                # Handle server-side playbook tools
                elif tool_name == "search_playbooks":
                    result = await handle_search_playbooks(session_id, tool_call)
                    session = await session_manager.get_session(session_id, auto_recover=False)
                    await session.add_message("user", result)
                    continue
                elif tool_name == "execute_playbook":
                    await handle_execute_playbook(session_id, tool_call, websocket)
                    continue
                elif tool_name == "ask_followup_question":
                    # Handle followup questions intelligently
                    result = await handle_followup_question(session_id, tool_call)
                    if result:  # Auto-answered
                        session = await session_manager.get_session(session_id, auto_recover=False)
                        await session.add_message("user", result)
                        continue
                    # else: let it go through normal approval flow

                # Tool is valid, request approval
                await request_tool_approval(session_id, tool_call, websocket)
        else:
            # AI generated text but no tool calls AND no validation errors
            # This means AI genuinely didn't want to call tools (not that it tried and failed)
            # Note: If there were validation errors with no valid tools, we already returned above
            logger.warning(f"⚠️ AI generated text without any tool calls - forcing task completion")

            # Add AI response to conversation first
            await session.add_message("assistant", response_content)

            # Auto-inject attempt_completion tool call
            auto_completion_call = {
                "name": "attempt_completion",
                "parameters": {
                    "result": response_content[:500]  # Use first 500 chars as summary
                }
            }

            # Execute attempt_completion directly (no approval needed)
            result_text = format_tool_result_for_ai({
                "status": "success",
                "data": {"completed": True},
                "metadata": {}
            })

            await session.add_message("user", result_text)

            # Send task_completed signal
            await websocket.send_text(json.dumps({
                "type": "task_completed",
                "session_id": session_id,
                "summary": response_content[:200]
            }))

            # End the agentic loop
            return

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

def parse_tool_calls(content: str) -> tuple:
    """Parse XML tool calls from AI response content.

    Returns:
        tuple: (valid_tool_calls, validation_errors)
    """
    import re

    # Simple XML tool call parser
    tool_pattern = r'<(\w+)>(.*?)</\1>'
    matches = re.findall(tool_pattern, content, re.DOTALL)

    tool_calls = []
    validation_errors = []

    for tool_name, tool_content in matches:
        if tool_name in tool_registry.list_tools():
            # Validate XML format first
            validation_result = validate_xml_tool_call(f"<{tool_name}>{tool_content}</{tool_name}>")

            if not validation_result.is_valid:
                # Collect error instead of silently skipping
                full_xml = f"<{tool_name}>{tool_content}</{tool_name}>"
                error_msg = f"Invalid XML format for {tool_name}: {'; '.join(validation_result.errors)}"

                # Get expected format from registry for helpful error
                tool_def = tool_registry.get_tool(tool_name)
                if tool_def and hasattr(tool_def, 'xml_format'):
                    error_msg += f"\nExpected format: {tool_def.xml_format}"

                validation_errors.append({
                    'tool_name': tool_name,
                    'error': error_msg,
                    'attempted_xml': full_xml[:300] + ('...' if len(full_xml) > 300 else '')
                })
                logger.warning(f"⚠️ {error_msg}")
                continue

            # Parse parameters from XML content using new parser
            # Need to pass full XML including tool tag for tool type detection
            full_xml = f"<{tool_name}>{tool_content}</{tool_name}>"
            params = ToolCallParser.parse_xml_parameters(full_xml)

            # Validate tool call against registry
            try:
                tool_registry.validate_tool_call(tool_name, params)
                tool_calls.append({
                    "name": tool_name,
                    "parameters": params
                })
            except Exception as e:
                # Collect parameter validation error
                validation_errors.append({
                    'tool_name': tool_name,
                    'error': f"Parameter validation failed for {tool_name}: {e}",
                    'attempted_xml': full_xml[:300] + ('...' if len(full_xml) > 300 else '')
                })
                logger.warning(f"⚠️ Tool validation failed for {tool_name}: {e}")
                continue

    return tool_calls, validation_errors

# XML parser function removed - now using modular ToolCallParser

def wrap_tool_parameters_for_client(tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Wrap tool parameters in the format expected by the client."""
    # All tools now use nested args structure for consistency

    # All tools now use standard nested args structure
    return {
        "args": params
    }


async def request_tool_approval(session_id: str, tool_call: dict, websocket: WebSocket):
    """Request user approval for tool execution."""
    request_id = str(uuid.uuid4())

    # Get session to check operating mode
    session = await session_manager.get_session(session_id, auto_recover=False)
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
        error_msg = result.get('error', 'Unknown error')
        data = result.get('data', {}) or {}
        metadata = result.get('metadata', {}) or {}

        # Build detailed error message
        error_parts = [f"Tool execution failed: {error_msg}"]

        # Include command execution details if available
        if 'exit_code' in data:
            error_parts.append(f"Exit code: {data['exit_code']}")

        if 'output' in data and data['output']:
            output = data['output'].strip()
            if output:
                # Truncate very long output but keep enough for AI to understand
                if len(output) > 1000:
                    output = output[:1000] + f"\n... (output truncated, {len(output)} total chars)"
                error_parts.append(f"Output:\n{output}")

        # Include metadata for context (command, timeout, etc.)
        if metadata:
            meta_str = ", ".join(f"{k}={v}" for k, v in metadata.items())
            error_parts.append(f"Context: {meta_str}")

        return "\n\n".join(error_parts)

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
        return f"Tool result: Read {path} ({len(content)} chars). Content: {content[:5000]}..."

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

async def handle_followup_question(session_id: str, tool_call: Dict[str, Any]) -> Optional[str]:
    """
    Handle ask_followup_question tool intelligently.

    Detects unnecessary questions where the AI already has sufficient context
    and auto-responds to keep the workflow moving.

    Returns:
        str: Auto-response if question is unnecessary
        None: Let it go through normal approval flow if legitimate
    """
    logger.info(f"🤔 Handling followup question for session {session_id}")

    try:
        # Extract question from parameters
        params = tool_call.get('parameters', {})
        question = params.get('question', '').lower()

        if not question:
            return None  # No question, let it through normal flow

        # Patterns that indicate unnecessary questions
        unnecessary_patterns = [
            # Claiming information is missing when it was just provided
            "doesn't mention",
            "doesn't detail",
            "doesn't contain",
            "doesn't specify",
            "doesn't have",
            "doesn't include",
            "no information about",
            "can't find",
            "couldn't find",
            "unable to find",

            # Asking about configuration that was just read
            'how do i configure',
            'how should i configure',
            'what configuration',
            'should i add',
            'do you want me to',

            # Asking about documentation that was just provided
            'which proxy',
            'which port',
            'what port',
            'where should',

            # Over-cautious confirmation requests
            'would you like me to proceed',
            'should i proceed',
            'is this correct',
            'does this look right',
        ]

        # Check if question matches unnecessary patterns
        for pattern in unnecessary_patterns:
            if pattern in question:
                logger.info(f"✅ Auto-answering unnecessary question: {question[:100]}...")

                # Return a directive to proceed with available information
                return (
                    "Please proceed with what you know from the previous messages and documentation. "
                    "Use your best judgment based on the information already provided."
                )

        # Question seems legitimate, let it go through normal flow
        logger.info(f"📋 Question appears legitimate, allowing normal approval flow")
        return None

    except Exception as e:
        logger.error(f"❌ Error handling followup question: {e}")
        return None  # On error, let it through normal flow


async def handle_store_knowledge(session_id: str, tool_call: Dict[str, Any]) -> str:
    """Handle store_knowledge tool - store information in session memory."""
    logger.info(f"💾 Storing knowledge for session {session_id}")

    try:
        # Get session
        session = await session_manager.get_session(session_id, auto_recover=False)
        if not session:
            return "Error: Session not found."

        # Extract parameters
        params = tool_call.get('parameters', {})
        key = params.get('key', '')
        value = params.get('value', '')
        description = params.get('description', '')

        if not key:
            return "Error: No key provided. Please provide a key to identify this information."

        if not value:
            return "Error: No value provided. Please provide the information to store."

        # Store in session working memory
        session.working_memory[key] = {
            'value': value,
            'description': description,
            'stored_at': len(session.messages)  # Track when it was stored
        }

        logger.info(f"✅ Stored knowledge: {key} = {value[:100]}...")

        return f"Successfully stored information under key '{key}'. You can retrieve it later using retrieve_knowledge with this key."

    except Exception as e:
        logger.error(f"❌ Error storing knowledge: {e}")
        return f"Error storing knowledge: {str(e)}"


async def handle_retrieve_knowledge(session_id: str, tool_call: Dict[str, Any]) -> str:
    """Handle retrieve_knowledge tool - retrieve information from session memory."""
    logger.info(f"🔍 Retrieving knowledge for session {session_id}")

    try:
        # Get session
        session = await session_manager.get_session(session_id, auto_recover=False)
        if not session:
            return "Error: Session not found."

        # Extract parameters
        params = tool_call.get('parameters', {})
        key = params.get('key', '')

        if not key:
            return "Error: No key provided. Please provide the key of the information to retrieve."

        # Retrieve from session working memory
        if key not in session.working_memory:
            available_keys = list(session.working_memory.keys())
            if available_keys:
                return f"Error: Key '{key}' not found in memory. Available keys: {', '.join(available_keys)}"
            else:
                return f"Error: Key '{key}' not found. No information has been stored yet."

        knowledge = session.working_memory[key]
        value = knowledge['value']
        description = knowledge.get('description', '')

        logger.info(f"✅ Retrieved knowledge: {key} = {value[:100]}...")

        result = f"Retrieved information for '{key}':\n\n{value}"
        if description:
            result += f"\n\nDescription: {description}"

        return result

    except Exception as e:
        logger.error(f"❌ Error retrieving knowledge: {e}")
        return f"Error retrieving knowledge: {str(e)}"


async def handle_list_knowledge(session_id: str, tool_call: Dict[str, Any]) -> str:
    """Handle list_knowledge tool - list all stored information."""
    logger.info(f"📋 Listing knowledge for session {session_id}")

    try:
        # Get session
        session = await session_manager.get_session(session_id, auto_recover=False)
        if not session:
            return "Error: Session not found."

        # List all stored knowledge
        if not session.working_memory:
            return "No information has been stored in memory yet."

        result_parts = ["Stored information in memory:\n"]

        for key, knowledge in session.working_memory.items():
            value = knowledge['value']
            description = knowledge.get('description', '')

            result_parts.append(f"\n• {key}")
            if description:
                result_parts.append(f"  Description: {description}")
            result_parts.append(f"  Preview: {value[:100]}{'...' if len(value) > 100 else ''}")

        logger.info(f"✅ Listed {len(session.working_memory)} knowledge items")

        return "\n".join(result_parts)

    except Exception as e:
        logger.error(f"❌ Error listing knowledge: {e}")
        return f"Error listing knowledge: {str(e)}"


async def handle_create_plan(session_id: str, tool_call: Dict[str, Any]) -> str:
    """Handle create_plan tool - create structured plan for multi-step tasks."""
    logger.info(f"📝 Creating plan for session {session_id}")

    try:
        # Get session
        session = await session_manager.get_session(session_id, auto_recover=False)
        if not session:
            return "Error: Session not found."

        # Extract parameters
        params = tool_call.get('parameters', {})
        task = params.get('task', '')
        goals = params.get('goals', '')
        rationale = params.get('rationale', '')

        if not task:
            return "Error: No task provided. Please provide a task description."

        if not goals:
            return "Error: No goals provided. Please provide a list of goals/steps."

        # Parse goals into list
        goal_lines = [line.strip() for line in goals.split('\n') if line.strip()]

        # Store plan in working memory
        plan_data = {
            'task': task,
            'goals': goal_lines,
            'rationale': rationale,
            'created_at': len(session.messages),
            'completed_goals': []
        }

        session.working_memory['_current_plan'] = {
            'value': plan_data,
            'description': f"Current plan for: {task}"
        }

        logger.info(f"✅ Created plan with {len(goal_lines)} goals for: {task}")

        # Format response
        result_parts = [
            f"✅ Plan created for: {task}\n",
            f"Goals ({len(goal_lines)} steps):"
        ]

        for i, goal in enumerate(goal_lines, 1):
            # Remove leading numbers if present (e.g., "1. " -> "")
            clean_goal = goal
            if goal and goal[0].isdigit() and '. ' in goal[:4]:
                clean_goal = goal.split('. ', 1)[1] if '. ' in goal else goal
            result_parts.append(f"  {i}. {clean_goal}")

        if rationale:
            result_parts.append(f"\nRationale: {rationale}")

        result_parts.append("\nPlan stored in memory. Work through these goals sequentially, marking progress as you go.")

        return "\n".join(result_parts)

    except Exception as e:
        logger.error(f"❌ Error creating plan: {e}")
        return f"Error creating plan: {str(e)}"


async def handle_search_playbooks(session_id: str, tool_call: Dict[str, Any]) -> str:
    """Handle search_playbooks tool - search playbook catalog."""
    logger.info(f"📚 Searching playbooks for session {session_id}")

    try:
        # Extract query from parameters
        params = tool_call.get('parameters', {})
        query = params.get('query', '')

        if not query:
            return "Error: No search query provided. Please provide a query describing what you want to do."

        # Get playbook registry and executor
        registry = get_playbook_registry()
        executor = get_playbook_executor()

        # Search for matching playbooks
        matches = registry.search_by_keywords(query)

        # Format results for AI
        result = executor.format_playbook_search_results(matches)
        logger.info(f"✅ Found {len(matches)} playbooks matching '{query}'")

        return f"Playbook search results:\n\n{result}"

    except Exception as e:
        logger.error(f"❌ Error searching playbooks: {e}")
        return f"Error searching playbooks: {str(e)}"

async def handle_execute_playbook(session_id: str, tool_call: Dict[str, Any], websocket: WebSocket):
    """Handle execute_playbook tool - execute a playbook's steps."""
    logger.info(f"🎬 Executing playbook for session {session_id}")

    try:
        # Extract parameters
        params = tool_call.get('parameters', {})
        playbook_name = params.get('name', '')
        variables = params.get('variables', {})

        if not playbook_name:
            error_msg = "Error: No playbook name provided."
            session = await session_manager.get_session(session_id, auto_recover=False)
            await session.add_message("assistant", error_msg)
            return

        # Get playbook
        registry = get_playbook_registry()
        playbook = registry.get_playbook(playbook_name)

        if not playbook:
            error_msg = f"Error: Playbook '{playbook_name}' not found."
            session = await session_manager.get_session(session_id, auto_recover=False)
            await session.add_message("assistant", error_msg)
            return

        # Get execution plan
        executor = get_playbook_executor()
        plan = executor.get_execution_plan(playbook, variables)

        if not plan.get('success'):
            error_msg = f"Error: {plan.get('error', 'Failed to create execution plan')}"
            session = await session_manager.get_session(session_id, auto_recover=False)
            await session.add_message("assistant", error_msg)
            return

        logger.info(f"📋 Executing playbook '{playbook_name}' with {len(plan['steps'])} steps")

        # Execute each step by sending it through the normal tool approval flow
        for step in plan['steps']:
            # Create a tool call for execute_command
            execute_command_tool = {
                "name": "execute_command",
                "parameters": step['parameters']['args']
            }

            # Send through normal approval flow
            await request_tool_approval(session_id, execute_command_tool, websocket)

        logger.info(f"✅ Playbook '{playbook_name}' execution initiated")

    except Exception as e:
        logger.error(f"❌ Error executing playbook: {e}")
        error_msg = f"Error executing playbook: {str(e)}"
        session = await session_manager.get_session(session_id, auto_recover=False)
        await session.add_message("assistant", error_msg)

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
        session = await session_manager.get_session(session_id, auto_recover=False)
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


async def auto_extract_knowledge(session, message: Dict[str, Any], result: Dict[str, Any]) -> None:
    """
    SERVER-SIDE INTELLIGENCE: Automatically extract and store important information.

    When key files are read (README, package.json, etc.), automatically extract
    critical information and store it in session memory so it's available even
    if the conversation context gets truncated.
    """
    try:
        # Get the file path that was read
        data = result.get("data", {})
        metadata = result.get("metadata", {})
        content = data.get("content", "")
        path = metadata.get("path", "").lower()

        if not content:
            return

        # Detect README files
        if "readme" in path:
            logger.info(f"🧠 Auto-extracting knowledge from README: {path}")

            # Extract proxy/websocket configuration
            import re
            proxy_patterns = [
                r'proxy.*?\n.*?```[\s\S]*?```',  # Proxy section with code
                r'websocket.*?\n.*?```[\s\S]*?```',  # WebSocket section with code
                r'server\.proxy.*?```[\s\S]*?```',  # Vite server.proxy
            ]

            proxy_configs = []
            for pattern in proxy_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                proxy_configs.extend(matches)

            if proxy_configs:
                # Store the first/best proxy config
                proxy_info = proxy_configs[0][:1000]  # Limit to 1000 chars
                session.working_memory["readme-proxy-config"] = {
                    'value': proxy_info,
                    'description': f'Proxy configuration extracted from {path}',
                    'stored_at': len(session.messages)
                }
                logger.info(f"✅ Auto-stored proxy config from README ({len(proxy_info)} chars)")

            # Extract installation commands
            install_patterns = [
                r'npm install [^\n]+',
                r'yarn add [^\n]+',
                r'pnpm add [^\n]+',
            ]

            install_commands = []
            for pattern in install_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                install_commands.extend(matches)

            if install_commands:
                commands_str = "\n".join(install_commands[:5])  # Store up to 5 commands
                session.working_memory["readme-install-commands"] = {
                    'value': commands_str,
                    'description': f'Installation commands from {path}',
                    'stored_at': len(session.messages)
                }
                logger.info(f"✅ Auto-stored {len(install_commands)} install commands from README")

        # Detect package.json
        elif "package.json" in path:
            logger.info(f"🧠 Auto-extracting knowledge from package.json")
            import json
            try:
                pkg = json.loads(content)

                # Store dependencies
                if "dependencies" in pkg:
                    deps = list(pkg["dependencies"].keys())[:10]  # Top 10
                    session.working_memory["package-dependencies"] = {
                        'value': json.dumps(deps),
                        'description': 'Key dependencies from package.json',
                        'stored_at': len(session.messages)
                    }
                    logger.info(f"✅ Auto-stored {len(deps)} dependencies from package.json")

                # Store scripts
                if "scripts" in pkg:
                    scripts = list(pkg["scripts"].keys())
                    session.working_memory["package-scripts"] = {
                        'value': json.dumps(scripts),
                        'description': 'Available npm scripts',
                        'stored_at': len(session.messages)
                    }
                    logger.info(f"✅ Auto-stored {len(scripts)} scripts from package.json")

            except json.JSONDecodeError:
                logger.warning(f"⚠️ Could not parse package.json content")

    except Exception as e:
        logger.error(f"❌ Error in auto_extract_knowledge: {e}", exc_info=True)
        # Don't fail the whole operation if extraction fails


async def handle_tool_result(session_id: str, message: Dict[str, Any]) -> Dict[str, Any]:
    """Handle tool execution result from client."""
    result = message["result"]
    execution_id = message["execution_id"]
    tool_name = message.get("tool_name", "unknown")

    logger.info(f"🛠️ Tool result received for execution {execution_id}: {result['status']}")

    # Check if this is attempt_completion - if so, stop the loop
    if tool_name == "attempt_completion" and result.get("status") == "success":
        logger.info(f"✅ Task completion confirmed - stopping agentic loop")
        return {
            "type": "task_completed",
            "session_id": session_id,
            "execution_id": execution_id,
            "status": "completed"
        }

    # Add tool result to session for automatic agentic loop
    session = await session_manager.get_session(session_id, auto_recover=False)
    if session:
        # Add a detailed tool result that AI can understand and act on
        tool_summary = format_tool_result_for_ai(result)
        await session.add_message("assistant", tool_summary)

        logger.info(f"✅ Tool result added to conversation")
        logger.info(f"🔍 Current conversation has {len(session.messages)} messages")

        # SERVER-SIDE INTELLIGENCE: Auto-extract important information
        # When key files are read, automatically extract and store critical information
        if tool_name == "read_file" and result.get("status") == "success":
            await auto_extract_knowledge(session, message, result)

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
  TRUSTGRAPH_URL                      # TrustGraph server URL
  TRUSTGRAPH_FLOW                     # TrustGraph flow ID
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

    # Update AI provider manager's default provider
    ai_provider_manager.default_provider = args.provider

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