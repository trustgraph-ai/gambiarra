#!/usr/bin/env python3
"""
Gambiarra Client - Main entry point for the secure AI coding assistant client.
Handles WebSocket communication and client-side tool execution.
"""

import asyncio
import json
import logging
import signal
import sys
import time
import uuid
from pathlib import Path
from typing import Dict, Any, Optional

import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

from client.tools.base import ToolManager
from client.tools.file_ops import ReadFileTool, WriteToFileTool, SearchFilesTool, ListFilesTool, InsertContentTool, SearchAndReplaceTool
from client.tools.command_ops import ExecuteCommandTool, GitOperationTool
from client.security.path_validator import PathValidator, SecurityError
from client.security.command_filter import CommandFilter
from client.security.approval_manager import ApprovalManager, ToolApprovalRequest, ApprovalResponse, ApprovalDecision
from client.security.smart_approval_manager import SmartApprovalManager, SmartApprovalConfig
from client.security.tool_repetition_detector import ToolRepetitionDetector
from client.security.tool_validator import ToolValidator, ValidationError
from client.config import ClientConfig

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class GambiarraClient:
    """Main Gambiarra client for secure AI coding assistance."""

    def __init__(self, config: ClientConfig):
        self.config = config
        self.websocket: Optional[websockets.WebSocketServerProtocol] = None
        self.session_id: Optional[str] = None
        self.running = False

        # Security components
        self.path_validator = PathValidator(config.workspace_root)
        self.command_filter = CommandFilter()
        self.tool_repetition_detector = ToolRepetitionDetector(limit=3)
        self.tool_validator = ToolValidator()

        # Tool management
        self.tool_manager = ToolManager(self._create_security_manager())

        # Smart approval system
        smart_config = SmartApprovalConfig(
            auto_approve_low_risk=True,
            auto_approve_read_operations=True,
            auto_approve_list_operations=True,
            mistake_limit_for_intervention=3
        )
        self.approval_manager = SmartApprovalManager(self._request_user_approval, smart_config)

        # Initialize tools
        self._initialize_tools()

        logger.info(f"🚀 Gambiarra Client initialized for workspace: {config.workspace_root}")

    def _create_security_manager(self):
        """Create security manager with path validator and command filter."""
        class SecurityManager:
            def __init__(self, path_validator, command_filter):
                self.path_validator = path_validator
                self.command_filter = command_filter

            def validate_path(self, path: str) -> str:
                return self.path_validator.validate_path(path)

            def is_command_allowed(self, command: str) -> bool:
                return self.command_filter.is_command_allowed(command)

        return SecurityManager(self.path_validator, self.command_filter)

    def _initialize_tools(self):
        """Initialize all client-side tools."""
        # File operation tools
        self.tool_manager.register_tool(ReadFileTool(self._create_security_manager()))
        self.tool_manager.register_tool(WriteToFileTool(self._create_security_manager()))
        self.tool_manager.register_tool(SearchFilesTool(self._create_security_manager()))
        self.tool_manager.register_tool(ListFilesTool(self._create_security_manager()))
        self.tool_manager.register_tool(InsertContentTool(self._create_security_manager()))
        self.tool_manager.register_tool(SearchAndReplaceTool(self._create_security_manager()))

        # Command execution tools
        self.tool_manager.register_tool(ExecuteCommandTool(
            self._create_security_manager(),
            stream_callback=self._handle_command_stream
        ))
        self.tool_manager.register_tool(GitOperationTool(self._create_security_manager()))

        logger.info(f"🔧 Initialized {len(self.tool_manager.list_tools())} tools")

    async def connect(self) -> None:
        """Connect to Gambiarra server."""
        try:
            logger.info(f"🔌 Connecting to {self.config.server_url}")

            self.websocket = await websockets.connect(self.config.server_url)
            self.running = True

            # Send initial connection message
            await self._send_message({
                "type": "connect",
                "protocol_version": "1.0",
                "client_info": {
                    "platform": "python",
                    "version": "1.0.0",
                    "capabilities": ["file_operations", "command_execution"]
                }
            })

            logger.info("✅ Connected to Gambiarra server")

        except Exception as e:
            logger.error(f"❌ Failed to connect: {e}")
            raise

    async def create_session(self) -> None:
        """Create a new session on the server."""
        try:
            session_config = {
                "working_directory": self.config.workspace_root,
                "auto_approve_reads": self.config.auto_approve_reads,
                "require_approval_for_writes": True,
                "max_concurrent_file_reads": 5
            }

            await self._send_message({
                "type": "create_session",
                "config": session_config
            })

            logger.info("🎯 Session creation requested")

        except Exception as e:
            logger.error(f"❌ Failed to create session: {e}")
            raise

    async def run(self) -> None:
        """Main client loop."""
        try:
            await self.connect()
            await self.create_session()

            logger.info("🏃 Client running - ready for interactive prompts")
            print("\n🤖 Gambiarra Interactive Client")
            print("=" * 60)
            print(f"📁 Workspace: {self.config.workspace_root}")
            print("🔧 Type your prompts and press Enter.")
            print("📝 Special commands:")
            print("   'quit', 'exit', 'q' - Exit the client")
            print("   'help' - Show examples")
            print("   'status' - Show session info")
            print("\n💡 Example prompts:")
            print("   • build hello world app")
            print("   • read the README.md file")
            print("   • list all Python files")
            print("   • change the program to add 2 numbers together")
            print("   • add Uvicorn framework")
            print("   • fix the missing host error")
            print("   • run the tests")
            print("=" * 60)

            # Start interactive mode
            await self._run_interactive()

        except KeyboardInterrupt:
            logger.info("⏹️  Client interrupted by user")
        except Exception as e:
            logger.error(f"❌ Client error: {e}")
        finally:
            await self._cleanup()

    async def _run_interactive(self):
        """Run interactive prompt mode."""
        import aioconsole

        prompt_count = 0

        while self.running:
            try:
                # Get user input
                user_input = await aioconsole.ainput("\n🤖 You: ")

                # Handle special commands
                cmd = user_input.lower().strip()

                if cmd in ['quit', 'exit', 'q', '']:
                    print("👋 Goodbye!")
                    self.running = False
                    break
                elif cmd == 'help':
                    self._show_help()
                    continue
                elif cmd == 'status':
                    self._show_status()
                    continue

                # Skip empty inputs
                if not user_input.strip():
                    continue

                prompt_count += 1
                print(f"\n🔥 PROMPT {prompt_count}: {user_input}")
                print("=" * 50)

                # Send prompt to server
                await self._send_user_message(user_input)

                # Wait for complete response including tool execution
                await self._wait_for_complete_response()

                print("\n✅ Prompt completed!")

            except EOFError:
                print("\n👋 Goodbye!")
                self.running = False
                break
            except Exception as e:
                logger.error(f"❌ Error in interactive mode: {e}")
                continue

    async def _wait_for_complete_response(self):
        """Wait for AI response and tool execution to complete."""
        ai_completed = False
        tools_executed = 0
        expected_tools = 0

        while self.running:
            try:
                message = await asyncio.wait_for(self.websocket.recv(), timeout=30.0)
                msg = json.loads(message)

                await self._handle_message(msg)

                # Track completion
                if msg.get("type") == "tool_approval_request":
                    expected_tools += 1
                elif msg.get("type") == "ai_response_chunk":
                    chunk = msg.get("chunk", {})
                    if chunk.get("is_complete"):
                        ai_completed = True
                        print("✅ AI response completed")
                        if expected_tools == 0:  # No tools expected
                            break
                elif msg.get("type") == "tool_result_received":
                    tools_executed += 1
                    print(f"✅ Tool {tools_executed}/{expected_tools} completed")
                    if ai_completed and tools_executed >= expected_tools:
                        break

            except asyncio.TimeoutError:
                logger.warning("⏰ Timeout waiting for response")
                break
            except ConnectionClosed:
                logger.info("🔌 Connection closed")
                break

    async def _handle_message(self, message: Dict[str, Any]) -> None:
        """Handle incoming WebSocket message."""
        message_type = message.get("type", "unknown")
        logger.debug(f"📨 Received message: {message_type}")

        try:
            if message_type == "connected":
                await self._handle_connected(message)

            elif message_type == "session_created":
                await self._handle_session_created(message)

            elif message_type == "tool_approval_request":
                await self._handle_tool_approval_request(message)

            elif message_type == "execute_tool":
                await self._handle_execute_tool(message)

            elif message_type == "ai_response_chunk":
                await self._handle_ai_response_chunk(message)

            elif message_type == "error":
                await self._handle_error(message)

            elif message_type == "tool_result_received":
                await self._handle_tool_result_received(message)

            else:
                logger.warning(f"🤷 Unknown message type: {message_type}")

        except Exception as e:
            logger.error(f"❌ Error handling {message_type}: {e}")

    async def _handle_connected(self, message: Dict[str, Any]) -> None:
        """Handle connection confirmation."""
        server_info = message.get("server_info", {})
        logger.info(f"✅ Connected to server version {server_info.get('version', 'unknown')}")
        logger.info(f"🔧 Available tools: {', '.join(server_info.get('available_tools', []))}")

    async def _handle_session_created(self, message: Dict[str, Any]) -> None:
        """Handle session creation confirmation."""
        self.session_id = message.get("session_id")

        # Reset tool repetition detector for new session
        self.tool_repetition_detector.reset()

        logger.info(f"🎯 Session created: {self.session_id}")
        print(f"🎯 Session created: {self.session_id}")

    async def _handle_tool_approval_request(self, message: Dict[str, Any]) -> None:
        """Handle tool approval request from server."""
        request_data = message["tool"]
        request_id = message["request_id"]

        tool_name = request_data["name"]
        parameters = request_data["parameters"]

        # 1. Validate tool parameters FIRST
        try:
            self.tool_validator.validate_tool_parameters(tool_name, parameters)
        except ValidationError as e:
            # Parameter validation failed - auto-deny
            logger.warning(f"🚫 Tool parameter validation failed: {e}")
            self.tool_validator.record_tool_error(tool_name, "validation_error", str(e), parameters)
            await self._send_message({
                "type": "tool_approval_response",
                "session_id": self.session_id,
                "request_id": request_id,
                "decision": "denied",
                "feedback": f"Parameter validation failed: {e}",
                "modified_parameters": {}
            })
            return

        # 2. Check for tool repetition
        repetition_result = self.tool_repetition_detector.check(tool_name, parameters)

        if not repetition_result.allow_execution:
            # Tool repetition detected - auto-deny
            logger.warning(f"🚫 Tool repetition detected: {repetition_result.ask_user['message_detail']}")
            self.tool_validator.record_tool_error(tool_name, "repetition_error", repetition_result.ask_user["message_detail"], parameters)
            await self._send_message({
                "type": "tool_approval_response",
                "session_id": self.session_id,
                "request_id": request_id,
                "decision": "denied",
                "feedback": repetition_result.ask_user["message_detail"],
                "modified_parameters": {}
            })
            return

        request = ToolApprovalRequest(
            request_id=request_id,
            tool_name=request_data["name"],
            parameters=request_data["parameters"],
            description=request_data["description"],
            risk_level=request_data["risk_level"],
            requires_approval=request_data["requires_approval"],
            session_id=self.session_id,
            timestamp=time.time()
        )

        # 3. Process approval with smart system (pass validator for mistake tracking)
        response = await self.approval_manager.request_approval(request, self.tool_validator)

        # Send response to server
        await self._send_message({
            "type": "tool_approval_response",
            "session_id": self.session_id,
            "request_id": request_id,
            "decision": response.decision.value,
            "feedback": response.feedback,
            "modified_parameters": response.modified_parameters
        })

    async def _handle_execute_tool(self, message: Dict[str, Any]) -> None:
        """Handle tool execution request from server."""
        tool_data = message["tool"]
        execution_id = message["execution_id"]

        tool_name = tool_data["name"]
        parameters = tool_data["parameters"]

        logger.info(f"🔧 Executing tool: {tool_name}")

        # Execute tool
        result = await self.tool_manager.execute_tool(tool_name, parameters)

        # Record success or failure in validator
        if result.status == "success":
            self.tool_validator.record_tool_success(tool_name)
        else:
            error_message = result.error.get("message", "Unknown error") if result.error else "Tool execution failed"
            self.tool_validator.record_tool_error(tool_name, "execution_error", error_message, parameters)

        # Send result back to server
        try:
            result_dict = result.to_dict()
            await self._send_message({
                "type": "tool_result",
                "session_id": self.session_id,
                "execution_id": execution_id,
                "result": result_dict
            })
        except Exception as e:
            logger.error(f"❌ Error serializing tool result: {e}")
            logger.error(f"Result type: {type(result)}")
            logger.error(f"Result dict: {result.to_dict()}")
            # Send a simplified result
            await self._send_message({
                "type": "tool_result",
                "session_id": self.session_id,
                "execution_id": execution_id,
                "result": {
                    "status": result.status,
                    "data": str(result.data) if result.data else None,
                    "metadata": {}
                }
            })

        logger.info(f"📤 Tool result sent: {result.status}")

    async def _handle_ai_response_chunk(self, message: Dict[str, Any]) -> None:
        """Handle streaming AI response chunk."""
        chunk = message["chunk"]
        content = chunk["content"]
        is_complete = chunk["is_complete"]

        # Display AI response
        if content:
            print(content, end="", flush=True)

        if is_complete:
            print()  # New line when complete

    async def _handle_error(self, message: Dict[str, Any]) -> None:
        """Handle error message from server."""
        error = message.get("error", {})
        logger.error(f"❌ Server error: {error.get('message', 'Unknown error')}")

    async def _handle_tool_result_received(self, message: Dict[str, Any]) -> None:
        """Handle tool result received acknowledgment from server."""
        execution_id = message.get("execution_id", "unknown")
        status = message.get("status", "unknown")
        logger.debug(f"✅ Server received tool result for execution {execution_id}: {status}")

    async def _send_message(self, message: Dict[str, Any]) -> None:
        """Send message to server."""
        if not self.websocket:
            raise RuntimeError("Not connected to server")

        await self.websocket.send(json.dumps(message))

    async def _send_user_message(self, content: str, images: list = None) -> None:
        """Send user message to server."""
        await self._send_message({
            "type": "user_message",
            "session_id": self.session_id,
            "message": {
                "content": content,
                "images": images or []
            }
        })

    async def _request_user_approval(self, request: ToolApprovalRequest) -> ApprovalResponse:
        """Request user approval for tool execution."""
        import aioconsole

        # Simple console-based approval for now
        print(f"\n🔐 APPROVAL REQUEST")
        print(f"Tool: {request.tool_name}")
        print(f"Risk Level: {request.risk_level}")
        print(f"Description: {request.description}")
        print(f"Parameters: {json.dumps(request.parameters, indent=2)}")

        while True:
            try:
                choice = await aioconsole.ainput("\nApprove? (y/n/m for modify): ")
                choice = choice.lower().strip()

                if choice in ['y', 'yes']:
                    return ApprovalResponse(
                        request_id=request.request_id,
                        decision=ApprovalDecision.APPROVED
                    )
                elif choice in ['n', 'no']:
                    feedback = await aioconsole.ainput("Reason for denial (optional): ")
                    feedback = feedback.strip()
                    return ApprovalResponse(
                        request_id=request.request_id,
                        decision=ApprovalDecision.DENIED,
                        feedback=feedback if feedback else None
                    )
                elif choice in ['m', 'modify']:
                    print("Parameter modification not implemented yet")
                    continue
                else:
                    print("Please enter y/n/m")
            except Exception as e:
                logger.error(f"❌ Error getting user input: {e}")
                # Default to deny for safety
                return ApprovalResponse(
                    request_id=request.request_id,
                    decision=ApprovalDecision.DENIED,
                    feedback="Error getting user input"
                )

    async def _handle_command_stream(self, stream_type: str, content: str) -> None:
        """Handle streaming command output."""
        prefix = "STDOUT" if stream_type == "stdout" else "STDERR"
        print(f"[{prefix}] {content}")

    async def _cleanup(self) -> None:
        """Clean up resources."""
        self.running = False

        if self.websocket:
            try:
                await self.websocket.close()
                logger.info("🔌 WebSocket connection closed")
            except Exception as e:
                logger.error(f"❌ Error closing WebSocket: {e}")

        logger.info("🧹 Client cleanup completed")

    def _show_help(self):
        """Show help information."""
        print("\n💡 Gambiarra Help")
        print("=" * 40)
        print("📝 File Operations:")
        print("   • read [filename] - Read a file")
        print("   • create [filename] - Create a file")
        print("   • list files - List files in directory")
        print("   • search for [pattern] - Search files")
        print("\n🔧 Development Tasks:")
        print("   • build hello world app")
        print("   • add error handling to [file]")
        print("   • refactor [function] in [file]")
        print("   • write tests for [file]")
        print("\n🌐 Web Development:")
        print("   • add FastAPI framework")
        print("   • create REST API")
        print("   • add database connection")
        print("\n🐛 Debugging:")
        print("   • fix the [error type] error")
        print("   • debug [function] in [file]")
        print("   • run the tests")
        print("=" * 40)

    def _show_status(self):
        """Show current status."""
        print("\n📊 Gambiarra Status")
        print("=" * 40)
        print(f"🔌 Connection: {'✅ Connected' if self.websocket else '❌ Disconnected'}")
        print(f"🎯 Session: {self.session_id or '❌ No session'}")
        print(f"📁 Workspace: {self.config.workspace_root}")
        print(f"🏃 Running: {'✅ Yes' if self.running else '❌ No'}")
        print(f"🔧 Available tools: {len(self.tool_manager.list_tools())}")
        print("=" * 40)

    def send_user_input(self, message: str) -> None:
        """Send user input (for interactive use)."""
        if self.running and self.session_id:
            asyncio.create_task(self._send_user_message(message))


async def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Gambiarra AI Coding Assistant Client")
    parser.add_argument("--workspace", "-w", default=".", help="Workspace root directory")
    parser.add_argument("--server", "-s", default="ws://localhost:8000/ws", help="Server WebSocket URL")
    parser.add_argument("--debug", "-d", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    # Create client config
    config = ClientConfig(
        server_url=args.server,
        workspace_root=args.workspace
    )

    # Create and run client
    client = GambiarraClient(config)

    # Handle shutdown gracefully
    def signal_handler(signum, frame):
        logger.info("🛑 Shutdown signal received")
        client.running = False

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        await client.run()
    except Exception as e:
        logger.error(f"❌ Client failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())