#!/usr/bin/env python3
"""
Fully automated Gambiarra client that executes commands.
"""

import asyncio
import json
import subprocess
import websockets
from pathlib import Path

class AutomatedClient:
    """Automated client that executes commands."""

    def __init__(self, workspace):
        self.workspace = Path(workspace)
        self.session_id = None

    async def execute_command(self, command):
        """Execute a shell command in the workspace."""
        print(f"      $ {command}")
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=str(self.workspace),
                capture_output=True,
                text=True,
                timeout=60
            )
            output = result.stdout + result.stderr
            success = result.returncode == 0
            print(f"      {'✓' if success else '✗'} Exit code: {result.returncode}")
            if output:
                preview = output[:200].replace('\n', ' ')
                print(f"      Output: {preview}...")
            return {
                "status": "success" if success else "error",
                "data": {"output": output, "exit_code": result.returncode},
                "metadata": {"command": command}
            }
        except Exception as e:
            print(f"      ✗ Error: {e}")
            return {
                "status": "error",
                "error": str(e),
                "data": None,
                "metadata": {"command": command}
            }

    async def list_files(self, path="."):
        """List files in directory."""
        target = self.workspace / path
        try:
            files = []
            dirs = []
            for item in target.iterdir():
                if item.is_file():
                    files.append({"name": item.name, "size": item.stat().st_size})
                elif item.is_dir():
                    dirs.append({"name": item.name})
            return {
                "status": "success",
                "data": {"files": files, "directories": dirs},
                "metadata": {"path": str(path)}
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "data": None,
                "metadata": {"path": str(path)}
            }

    async def run(self):
        """Run the automated client."""
        uri = "ws://127.0.0.1:8010/ws"

        print(f"🤖 Automated Gambiarra Client")
        print(f"📂 Workspace: {self.workspace}")
        print(f"🔗 Server: {uri}")
        print()

        async with websockets.connect(uri) as ws:
            # Connect
            await ws.send(json.dumps({"type": "connect"}))
            msg = json.loads(await ws.recv())
            print(f"✅ Connected")

            # Create session
            await ws.send(json.dumps({
                "type": "create_session",
                "config": {"working_directory": str(self.workspace)}
            }))
            msg = json.loads(await ws.recv())
            self.session_id = msg['session_id']
            print(f"✅ Session created")
            print()

            # Send request
            request = """Please create a new Vite application using:

npx create-vite@latest my-app --template vanilla

Then list the files to show me what was created."""

            print(f"💬 Request: Create Vite app")
            await ws.send(json.dumps({
                "type": "user_message",
                "message": {"content": request}
            }))
            print()

            # Handle responses
            response_text = ""

            while True:
                try:
                    msg_text = await asyncio.wait_for(ws.recv(), timeout=30)
                    msg = json.loads(msg_text)

                    if msg['type'] == 'ai_response_chunk':
                        chunk = msg['chunk']
                        if chunk['is_complete']:
                            if response_text:
                                print(f"📝 AI: {response_text[:150]}...")
                                print()
                            # Don't break - continue to handle tool execution
                        else:
                            response_text += chunk['content']

                    elif msg['type'] == 'tool_approval_request':
                        tool = msg['tool']
                        print(f"🔧 Tool: {tool['name']}")
                        print(f"   Risk: {tool.get('risk_level', 'unknown')}")
                        print(f"   ✓ Auto-approving...")

                        # Auto-approve
                        await ws.send(json.dumps({
                            "type": "tool_approval_response",
                            "request_id": msg['request_id'],
                            "decision": "approved"
                        }))

                    elif msg['type'] == 'execute_tool':
                        tool = msg['tool']
                        tool_name = tool['name']
                        params = tool['parameters']

                        print(f"⚙️  Executing: {tool_name}")

                        # Execute the actual tool
                        if tool_name == 'execute_command':
                            command = params['args'].get('command', '')
                            result = await self.execute_command(command)
                        elif tool_name == 'list_files':
                            path = params['args'].get('path', '.')
                            result = await self.list_files(path)
                        else:
                            result = {
                                "status": "error",
                                "error": f"Tool {tool_name} not implemented",
                                "data": None,
                                "metadata": {}
                            }

                        # Send result back
                        await ws.send(json.dumps({
                            "type": "tool_result",
                            "execution_id": msg['execution_id'],
                            "tool_name": tool_name,
                            "result": result
                        }))
                        print()

                    elif msg['type'] == 'task_completed':
                        print(f"✅ Task completed!")
                        break

                    elif msg['type'] == 'error':
                        print(f"❌ Error: {msg['error']['message']}")
                        break

                except asyncio.TimeoutError:
                    print("⏱️  Done (timeout)")
                    break
                except Exception as e:
                    print(f"❌ Error: {e}")
                    break

            print()
            print("📊 Final workspace contents:")
            for item in self.workspace.iterdir():
                print(f"   {'📁' if item.is_dir() else '📄'} {item.name}")

async def main():
    workspace = Path.cwd() / "WORKSPACE"
    workspace.mkdir(exist_ok=True)

    client = AutomatedClient(workspace)
    await client.run()

if __name__ == "__main__":
    asyncio.run(main())
