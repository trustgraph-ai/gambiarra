"""
Smart approval manager for Gambiarra client.
Integrates with tool validator for intelligent auto-approval based on mistake counting.
Provides intelligent auto-approval for trusted operations.
"""

import logging
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass
from enum import Enum
from .approval_manager import ApprovalManager, ToolApprovalRequest, ApprovalResponse, ApprovalDecision

logger = logging.getLogger(__name__)


class AutoApprovalReason(Enum):
    """Reasons for auto-approval decisions."""
    LOW_RISK = "low_risk"
    TRUSTED_TOOL = "trusted_tool"
    MISTAKE_LIMIT_EXCEEDED = "mistake_limit_exceeded"
    USER_GUIDANCE_REQUIRED = "user_guidance_required"


@dataclass
class SmartApprovalConfig:
    """Configuration for smart approval behavior."""
    auto_approve_low_risk: bool = True
    auto_approve_read_operations: bool = True
    auto_approve_list_operations: bool = True
    mistake_limit_for_intervention: int = 3
    cost_limit_for_intervention: float = 5.0  # USD
    max_consecutive_auto_approvals: int = 10


class SmartApprovalManager:
    """
    Enhanced approval manager with intelligent auto-approval based on context.
    """

    def __init__(self, request_user_approval: Callable, config: SmartApprovalConfig = None):
        self.base_approval_manager = ApprovalManager(request_user_approval)
        self.config = config or SmartApprovalConfig()

        # State tracking
        self.consecutive_auto_approvals = 0
        self.total_cost_estimate = 0.0

        # Tool categorization
        self.low_risk_tools = {
            "read_file", "list_files", "search_files", "list_code_definition_names"
        }
        self.medium_risk_tools = {
            "search_and_replace", "insert_content"
        }
        self.high_risk_tools = {
            "write_to_file", "execute_command"
        }

        logger.info("🧠 Smart approval manager initialized")

    async def request_approval(self, request: ToolApprovalRequest, tool_validator=None) -> ApprovalResponse:
        """
        Request approval with smart auto-approval logic.

        Args:
            request: Tool approval request
            tool_validator: Optional tool validator for mistake tracking

        Returns:
            ApprovalResponse with decision
        """

        # Check if we should request user guidance due to mistakes
        if tool_validator and tool_validator.should_request_guidance():
            return await self._request_user_guidance(request, tool_validator)

        # Check for auto-approval conditions
        auto_approval_reason = self._should_auto_approve(request, tool_validator)

        if auto_approval_reason:
            self.consecutive_auto_approvals += 1
            logger.info(f"✅ Auto-approved {request.tool_name} (reason: {auto_approval_reason.value})")

            return ApprovalResponse(
                request_id=request.request_id,
                decision=ApprovalDecision.APPROVED,
                feedback=f"Auto-approved: {auto_approval_reason.value}",
                modified_parameters={}
            )

        # Reset consecutive auto-approvals when user input is required
        self.consecutive_auto_approvals = 0

        # Fall back to manual approval
        return await self.base_approval_manager.request_approval(request)

    def _should_auto_approve(self, request: ToolApprovalRequest, tool_validator=None) -> Optional[AutoApprovalReason]:
        """
        Determine if request should be auto-approved and why.

        Args:
            request: Tool approval request
            tool_validator: Optional tool validator for context

        Returns:
            AutoApprovalReason if should auto-approve, None otherwise
        """

        # Check consecutive auto-approval limit
        if self.consecutive_auto_approvals >= self.config.max_consecutive_auto_approvals:
            logger.info(f"🛑 Consecutive auto-approval limit reached ({self.consecutive_auto_approvals})")
            return None

        # Check cost limit
        if self.total_cost_estimate > self.config.cost_limit_for_intervention:
            logger.info(f"🛑 Cost limit reached (${self.total_cost_estimate:.2f})")
            return None

        # Auto-approve low-risk tools if enabled
        if (self.config.auto_approve_low_risk and
            request.tool_name in self.low_risk_tools and
            request.risk_level in ["low", "minimal"]):
            return AutoApprovalReason.LOW_RISK

        # Auto-approve read operations if enabled
        if (self.config.auto_approve_read_operations and
            self._is_read_operation(request)):
            return AutoApprovalReason.TRUSTED_TOOL

        # Auto-approve list operations if enabled
        if (self.config.auto_approve_list_operations and
            self._is_list_operation(request)):
            return AutoApprovalReason.TRUSTED_TOOL

        # No auto-approval conditions met
        return None

    def _is_read_operation(self, request: ToolApprovalRequest) -> bool:
        """Check if request is a read-only operation."""
        return request.tool_name in {"read_file", "list_code_definition_names"}

    def _is_list_operation(self, request: ToolApprovalRequest) -> bool:
        """Check if request is a listing operation."""
        return request.tool_name in {"list_files", "search_files"}

    async def _request_user_guidance(self, request: ToolApprovalRequest, tool_validator) -> ApprovalResponse:
        """
        Request user guidance when mistake limit is exceeded.

        Args:
            request: Tool approval request
            tool_validator: Tool validator with error tracking

        Returns:
            ApprovalResponse with user decision
        """

        error_stats = tool_validator.get_error_stats()
        recent_errors = tool_validator.get_recent_errors(3)

        # Build guidance message
        guidance_message = f"""
🚨 Multiple tool execution errors detected ({error_stats['consecutive_mistakes']} consecutive mistakes).

Recent errors:
"""
        for error in recent_errors:
            guidance_message += f"- {error.tool_name}: {error.message}\n"

        guidance_message += f"""
The AI may need guidance to proceed effectively.

Current request: {request.tool_name} with risk level {request.risk_level}

Would you like to:
1. Approve this tool and continue
2. Deny this tool and provide guidance
3. Reset mistake counter and auto-approve low-risk tools
"""

        # Create modified request with guidance context
        guided_request = ToolApprovalRequest(
            request_id=request.request_id,
            tool_name=request.tool_name,
            parameters=request.parameters,
            description=f"GUIDANCE NEEDED: {request.description}\n\n{guidance_message}",
            risk_level="high",  # Escalate to high risk when guidance needed
            requires_approval=True,
            session_id=request.session_id,
            timestamp=request.timestamp
        )

        # Request manual approval with guidance
        response = await self.base_approval_manager.request_approval(guided_request)

        # If approved, reset mistake counter
        if response.decision == ApprovalDecision.APPROVED and "reset" in response.feedback.lower():
            tool_validator.reset_mistake_count()
            logger.info("🔄 Mistake counter reset by user")

        return response

    def update_cost_estimate(self, additional_cost: float) -> None:
        """Update running cost estimate."""
        self.total_cost_estimate += additional_cost
        logger.debug(f"💰 Cost estimate updated: ${self.total_cost_estimate:.2f}")

    def reset_cost_estimate(self) -> None:
        """Reset cost estimate (e.g., for new session)."""
        self.total_cost_estimate = 0.0
        logger.info("💰 Cost estimate reset")

    def reset_auto_approval_count(self) -> None:
        """Reset consecutive auto-approval count."""
        self.consecutive_auto_approvals = 0
        logger.info("🔄 Auto-approval count reset")

    def get_approval_stats(self) -> Dict[str, Any]:
        """Get approval statistics."""
        return {
            "consecutive_auto_approvals": self.consecutive_auto_approvals,
            "total_cost_estimate": self.total_cost_estimate,
            "config": {
                "auto_approve_low_risk": self.config.auto_approve_low_risk,
                "auto_approve_read_operations": self.config.auto_approve_read_operations,
                "auto_approve_list_operations": self.config.auto_approve_list_operations,
                "mistake_limit": self.config.mistake_limit_for_intervention,
                "cost_limit": self.config.cost_limit_for_intervention,
                "max_consecutive_auto_approvals": self.config.max_consecutive_auto_approvals
            }
        }