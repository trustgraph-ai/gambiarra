"""
Command execution tools for Gambiarra client.
Implements secure shell command execution with output streaming.
"""

import asyncio
import os
import shlex
import subprocess
import time
from pathlib import Path
from typing import Dict, Any, Optional, Callable

from gambiarra.client.tools.base import CommandExecutionTool, ToolResult


class ExecuteCommandTool(CommandExecutionTool):
    """Execute shell commands with security controls."""

    @property
    def name(self) -> str:
        return "execute_command"

    @property
    def risk_level(self) -> str:
        return "high"

    def __init__(self, security_manager, stream_callback: Optional[Callable] = None):
        super().__init__(security_manager)
        self.stream_callback = stream_callback

    async def execute(self, parameters: Dict[str, Any]) -> ToolResult:
        """Execute shell command."""
        self.validate_parameters(parameters, ["command"], ["cwd", "timeout"])

        command = parameters["command"]
        cwd = parameters.get("cwd", ".")
        timeout = parameters.get("timeout", 30)

        try:
            # Validate working directory
            work_dir = Path(cwd)
            if not work_dir.exists():
                return ToolResult.create_error(
                    "DIRECTORY_NOT_FOUND",
                    f"Working directory '{cwd}' does not exist",
                    {"cwd": cwd}
                )

            # Resolve working directory
            resolved_cwd = self.security_manager.validate_path(str(work_dir))

            # Execute command
            start_time = time.time()
            result = await self._execute_with_streaming(command, resolved_cwd, timeout)
            execution_time = time.time() - start_time

            return ToolResult.success(
                data={
                    "stdout": result["stdout"],
                    "stderr": result["stderr"],
                    "exit_code": result["exit_code"],
                    "execution_time": round(execution_time, 2)
                },
                metadata={
                    "command": command,
                    "cwd": resolved_cwd,
                    "timeout": timeout
                }
            )

        except asyncio.TimeoutError:
            return ToolResult.create_error(
                "COMMAND_TIMEOUT",
                f"Command timed out after {timeout} seconds",
                {"command": command, "timeout": timeout}
            )
        except Exception as e:
            return ToolResult.create_error(
                "COMMAND_ERROR",
                str(e),
                {"command": command, "cwd": cwd}
            )

    async def _execute_with_streaming(self, command: str, cwd: str, timeout: int) -> Dict[str, Any]:
        """Execute command with streaming output."""
        try:
            # Split command safely
            cmd_parts = shlex.split(command)

            # Create process
            process = await asyncio.create_subprocess_exec(
                *cmd_parts,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self._get_safe_environment()
            )

            stdout_chunks = []
            stderr_chunks = []

            # Stream output
            async def read_stdout():
                while True:
                    line = await process.stdout.readline()
                    if not line:
                        break

                    line_str = line.decode('utf-8', errors='replace')
                    stdout_chunks.append(line_str)

                    # Send to stream callback if available
                    if self.stream_callback:
                        await self.stream_callback("stdout", line_str.rstrip())

            async def read_stderr():
                while True:
                    line = await process.stderr.readline()
                    if not line:
                        break

                    line_str = line.decode('utf-8', errors='replace')
                    stderr_chunks.append(line_str)

                    # Send to stream callback if available
                    if self.stream_callback:
                        await self.stream_callback("stderr", line_str.rstrip())

            # Wait for completion with timeout
            try:
                await asyncio.wait_for(
                    asyncio.gather(read_stdout(), read_stderr(), process.wait()),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                # Kill process on timeout
                process.kill()
                await process.wait()
                raise

            return {
                "stdout": "".join(stdout_chunks),
                "stderr": "".join(stderr_chunks),
                "exit_code": process.returncode
            }

        except FileNotFoundError:
            raise Exception(f"Command not found: {command.split()[0]}")
        except PermissionError:
            raise Exception(f"Permission denied executing command: {command}")

    def _get_safe_environment(self) -> Dict[str, str]:
        """Get a safe environment for command execution."""
        # Start with minimal environment
        safe_env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": os.environ.get("HOME", ""),
            "USER": os.environ.get("USER", ""),
            "SHELL": os.environ.get("SHELL", "/bin/sh"),
            "TERM": os.environ.get("TERM", "xterm"),
            "LANG": os.environ.get("LANG", "en_US.UTF-8"),
        }

        # Add development tools if available
        for var in ["PYTHON_PATH", "NODE_PATH", "JAVA_HOME", "CARGO_HOME"]:
            if var in os.environ:
                safe_env[var] = os.environ[var]

        return safe_env


class GitOperationTool(CommandExecutionTool):
    """Specialized tool for Git operations."""

    @property
    def name(self) -> str:
        return "git_operation"

    @property
    def risk_level(self) -> str:
        return "medium"

    async def execute(self, parameters: Dict[str, Any]) -> ToolResult:
        """Execute Git command."""
        self.validate_parameters(parameters, ["operation"], ["args", "cwd"])

        operation = parameters["operation"]
        args = parameters.get("args", [])
        cwd = parameters.get("cwd", ".")

        # Validate Git operation
        allowed_operations = [
            "status", "add", "commit", "push", "pull", "fetch", "checkout",
            "branch", "log", "diff", "show", "reset", "stash"
        ]

        if operation not in allowed_operations:
            return ToolResult.create_error(
                "INVALID_GIT_OPERATION",
                f"Git operation '{operation}' not allowed",
                {"allowed_operations": allowed_operations}
            )

        try:
            # Build Git command
            git_command = ["git", operation] + args
            command_str = " ".join(shlex.quote(arg) for arg in git_command)

            # Validate working directory
            work_dir = Path(cwd)
            if not work_dir.exists():
                return ToolResult.create_error(
                    "DIRECTORY_NOT_FOUND",
                    f"Working directory '{cwd}' does not exist",
                    {"cwd": cwd}
                )

            resolved_cwd = self.security_manager.validate_path(str(work_dir))

            # Check if it's a Git repository
            git_dir = work_dir / ".git"
            if not git_dir.exists():
                return ToolResult.create_error(
                    "NOT_A_GIT_REPO",
                    f"Directory '{cwd}' is not a Git repository",
                    {"cwd": cwd}
                )

            # Execute Git command
            process = await asyncio.create_subprocess_exec(
                *git_command,
                cwd=resolved_cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            return ToolResult.success(
                data={
                    "stdout": stdout.decode('utf-8', errors='replace'),
                    "stderr": stderr.decode('utf-8', errors='replace'),
                    "exit_code": process.returncode
                },
                metadata={
                    "operation": operation,
                    "args": args,
                    "cwd": resolved_cwd,
                    "command": command_str
                }
            )

        except Exception as e:
            return ToolResult.create_error(
                "GIT_ERROR",
                str(e),
                {"operation": operation, "cwd": cwd}
            )