"""
Tool approval workflow system for Gambiarra client.
Manages user approval for tool execution with configurable policies.
"""

import asyncio
import time
from typing import Dict, Any, Optional, Callable, List
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class ApprovalDecision(Enum):
    """Tool approval decisions."""
    APPROVED = "approved"
    DENIED = "denied"
    APPROVED_WITH_MODIFICATION = "approved_with_modification"


@dataclass
class ToolApprovalRequest:
    """Tool approval request data."""
    request_id: str
    tool_name: str
    parameters: Dict[str, Any]
    description: str
    risk_level: str
    requires_approval: bool
    session_id: str
    timestamp: float


@dataclass
class ApprovalResponse:
    """Tool approval response data."""
    request_id: str
    decision: ApprovalDecision
    feedback: Optional[str] = None
    modified_parameters: Optional[Dict[str, Any]] = None
    approved_by: str = "user"
    timestamp: float = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()


class ApprovalPolicy:
    """Defines approval policies for different tools and risk levels."""

    def __init__(self):
        self.auto_approve_rules: List[Dict[str, Any]] = []
        self.require_approval_rules: List[Dict[str, Any]] = []
        self.block_rules: List[Dict[str, Any]] = []

    def add_auto_approve_rule(self, tool_name: str = None, risk_level: str = None,
                             conditions: Dict[str, Any] = None) -> None:
        """Add rule for automatic approval."""
        rule = {
            "tool_name": tool_name,
            "risk_level": risk_level,
            "conditions": conditions or {}
        }
        self.auto_approve_rules.append(rule)

    def add_require_approval_rule(self, tool_name: str = None, risk_level: str = None,
                                 conditions: Dict[str, Any] = None) -> None:
        """Add rule that requires user approval."""
        rule = {
            "tool_name": tool_name,
            "risk_level": risk_level,
            "conditions": conditions or {}
        }
        self.require_approval_rules.append(rule)

    def add_block_rule(self, tool_name: str = None, risk_level: str = None,
                      conditions: Dict[str, Any] = None) -> None:
        """Add rule that blocks tool execution."""
        rule = {
            "tool_name": tool_name,
            "risk_level": risk_level,
            "conditions": conditions or {}
        }
        self.block_rules.append(rule)

    def should_auto_approve(self, request: ToolApprovalRequest) -> bool:
        """Check if request should be auto-approved."""
        return self._matches_rules(request, self.auto_approve_rules)

    def should_block(self, request: ToolApprovalRequest) -> bool:
        """Check if request should be blocked."""
        return self._matches_rules(request, self.block_rules)

    def requires_approval(self, request: ToolApprovalRequest) -> bool:
        """Check if request requires user approval."""
        # Block rules take precedence
        if self.should_block(request):
            return False

        # Auto-approve rules take precedence over require approval
        if self.should_auto_approve(request):
            return False

        # Check require approval rules
        return self._matches_rules(request, self.require_approval_rules)

    def _matches_rules(self, request: ToolApprovalRequest, rules: List[Dict[str, Any]]) -> bool:
        """Check if request matches any of the given rules."""
        for rule in rules:
            if self._matches_rule(request, rule):
                return True
        return False

    def _matches_rule(self, request: ToolApprovalRequest, rule: Dict[str, Any]) -> bool:
        """Check if request matches a specific rule."""
        # Check tool name
        if rule["tool_name"] and rule["tool_name"] != request.tool_name:
            return False

        # Check risk level
        if rule["risk_level"] and rule["risk_level"] != request.risk_level:
            return False

        # Check conditions
        conditions = rule["conditions"]
        for key, expected_value in conditions.items():
            if key in request.parameters:
                actual_value = request.parameters[key]
                if actual_value != expected_value:
                    return False

        return True


class ApprovalManager:
    """Manages tool approval workflows."""

    def __init__(self, approval_callback: Optional[Callable] = None):
        self.approval_callback = approval_callback
        self.pending_approvals: Dict[str, ToolApprovalRequest] = {}
        self.approval_history: List[ApprovalResponse] = []
        self.policy = ApprovalPolicy()
        self._setup_default_policies()

    def _setup_default_policies(self) -> None:
        """Setup default approval policies."""
        # Auto-approve low-risk read operations
        self.policy.add_auto_approve_rule(risk_level="low")
        self.policy.add_auto_approve_rule(tool_name="read_file")
        self.policy.add_auto_approve_rule(tool_name="list_files")
        self.policy.add_auto_approve_rule(tool_name="search_files")

        # Require approval for high-risk operations
        self.policy.add_require_approval_rule(risk_level="high")
        self.policy.add_require_approval_rule(tool_name="write_to_file")
        self.policy.add_require_approval_rule(tool_name="execute_command")

        # Block extremely dangerous operations
        self.policy.add_block_rule(
            tool_name="execute_command",
            conditions={"command": "rm -rf /"}
        )

        logger.info("🔐 Default approval policies configured")

    async def request_approval(self, request: ToolApprovalRequest) -> ApprovalResponse:
        """Request approval for tool execution."""
        logger.info(f"🔐 Approval requested for {request.tool_name} (risk: {request.risk_level})")

        # Check if should be blocked
        if self.policy.should_block(request):
            logger.warning(f"🚫 Tool {request.tool_name} blocked by policy")
            return ApprovalResponse(
                request_id=request.request_id,
                decision=ApprovalDecision.DENIED,
                feedback="Tool execution blocked by security policy",
                approved_by="policy"
            )

        # Check if should be auto-approved
        if self.policy.should_auto_approve(request):
            logger.info(f"✅ Tool {request.tool_name} auto-approved")
            response = ApprovalResponse(
                request_id=request.request_id,
                decision=ApprovalDecision.APPROVED,
                approved_by="auto_policy"
            )
            self.approval_history.append(response)
            return response

        # Requires user approval
        if not self.approval_callback:
            logger.warning(f"❌ No approval callback configured for {request.tool_name}")
            return ApprovalResponse(
                request_id=request.request_id,
                decision=ApprovalDecision.DENIED,
                feedback="No approval mechanism available",
                approved_by="system"
            )

        # Store pending approval
        self.pending_approvals[request.request_id] = request

        try:
            # Request user approval
            response = await self.approval_callback(request)

            # Remove from pending
            self.pending_approvals.pop(request.request_id, None)

            # Store in history
            self.approval_history.append(response)

            logger.info(f"🔐 Tool {request.tool_name} approval: {response.decision.value}")
            return response

        except Exception as e:
            logger.error(f"❌ Error in approval process: {e}")
            # Remove from pending
            self.pending_approvals.pop(request.request_id, None)

            return ApprovalResponse(
                request_id=request.request_id,
                decision=ApprovalDecision.DENIED,
                feedback=f"Approval process error: {e}",
                approved_by="error_handler"
            )

    async def handle_approval_response(self, response: ApprovalResponse) -> None:
        """Handle approval response from user."""
        request = self.pending_approvals.get(response.request_id)
        if not request:
            logger.warning(f"❌ No pending approval for request {response.request_id}")
            return

        # Remove from pending
        self.pending_approvals.pop(response.request_id)

        # Store in history
        self.approval_history.append(response)

        logger.info(f"🔐 Processed approval response: {response.decision.value}")

    def get_pending_approvals(self) -> List[ToolApprovalRequest]:
        """Get list of pending approval requests."""
        return list(self.pending_approvals.values())

    def get_approval_history(self, limit: int = 50) -> List[ApprovalResponse]:
        """Get approval history."""
        return self.approval_history[-limit:]

    def get_approval_stats(self) -> Dict[str, Any]:
        """Get approval statistics."""
        total_approvals = len(self.approval_history)

        if total_approvals == 0:
            return {
                "total_requests": 0,
                "approved": 0,
                "denied": 0,
                "auto_approved": 0,
                "pending": len(self.pending_approvals)
            }

        approved = sum(1 for r in self.approval_history if r.decision == ApprovalDecision.APPROVED)
        denied = sum(1 for r in self.approval_history if r.decision == ApprovalDecision.DENIED)
        auto_approved = sum(1 for r in self.approval_history if r.approved_by == "auto_policy")

        return {
            "total_requests": total_approvals,
            "approved": approved,
            "denied": denied,
            "auto_approved": auto_approved,
            "pending": len(self.pending_approvals),
            "approval_rate": round(approved / total_approvals * 100, 1) if total_approvals > 0 else 0
        }

    def configure_policy(self,
                        auto_approve_reads: bool = True,
                        require_approval_writes: bool = True,
                        require_approval_commands: bool = True,
                        block_dangerous_commands: bool = True) -> None:
        """Configure approval policy with common settings."""
        # Clear existing rules
        self.policy = ApprovalPolicy()

        if auto_approve_reads:
            self.policy.add_auto_approve_rule(tool_name="read_file")
            self.policy.add_auto_approve_rule(tool_name="list_files")
            self.policy.add_auto_approve_rule(tool_name="search_files")

        if require_approval_writes:
            self.policy.add_require_approval_rule(tool_name="write_to_file")
            self.policy.add_require_approval_rule(tool_name="insert_content")
            self.policy.add_require_approval_rule(tool_name="search_and_replace")

        if require_approval_commands:
            self.policy.add_require_approval_rule(tool_name="execute_command")

        if block_dangerous_commands:
            # Block some extremely dangerous patterns
            dangerous_commands = [
                "rm -rf /",
                "dd if=/dev/zero",
                "mkfs.",
                "format",
                "sudo rm",
            ]

            for cmd in dangerous_commands:
                self.policy.add_block_rule(
                    tool_name="execute_command",
                    conditions={"command": cmd}
                )

        logger.info("🔐 Approval policy reconfigured")

    def cleanup_old_history(self, max_age_hours: int = 24) -> int:
        """Clean up old approval history."""
        cutoff_time = time.time() - (max_age_hours * 3600)
        original_count = len(self.approval_history)

        self.approval_history = [
            response for response in self.approval_history
            if response.timestamp > cutoff_time
        ]

        removed_count = original_count - len(self.approval_history)
        if removed_count > 0:
            logger.info(f"🧹 Cleaned up {removed_count} old approval records")

        return removed_count