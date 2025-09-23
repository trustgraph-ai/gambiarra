#!/usr/bin/env python3
"""
Basic integration test for Gambiarra.
Tests the complete flow: Client -> Server -> Test LLM -> Client
"""

import asyncio
import json
import time
import tempfile
import os
from pathlib import Path

import websockets
import aiohttp


async def test_integration():
    """Test complete Gambiarra integration."""
    print("🧪 Starting Gambiarra Integration Test")

    # Create temporary workspace
    with tempfile.TemporaryDirectory() as temp_dir:
        workspace = Path(temp_dir)
        print(f"📁 Using workspace: {workspace}")

        # Create test files
        test_file = workspace / "test.py"
        test_file.write_text("print('Hello, Gambiarra!')\n")

        # Test 1: Check Test LLM Server
        print("\n1️⃣ Testing Test LLM Server...")
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get("http://localhost:8001/health") as response:
                    if response.status == 200:
                        health = await response.json()
                        print(f"✅ Test LLM Server: {health['status']}")
                    else:
                        print(f"❌ Test LLM Server health check failed: {response.status}")
                        return False
            except Exception as e:
                print(f"❌ Test LLM Server not running: {e}")
                return False

        # Test 2: Check Gambiarra Server
        print("\n2️⃣ Testing Gambiarra Server...")
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get("http://localhost:8000/health") as response:
                    if response.status == 200:
                        health = await response.json()
                        print(f"✅ Gambiarra Server: {health['status']}")
                    else:
                        print(f"❌ Gambiarra Server health check failed: {response.status}")
                        return False
            except Exception as e:
                print(f"❌ Gambiarra Server not running: {e}")
                return False

        # Test 3: WebSocket Connection
        print("\n3️⃣ Testing WebSocket Connection...")
        try:
            async with websockets.connect("ws://localhost:8000/ws") as websocket:
                # Send connect message
                connect_msg = {
                    "type": "connect",
                    "protocol_version": "1.0",
                    "client_info": {
                        "platform": "python",
                        "version": "1.0.0",
                        "capabilities": ["file_operations", "command_execution"]
                    }
                }

                await websocket.send(json.dumps(connect_msg))

                # Receive connected response
                response = await websocket.recv()
                connected_msg = json.loads(response)

                if connected_msg.get("type") == "connected":
                    print("✅ WebSocket connection established")
                else:
                    print(f"❌ Unexpected response: {connected_msg}")
                    return False

                # Test 4: Session Creation
                print("\n4️⃣ Testing Session Creation...")
                session_msg = {
                    "type": "create_session",
                    "config": {
                        "working_directory": str(workspace),
                        "ai_provider": "test",
                        "model": "gpt-4"
                    }
                }

                await websocket.send(json.dumps(session_msg))

                # Receive session created response
                response = await websocket.recv()
                session_response = json.loads(response)

                if session_response.get("type") == "session_created":
                    session_id = session_response.get("session_id")
                    print(f"✅ Session created: {session_id}")
                else:
                    print(f"❌ Session creation failed: {session_response}")
                    return False

                # Test 5: Send User Message
                print("\n5️⃣ Testing User Message with AI Response...")
                user_msg = {
                    "type": "user_message",
                    "session_id": session_id,
                    "message": {
                        "content": "read_file test.py",
                        "images": []
                    }
                }

                await websocket.send(json.dumps(user_msg))
                print("📤 Sent user message: 'read_file test.py'")

                # Collect responses
                responses = []
                timeout_count = 0
                max_timeout = 15  # 15 second timeout
                ai_completed = False
                tool_executed = False

                while timeout_count < max_timeout:
                    try:
                        response = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                        msg = json.loads(response)
                        responses.append(msg)

                        print(f"📨 Received: {msg.get('type', 'unknown')}")

                        # Check for tool approval request
                        if msg.get("type") == "tool_approval_request":
                            print("🔐 Tool approval requested")

                            # Auto-approve the tool
                            approval_response = {
                                "type": "tool_approval_response",
                                "session_id": session_id,
                                "request_id": msg["request_id"],
                                "decision": "approved",
                                "feedback": "Auto-approved for testing"
                            }

                            await websocket.send(json.dumps(approval_response))
                            print("✅ Tool approved automatically")

                        # Check for tool execution request
                        elif msg.get("type") == "execute_tool":
                            print("🔧 Tool execution requested")

                            tool = msg["tool"]
                            execution_id = msg["execution_id"]

                            # Simulate tool execution (read_file)
                            if tool["name"] == "read_file":
                                file_path = tool["parameters"]["path"]
                                try:
                                    # Read the file content
                                    content = test_file.read_text()

                                    tool_result = {
                                        "type": "tool_result",
                                        "session_id": session_id,
                                        "execution_id": execution_id,
                                        "result": {
                                            "status": "success",
                                            "data": content,
                                            "metadata": {
                                                "file_size": len(content),
                                                "line_count": len(content.split('\n')),
                                                "read_lines": "all"
                                            }
                                        }
                                    }

                                    await websocket.send(json.dumps(tool_result))
                                    print(f"✅ Tool executed: read {file_path}")
                                    tool_executed = True
                                    # Check if we've completed the full flow
                                    if ai_completed:
                                        break

                                except Exception as e:
                                    tool_result = {
                                        "type": "tool_result",
                                        "session_id": session_id,
                                        "execution_id": execution_id,
                                        "result": {
                                            "status": "error",
                                            "error": {
                                                "code": "FILE_READ_ERROR",
                                                "message": str(e)
                                            }
                                        }
                                    }

                                    await websocket.send(json.dumps(tool_result))
                                    print(f"❌ Tool failed: {e}")

                        # Check for AI response chunks
                        elif msg.get("type") == "ai_response_chunk":
                            chunk = msg["chunk"]
                            if chunk.get("is_complete"):
                                print("✅ AI response completed")
                                ai_completed = True
                                # Check if we've completed the full flow
                                if tool_executed:
                                    break
                            elif chunk.get("content"):
                                print(f"🧠 AI: {chunk['content'][:50]}...")

                        # Check for errors
                        elif msg.get("type") == "error":
                            error = msg.get("error", {})
                            print(f"❌ Server error: {error.get('code', 'UNKNOWN')} - {error.get('message', 'No message')}")
                            if error.get("details"):
                                print(f"   Details: {error['details']}")
                            break

                    except asyncio.TimeoutError:
                        timeout_count += 1
                        if timeout_count >= max_timeout:
                            print("⏰ Timeout waiting for responses")
                            break

                print(f"\n📊 Test Results:")
                print(f"   - Total responses: {len(responses)}")
                print(f"   - Response types: {[r.get('type') for r in responses]}")

                # Check if we got the expected flow
                response_types = [r.get('type') for r in responses]
                expected_types = ['tool_approval_request', 'execute_tool', 'ai_response_chunk']

                success = all(expected in response_types for expected in expected_types)

                if success:
                    print("✅ Integration test PASSED")
                    return True
                else:
                    print("❌ Integration test FAILED - missing expected responses")
                    return False

        except Exception as e:
            print(f"❌ WebSocket test failed: {e}")
            return False


async def main():
    """Main test function."""
    print("🚀 Gambiarra Integration Test Suite")
    print("=" * 50)

    print("\n📋 Prerequisites:")
    print("   1. Test LLM server running on localhost:8001")
    print("   2. Gambiarra server running on localhost:8000")
    print("   3. Both servers should be healthy")

    print("\n🔄 Starting tests...")

    success = await test_integration()

    print("\n" + "=" * 50)
    if success:
        print("🎉 ALL TESTS PASSED!")
        print("   Gambiarra is working correctly!")
    else:
        print("💥 TESTS FAILED!")
        print("   Check server logs for errors.")

    return success


if __name__ == "__main__":
    try:
        result = asyncio.run(main())
        exit(0 if result else 1)
    except KeyboardInterrupt:
        print("\n⏹️  Test interrupted by user")
        exit(1)
    except Exception as e:
        print(f"\n❌ Test suite error: {e}")
        exit(1)