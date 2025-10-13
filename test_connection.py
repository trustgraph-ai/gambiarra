#!/usr/bin/env python3
"""
Simple test script to verify Gambiarra server/client connection.
"""

import asyncio
import json
import websockets

async def test_connection():
    """Test connection to Gambiarra server."""
    uri = "ws://127.0.0.1:8010/ws"

    print(f"🔌 Connecting to {uri}...")

    try:
        async with websockets.connect(uri) as websocket:
            print("✅ Connected!")

            # Send connect message
            connect_msg = {
                "type": "connect",
                "client_version": "1.0.0"
            }
            await websocket.send(json.dumps(connect_msg))
            print("📤 Sent connect message")

            # Receive response
            response = await websocket.recv()
            data = json.loads(response)
            print(f"📥 Received: {data['type']}")
            print(f"   Connection ID: {data.get('connection_id', 'N/A')[:16]}...")
            print(f"   Available providers: {data['server_info']['supported_providers']}")

            # Create session
            session_msg = {
                "type": "create_session",
                "config": {
                    "working_directory": "/tmp/test"
                }
            }
            await websocket.send(json.dumps(session_msg))
            print("📤 Sent create_session message")

            # Receive session response
            response = await websocket.recv()
            data = json.loads(response)
            print(f"📥 Received: {data['type']}")
            if data['type'] == 'session_created':
                session_id = data['session_id']
                print(f"   Session ID: {session_id[:16]}...")
                print(f"   Status: {data['status']}")

                # Send a test message
                user_msg = {
                    "type": "user_message",
                    "message": {
                        "content": "Hello! Can you introduce yourself and tell me what you can do?"
                    }
                }
                await websocket.send(json.dumps(user_msg))
                print("📤 Sent user message: 'Hello! Can you introduce yourself...'")

                # Receive AI response chunks
                print("📥 Receiving AI response...")
                full_response = ""
                chunk_count = 0

                while True:
                    response = await websocket.recv()
                    data = json.loads(response)

                    if data['type'] == 'ai_response_chunk':
                        chunk = data['chunk']
                        if chunk['is_complete']:
                            print(f"✅ Response complete ({chunk_count} chunks, {len(full_response)} chars)")
                            break
                        else:
                            full_response += chunk['content']
                            chunk_count += 1
                            if chunk_count <= 3:
                                print(f"   Chunk {chunk_count}: {len(chunk['content'])} chars")
                    elif data['type'] == 'error':
                        print(f"❌ Error: {data['error']}")
                        break

                if full_response:
                    print(f"\n📝 AI Response Preview:")
                    print(f"   {full_response[:200]}...")

                print("\n✅ Test completed successfully!")
                return True

    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_connection())
    exit(0 if success else 1)
