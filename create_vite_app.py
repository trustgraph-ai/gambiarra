#!/usr/bin/env python3
"""
Automated script to create a Vite app using Gambiarra.
"""

import asyncio
import json
import websockets
from pathlib import Path

async def create_vite_app():
    """Connect to Gambiarra and request Vite app creation."""

    uri = "ws://127.0.0.1:8010/ws"
    workspace = str(Path.cwd() / "WORKSPACE")

    print(f"🚀 Gambiarra - Create Vite App")
    print(f"📂 Workspace: {workspace}")
    print(f"🔗 Server: {uri}")
    print()

    try:
        async with websockets.connect(uri) as websocket:
            # Connect
            await websocket.send(json.dumps({"type": "connect"}))
            response = json.loads(await websocket.recv())
            print(f"✅ Connected (connection_id: {response['connection_id'][:8]}...)")

            # Create session
            await websocket.send(json.dumps({
                "type": "create_session",
                "config": {"working_directory": workspace}
            }))
            response = json.loads(await websocket.recv())
            session_id = response['session_id']
            print(f"✅ Session created ({session_id[:8]}...)")
            print()

            # Send message to create Vite app
            message = """Please create a new Vite application in this directory using:

npx create-vite@latest my-vite-app --template vanilla

After creating it, list the files so I can see what was created."""

            print(f"💬 Sending request:")
            print(f"   {message.split('.')[0]}...")
            print()

            await websocket.send(json.dumps({
                "type": "user_message",
                "message": {"content": message}
            }))

            print("⏳ Waiting for AI response...")

            # Handle responses
            full_response = ""
            tool_requests = []

            while True:
                try:
                    response_text = await asyncio.wait_for(websocket.recv(), timeout=30.0)
                    response = json.loads(response_text)
                    msg_type = response['type']

                    if msg_type == 'ai_response_chunk':
                        chunk = response['chunk']
                        if chunk['is_complete']:
                            print(f"✅ AI response complete ({len(full_response)} chars)")
                            print()
                            if full_response:
                                # Show preview
                                preview = full_response[:300].replace('\n', ' ')
                                print(f"📝 AI said: {preview}...")
                                print()
                            break
                        else:
                            full_response += chunk['content']

                    elif msg_type == 'tool_approval_request':
                        tool = response['tool']
                        tool_requests.append(response)
                        print(f"🔧 Tool requested: {tool['name']}")
                        print(f"   Risk: {tool.get('risk_level', 'unknown')}")

                        # Auto-approve the tool
                        print(f"   ✓ Auto-approving...")
                        await websocket.send(json.dumps({
                            "type": "tool_approval_response",
                            "request_id": response['request_id'],
                            "decision": "approved"
                        }))

                    elif msg_type == 'execute_tool':
                        tool = response['tool']
                        print(f"⚙️  Executing: {tool['name']}")
                        # In a real client, this would execute the tool
                        # For now, just send mock success
                        await websocket.send(json.dumps({
                            "type": "tool_result",
                            "execution_id": response['execution_id'],
                            "tool_name": tool['name'],
                            "result": {
                                "status": "success",
                                "data": {"output": "Mock execution"},
                                "metadata": {}
                            }
                        }))

                    elif msg_type == 'error':
                        print(f"❌ Error: {response['error']['message']}")
                        break

                except asyncio.TimeoutError:
                    print("⏱️  Timeout waiting for response")
                    break
                except Exception as e:
                    print(f"❌ Error: {e}")
                    break

            print()
            print(f"📊 Summary:")
            print(f"   Tools requested: {len(tool_requests)}")
            print(f"   Response length: {len(full_response)} chars")

    except Exception as e:
        print(f"❌ Connection error: {e}")
        return False

    return True

if __name__ == "__main__":
    success = asyncio.run(create_vite_app())
    exit(0 if success else 1)
