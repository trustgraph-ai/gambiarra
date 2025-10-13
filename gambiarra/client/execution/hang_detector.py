"""
Hang Detection for Command Execution.

This module detects when commands are hanging (waiting for input, stuck in
infinite loops, or otherwise not progressing) and enables intelligent
recovery strategies.

Detection strategies:
1. Output stagnation: No output for extended period
2. Interactive prompt patterns: Recognized prompt text in output
3. CPU/memory stagnation: Process alive but not consuming resources
4. Known hang patterns: Specific commands with known hang behavior
"""

import time
import re
from typing import Optional, List, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class HangSignal:
    """Represents a detected hang signal."""

    signal_type: str  # "output_stagnation", "interactive_prompt", "resource_stagnation", "known_pattern"
    confidence: float  # 0.0 to 1.0
    reason: str
    detected_at: datetime
    suggested_action: str  # "abort", "wait", "input", "kill"
    prompt_text: Optional[str] = None  # For interactive_prompt type


class HangDetector:
    """
    Detects command hangs using multiple strategies.

    Monitors command execution and identifies when a command is likely
    hanging, providing suggestions for recovery.
    """

    # Interactive prompt patterns that indicate input is needed
    INTERACTIVE_PATTERNS = [
        r"^\? ",  # ? Select a framework
        r"^\[Y/n\]",  # [Y/n] prompt
        r"^\(y/N\)",  # (y/N) prompt
        r"^Press any key",
        r"^Enter ",
        r"^Password:",
        r"^username:",
        r"^Are you sure",
        r"^Do you want",
        r"^Would you like",
        r"^Continue\?",
        r"^Overwrite",
        r"^Ok to proceed",
        r"^Select.*:",
        r"^\>\s*$",  # Just a prompt character
    ]

    # Known hang patterns for specific commands
    KNOWN_HANG_PATTERNS = {
        "npm create vite": {
            "max_silent_duration": 10,
            "expected_prompts": ["Select a framework", "Select a variant"],
            "confidence": 0.9
        },
        "npx create-": {
            "max_silent_duration": 15,
            "expected_prompts": ["Ok to proceed"],
            "confidence": 0.9
        },
        "npm init": {
            "max_silent_duration": 5,
            "expected_prompts": ["package name"],
            "confidence": 0.95
        },
        "git clone": {
            "max_silent_duration": 300,  # Large repos can take time
            "expected_prompts": ["Username", "Password"],
            "confidence": 0.7
        }
    }

    def __init__(
        self,
        command: str,
        default_timeout: int = 60,
        output_stagnation_threshold: int = 30
    ):
        """
        Initialize hang detector.

        Args:
            command: The command being executed
            default_timeout: Default timeout in seconds before considering hang
            output_stagnation_threshold: Seconds without output before flagging
        """
        self.command = command
        self.default_timeout = default_timeout
        self.output_stagnation_threshold = output_stagnation_threshold

        self.start_time = datetime.now()
        self.last_output_time = datetime.now()
        self.last_output = ""
        self.total_output = ""
        self.output_lines: List[str] = []

        # Adjust thresholds based on known patterns
        self._adjust_for_known_patterns()

    def _adjust_for_known_patterns(self):
        """Adjust detection thresholds based on known command patterns."""
        for pattern, config in self.KNOWN_HANG_PATTERNS.items():
            if pattern in self.command:
                self.output_stagnation_threshold = config["max_silent_duration"]
                break

    def record_output(self, output: str):
        """
        Record new output from the command.

        Args:
            output: New output text
        """
        self.last_output = output
        self.total_output += output
        self.last_output_time = datetime.now()

        # Split into lines for analysis
        new_lines = output.split('\n')
        self.output_lines.extend(new_lines)

        # Keep only last 100 lines to avoid memory issues
        if len(self.output_lines) > 100:
            self.output_lines = self.output_lines[-100:]

    def check_for_hang(self) -> Optional[HangSignal]:
        """
        Check if the command is hanging.

        Returns:
            HangSignal if hang detected, None otherwise
        """
        now = datetime.now()

        # Strategy 1: Check for interactive prompts in recent output
        prompt_signal = self._check_interactive_prompt()
        if prompt_signal:
            return prompt_signal

        # Strategy 2: Check for output stagnation
        stagnation_signal = self._check_output_stagnation(now)
        if stagnation_signal:
            return stagnation_signal

        # Strategy 3: Check for known hang patterns
        pattern_signal = self._check_known_patterns(now)
        if pattern_signal:
            return pattern_signal

        # Strategy 4: Check overall timeout
        timeout_signal = self._check_timeout(now)
        if timeout_signal:
            return timeout_signal

        return None

    def _check_interactive_prompt(self) -> Optional[HangSignal]:
        """Check if recent output contains interactive prompt patterns."""
        if not self.output_lines:
            return None

        # Check last few lines for interactive patterns
        recent_lines = self.output_lines[-5:]

        for line in recent_lines:
            line = line.strip()
            if not line:
                continue

            for pattern in self.INTERACTIVE_PATTERNS:
                if re.search(pattern, line, re.IGNORECASE | re.MULTILINE):
                    return HangSignal(
                        signal_type="interactive_prompt",
                        confidence=0.95,
                        reason=f"Interactive prompt detected: '{line}'",
                        detected_at=datetime.now(),
                        suggested_action="input",
                        prompt_text=line
                    )

        return None

    def _check_output_stagnation(self, now: datetime) -> Optional[HangSignal]:
        """Check if output has been stagnant for too long."""
        time_since_output = (now - self.last_output_time).total_seconds()

        if time_since_output > self.output_stagnation_threshold:
            # Determine if this is likely waiting for input or truly hung
            has_output = bool(self.total_output.strip())

            if not has_output:
                # No output at all - might be waiting for something
                confidence = 0.6
                reason = f"No output for {time_since_output:.1f}s since start"
                suggested_action = "wait"
            else:
                # Had output before, now silent
                confidence = 0.8
                reason = f"No output for {time_since_output:.1f}s (last: '{self.last_output[:50]}')"
                suggested_action = "abort"

            return HangSignal(
                signal_type="output_stagnation",
                confidence=confidence,
                reason=reason,
                detected_at=now,
                suggested_action=suggested_action
            )

        return None

    def _check_known_patterns(self, now: datetime) -> Optional[HangSignal]:
        """Check for known hang patterns specific to the command."""
        for pattern, config in self.KNOWN_HANG_PATTERNS.items():
            if pattern not in self.command:
                continue

            # Check if expected prompts appear in output
            for expected_prompt in config.get("expected_prompts", []):
                if expected_prompt.lower() in self.total_output.lower():
                    return HangSignal(
                        signal_type="known_pattern",
                        confidence=config["confidence"],
                        reason=f"Known interactive pattern for '{pattern}': waiting for input",
                        detected_at=now,
                        suggested_action="input",
                        prompt_text=expected_prompt
                    )

            # Check if silent for too long based on known pattern
            time_since_output = (now - self.last_output_time).total_seconds()
            if time_since_output > config["max_silent_duration"]:
                return HangSignal(
                    signal_type="known_pattern",
                    confidence=config["confidence"] * 0.8,
                    reason=f"Known pattern '{pattern}' silent for {time_since_output:.1f}s",
                    detected_at=now,
                    suggested_action="abort"
                )

        return None

    def _check_timeout(self, now: datetime) -> Optional[HangSignal]:
        """Check if overall execution timeout has been exceeded."""
        elapsed = (now - self.start_time).total_seconds()

        if elapsed > self.default_timeout:
            return HangSignal(
                signal_type="timeout",
                confidence=1.0,
                reason=f"Command exceeded timeout of {self.default_timeout}s",
                detected_at=now,
                suggested_action="abort"
            )

        return None

    def get_execution_stats(self) -> dict:
        """
        Get execution statistics.

        Returns:
            Dictionary with execution statistics
        """
        now = datetime.now()
        elapsed = (now - self.start_time).total_seconds()
        time_since_output = (now - self.last_output_time).total_seconds()

        return {
            "command": self.command,
            "elapsed_seconds": elapsed,
            "time_since_last_output": time_since_output,
            "total_output_length": len(self.total_output),
            "output_lines_count": len(self.output_lines),
            "last_output_preview": self.last_output[-100:] if self.last_output else ""
        }


class AdaptiveHangDetector(HangDetector):
    """
    Adaptive hang detector that learns from command behavior.

    Adjusts detection thresholds based on observed output patterns
    and command behavior.
    """

    def __init__(
        self,
        command: str,
        default_timeout: int = 60,
        output_stagnation_threshold: int = 30
    ):
        """Initialize adaptive hang detector."""
        super().__init__(command, default_timeout, output_stagnation_threshold)

        self.output_intervals: List[float] = []
        self.has_been_active = False

    def record_output(self, output: str):
        """Record output and update interval statistics."""
        now = datetime.now()

        if self.last_output:
            # Calculate interval since last output
            interval = (now - self.last_output_time).total_seconds()
            self.output_intervals.append(interval)

            # Keep only recent intervals
            if len(self.output_intervals) > 20:
                self.output_intervals = self.output_intervals[-20:]

            self.has_been_active = True

        super().record_output(output)

        # Adapt threshold based on observed behavior
        self._adapt_threshold()

    def _adapt_threshold(self):
        """Adapt stagnation threshold based on observed output patterns."""
        if len(self.output_intervals) < 3:
            return  # Not enough data

        # Calculate average and max intervals
        avg_interval = sum(self.output_intervals) / len(self.output_intervals)
        max_interval = max(self.output_intervals)

        # Adjust threshold to be 3x the average interval, but at least 10s
        # and no more than 5x the max observed interval
        adapted_threshold = max(
            10,
            min(
                avg_interval * 3,
                max_interval * 5
            )
        )

        # Don't reduce threshold below original value
        if adapted_threshold > self.output_stagnation_threshold:
            self.output_stagnation_threshold = int(adapted_threshold)

    def _check_output_stagnation(self, now: datetime) -> Optional[HangSignal]:
        """Enhanced stagnation check with adaptive learning."""
        if not self.has_been_active:
            # Command hasn't produced output yet - be more patient
            time_since_start = (now - self.start_time).total_seconds()
            if time_since_start > 60:  # 1 minute with no output
                return HangSignal(
                    signal_type="output_stagnation",
                    confidence=0.7,
                    reason=f"No output for {time_since_start:.1f}s since start",
                    detected_at=now,
                    suggested_action="wait"
                )
            return None

        # Use parent implementation with adapted threshold
        return super()._check_output_stagnation(now)
