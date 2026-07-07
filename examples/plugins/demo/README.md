# Demo Plugin for Yoker

This is a demonstration plugin for the Yoker plugin system. It shows how to create a plugin that provides tools, skills, and agents.

## Components

### 1. Echo Tool

A simple tool that echoes back input messages with a prefix.

```python
from yoker.tools import ToolRegistry
from yoker_plugin_demo.tools import echo

registry = ToolRegistry()
registry.register(echo)
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
    tools.py              # echo tool implementation
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
# Output: PluginManifest(tools=[<function echo at 0x...>], skills_dir='skills', agents_dir='agents')
```

### Running with Plugin

```bash
# Run yoker with demo plugin
# (requires [plugins] enabled = true and [plugins.trusted] yoker_plugin_demo = true)
uv run yoker --with yoker_plugin_demo --agent demo

# The agent can now use:
# - echo tool (namespaced as "echo" when loaded via plugin)
# - greeting skill (via /greeting)
# - demo agent definition
```

### Programmatic Loading

Plugin components are discovered via the `load_plugins(config, extra_plugins=())`
generator (in `yoker.plugins`) and registered through the `register_plugin_*`
methods on each registry. `load_plugins` applies the global-enabled gate and
per-plugin security checks, then yields `PluginComponents` (tools, skills,
agents, source) for the registries to consume.

```python
from yoker.config import Config
from yoker.plugins import load_plugins
from yoker.tools import ToolRegistry
from yoker.skills import SkillRegistry

config = Config()
config.plugins.enabled = True

# Load the plugin (plus the always-loaded yoker builtin) and register
# tools and skills. load_plugins yields PluginComponents — registries
# apply namespacing via the register_plugin_* methods.
plugins = list(load_plugins(config, extra_plugins=("yoker_plugin_demo",)))

tool_registry = ToolRegistry()
tool_registry.register_plugin_tools(plugins, config)

skill_registry = SkillRegistry()
skill_registry.register_plugin_skills(plugins)

# Plugin agents are registered on the AgentRegistry via
# register_configured_plugin_agents (used by Session); the PluginComponents
# yielded above carry the loaded agent definitions in `.agents`.
```

For direct single-package discovery, use `load_plugin(package_name)` to get a
`PluginComponents` without the enabled/security gating, then register it
manually with the registry `register_plugin_*` methods (or `register_all` with
an explicit namespace).

## Testing

The demo plugin is exercised through Yoker's main test suite, which validates:

- Plugin discovery and import
- Manifest declaration
- Tool functionality
- Skill loading
- Agent loading
- Registration with namespaces

Run the relevant tests from the project root:

```bash
pytest tests/test_plugins/test_loader.py -v
```

## Plugin Development Notes

### Package Naming

**CRITICAL**: The package directory MUST NOT conflict with the main `yoker` package. Use a unique name like `yoker_plugin_demo` instead of `yoker`.

### Manifest

The plugin exports `__YOKER_MANIFEST__` in `yoker_plugin_demo/__init__.py`:

```python
__YOKER_MANIFEST__ = PluginManifest(
  tools=[echo],
  skills_dir="skills",
  agents_dir="agents",
)
```

### Tools

Tools are plain functions or callable class instances:
1. Annotate string parameters with `yoker.tools.annotations` markers (`Path`, `Url`, `Query`, `Text`).
2. Use the function/class docstring as the tool description, or set `__yoker_description__`.
3. Return any JSON-serializable value; the harness wraps results and exceptions in `ToolResult`.

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
