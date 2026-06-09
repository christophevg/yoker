# Demo Plugin for Yoker

This is a demonstration plugin for the Yoker plugin system. It shows how to create a plugin that provides tools, skills, and agents.

## Components

### 1. EchoTool

A simple tool that echoes back input messages with a prefix.

```python
from demo.yoker import EchoTool

tool = EchoTool()
result = await tool.execute(message="Hello")
# Result: "Echo: Hello"
```

### 2. Greeting Skill

A skill that provides friendly greetings.

Location: `demo/skills/greeting.md`

### 3. Demo Agent

A demonstration agent definition.

Location: `demo/agents/demo.md`

## Structure

```
examples/plugins/demo/
  __init__.py           # Package marker with __YOKER_MANIFEST__
  yoker/
    __init__.py         # Plugin manifest and tool exports
    tools.py            # EchoTool implementation
  skills/
    greeting.md         # Greeting skill definition
  agents/
    demo.md             # Demo agent definition
```

## Usage

### As a Plugin

```bash
# Run yoker with demo plugin (future feature)
yoker --with demo

# The agent can now use:
# - demo:echo tool
# - demo:greeting skill (via /greeting)
# - demo:demo agent
```

### Programmatic Loading

```python
from yoker.plugins import load_plugin, load_skills_from_package, load_agents_from_package
from yoker.plugins import register_tools, register_skills
from yoker.tools import ToolRegistry
from yoker.skills import SkillRegistry

# Load the plugin
plugin = load_plugin("demo")

# Register tools
tool_registry = ToolRegistry()
register_tools(plugin.tools, tool_registry, namespace="demo")

# Load and register skills
skills = load_skills_from_package("demo", skills_dir="skills")
skill_registry = SkillRegistry()
register_skills(skills, skill_registry, namespace="demo")

# Load agents
agents = load_agents_from_package("demo", agents_dir="agents")
```

## Testing

The plugin includes comprehensive tests in `tests/test_demo_plugin.py` that validate:

- Plugin discovery and import
- Manifest declaration
- Tool functionality
- Skill loading
- Agent loading
- Registration with namespaces

Run tests:

```bash
pytest tests/test_demo_plugin.py -v
```

## Plugin Development Notes

### Manifest

The plugin exports `__YOKER_MANIFEST__` in both the main `__init__.py` and the `yoker` submodule for backward compatibility:

```python
__YOKER_MANIFEST__ = PluginManifest(
  tools=[EchoTool()],
  skills_dir="skills",
  agents_dir="agents",
)
```

### Tools

Tools must:
1. Inherit from `yoker.tools.base.Tool`
2. Implement `name`, `description`, `get_schema()`, and `execute()` methods
3. Return `ToolResult` from `execute()`

### Skills

Skills are Markdown files with YAML frontmatter:

```markdown
---
name: greeting
description: A friendly greeting skill
triggers:
  - hello
  - hi
---

## Instructions
... skill content ...
```

### Agents

Agents are Markdown files with YAML frontmatter:

```markdown
---
name: demo
description: A demonstration agent
model: llama3.2:latest
tools:
  - demo:echo
---

System prompt content...
```

## Current Limitations

1. Skills must be at the package level (`demo/skills/`), not in the yoker submodule
2. Agent files must end with `.md` extension
3. Skill files must NOT be named `SKILL.md` (reserved for future use)