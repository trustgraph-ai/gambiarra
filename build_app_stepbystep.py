#!/usr/bin/env python3
"""
Build a complete TrustGraph React chat app using step-by-step prompts.
"""

############################################################################
#
# NOTE TO DEVELOPERS!  THIS CODE EMULATES AN END-USER.  IT IS NOT A SOLUTION.
# IT DOES NOT MAKE SENSE TO ADD CODE BUILDING LOGIC TO THIS SCRIPT
#
############################################################################

import asyncio
import json
import subprocess
import websockets
from pathlib import Path

class AppBuilder:
    """Automated client that builds an app step-by-step."""

    def __init__(self, workspace):
        self.workspace = Path(workspace)
        self.session_id = None
        self.prompts = [
            """Create a React application in this directory (the current directory). Use:
- Typescript
- Vite

Use this command exactly (the printf handles the interactive prompt):

printf "y\\n" | npx --yes create-vite@latest . --template react-ts

This creates the app in the current directory, not a subdirectory.""",

            """Downgrade to React 18 by running these commands:

npm install react@18 react-dom@18
npm install @types/react@18 @types/react-dom@18 --save-dev

This is required for @trustgraph/react-state compatibility.""",

            """Install @trustgraph/react-state and read its README to learn how to configure the websocket proxy.""",

            """Update vite.config.ts to add the websocket proxy configuration for TrustGraph.

Based on the README you just read, add a server.proxy configuration that proxies /tg-sse to ws://localhost:8088/tg-sse with websocket support enabled.""",

            """Now replace the React app placeholder page with a real application:

Chat Interface: Build a classic conversational UI with:
- A scrollable message list displaying the conversation history
- User messages displayed on the right side in blue
- Agent responses displayed on the left side in dark gray
- Auto-scrolling to the latest message
- An input field for message entry at the bottom
- A "Send" button that also responds to the Enter/Return key
- Loading state showing "Sending..." on the button while processing
- Disabled input during message submission

Use the TrustGraph GraphRAG service to provide messages. Use collection 'default' flow 'default'. Operate as user 'trustgraph'.""",

            "Run npm build and fix any problems",

            "It overflows the screen top and bottom, can you fix?"
        ]

    async def execute_command(self, command, timeout=30):
        """Execute a shell command in the workspace."""
        # Skip npm run dev - it starts a server that doesn't exit
        if "npm run dev" in command or "npm dev" in command:
            print(f"      $ {command}")
            print(f"      ⏭️  Skipped (dev server - run manually)")
            return {
                "status": "success",
                "data": {"output": "Skipped: dev servers should be run manually", "exit_code": 0},
                "metadata": {"command": command, "skipped": True}
            }

        print(f"      $ {command}")
        print(f"      ⏱️  Timeout: {timeout}s")
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=str(self.workspace),
                stdin=subprocess.DEVNULL,  # Prevent hanging on interactive prompts
                capture_output=True,
                text=True,
                timeout=timeout
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

    async def find_file(self, path=".", pattern="*", max_depth=3):
        """Find files matching a glob pattern."""
        target = self.workspace / path
        try:
            from pathlib import Path
            import fnmatch

            matches = []

            def search_dir(directory, depth=0):
                if depth > max_depth:
                    return
                try:
                    # Optimization: Check current directory first before recursing
                    files = []
                    dirs = []
                    for item in directory.iterdir():
                        if item.is_file():
                            if fnmatch.fnmatch(item.name, pattern):
                                relative_path = item.relative_to(self.workspace)
                                matches.append({
                                    "path": str(relative_path),
                                    "name": item.name,
                                    "size": item.stat().st_size
                                })
                        elif item.is_dir() and depth < max_depth:
                            dirs.append(item)

                    # Only recurse if we didn't find matches at this level
                    if not matches:
                        for subdir in dirs:
                            search_dir(subdir, depth + 1)
                except PermissionError:
                    pass  # Skip directories we can't access

            search_dir(target)

            return {
                "status": "success",
                "data": {"matches": matches, "count": len(matches)},
                "metadata": {"path": str(path), "pattern": pattern, "max_depth": max_depth}
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "data": None,
                "metadata": {"path": str(path), "pattern": pattern}
            }

    async def read_file(self, path):
        """Read file contents."""
        target = self.workspace / path
        try:
            content = target.read_text()
            return {
                "status": "success",
                "data": {"content": content},
                "metadata": {"path": str(path), "size": len(content)}
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "data": None,
                "metadata": {"path": str(path)}
            }

    async def write_file(self, path, content):
        """Write file contents."""
        target = self.workspace / path
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
            return {
                "status": "success",
                "data": {"bytes_written": len(content)},
                "metadata": {"path": str(path)}
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "data": None,
                "metadata": {"path": str(path)}
            }

    async def handle_prompt(self, ws, prompt_num, prompt):
        """Send a prompt and handle all responses until completion."""
        print(f"\n{'='*80}")
        print(f"📝 STEP {prompt_num + 1}/{len(self.prompts)}")
        print(f"{'='*80}")
        print(f"Prompt: {prompt[:100]}..." if len(prompt) > 100 else f"Prompt: {prompt}")
        print()

        # Send the prompt
        await ws.send(json.dumps({
            "type": "user_message",
            "message": {"content": prompt}
        }))

        response_text = ""

        while True:
            try:
                msg_text = await asyncio.wait_for(ws.recv(), timeout=180)
                msg = json.loads(msg_text)

                if msg['type'] == 'ai_response_chunk':
                    chunk = msg['chunk']
                    if chunk['is_complete']:
                        if response_text:
                            print(f"🤖 AI response complete ({len(response_text)} chars)")
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
                        timeout = params['args'].get('timeout', 30)  # Default 30s
                        # Ensure timeout is a number (could be string from JSON)
                        timeout = float(timeout) if timeout is not None else 30.0
                        result = await self.execute_command(command, timeout)
                    elif tool_name == 'list_files':
                        path = params['args'].get('path', '.')
                        result = await self.list_files(path)
                    elif tool_name == 'find_file':
                        path = params['args'].get('path', '.')
                        pattern = params['args'].get('pattern', '*')
                        max_depth = int(params['args'].get('max_depth', 3))
                        result = await self.find_file(path, pattern, max_depth)
                    elif tool_name == 'read_file':
                        path = params['args'].get('path', '')
                        result = await self.read_file(path)
                    elif tool_name == 'write_file':
                        path = params['args'].get('path', '')
                        content = params['args'].get('content', '')
                        result = await self.write_file(path, content)
                    elif tool_name == 'attempt_completion':
                        print(f"   ✅ Step complete!")
                        result = {
                            "status": "success",
                            "data": {"completed": True},
                            "metadata": {}
                        }
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

                    # If it was attempt_completion, we're done with this step
                    if tool_name == 'attempt_completion':
                        print()
                        return True

                elif msg['type'] == 'task_completed':
                    print(f"✅ Task completed!")
                    return True

                elif msg['type'] == 'error':
                    print(f"❌ Error: {msg['error']['message']}")
                    return False

            except asyncio.TimeoutError:
                print("⏱️  Step done (timeout)")
                return True
            except Exception as e:
                print(f"❌ Error: {e}")
                return False

    async def run(self):
        """Run the app builder."""
        uri = "ws://127.0.0.1:8010/ws"

        print(f"🏗️  Building TrustGraph React Chat App")
        print(f"📂 Workspace: {self.workspace}")
        print(f"🔗 Server: {uri}")
        print(f"📋 Steps: {len(self.prompts)}")
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

            # Execute each prompt step-by-step
            for i, prompt in enumerate(self.prompts):
                success = await self.handle_prompt(ws, i, prompt)
                if not success:
                    print(f"\n❌ Failed at step {i + 1}, stopping")
                    break

                # Small delay between steps
                await asyncio.sleep(1)

            print()
            print("="*80)
            print("📊 Final workspace contents:")
            print("="*80)
            for item in sorted(self.workspace.iterdir()):
                print(f"   {'📁' if item.is_dir() else '📄'} {item.name}")

async def main():
    workspace = Path.cwd() / "WORKSPACE"
    workspace.mkdir(exist_ok=True)

    builder = AppBuilder(workspace)
    await builder.run()

if __name__ == "__main__":
    asyncio.run(main())
