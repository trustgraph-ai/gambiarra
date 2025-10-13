"""
Prompt Template Engine for Gambiarra.

This module provides a flexible, customizable prompt generation system using
Jinja2 templates and YAML contexts. It enables:

- LLM-specific prompt variants (Claude, GPT-4, Gemini, etc.)
- Deployment context customization (enterprise, personal, CI/CD)
- Easy prompt iteration without code changes
- Inheritance and composition of prompt sections

Architecture:
- Templates: Jinja2 templates in templates/ directory
- Contexts: YAML files defining variables for different deployments
- Engine: Combines templates + contexts to generate final prompts

Usage:
    engine = PromptTemplateEngine()
    prompt = engine.render_system_prompt(
        llm="claude",
        deployment="enterprise",
        cwd="/path/to/project"
    )
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, List
from jinja2 import Environment, FileSystemLoader, select_autoescape, TemplateNotFound
import logging

logger = logging.getLogger(__name__)


class PromptTemplateEngine:
    """
    Template engine for generating LLM-specific prompts.

    Uses Jinja2 for templating and YAML for context configuration.
    Supports template inheritance and multiple deployment contexts.
    """

    def __init__(
        self,
        templates_dir: Optional[Path] = None,
        contexts_dir: Optional[Path] = None
    ):
        """
        Initialize the template engine.

        Args:
            templates_dir: Directory containing Jinja2 templates
            contexts_dir: Directory containing YAML context files
        """
        # Default directories
        if templates_dir is None:
            templates_dir = Path(__file__).parent.parent / "templates"
        if contexts_dir is None:
            contexts_dir = Path(__file__).parent.parent / "contexts"

        self.templates_dir = templates_dir
        self.contexts_dir = contexts_dir

        # Create Jinja2 environment
        self.jinja_env = Environment(
            loader=FileSystemLoader(str(templates_dir)),
            autoescape=select_autoescape(['html', 'xml']),
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True
        )

        # Add custom filters
        self._register_custom_filters()

        # Cache for loaded contexts
        self._context_cache: Dict[str, Dict[str, Any]] = {}

        logger.info(
            f"Initialized PromptTemplateEngine: "
            f"templates={templates_dir}, contexts={contexts_dir}"
        )

    def _register_custom_filters(self):
        """Register custom Jinja2 filters."""

        def format_tools(tools: List[Dict[str, Any]], llm: str) -> str:
            """Format tools list according to LLM preference."""
            if llm == "claude":
                # Claude prefers XML format
                result = []
                for tool in tools:
                    result.append(f"<tool>{tool['name']}</tool>")
                return "\n".join(result)
            elif llm in ["gpt4", "gpt-4"]:
                # GPT-4 prefers JSON format
                import json
                return json.dumps(tools, indent=2)
            else:
                # Default: simple list
                return "\n".join([f"- {tool['name']}" for tool in tools])

        self.jinja_env.filters['format_tools'] = format_tools

    def load_context(self, context_name: str) -> Dict[str, Any]:
        """
        Load context from YAML file.

        Args:
            context_name: Name of the context (e.g., "enterprise", "personal")

        Returns:
            Dictionary with context variables

        Raises:
            FileNotFoundError: If context file doesn't exist
        """
        # Check cache
        if context_name in self._context_cache:
            return self._context_cache[context_name].copy()

        # Load from file
        context_file = self.contexts_dir / f"{context_name}.yaml"

        if not context_file.exists():
            raise FileNotFoundError(f"Context file not found: {context_file}")

        try:
            with open(context_file, 'r') as f:
                context = yaml.safe_load(f)

            # Handle inheritance
            if "extends" in context:
                parent_context = self.load_context(context["extends"])
                # Merge with parent (child overrides parent)
                merged = parent_context.copy()
                merged.update(context)
                context = merged

            # Cache and return
            self._context_cache[context_name] = context
            return context.copy()

        except yaml.YAMLError as e:
            raise ValueError(f"Error parsing context file {context_file}: {e}")

    def render_system_prompt(
        self,
        llm: str = "claude",
        deployment: str = "default",
        **kwargs
    ) -> str:
        """
        Render the system prompt for a specific LLM and deployment.

        Args:
            llm: LLM identifier (claude, gpt4, gemini, opensource)
            deployment: Deployment context (default, enterprise, personal, cicd)
            **kwargs: Additional variables to pass to template

        Returns:
            Rendered system prompt string

        Example:
            >>> engine = PromptTemplateEngine()
            >>> prompt = engine.render_system_prompt(
            ...     llm="claude",
            ...     deployment="enterprise",
            ...     cwd="/path/to/project"
            ... )
        """
        # Load deployment context
        try:
            context = self.load_context(deployment)
        except FileNotFoundError:
            logger.warning(f"Context '{deployment}' not found, using default")
            context = self.load_context("default")

        # Merge kwargs
        context.update(kwargs)

        # Add LLM identifier to context
        context['llm'] = llm

        # Render template
        template_name = f"system_prompt_{llm}.j2"

        try:
            template = self.jinja_env.get_template(template_name)
        except TemplateNotFound:
            logger.warning(
                f"Template '{template_name}' not found, using default template"
            )
            template = self.jinja_env.get_template("system_prompt_default.j2")

        return template.render(**context)

    def render_tool_prompt(
        self,
        llm: str = "claude",
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> str:
        """
        Render tool descriptions for a specific LLM.

        Args:
            llm: LLM identifier
            tools: List of tool definitions
            **kwargs: Additional variables

        Returns:
            Rendered tool prompt string
        """
        context = {
            'llm': llm,
            'tools': tools or []
        }
        context.update(kwargs)

        template_name = f"tools_{llm}.j2"

        try:
            template = self.jinja_env.get_template(template_name)
        except TemplateNotFound:
            template = self.jinja_env.get_template("tools_default.j2")

        return template.render(**context)

    def render_custom_template(
        self,
        template_name: str,
        context: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> str:
        """
        Render any custom template.

        Args:
            template_name: Name of the template file
            context: Context dictionary
            **kwargs: Additional variables

        Returns:
            Rendered template string
        """
        ctx = context.copy() if context else {}
        ctx.update(kwargs)

        template = self.jinja_env.get_template(template_name)
        return template.render(**ctx)

    def list_available_templates(self) -> List[str]:
        """
        List all available templates.

        Returns:
            List of template names
        """
        if not self.templates_dir.exists():
            return []

        return [
            f.name for f in self.templates_dir.iterdir()
            if f.is_file() and f.suffix in ['.j2', '.jinja2']
        ]

    def list_available_contexts(self) -> List[str]:
        """
        List all available contexts.

        Returns:
            List of context names (without .yaml extension)
        """
        if not self.contexts_dir.exists():
            return []

        return [
            f.stem for f in self.contexts_dir.iterdir()
            if f.is_file() and f.suffix in ['.yaml', '.yml']
        ]

    def validate_template(self, template_name: str) -> bool:
        """
        Validate that a template can be loaded and parsed.

        Args:
            template_name: Name of template to validate

        Returns:
            True if valid, False otherwise
        """
        try:
            self.jinja_env.get_template(template_name)
            return True
        except Exception as e:
            logger.error(f"Template validation failed for {template_name}: {e}")
            return False

    def validate_context(self, context_name: str) -> bool:
        """
        Validate that a context can be loaded and parsed.

        Args:
            context_name: Name of context to validate

        Returns:
            True if valid, False otherwise
        """
        try:
            self.load_context(context_name)
            return True
        except Exception as e:
            logger.error(f"Context validation failed for {context_name}: {e}")
            return False

    def reload_contexts(self):
        """Clear context cache to force reload from disk."""
        self._context_cache.clear()
        logger.info("Context cache cleared")

    def get_context_info(self, context_name: str) -> Dict[str, Any]:
        """
        Get information about a context.

        Args:
            context_name: Name of context

        Returns:
            Dictionary with context metadata
        """
        context = self.load_context(context_name)

        return {
            "name": context_name,
            "description": context.get("description", "No description"),
            "extends": context.get("extends"),
            "variables": list(context.keys()),
            "variable_count": len(context)
        }


# Global instance
_global_engine: Optional[PromptTemplateEngine] = None


def get_prompt_engine() -> PromptTemplateEngine:
    """
    Get the global prompt template engine instance.

    Returns:
        Global PromptTemplateEngine instance
    """
    global _global_engine
    if _global_engine is None:
        _global_engine = PromptTemplateEngine()
    return _global_engine


def set_prompt_engine(engine: PromptTemplateEngine):
    """
    Set the global prompt template engine instance.

    Args:
        engine: PromptTemplateEngine instance to use globally
    """
    global _global_engine
    _global_engine = engine
