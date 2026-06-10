# Demo Plugin for Yoker

This is a demonstration plugin for the Yoker plugin system. It shows how to create a plugin that provides tools, skills, and agents.

## Components

### 1. EchoTool

A simple tool that echoes back input messages with a prefix.

```python
from yoker_plugin_demo import EchoTool

tool = EchoTool()
result = await tool.execute(message="Hello")
# Result: "Echo: Hello"
```

### 2. Greeting Skill

A skill that provides friendly greetings.

Location: `yoker_plugin_demo/skills/greeting/SKILL.md`

### 3. Demo Agent

A demonstration agent definition.

Location: `yoker_plugin_demo/agents/demo.md`

## Structure

```
examples/plugins/demo/
  pyproject.toml          # Package configuration
  README.md               # This file
  yoker_plugin_demo/      # Plugin package (NO conflict with yoker!)
    __init__.py           # Plugin manifest with __YOKER_MANIFEST__
    tools.py              # EchoTool implementation
    agents/
      demo.md             # Demo agent definition
    skills/
      greeting/
        SKILL.md          # Greeting skill definition
```

## Usage

### Installation

```bash
# From yoker root directory
cd /path/to/yoker
uv pip install -e examples/plugins/demo

# Or from plugin directory
cd examples/plugins/demo
uv pip install -e .
```

### Verification

```bash
# Verify installation
python -c "import yoker_plugin_demo; print(yoker_plugin_demo.__YOKER_MANIFEST__)"
# Output: PluginManifest(tools=[EchoTool()], skills_dir='skills', agents_dir='agents')
```

### Running with Plugin

```bash
# Run yoker with demo plugin
uv run yoker --with yoker-plugin-demo --agents-definition plugin://yoker-plugin-demo/agents/demo

# The agent can now use:
# - echo tool (namespaced as "echo" when loaded via plugin)
# - greeting skill (via /greeting)
# - demo agent definition
```

### Programmatic Loading

```python
from yoker.plugins import load_plugin, load_skills_from_package, load_agents_from_package
from yoker.plugins import register_tools, register_skills
from yoker.tools import ToolRegistry
from yoker.skills import SkillRegistry

# Load the plugin
plugin = load_plugin("yoker_plugin_demo")

# Register tools
tool_registry = ToolRegistry()
register_tools(plugin.tools, tool_registry, namespace="demo")

# Load and register skills
skills = load_skills_from_package("yoker_plugin_demo", skills_dir="skills")
skill_registry = SkillRegistry()
register_skills(skills, skill_registry, namespace="demo")

# Load agents
agents = load_agents_from_package("yoker_plugin_demo", agents_dir="agents")
```

## Testing

The plugin includes comprehensive tests that validate:

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

### Package Naming

**CRITICAL**: The package directory MUST NOT conflict with the main `yoker` package. Use a unique name like `yoker_plugin_demo` instead of `yoker`.

### Manifest

The plugin exports `__YOKER_MANIFEST__` in `yoker_plugin_demo/__init__.py`:

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

## Why the Package Rename?

The original structure had `yoker/` subdirectory which conflicts with the main yoker package when installed. The new structure uses `yoker_plugin_demo/` to:

1. Avoid namespace collision with yoker package
2. Allow both packages to be installed simultaneously
3. Follow Python package naming best practices
4. Make the plugin import path explicit (`import yoker_plugin_demo`)

## Current Limitations

1. Skills must be at the package level (`yoker_plugin_demo/skills/`)
2. Agent files must end with `.md` extension
3. Skill files must be named `SKILL.md`