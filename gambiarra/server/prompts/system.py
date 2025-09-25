"""
System prompt generator for Gambiarra with modular component system.
"""

from .sections import (
    get_objective_section,
    get_tool_use_guidelines_section,
    get_capabilities_section,
    get_rules_section,
    get_system_info_section,
    get_markdown_formatting_section
)
from .tools import get_tool_descriptions


def generate_system_prompt(cwd: str = "/workspace", mode: str = "code") -> str:
    """
    Generate complete system prompt using modular sections.

    Args:
        cwd: Current working directory
        mode: Operating mode (currently only 'code' supported)

    Returns:
        Complete system prompt string
    """

    # Role definition based on mode
    if mode == "code":
        role_definition = "You are Gambiarra, an AI coding assistant with a secure client-server architecture. You have access to powerful tools for file operations, code analysis, and system commands."
    else:
        role_definition = "You are Gambiarra, an AI assistant with access to various tools for helping users with their tasks."

    # Assemble the complete prompt
    prompt_sections = [
        role_definition,
        "",
        get_markdown_formatting_section(),
        "",
        get_tool_use_guidelines_section(),
        "",
        get_tool_descriptions(),
        "",
        get_capabilities_section(cwd),
        "",
        get_rules_section(),
        "",
        get_system_info_section(cwd),
        "",
        get_objective_section(),
    ]

    return "\n".join(prompt_sections)


def get_role_definition(mode: str = "code") -> str:
    """Get role definition for specific mode."""
    if mode == "code":
        return "You are Gambiarra, an AI coding assistant with a secure client-server architecture. You have access to powerful tools for file operations, code analysis, and system commands."
    elif mode == "ask":
        return "You are Gambiarra, an AI assistant focused on answering questions and providing guidance."
    elif mode == "architect":
        return "You are Gambiarra, an AI assistant focused on high-level system design and architecture planning."
    else:
        return "You are Gambiarra, an AI assistant with access to various tools for helping users with their tasks."