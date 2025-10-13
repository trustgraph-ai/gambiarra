"""
Smart Command Execution Handler.

This module orchestrates intelligent command execution by combining:
- Pre-execution validation
- Hang detection
- Interactive prompt handling
- Real-time monitoring
- Bidirectional server-client communication

The SmartExecutionHandler replaces the basic command execution with
a sophisticated system that can handle the complexities of real-world
command execution scenarios.
"""

import asyncio
import subprocess
import os
import signal
from typing import Optional, Callable, Dict, Any
from datetime import datetime
import logging

from .command_knowledge import CommandKnowledgeBase
from .hang_detector import AdaptiveHangDetector, HangSignal
from gambiarra.server.core.protocol.execution_messages import (
    ExecuteRequestMessage,
    ValidationRequestMessage,
    ValidationResultMessage,
    InputRequiredMessage,
    ExecutionStartedMessage,
    ExecutionOutputMessage,
    ExecutionCompletedMessage,
    ExecutionFailedMessage,
    HangDetectedMessage,
    CommandRiskLevel
)

logger = logging.getLogger(__name__)


class SmartExecutionHandler:
    """
    Intelligent command execution handler.

    Orchestrates pre-execution validation, hang detection, and
    bidirectional communication with the server during execution.
    """

    def __init__(
        self,
        knowledge_base: Optional[CommandKnowledgeBase] = None,
        send_message: Optional[Callable] = None
    ):
        """
        Initialize smart execution handler.

        Args:
            knowledge_base: Command knowledge base for validation
            send_message: Callback to send messages to server
        """
        self.knowledge_base = knowledge_base or CommandKnowledgeBase()
        self.send_message = send_message
        self.active_processes: Dict[str, subprocess.Popen] = {}
        self.hang_detectors: Dict[str, AdaptiveHangDetector] = {}

    async def validate_command(
        self,
        request: ValidationRequestMessage
    ) -> ValidationResultMessage:
        """
        Validate a command before execution.

        Args:
            request: Validation request from server

        Returns:
            ValidationResultMessage with validation results
        """
        command = request.command
        cwd = request.cwd or os.getcwd()
        intent = request.intent

        # Analyze command using knowledge base
        risk_level, issues, suggested_command = self.knowledge_base.analyze_command(
            command, cwd, intent
        )

        # Estimate duration
        estimated_duration = self.knowledge_base.estimate_duration(command)

        # Determine if command can be executed
        can_execute = all(issue.severity != "error" for issue in issues)

        # Check if command requires input
        requires_input = any(
            issue.issue_type.value == "interactive_prompt" for issue in issues
        )

        # Build result message
        message = None
        if not can_execute:
            error_messages = [
                issue.message for issue in issues if issue.severity == "error"
            ]
            message = "; ".join(error_messages)
        elif issues:
            warning_messages = [
                issue.message for issue in issues if issue.severity == "warning"
            ]
            if warning_messages:
                message = "; ".join(warning_messages)

        result = ValidationResultMessage(
            request_id=request.request_id,
            can_execute=can_execute,
            risk_level=risk_level,
            issues=issues,
            suggested_command=suggested_command,
            estimated_duration=estimated_duration,
            requires_input=requires_input,
            message=message
        )

        logger.info(
            f"Validated command '{command}': can_execute={can_execute}, "
            f"risk_level={risk_level.value}, issues={len(issues)}"
        )

        return result

    async def execute_command(
        self,
        request: ExecuteRequestMessage
    ) -> None:
        """
        Execute a command with intelligent monitoring.

        Args:
            request: Execution request from server
        """
        command = request.command
        cwd = request.cwd or os.getcwd()
        timeout = request.timeout
        request_id = request.request_id

        logger.info(f"Executing command: {command} (request_id={request_id})")

        # Optionally validate first
        if request.require_validation:
            validation_request = ValidationRequestMessage(
                command=command,
                cwd=cwd,
                intent=request.intent,
                request_id=request_id
            )
            validation_result = await self.validate_command(validation_request)

            if not validation_result.can_execute:
                # Send failure message
                await self._send_failed_message(
                    request_id,
                    f"Validation failed: {validation_result.message}",
                    error_type="validation_failed"
                )
                return

            # If suggested command provided, use it
            if validation_result.suggested_command:
                logger.info(
                    f"Using suggested command: {validation_result.suggested_command}"
                )
                command = validation_result.suggested_command

        # Create hang detector
        hang_detector = AdaptiveHangDetector(
            command=command,
            default_timeout=timeout
        )
        self.hang_detectors[request_id] = hang_detector

        try:
            # Start execution
            await self._execute_with_monitoring(
                request_id, command, cwd, hang_detector, request.environment
            )
        finally:
            # Cleanup
            if request_id in self.hang_detectors:
                del self.hang_detectors[request_id]
            if request_id in self.active_processes:
                del self.active_processes[request_id]

    async def _execute_with_monitoring(
        self,
        request_id: str,
        command: str,
        cwd: str,
        hang_detector: AdaptiveHangDetector,
        environment: Optional[Dict[str, str]] = None
    ) -> None:
        """Execute command with real-time monitoring."""
        start_time = datetime.now()

        # Prepare environment
        env = os.environ.copy()
        if environment:
            env.update(environment)

        # Ensure CI=true for non-interactive mode
        env['CI'] = 'true'

        try:
            # Start process
            process = subprocess.Popen(
                command,
                shell=True,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.PIPE,
                env=env,
                text=True,
                bufsize=1  # Line buffered
            )

            self.active_processes[request_id] = process

            # Send execution started message
            await self._send_started_message(request_id, command, cwd, process.pid)

            # Monitor execution
            await self._monitor_execution(request_id, process, hang_detector)

            # Wait for completion
            stdout, stderr = process.communicate(timeout=5)

            # Calculate duration
            duration = (datetime.now() - start_time).total_seconds()

            # Send completion message
            if process.returncode == 0:
                await self._send_completed_message(
                    request_id, process.returncode, stdout, stderr, duration
                )
            else:
                await self._send_failed_message(
                    request_id,
                    f"Command exited with code {process.returncode}",
                    exit_code=process.returncode,
                    stdout=stdout,
                    stderr=stderr,
                    error_type="execution_error"
                )

        except subprocess.TimeoutExpired:
            # Timeout - kill process
            process.kill()
            await self._send_failed_message(
                request_id,
                f"Command timed out after {hang_detector.default_timeout}s",
                error_type="timeout"
            )

        except Exception as e:
            logger.error(f"Execution error: {e}", exc_info=True)
            await self._send_failed_message(
                request_id,
                f"Execution error: {str(e)}",
                error_type="execution_error"
            )

    async def _monitor_execution(
        self,
        request_id: str,
        process: subprocess.Popen,
        hang_detector: AdaptiveHangDetector
    ) -> None:
        """Monitor command execution and detect hangs."""
        # Create async tasks for stdout and stderr monitoring
        loop = asyncio.get_event_loop()

        async def read_stream(stream, output_type: str):
            """Read from stream and send output messages."""
            while True:
                try:
                    # Read line (blocking, so run in executor)
                    line = await loop.run_in_executor(None, stream.readline)

                    if not line:
                        break  # EOF

                    # Record output in hang detector
                    hang_detector.record_output(line)

                    # Send output message
                    await self._send_output_message(request_id, output_type, line)

                except Exception as e:
                    logger.error(f"Error reading {output_type}: {e}")
                    break

        async def check_for_hangs():
            """Periodically check for hangs."""
            while process.poll() is None:
                await asyncio.sleep(5)  # Check every 5 seconds

                hang_signal = hang_detector.check_for_hang()
                if hang_signal:
                    logger.warning(
                        f"Hang detected: {hang_signal.reason} "
                        f"(confidence={hang_signal.confidence})"
                    )

                    # Send hang detected message
                    await self._send_hang_detected_message(
                        request_id, hang_signal
                    )

                    # Take action based on suggested action
                    if hang_signal.suggested_action == "abort" and hang_signal.confidence > 0.8:
                        logger.info("Auto-aborting due to high-confidence hang")
                        process.kill()
                        break

        # Run monitoring tasks
        try:
            await asyncio.gather(
                read_stream(process.stdout, "stdout"),
                read_stream(process.stderr, "stderr"),
                check_for_hangs()
            )
        except Exception as e:
            logger.error(f"Monitoring error: {e}", exc_info=True)

    async def abort_command(self, request_id: str, force: bool = False) -> bool:
        """
        Abort a running command.

        Args:
            request_id: Request ID of command to abort
            force: If True, use SIGKILL instead of SIGTERM

        Returns:
            True if command was aborted, False if not found
        """
        process = self.active_processes.get(request_id)
        if not process:
            return False

        try:
            if force:
                process.kill()  # SIGKILL
            else:
                process.terminate()  # SIGTERM

            logger.info(f"Aborted command (request_id={request_id}, force={force})")
            return True
        except Exception as e:
            logger.error(f"Error aborting command: {e}")
            return False

    # Message sending helpers

    async def _send_started_message(
        self,
        request_id: str,
        command: str,
        cwd: str,
        pid: Optional[int]
    ):
        """Send execution started message."""
        if self.send_message:
            message = ExecutionStartedMessage(
                request_id=request_id,
                command=command,
                cwd=cwd,
                pid=pid
            )
            await self.send_message(message)

    async def _send_output_message(
        self,
        request_id: str,
        output_type: str,
        content: str
    ):
        """Send execution output message."""
        if self.send_message:
            message = ExecutionOutputMessage(
                request_id=request_id,
                output_type=output_type,
                content=content
            )
            await self.send_message(message)

    async def _send_completed_message(
        self,
        request_id: str,
        exit_code: int,
        stdout: str,
        stderr: str,
        duration: float
    ):
        """Send execution completed message."""
        if self.send_message:
            message = ExecutionCompletedMessage(
                request_id=request_id,
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                duration=duration
            )
            await self.send_message(message)

    async def _send_failed_message(
        self,
        request_id: str,
        error: str,
        exit_code: Optional[int] = None,
        stdout: Optional[str] = None,
        stderr: Optional[str] = None,
        error_type: str = "execution_error"
    ):
        """Send execution failed message."""
        if self.send_message:
            message = ExecutionFailedMessage(
                request_id=request_id,
                error=error,
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                error_type=error_type
            )
            await self.send_message(message)

    async def _send_hang_detected_message(
        self,
        request_id: str,
        hang_signal: HangSignal
    ):
        """Send hang detected message."""
        if self.send_message:
            message = HangDetectedMessage(
                request_id=request_id,
                reason=hang_signal.reason,
                duration=(datetime.now() - hang_signal.detected_at).total_seconds(),
                last_output=hang_signal.prompt_text,
                suggested_action=hang_signal.suggested_action
            )
            await self.send_message(message)
