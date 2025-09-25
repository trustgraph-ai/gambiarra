"""
Conversation memory management for Gambiarra client.
Handles message history, context windows, and token counting for AI conversations.
"""

import logging
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class MessageType(Enum):
    """Types of messages in conversation history."""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"


@dataclass
class ConversationMessage:
    """A message in the conversation history."""
    content: str
    message_type: MessageType
    timestamp: datetime
    metadata: Dict[str, Any]
    token_count: Optional[int] = None


class ConversationMemory:
    """
    Manages conversation memory with token-aware context window management.
    Provides intelligent conversation memory management.
    """

    def __init__(self, max_tokens: int = 32000, context_window_ratio: float = 0.8):
        """
        Initialize conversation memory.

        Args:
            max_tokens: Maximum tokens for the entire conversation context
            context_window_ratio: Ratio of max_tokens to use for conversation history
        """
        self.max_tokens = max_tokens
        self.context_window_tokens = int(max_tokens * context_window_ratio)
        self.messages: List[ConversationMessage] = []
        self.current_token_count = 0
        self.compressed_message_count = 0

        logger.info(f"💭 Conversation memory initialized (max: {max_tokens}, context: {self.context_window_tokens})")

    def add_message(self, content: str, message_type: MessageType, metadata: Dict[str, Any] = None) -> None:
        """
        Add a message to conversation history.

        Args:
            content: Message content
            message_type: Type of message
            metadata: Optional metadata
        """
        if metadata is None:
            metadata = {}

        # Estimate token count (rough approximation: 4 chars = 1 token)
        estimated_tokens = len(content) // 4 + 10  # Add overhead for message structure

        message = ConversationMessage(
            content=content,
            message_type=message_type,
            timestamp=datetime.now(),
            metadata=metadata,
            token_count=estimated_tokens
        )

        self.messages.append(message)
        self.current_token_count += estimated_tokens

        logger.debug(f"💬 Added {message_type.value} message ({estimated_tokens} tokens)")

        # Check if we need to compress/trim history
        if self.current_token_count > self.context_window_tokens:
            self._manage_context_window()

    def add_user_message(self, content: str, metadata: Dict[str, Any] = None) -> None:
        """Add a user message."""
        self.add_message(content, MessageType.USER, metadata)

    def add_assistant_message(self, content: str, metadata: Dict[str, Any] = None) -> None:
        """Add an assistant message."""
        self.add_message(content, MessageType.ASSISTANT, metadata)

    def add_system_message(self, content: str, metadata: Dict[str, Any] = None) -> None:
        """Add a system message."""
        self.add_message(content, MessageType.SYSTEM, metadata)

    def add_tool_call(self, tool_name: str, parameters: Dict[str, Any], metadata: Dict[str, Any] = None) -> None:
        """Add a tool call message."""
        if metadata is None:
            metadata = {}
        metadata.update({"tool_name": tool_name, "parameters": parameters})

        content = f"Tool call: {tool_name}"
        self.add_message(content, MessageType.TOOL_CALL, metadata)

    def add_tool_result(self, tool_name: str, result: str, success: bool = True, metadata: Dict[str, Any] = None) -> None:
        """Add a tool result message."""
        if metadata is None:
            metadata = {}
        metadata.update({"tool_name": tool_name, "success": success})

        content = f"Tool result: {tool_name} - {'Success' if success else 'Error'}"
        if len(result) > 200:
            # Truncate very long results in the content preview
            content += f"\n{result[:200]}..."
        else:
            content += f"\n{result}"

        self.add_message(content, MessageType.TOOL_RESULT, metadata)

    def get_conversation_context(self, include_system: bool = True) -> List[Dict[str, Any]]:
        """
        Get conversation context for sending to AI.

        Args:
            include_system: Whether to include system messages

        Returns:
            List of message dictionaries suitable for AI API
        """
        context_messages = []

        for message in self.messages:
            if not include_system and message.message_type == MessageType.SYSTEM:
                continue

            # Convert to API format
            if message.message_type == MessageType.USER:
                role = "user"
            elif message.message_type == MessageType.ASSISTANT:
                role = "assistant"
            elif message.message_type == MessageType.SYSTEM:
                role = "system"
            else:
                # Tool calls and results as user messages with metadata
                role = "user"

            context_messages.append({
                "role": role,
                "content": message.content,
                "metadata": message.metadata,
                "timestamp": message.timestamp.isoformat()
            })

        return context_messages

    def get_recent_messages(self, count: int = 10) -> List[ConversationMessage]:
        """Get the most recent messages."""
        return self.messages[-count:] if self.messages else []

    def get_messages_by_type(self, message_type: MessageType) -> List[ConversationMessage]:
        """Get all messages of a specific type."""
        return [msg for msg in self.messages if msg.message_type == message_type]

    def clear_history(self) -> None:
        """Clear all conversation history."""
        cleared_count = len(self.messages)
        self.messages.clear()
        self.current_token_count = 0
        self.compressed_message_count = 0
        logger.info(f"🗑️ Cleared {cleared_count} messages from conversation history")

    def _manage_context_window(self) -> None:
        """Manage context window by compressing or removing old messages."""
        if not self.messages:
            return

        # Strategy: Keep recent important messages, compress old ones
        # 1. Always keep the last 5 messages
        # 2. Compress tool results and intermediate messages
        # 3. Remove very old messages if needed

        keep_recent = 5
        recent_messages = self.messages[-keep_recent:] if len(self.messages) > keep_recent else self.messages
        older_messages = self.messages[:-keep_recent] if len(self.messages) > keep_recent else []

        # Compress older messages
        compressed_messages = self._compress_messages(older_messages)

        # Recalculate token count
        new_messages = compressed_messages + recent_messages
        new_token_count = sum(msg.token_count or 0 for msg in new_messages)

        # If still too many tokens, remove oldest compressed messages
        while new_token_count > self.context_window_tokens and len(compressed_messages) > 0:
            removed_msg = compressed_messages.pop(0)
            new_token_count -= (removed_msg.token_count or 0)
            self.compressed_message_count += 1

        self.messages = compressed_messages + recent_messages
        self.current_token_count = new_token_count

        logger.info(f"🔄 Context window managed: {len(self.messages)} messages, {self.current_token_count} tokens")

    def _compress_messages(self, messages: List[ConversationMessage]) -> List[ConversationMessage]:
        """
        Compress a list of messages to reduce token usage.

        Args:
            messages: Messages to compress

        Returns:
            Compressed messages
        """
        if not messages:
            return []

        compressed = []

        # Group consecutive tool calls/results
        current_group = []
        current_type = None

        for message in messages:
            if message.message_type in [MessageType.TOOL_CALL, MessageType.TOOL_RESULT]:
                if current_type == message.message_type:
                    current_group.append(message)
                else:
                    if current_group:
                        compressed.extend(self._compress_group(current_group, current_type))
                    current_group = [message]
                    current_type = message.message_type
            else:
                if current_group:
                    compressed.extend(self._compress_group(current_group, current_type))
                    current_group = []
                    current_type = None
                compressed.append(message)

        # Handle final group
        if current_group:
            compressed.extend(self._compress_group(current_group, current_type))

        return compressed

    def _compress_group(self, group: List[ConversationMessage], group_type: MessageType) -> List[ConversationMessage]:
        """
        Compress a group of similar messages.

        Args:
            group: Group of messages to compress
            group_type: Type of messages in the group

        Returns:
            Compressed messages
        """
        if len(group) <= 2:
            return group  # Don't compress small groups

        if group_type == MessageType.TOOL_RESULT:
            # Compress tool results by summarizing
            tools_used = set(msg.metadata.get("tool_name", "unknown") for msg in group)
            success_count = sum(1 for msg in group if msg.metadata.get("success", True))
            error_count = len(group) - success_count

            summary_content = f"Tool execution summary: {len(group)} operations"
            if len(tools_used) <= 3:
                summary_content += f" ({', '.join(tools_used)})"
            summary_content += f" - {success_count} successful, {error_count} errors"

            summary_message = ConversationMessage(
                content=summary_content,
                message_type=MessageType.TOOL_RESULT,
                timestamp=group[-1].timestamp,
                metadata={
                    "compressed": True,
                    "original_count": len(group),
                    "tools_used": list(tools_used)
                },
                token_count=len(summary_content) // 4 + 10
            )

            return [summary_message]

        elif group_type == MessageType.TOOL_CALL:
            # Compress tool calls by counting
            tools_used = {}
            for msg in group:
                tool_name = msg.metadata.get("tool_name", "unknown")
                tools_used[tool_name] = tools_used.get(tool_name, 0) + 1

            summary_content = f"Tool calls summary: {len(group)} calls"
            tool_summary = ", ".join(f"{tool}({count})" for tool, count in tools_used.items())
            summary_content += f" - {tool_summary}"

            summary_message = ConversationMessage(
                content=summary_content,
                message_type=MessageType.TOOL_CALL,
                timestamp=group[-1].timestamp,
                metadata={
                    "compressed": True,
                    "original_count": len(group),
                    "tools_used": tools_used
                },
                token_count=len(summary_content) // 4 + 10
            )

            return [summary_message]

        return group

    def get_memory_stats(self) -> Dict[str, Any]:
        """Get memory statistics."""
        type_counts = {}
        for msg_type in MessageType:
            type_counts[msg_type.value] = len([msg for msg in self.messages if msg.message_type == msg_type])

        return {
            "total_messages": len(self.messages),
            "current_tokens": self.current_token_count,
            "max_tokens": self.max_tokens,
            "context_window_tokens": self.context_window_tokens,
            "token_usage_percent": (self.current_token_count / self.context_window_tokens) * 100,
            "compressed_messages": self.compressed_message_count,
            "message_types": type_counts
        }

    def suggest_compression(self) -> Optional[str]:
        """Suggest when compression might be beneficial."""
        stats = self.get_memory_stats()

        if stats["token_usage_percent"] > 90:
            return "⚠️ Memory usage critical - consider clearing old conversation history"
        elif stats["token_usage_percent"] > 75:
            return "💭 Memory usage high - automatic compression will occur soon"
        elif stats["total_messages"] > 100:
            return "📚 Large conversation - consider periodic cleanup for performance"

        return None