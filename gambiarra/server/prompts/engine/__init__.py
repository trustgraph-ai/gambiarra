"""
Prompt Template Engine for Gambiarra.

Provides flexible, customizable prompt generation using Jinja2 templates
and YAML contexts.
"""

from .template_engine import (
    PromptTemplateEngine,
    get_prompt_engine,
    set_prompt_engine
)

__all__ = [
    'PromptTemplateEngine',
    'get_prompt_engine',
    'set_prompt_engine',
]
