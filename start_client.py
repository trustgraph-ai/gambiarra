#!/usr/bin/env python3
"""
Start Gambiarra client and interact with it.
"""

import asyncio
import sys
from pathlib import Path

# Add to path
sys.path.insert(0, str(Path(__file__).parent))

from gambiarra.client.main import GambiarraClient
from gambiarra.client.config import ClientConfig

async def main():
    """Start client and send initial message."""

    # Configure client
    config = ClientConfig(
        server_url="ws://127.0.0.1:8010/ws",
        workspace_root=str(Path.cwd() / "WORKSPACE"),
        auto_approve_reads=True,  # Auto-approve read operations
        interactive_mode=True  # Interactive approval for writes
    )

    print(f"🚀 Starting Gambiarra Client")
    print(f"📂 Workspace: {config.workspace_root}")
    print(f"🔗 Server: {config.server_url}")
    print()

    # Create and start client
    client = GambiarraClient(config, permissive_mode=False)

    try:
        # Connect to server
        await client.connect()
        print("✅ Connected to server")

        # Create session
        await client.create_session()
        print(f"✅ Session created: {client.session_id}")
        print()

        # Send initial message
        message = """Hello! I need you to create a new Vite app in this directory.

Please use 'npx create-vite@latest my-vite-app --template vanilla' to create a basic Vite application with vanilla JavaScript.

After creating it, please show me the directory structure so I can see what was created."""

        print(f"💬 Sending message:")
        print(f"   {message[:100]}...")
        print()

        await client.send_message(message)

        # Keep client running to handle responses
        print("⏳ Waiting for AI response and tool executions...")
        print("   (Client will handle tool approvals interactively)")
        print()

        # Run client event loop
        await client.run()

    except KeyboardInterrupt:
        print("\n⚠️ Interrupted by user")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if client.websocket:
            await client.websocket.close()
        print("👋 Client stopped")

if __name__ == "__main__":
    asyncio.run(main())
