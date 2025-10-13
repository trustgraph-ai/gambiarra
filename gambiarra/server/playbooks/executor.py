"""
Playbook executor - runs playbook steps with variable substitution.
"""

import logging
import re
import json
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

from .registry import PlaybookDefinition, PlaybookStep

logger = logging.getLogger(__name__)


@dataclass
class PlaybookExecutionResult:
    """Result of playbook execution."""
    success: bool
    steps_completed: int
    total_steps: int
    error: Optional[str] = None
    step_results: List[Dict[str, Any]] = None

    def __post_init__(self):
        if self.step_results is None:
            self.step_results = []


class PlaybookExecutor:
    """Executes playbook steps."""

    def __init__(self):
        """Initialize executor."""
        pass

    def substitute_variables(self, text: str, variables: Dict[str, str]) -> str:
        """Substitute {{variable}} placeholders in text."""
        result = text
        for key, value in variables.items():
            # Replace {{key}} with value
            result = result.replace(f"{{{{{key}}}}}", str(value))

        # Check for any remaining unsubstituted variables
        remaining = re.findall(r'\{\{(\w+)\}\}', result)
        if remaining:
            logger.warning(f"⚠️ Unsubstituted variables: {remaining}")

        return result

    def prepare_step_for_execution(self,
                                   step: PlaybookStep,
                                   variables: Dict[str, str],
                                   base_workspace: str) -> Dict[str, Any]:
        """Prepare a playbook step for execution by the client."""
        # Substitute variables in command and working_dir
        command = self.substitute_variables(step.command, variables)
        working_dir = self.substitute_variables(step.working_dir, variables)

        # Build full command with cd if working_dir is not current
        if working_dir and working_dir != ".":
            # Wrap command to execute in specific directory
            full_command = f"cd {working_dir} && {command}"
        else:
            full_command = command

        return {
            "tool_name": "execute_command",
            "parameters": {
                "args": {
                    "command": full_command,
                    "timeout": step.timeout
                }
            },
            "description": step.description,
            "original_command": command,
            "working_dir": working_dir
        }

    def validate_variables(self,
                          playbook: PlaybookDefinition,
                          provided_variables: Dict[str, str]) -> tuple[bool, Optional[str]]:
        """Validate that all required variables are provided."""
        missing = []

        for var_def in playbook.variables:
            if var_def.required and var_def.name not in provided_variables:
                # Check if there's a default
                if var_def.default is None:
                    missing.append(var_def.name)

        if missing:
            return False, f"Missing required variables: {', '.join(missing)}"

        return True, None

    def get_execution_plan(self,
                          playbook: PlaybookDefinition,
                          variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Generate an execution plan for the playbook."""
        # Merge provided variables with defaults
        final_variables = {}

        # First, add all defaults
        for var_def in playbook.variables:
            if var_def.default is not None:
                final_variables[var_def.name] = var_def.default

        # Then override with provided variables
        if variables:
            # Handle both dict and JSON string
            if isinstance(variables, str):
                try:
                    variables = json.loads(variables)
                except json.JSONDecodeError:
                    logger.error(f"❌ Failed to parse variables JSON: {variables}")
                    variables = {}

            final_variables.update(variables)

        # Validate
        valid, error = self.validate_variables(playbook, final_variables)
        if not valid:
            return {
                "success": False,
                "error": error,
                "steps": []
            }

        # Prepare all steps
        steps = []
        for i, step in enumerate(playbook.steps, 1):
            prepared = self.prepare_step_for_execution(step, final_variables, ".")
            prepared["step_number"] = i
            prepared["total_steps"] = len(playbook.steps)
            steps.append(prepared)

        return {
            "success": True,
            "playbook_name": playbook.name,
            "description": playbook.description,
            "variables": final_variables,
            "steps": steps,
            "total_steps": len(steps)
        }

    def format_playbook_search_results(self, playbooks: List[PlaybookDefinition]) -> str:
        """Format playbook search results for AI."""
        if not playbooks:
            return "No playbooks found matching your query."

        result_lines = [f"Found {len(playbooks)} matching playbook(s):\n"]

        for i, playbook in enumerate(playbooks, 1):
            result_lines.append(f"{i}. **{playbook.name}**")
            result_lines.append(f"   Description: {playbook.description}")
            result_lines.append(f"   Category: {playbook.category}")
            result_lines.append(f"   Steps: {len(playbook.steps)}")

            if playbook.variables:
                var_list = []
                for var in playbook.variables:
                    var_str = f"{var.name}"
                    if var.required:
                        var_str += " (required)"
                    if var.default:
                        var_str += f" [default: {var.default}]"
                    var_list.append(var_str)
                result_lines.append(f"   Variables: {', '.join(var_list)}")

            result_lines.append(f"   Tags: {', '.join(playbook.tags)}")
            result_lines.append("")

        result_lines.append("\nTo use a playbook, call execute_playbook with the playbook name and any required variables.")

        return "\n".join(result_lines)


# Global executor instance
_executor: Optional[PlaybookExecutor] = None


def get_playbook_executor() -> PlaybookExecutor:
    """Get the global playbook executor."""
    global _executor
    if _executor is None:
        _executor = PlaybookExecutor()
    return _executor
