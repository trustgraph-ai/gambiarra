# Prompt Template System

The Gambiarra Prompt Template System provides flexible, customizable prompt generation using Jinja2 templates and YAML contexts.

## Overview

This system solves a critical challenge: **different LLMs need different prompts, and different deployments need different behaviors**. Instead of hardcoding prompts in Python, we use:

- **Templates**: Jinja2 templates for each LLM (Claude, GPT-4, etc.)
- **Contexts**: YAML files defining variables for different deployments
- **Engine**: Combines templates + contexts to generate final prompts

## Directory Structure

```
prompts/
├── engine/              # Template engine implementation
│   ├── template_engine.py
│   └── __init__.py
├── templates/           # Jinja2 templates for different LLMs
│   ├── system_prompt_default.j2
│   ├── system_prompt_claude.j2
│   ├── system_prompt_gpt4.j2
│   └── tools_*.j2
├── contexts/            # YAML context files for deployments
│   ├── default.yaml
│   ├── enterprise.yaml
│   ├── personal.yaml
│   └── cicd.yaml
└── README.md
```

## Quick Start

### Basic Usage

```python
from gambiarra.server.prompts.engine import PromptTemplateEngine

# Initialize engine
engine = PromptTemplateEngine()

# Generate prompt for Claude in enterprise mode
prompt = engine.render_system_prompt(
    llm="claude",
    deployment="enterprise",
    cwd="/path/to/project"
)
```

### Using Global Instance

```python
from gambiarra.server.prompts.engine import get_prompt_engine

engine = get_prompt_engine()
prompt = engine.render_system_prompt(llm="gpt4", deployment="personal")
```

## Templates

Templates are Jinja2 files that define the structure of prompts for specific LLMs.

### Available Templates

- `system_prompt_default.j2` - Generic template for any LLM
- `system_prompt_claude.j2` - Optimized for Claude (uses `<thinking>` tags, XML format)
- `system_prompt_gpt4.j2` - Optimized for GPT-4 (function-calling style)

### Creating Custom Templates

Create a new `.j2` file in `templates/`:

```jinja2
{# templates/system_prompt_mymodel.j2 #}
You are {{ assistant_name }}.

## Your Role
{{ role_description }}

## Working Directory
{{ cwd }}

{% if custom_instructions %}
{{ custom_instructions }}
{% endif %}
```

### Template Variables

All templates have access to variables from the context:

- `assistant_name`: Name of the assistant
- `role_description`: Description of the assistant's role
- `cwd`: Current working directory
- `capabilities`: List of capabilities
- `command_rules`: List of command execution rules
- `file_rules`: List of file operation rules
- `safety_rules`: List of safety rules
- `custom_instructions`: Additional instructions
- Plus any custom variables you add to contexts

## Contexts

Contexts are YAML files that define variables for different deployment scenarios.

### Available Contexts

- **default.yaml** - Base configuration for all deployments
- **enterprise.yaml** - Enhanced security, strict policies, audit logging
- **personal.yaml** - Relaxed rules, helpful suggestions, learning-focused
- **cicd.yaml** - Fully automated, non-interactive, deterministic

### Context Inheritance

Contexts support inheritance using the `extends` key:

```yaml
# contexts/my-context.yaml
extends: "default"

assistant_name: "My Custom Assistant"
custom_instructions: "Always write tests!"
```

### Creating Custom Contexts

Create a new `.yaml` file in `contexts/`:

```yaml
# contexts/startup.yaml
extends: "personal"

description: "Fast-moving startup environment"

assistant_name: "Gambiarra Startup"

# Override guidelines for speed
guidelines:
  - "Move fast and ship features"
  - "Iterate quickly based on feedback"
  - "Focus on MVP functionality"

# Add startup-specific instructions
custom_instructions: |
  You're in a fast-paced startup environment.
  Prioritize shipping working features over perfection.
```

## Examples

### Example 1: Claude for Enterprise

```python
engine = PromptTemplateEngine()

prompt = engine.render_system_prompt(
    llm="claude",
    deployment="enterprise",
    cwd="/enterprise/secure-project"
)

# Result: Strict security policies, audit logging, XML format
```

### Example 2: GPT-4 for Personal Use

```python
prompt = engine.render_system_prompt(
    llm="gpt4",
    deployment="personal",
    cwd="/home/user/hobby-project"
)

# Result: Friendly, helpful, function-calling format
```

### Example 3: CI/CD Automation

```python
prompt = engine.render_system_prompt(
    llm="claude",
    deployment="cicd",
    cwd="/builds/project-123"
)

# Result: Fully non-interactive, deterministic, fast-fail
```

### Example 4: Custom Variables

```python
prompt = engine.render_system_prompt(
    llm="claude",
    deployment="personal",
    cwd="/my/project",
    custom_instructions="Always use TypeScript strict mode"
)
```

## Advanced Usage

### Validating Templates and Contexts

```python
engine = PromptTemplateEngine()

# Validate template
if engine.validate_template("system_prompt_claude.j2"):
    print("Template is valid")

# Validate context
if engine.validate_context("enterprise"):
    print("Context is valid")
```

### Listing Available Options

```python
# List all templates
templates = engine.list_available_templates()
print(f"Available templates: {templates}")

# List all contexts
contexts = engine.list_available_contexts()
print(f"Available contexts: {contexts}")

# Get context information
info = engine.get_context_info("enterprise")
print(f"Context: {info['description']}")
print(f"Variables: {info['variables']}")
```

### Reloading Contexts

Contexts are cached. To reload after editing:

```python
engine.reload_contexts()
```

### Custom Template Directories

```python
from pathlib import Path

engine = PromptTemplateEngine(
    templates_dir=Path("/custom/templates"),
    contexts_dir=Path("/custom/contexts")
)
```

## Best Practices

### For Template Authors

1. **Use inheritance**: Extend `system_prompt_default.j2` for consistency
2. **LLM-specific optimizations**: Leverage each LLM's strengths
   - Claude: Use `<thinking>` tags, XML format
   - GPT-4: Use function-calling style, JSON examples
3. **Keep DRY**: Use Jinja2 includes and macros for repeated sections
4. **Test thoroughly**: Validate with different contexts

### For Context Authors

1. **Extend default**: Always extend `default.yaml` for consistency
2. **Document clearly**: Add good descriptions
3. **Security first**: Define appropriate safety rules
4. **Environment-specific**: Tailor to actual deployment needs

### For Deployers

1. **Choose the right context**: Match your deployment environment
2. **Customize as needed**: Create deployment-specific contexts
3. **Test before production**: Validate prompts generate correctly
4. **Version control**: Track context changes with your code

## Integration with Gambiarra

The prompt engine integrates seamlessly with Gambiarra's server:

```python
from gambiarra.server.prompts.engine import get_prompt_engine

# In your AI provider
engine = get_prompt_engine()

# Generate prompt for current session
system_prompt = engine.render_system_prompt(
    llm=session.llm_type,
    deployment=config.deployment_context,
    cwd=session.working_directory
)

# Use in AI request
response = await ai_provider.stream_completion(
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ]
)
```

## Migration from Hardcoded Prompts

To migrate from hardcoded prompts:

1. **Extract current prompt** to a template file
2. **Identify variables** and move them to a context
3. **Create LLM variants** for different models
4. **Update code** to use `PromptTemplateEngine`
5. **Test thoroughly** with existing workflows

## Demo

Run the demo to see examples:

```bash
python examples/prompt_engine_demo.py
```

## Troubleshooting

### Template Not Found

- Ensure template file exists in `templates/` directory
- Check file extension is `.j2` or `.jinja2`
- Verify template name matches exactly

### Context Not Found

- Ensure context file exists in `contexts/` directory
- Check file extension is `.yaml` or `.yml`
- Verify context name (without extension)

### Invalid YAML

- Validate YAML syntax with a linter
- Check indentation (spaces, not tabs)
- Ensure quotes are balanced

### Template Rendering Errors

- Check all referenced variables exist in context
- Validate Jinja2 syntax
- Use `{% if variable %}` for optional variables

## Contributing

To add new templates or contexts:

1. Create the template/context file
2. Validate it works with the engine
3. Document any new variables or features
4. Test with multiple scenarios
5. Submit a pull request

---

For more information, see `examples/prompt_engine_demo.py` or the engine source at `engine/template_engine.py`.
