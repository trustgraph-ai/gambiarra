"""
Demo script for the Prompt Template Engine.

This demonstrates how to use the prompt template engine to generate
LLM-specific prompts for different deployment contexts.
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from gambiarra.server.prompts.engine import PromptTemplateEngine


def main():
    """Demonstrate prompt template engine usage."""

    # Initialize engine
    engine = PromptTemplateEngine()

    print("=" * 80)
    print("GAMBIARRA PROMPT TEMPLATE ENGINE DEMO")
    print("=" * 80)
    print()

    # List available templates and contexts
    print("Available Templates:")
    for template in engine.list_available_templates():
        print(f"  - {template}")
    print()

    print("Available Contexts:")
    for context in engine.list_available_contexts():
        info = engine.get_context_info(context)
        print(f"  - {context}: {info['description']}")
    print()

    # Example 1: Claude with default context
    print("=" * 80)
    print("Example 1: Claude with Default Context")
    print("=" * 80)
    prompt = engine.render_system_prompt(
        llm="claude",
        deployment="default",
        cwd="/home/user/my-project"
    )
    print(prompt[:500] + "...\n")

    # Example 2: GPT-4 with enterprise context
    print("=" * 80)
    print("Example 2: GPT-4 with Enterprise Context")
    print("=" * 80)
    prompt = engine.render_system_prompt(
        llm="gpt4",
        deployment="enterprise",
        cwd="/enterprise/project"
    )
    print(prompt[:500] + "...\n")

    # Example 3: Claude with personal context
    print("=" * 80)
    print("Example 3: Claude with Personal Context")
    print("=" * 80)
    prompt = engine.render_system_prompt(
        llm="claude",
        deployment="personal",
        cwd="/home/user/hobby-project"
    )
    print(prompt[:500] + "...\n")

    # Example 4: Default with CI/CD context
    print("=" * 80)
    print("Example 4: Default Template with CI/CD Context")
    print("=" * 80)
    prompt = engine.render_system_prompt(
        llm="default",
        deployment="cicd",
        cwd="/builds/project"
    )
    print(prompt[:500] + "...\n")

    # Example 5: Custom variables
    print("=" * 80)
    print("Example 5: Custom Variables")
    print("=" * 80)
    prompt = engine.render_system_prompt(
        llm="claude",
        deployment="personal",
        cwd="/custom/project",
        custom_instructions="Always write tests for new functions."
    )
    print(prompt[:500] + "...\n")

    print("=" * 80)
    print("DEMO COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
