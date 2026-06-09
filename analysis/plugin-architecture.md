# Plugin Architecture Design

**Date**: 2026-06-08
**Issue**: #14 - Package Plugin System
**Priority**: P1 (MVP Phase 3)
**Status**: Design (Updated with configuration and built-in plugin insights)

## Executive Summary

This document defines the plugin architecture for yoker's Package Plugin System, enabling Python packages to provide tools, skills, and agents to the yoker environment. The design follows existing patterns from the skill system while addressing namespace management, error handling, and security concerns.

**Key Design Decisions**:
- **Importlib-based discovery**: Use Python's import mechanism for plugin discovery
- **Namespace prefixes**: `{package}:{component}` format for all plugin components
- **Graceful degradation**: Continue operation when plugins fail to load
- **Security model**: No sandboxing - plugins run with full yoker privileges
- **Built-in as plugin**: Standard tools/skills/agents provided by "yoker" package itself
- **Configuration integration**: Plugin tools can have TOML configuration like built-in tools
- **Simplified CLI**: Config-based plugin specification; `--with` proposed for Clevis

## Goals and Non-Goals

### Goals

1. **Enable package extensibility**: Allow third-party packages to provide yoker components
2. **Maintain simplicity**: Use established Python patterns (importlib, module attributes)
3. **Preserve user experience**: Graceful error handling, clear error messages
4. **Support multiple component types**: Tools, skills, and agents
5. **Maintain namespace hygiene**: Prevent name collisions between packages
6. **Leverage existing infrastructure**: Use existing registries and loaders

### Non-Goals

1. **Plugin sandboxing**: Plugins run with full yoker privileges (same trust model as skills)
2. **Hot reloading**: Plugins are loaded at startup, not dynamically
3. **Plugin versioning**: No version conflict resolution between plugins
4. **Plugin dependencies**: Plugins must manage their own dependencies
5. **Plugin marketplace**: No central plugin repository or discovery mechanism
6. **Short name resolution**: All tool calls require full namespace (no `find` → `pkgq:find`)
7. **Plugin metadata/version constraints**: Start simple, no version checking
8. **Override/alias system**: Fail on collision, no custom namespace mapping

## Architecture Overview

### Component Types

Yoker supports three plugin component types:

| Component | Purpose | Registry | Namespace Example |
|-----------|---------|----------|-------------------|
| **Tools** | Execute actions | `ToolRegistry` | `pkgq:find` |
| **Skills** | Inject context | `SkillRegistry` | `c3:develop-skill` |
| **Agents** | Autonomous tasks | `AgentRegistry` (future) | `c3:code-reviewer` |

### Built-in Plugin

**"Eat Your Own Dogfood"**: The yoker package itself provides its standard tools, skills, and agents as a built-in plugin named `yoker` (or `standard`). This ensures consistency between built-in and third-party components:

**Benefits**:
- No special paths or registration logic for built-in components
- All tools use same namespace format: `yoker:read`, `yoker:write`, etc.
- Same configuration mechanism for all tools
- Easier testing - built-in tools loaded via same plugin loader
- Plugin authors see same pattern as built-in tools

**Implementation**:
```python
# src/yoker/plugins/builtin.py

from yoker.tools import ReadTool, WriteTool, ListTool, SearchTool
from yoker.skills import ThinkSkill, HelpSkill

TOOLS = [
  ReadTool(),
  WriteTool(),
  ListTool(),
  SearchTool(),
]

SKILLS = [
  ThinkSkill(),
  HelpSkill(),
]

AGENTS = []  # Future: standard agents
```

**Auto-loading**:
The built-in plugin is loaded automatically by the yoker runtime, no `--with yoker` needed.

### Configuration Integration

Plugin tools can have configuration that integrates with yoker's TOML config system, following the same pattern as built-in tools.

**Example: GitTool with allowed operations**

```toml
# yoker.toml

[tools]
# Built-in tools configuration
filesystem.allowed_paths = ["/workspace"]
filesystem.allowed_operations = ["read", "write", "list"]

# Plugin tools configuration (namespace prefix)
[tools.pkgq]
package_index_url = "https://pypi.org/simple"
cache_ttl = 3600

[tools.git]
allowed_operations = ["status", "log", "diff", "commit"]
require_approval_for = ["push", "reset"]
```

**Plugin tool configuration structure**:

```python
# pkgq/yoker/tools.py

from yoker.tools import Tool, ToolResult
from dataclasses import dataclass

@dataclass
class FindPackageConfig:
  """Configuration for FindPackageTool."""
  package_index_url: str = "https://pypi.org/simple"
  cache_ttl: int = 3600

class FindPackageTool(Tool):
  """Find package documentation."""

  name = "find"
  description = "Find package documentation"

  def __init__(self, config: FindPackageConfig | None = None):
    self.config = config or FindPackageConfig()

  async def execute(self, package: str, version: str | None = None) -> ToolResult:
    # Use self.config.package_index_url
    # Use self.config.cache_ttl
    ...
```

**Configuration loading**:

```python
# src/yoker/plugins/loader.py

def load_plugin(package_name: str, config: dict | None = None) -> PluginComponents | None:
  """Load plugin components from a package.

  Args:
    package_name: Python package name (e.g., "pkgq", "c3").
    config: Optional configuration dict from yoker.toml.

  Returns:
    PluginComponents if plugin exists, None if not found.
  """
  module = importlib.import_module(f"{package_name}.yoker")

  # Extract and configure components
  tools = []
  for tool_class_or_instance in _extract_list(module, "TOOLS"):
    if isinstance(tool_class_or_instance, type):
      # Tool class needs instantiation with config
      tool_config = config.get(package_name, {}) if config else {}
      tool = tool_class_or_instance(config=tool_config)
    else:
      # Tool instance already created
      tool = tool_class_or_instance
    tools.append(tool)

  return PluginComponents(tools=tools, ...)
```

### Discovery Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    Plugin Discovery Flow                         │
└─────────────────────────────────────────────────────────────────┘

1. User starts yoker (with or without --with argument)

2. Built-in plugin auto-loaded
   │
   ├──▶ Load: src/yoker/plugins/builtin.py
   │    │
   │    ├──▶ Register tools: yoker:read, yoker:write, yoker:list, etc.
   │    ├──▶ Register skills: yoker:think, yoker:help
   │    └──▶ Apply configuration from yoker.toml
   │
   ▼
3. Load plugin packages (from config or --with)
   │
   ├──▶ Read yoker.toml: plugins = ["pkgq", "c3"]
   │    │
   │    ├──▶ For each package:
   │    │    │
   │    │    ├──▶ Try: import {package}.yoker
   │    │    │    │
   │    │    │    ├──▶ Extract TOOLS, SKILLS, AGENTS
   │    │    │    ├──▶ Load configuration from yoker.toml
   │    │    │    ├──▶ Configure tools with package-specific config
   │    │    │    └──▶ Register in ToolRegistry with namespace
   │    │    │
   │    │    └──▶ Failure: Log warning, continue
   │    │
   │    └──▶ CLI --with (future via Clevis): extends plugin list
   │
   ▼
4. Agent starts with all registries populated
```

### Integration Points

```
┌─────────────────────────────────────────────────────────────────┐
│                    Existing Infrastructure                       │
└─────────────────────────────────────────────────────────────────┘

PluginLoader ──────┬──▶ ToolRegistry ──────── Agent.tool_registry
                   │         │
                   │         └──▶ get_schema() ──▶ LLM
                   │
                   ├──▶ SkillRegistry ─────── Agent.skill_registry
                   │         │
                   │         └──▶ list_skills() ──▶ Context injection
                   │
                   └──▶ AgentRegistry ──────── (future)
                             │
                             └──▶ load_agent() ──▶ Agent.spawn()
```

## Plugin Discovery Mechanism

### Package Module Convention

Packages opt-in to yoker integration by providing a `yoker` submodule:

```
pkgq/
  __init__.py          # Package root
  yoker/
    __init__.py        # Yoker integration point
    tools.py           # Tool definitions
    skills.py          # Skill definitions (optional)
```

**Why submodule?**
- Clear separation between package core and yoker integration
- Avoids namespace pollution in package root
- Allows lazy loading (import only when needed)
- Follows Python packaging best practices

### Module Interface

```python
# pkgq/yoker/__init__.py

from yoker.tools import Tool
from yoker.skills import Skill

# Export component lists
TOOLS: list[Tool] = [
  FindPackageTool(),
  # ... more tools
]

SKILLS: list[Skill] = [
  Skill(
    name="create",
    description="Generate PACKAGE.md for a project",
    content="...",
  ),
  # ... more skills
]

AGENTS: list[AgentDefinition] = []  # Future use

# Optional: Plugin metadata
__YOKER_VERSION__ = "1.0.0"  # Minimum yoker version
__PLUGIN_VERSION__ = "0.1.0"  # Plugin version
```

**Interface Design Rationale**:
- **Simple lists**: Easy to understand, no complex protocols
- **Type hints**: IDE support and static checking
- **Optional metadata**: Version constraints without enforcement (future)
- **All lists optional**: Packages can provide any combination of components

### Discovery Implementation

**File**: `src/yoker/plugins/loader.py`

```python
"""Plugin loader for yoker.

Discovers and loads plugins from Python packages.
"""

import importlib
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from yoker.exceptions import PluginError

if TYPE_CHECKING:
  from yoker.tools import Tool
  from yoker.skills import Skill
  from yoker.agents import AgentDefinition

log = logging.getLogger(__name__)


@dataclass
class PluginComponents:
  """Container for plugin-discovered components."""

  tools: list["Tool"]
  skills: list["Skill"]
  agents: list["AgentDefinition"]
  source: str  # Package name


def load_plugin(package_name: str) -> PluginComponents | None:
  """Load plugin components from a package.

  Attempts to import {package_name}.yoker module and extract
  TOOLS, SKILLS, and AGENTS lists.

  Args:
    package_name: Python package name (e.g., "pkgq", "c3").

  Returns:
    PluginComponents if plugin exists, None if not found.

  Raises:
    PluginError: If plugin module exists but fails to load.
  """
  module_name = f"{package_name}.yoker"

  try:
    module = importlib.import_module(module_name)
    log.info("plugin_module_imported", package=package_name)
  except ImportError as e:
    # Package doesn't have yoker submodule - not an error
    log.debug(
      "plugin_module_not_found",
      package=package_name,
      module=module_name,
      error=str(e),
    )
    return None
  except Exception as e:
    # Module exists but failed to import - this is an error
    log.error(
      "plugin_module_import_error",
      package=package_name,
      module=module_name,
      error=str(e),
    )
    raise PluginError(
      package=package_name,
      message=f"Failed to import plugin module '{module_name}': {e}",
    ) from e

  # Extract component lists
  tools = _extract_list(module, "TOOLS")
  skills = _extract_list(module, "SKILLS")
  agents = _extract_list(module, "AGENTS")

  log.info(
    "plugin_components_extracted",
    package=package_name,
    tools=len(tools),
    skills=len(skills),
    agents=len(agents),
  )

  return PluginComponents(
    tools=tools,
    skills=skills,
    agents=agents,
    source=package_name,
  )


def _extract_list(module, attribute: str) -> list:
  """Extract a list from module attributes.

  Args:
    module: Imported module object.
    attribute: Attribute name (e.g., "TOOLS", "SKILLS").

  Returns:
    List of components, or empty list if not defined.
  """
  value = getattr(module, attribute, None)

  if value is None:
    return []

  if not isinstance(value, list):
    log.warning(
      "plugin_attribute_not_list",
      attribute=attribute,
      type=type(value).__name__,
    )
    return []

  return value


def load_plugins(package_names: list[str]) -> list[PluginComponents]:
  """Load multiple plugins.

  Args:
    package_names: List of package names to load.

  Returns:
    List of successfully loaded PluginComponents.

  Raises:
    PluginError: If any plugin fails critically.
  """
  plugins: list[PluginComponents] = []

  for package_name in package_names:
    try:
      plugin = load_plugin(package_name)
      if plugin:
        plugins.append(plugin)
    except PluginError as e:
      # Log but continue with other plugins
      log.error(
        "plugin_load_failed",
        package=package_name,
        error=str(e),
      )
      # Re-raise to notify user
      raise

  return plugins


__all__ = [
  "PluginComponents",
  "load_plugin",
  "load_plugins",
]
```

### Exception Handling

**File**: `src/yoker/exceptions.py` (additions)

```python
class PluginError(YokerError):
  """Error loading or registering a plugin."""

  def __init__(self, package: str, message: str):
    self.package = package
    super().__init__(f"Plugin '{package}': {message}")
```

## Component Registration

### Namespace Format

All plugin components use namespace prefixes:

```
{package}:{component_name}
```

**Examples**:
- `pkgq:find` - FindPackageTool from pkgq package
- `c3:develop-skill` - develop-skill from c3 package
- `c3:code-reviewer` - code-reviewer agent from c3 package

**Why colon separator?**
- Unambiguous (not used in typical tool/skill names)
- Matches existing skill namespace pattern (see `api-skill-infrastructure.md`)
- Familiar to users (similar to `git:stash`, `docker:run`)

### Tool Registration

**File**: `src/yoker/plugins/registration.py`

```python
"""Register plugin components with yoker registries."""

import logging
from typing import TYPE_CHECKING

from yoker.tools import ToolRegistry

if TYPE_CHECKING:
  from yoker.tools import Tool
  from yoker.skills import Skill
  from yoker.agents import AgentDefinition

log = logging.getLogger(__name__)


def register_tools(
  tools: list["Tool"],
  registry: ToolRegistry,
  namespace: str,
) -> list[str]:
  """Register tools with namespace prefix.

  Args:
    tools: List of Tool instances.
    registry: ToolRegistry to register with.
    namespace: Package namespace prefix.

  Returns:
    List of registered tool names.

  Raises:
    ValueError: If tool name already registered.
  """
  registered = []

  for tool in tools:
    # Create namespaced name
    namespaced_name = f"{namespace}:{tool.name}"

    # Check for collision
    if registry.get(namespaced_name):
      log.warning(
        "tool_name_collision",
        name=namespaced_name,
        namespace=namespace,
        existing=registry.get(namespaced_name).__class__.__name__,
        new=tool.__class__.__name__,
      )
      raise ValueError(
        f"Tool '{namespaced_name}' is already registered "
        f"(from {registry.get(namespaced_name).__class__.__name__})"
      )

    # Clone tool with namespaced name
    # Note: Tools are dataclasses, we create a new instance with modified name
    namespaced_tool = _clone_tool_with_name(tool, namespaced_name)

    registry.register(namespaced_tool)
    registered.append(namespaced_name)

    log.info(
      "tool_registered",
      original_name=tool.name,
      namespaced_name=namespaced_name,
      namespace=namespace,
    )

  return registered


def _clone_tool_with_name(tool: "Tool", new_name: str) -> "Tool":
  """Create a copy of tool with namespaced name.

  Tools are frozen dataclasses, so we create a new instance
  with modified name attribute.

  Args:
    tool: Original tool instance.
    new_name: New name for the tool.

  Returns:
    New tool instance with namespaced name.
  """
  from dataclasses import fields

  # Get all field values from original tool
  field_values = {
    f.name: getattr(tool, f.name)
    for f in fields(tool)
  }

  # Override name
  field_values["name"] = new_name

  # Create new instance
  return type(tool)(**field_values)


def register_skills(
  skills: list["Skill"],
  registry: "SkillRegistry",
  namespace: str,
) -> list[str]:
  """Register skills with namespace prefix.

  Skills already support namespace via Skill.namespace attribute.

  Args:
    skills: List of Skill instances.
    registry: SkillRegistry to register with.
    namespace: Package namespace prefix.

  Returns:
    List of registered skill names.
  """
  from yoker.skills import Skill

  registered = []

  for skill in skills:
    # Create namespaced skill
    # Skill.full_name already handles namespace
    namespaced_skill = Skill(
      name=skill.name,
      description=skill.description,
      content=skill.content,
      triggers=skill.triggers,
      tools=skill.tools,
      source_path=skill.source_path,
      namespace=namespace,  # Set namespace
    )

    try:
      registry.register(namespaced_skill)
      registered.append(namespaced_skill.full_name)

      log.info(
        "skill_registered",
        original_name=skill.name,
        namespaced_name=namespaced_skill.full_name,
        namespace=namespace,
      )
    except ValueError as e:
      # Skill already registered
      log.warning(
        "skill_name_collision",
        name=namespaced_skill.full_name,
        namespace=namespace,
        error=str(e),
      )
      raise

  return registered


def register_agents(
  agents: list["AgentDefinition"],
  registry: "AgentRegistry",
  namespace: str,
) -> list[str]:
  """Register agents with namespace prefix.

  Note: AgentRegistry doesn't exist yet, this is for future use.

  Args:
    agents: List of AgentDefinition instances.
    registry: AgentRegistry to register with.
    namespace: Package namespace prefix.

  Returns:
    List of registered agent names.
  """
  # Future implementation
  registered = []

  for agent_def in agents:
    # Create namespaced name
    namespaced_name = f"{namespace}:{agent_def.name}"

    # Clone with namespaced name
    namespaced_agent = _clone_agent_with_name(agent_def, namespaced_name)

    registry.register(namespaced_agent)
    registered.append(namespaced_name)

    log.info(
      "agent_registered",
      original_name=agent_def.name,
      namespaced_name=namespaced_name,
      namespace=namespace,
    )

  return registered


def _clone_agent_with_name(
  agent_def: "AgentDefinition",
  new_name: str,
) -> "AgentDefinition":
  """Create a copy of agent definition with namespaced name."""
  from dataclasses import fields

  field_values = {
    f.name: getattr(agent_def, f.name)
    for f in fields(agent_def)
  }
  field_values["name"] = new_name

  return type(agent_def)(**field_values)


__all__ = [
  "register_tools",
  "register_skills",
  "register_agents",
]
```

### Registration in Agent Initialization

**File**: `src/yoker/agent.py` (modifications)

```python
def __init__(
  self,
  config: Config,
  plugins: list[str] | None = None,  # Override from config
):
  # ... existing initialization ...

  # Load built-in plugin first (always loaded)
  self._load_builtin_plugin(config)

  # Load configured/override plugins
  plugin_packages = plugins if plugins is not None else config.plugins.packages
  for package_name in plugin_packages:
    self._load_plugin(package_name, config)

def _load_builtin_plugin(self, config: Config) -> None:
  """Load built-in yoker plugin (standard tools/skills).

  Args:
    config: Configuration with tool settings.
  """
  from yoker.plugins.builtin import TOOLS, SKILLS

  # Apply configuration to built-in tools
  configured_tools = self._configure_tools(TOOLS, config.tools)

  # Register with "yoker" namespace
  for tool in configured_tools:
    namespaced_name = f"yoker:{tool.name}"
    self.tool_registry.register(_clone_tool_with_name(tool, namespaced_name))

  for skill in SKILLS:
    # Skills already support namespace attribute
    skill.namespace = "yoker"
    self.skill_registry.register(skill)

  log.info(
    "builtin_plugin_loaded",
    tools=len(TOOLS),
    skills=len(SKILLS),
  )

def _load_plugin(self, package_name: str, config: Config) -> None:
  """Load and register a plugin package.

  Args:
    package_name: Package name to load.
    config: Configuration with plugin settings.

  Raises:
    PluginError: If plugin loading fails critically.
  """
  from yoker.plugins import load_plugin

  try:
    # Get plugin-specific configuration
    plugin_config = getattr(config.plugins, package_name, {})

    # Load plugin with configuration
    plugin = load_plugin(package_name, config=plugin_config)
    if not plugin:
      log.debug("plugin_not_found", package=package_name)
      return

    # Register tools
    if plugin.tools:
      self._register_tools(plugin.tools, namespace=plugin.source)

    # Register skills
    if plugin.skills:
      self._register_skills(plugin.skills, namespace=plugin.source)

    log.info(
      "plugin_loaded",
      package=plugin.source,
      tools=len(plugin.tools),
      skills=len(plugin.skills),
    )

  except PluginError as e:
    log.error("plugin_load_error", package=e.package, error=str(e))
    raise
```

## CLI Integration

### Current Approach: Configuration-Based

**File**: `yoker.toml`

Plugins are specified in the configuration file, not via CLI arguments. This follows yoker's design principle of configuration-driven behavior.

```toml
# yoker.toml

[plugins]
# List of plugin packages to load
packages = ["pkgq", "c3"]

# Optional: Plugin-specific settings
[plugins.pkgq]
package_index_url = "https://pypi.org/simple"

[plugins.c3]
some_setting = "value"
```

**File**: `src/yoker/config/schema.py`

```python
@dataclass(frozen=True)
class PluginConfig:
  """Configuration for plugin loading."""

  packages: list[str] = field(default_factory=list)

@dataclass(frozen=True)
class Config:
  """Main configuration."""

  # ... existing fields ...

  plugins: PluginConfig = field(default_factory=PluginConfig)
```

**File**: `src/yoker/agent.py`

```python
def __init__(
  self,
  config: Config,
  plugins: list[str] | None = None,  # Override from CLI (future)
):
  # Load plugins from config (can be overridden by CLI)
  plugin_packages = plugins or config.plugins.packages

  # Load built-in plugin first
  self._load_builtin_plugin(config)

  # Load configured plugins
  for package_name in plugin_packages:
    self._load_plugin(package_name, config)
```

### Future Approach: Clevis Integration

The `--with` argument should be proposed as a Clevis feature rather than implemented in yoker directly. This provides a consistent plugin mechanism across all Clevis-based applications.

**Proposed Clevis feature**:

```python
# In clevis/config.py (proposed)

@dataclass
class SecurityConfig:
  # ... existing fields ...

  # Proposed: Plugin loading
  plugins: list[str] = field(default_factory=list)

# In clevis/cli.py (proposed)

def parse_args():
  parser.add_argument(
    "--with",
    action="append",
    dest="plugins",
    metavar="PACKAGE",
    help="Load plugin from Python package",
  )
```

**Benefits of Clevis integration**:
- Consistent plugin loading across all Clevis applications
- Centralized `--with` argument handling
- Clevis can manage plugin security sandboxing in future
- Applications get plugin support without implementing CLI parsing

**yoker's role while waiting for Clevis**:
- Use configuration file for plugin specification
- Implement `--with` as temporary local solution if needed
- Plan migration to Clevis `--with` when available

### Configuration File Approach

**Why configuration file for now?**:
1. Aligns with yoker's TOML-based configuration philosophy
2. Allows plugin-specific settings (like `package_index_url`)
3. No need to remember plugin names on every invocation
4. Easier to manage multiple plugins
5. Can be overridden by future Clevis `--with` argument

**Example configuration**:

```toml
# yoker.toml

[agent]
model = "llama3.2:latest"
system_prompt = "You are a helpful assistant."

[plugins]
packages = ["pkgq", "c3"]

[plugins.pkgq]
package_index_url = "https://custom.pypi.org/simple"
cache_ttl = 7200

[plugins.git]
allowed_operations = ["status", "log", "diff"]

[tools.filesystem]
allowed_paths = ["/workspace"]
allowed_operations = ["read", "write", "list"]
```

### Usage Examples

```bash
# Configuration-based (current approach)
yoker --config yoker.toml

# With default config (loads plugins from yoker.toml)
yoker

# With agent definition
yoker --agent myagent.md

# Future: Clevis --with argument
yoker --with pkgq --with c3  # Would work once Clevis implements --with
```

## Namespace Management

### Collision Handling

**Strategy**: Fail on collision (explicit error)

```python
# Register tool
try:
  register_tools(tools, registry, namespace="pkgq")
except ValueError as e:
  # Tool name collision
  log.error("tool_collision", error=str(e))
  raise PluginError(
    package="pkgq",
    message=f"Tool name collision: {e}",
  )
```

**Why fail on collision?**
- Prevents silent failures and unpredictable behavior
- Forces explicit naming in tool calls
- Makes conflicts visible to users immediately
- No ambiguity about which tool is invoked

### Namespace Resolution (Simplified)

**No short name resolution** - All tool invocations require full namespace:

```python
# Required: Full name with namespace
tool = registry.get("pkgq:find")  # ✓ Correct
tool = registry.get("yoker:read")  # ✓ Correct (built-in)

# Not supported: Short name
tool = registry.get("find")  # ✗ Returns None (no short name resolution)
```

**Why no short name resolution?**
1. **Explicit is better than implicit**: Users always know which tool is invoked
2. **No lookup ambiguity**: No need to search across namespaces
3. **Simpler implementation**: Direct dictionary lookup only
4. **Avoids order dependencies**: No need to define "built-in first" ordering
5. **Future-friendly**: When Clevis implements `--with`, short names would be confusing

**Implementation**:

```python
def get(self, name: str) -> Tool | None:
  """Get tool by full namespaced name.

  Args:
    name: Tool name with namespace (e.g., "pkgq:find", "yoker:read").

  Returns:
    Tool if found, None otherwise.

  Note:
    Short names (without namespace) are NOT resolved.
    Always use full namespace: "pkgq:find", not "find".
  """
  # Only exact match - no short name resolution
  return self._tools.get(name)
```

**Listing tools**:

```python
# List all tools (all have namespaces)
tools = registry.list_tools()
# ["yoker:read", "yoker:write", "yoker:list", "pkgq:find", "pkgq:create"]

# Filter by namespace
yoker_tools = [t for t in tools if t.startswith("yoker:")]
pkgq_tools = [t for t in tools if t.startswith("pkgq:")]
```

## Security Model

### Trust Assumptions

1. **Plugins are trusted**: Same trust model as skills
2. **No sandboxing**: Plugins run with full yoker privileges
3. **Filesystem access**: Tools can access same paths as yoker
4. **Network access**: Tools can make same network requests as yoker

### Security Considerations

| Concern | Mitigation |
|---------|------------|
| **Malicious plugins** | User must explicitly install (`pip install package`) |
| **Code execution** | Plugins are Python code - same risk as skills |
| **Data exfiltration** | Tools guarded by existing PathGuardrail |
| **Namespace collision** | Explicit error on collision |
| **Import errors** | Graceful degradation, continue without plugin |

### Guardrails

Plugin tools inherit all existing guardrails:

```python
# PathGuardrail still applies
tool_result = await tool.execute(path="/etc/passwd")  # Blocked if path not allowed

# Operation allowlist still applies
result = await git_tool.execute(operation="push")  # Blocked if operation not allowed
```

**Why no additional security?**
- Plugins require explicit user action to install
- Same trust model as Python packages in general
- Existing guardrails provide sufficient protection
- Simplicity over security-through-obscurity

## Error Handling

### Error Types

| Error | Cause | User Message | Action |
|-------|-------|--------------|--------|
| `ImportError` | Package not installed | "Package '{name}' is not installed" | Suggest `pip install` |
| `ModuleNotFoundError` | No `yoker` submodule | "Package '{name}' does not provide yoker integration" | Continue without plugin |
| `AttributeError` | Missing `TOOLS`/`SKILLS` | "Plugin '{name}' has no components" | Continue without plugin |
| `PluginError` | Import error in module | "Failed to load plugin '{name}': {error}" | Raise with context |
| `ValueError` | Name collision | "Tool '{name}' already registered" | Raise with context |

### Graceful Degradation

```python
def _load_plugins(self, package_names: list[str]) -> None:
  """Load plugins with graceful degradation."""
  from yoker.plugins import load_plugins

  loaded = []

  for package_name in package_names:
    try:
      plugin = load_plugin(package_name)
      if plugin:
        loaded.append(plugin)
    except PluginError as e:
      # Critical error - fail fast
      log.error("plugin_load_failed", package=e.package, error=str(e))
      raise
    except ImportError:
      # Package not installed - suggest installation
      log.warning("plugin_not_installed", package=package_name)
      print(f"Warning: Package '{package_name}' is not installed.")
      print(f"Install it with: pip install {package_name}")
      continue

  # Register loaded plugins
  for plugin in loaded:
    self._register_plugin(plugin)
```

### Logging

All plugin operations are logged with structured logging:

```python
log.info("plugin_module_imported", package="pkgq")
log.info("plugin_components_extracted", package="pkgq", tools=2, skills=3)
log.info("tool_registered", name="pkgq:find", namespace="pkgq")
log.warning("plugin_not_installed", package="nonexistent")
log.error("plugin_import_error", package="broken", error="...")
```

## Implementation Phases

### Phase 3.1: Core Plugin Infrastructure

**Estimated time**: 3-4 hours

1. **Create plugin module**:
   - `src/yoker/plugins/__init__.py`
   - `src/yoker/plugins/loader.py`
   - `src/yoker/plugins/registration.py`
   - `src/yoker/plugins/builtin.py`

2. **Implement built-in plugin**:
   - Create `builtin.py` with standard tools/skills
   - Export TOOLS and SKILLS lists
   - Remove special registration logic from Agent
   - Update Agent to load built-in plugin first

3. **Implement loader**:
   - `PluginComponents` dataclass
   - `load_plugin()` function with config parameter
   - `load_plugins()` function
   - Import error handling

4. **Implement registration**:
   - `register_tools()` with namespace
   - `register_skills()` with namespace
   - `register_agents()` stub (future)

5. **Add configuration support**:
   - Add `PluginConfig` to `config/schema.py`
   - Plugin-specific settings in TOML
   - Tool configuration passing

6. **Add exception types**:
   - `PluginError` in `exceptions.py`

7. **Write unit tests**:
   - `tests/test_plugins/test_loader.py`
   - `tests/test_plugins/test_registration.py`
   - `tests/test_plugins/test_builtin.py`

### Phase 3.2: Configuration Integration

**Estimated time**: 2 hours

1. **Update configuration schema**:
   - Add `plugins` section to Config
   - Add plugin-specific settings support

2. **Integrate with Agent**:
   - Add `plugins` parameter to `Agent.__init__()`
   - Implement `_load_builtin_plugin()` method
   - Implement `_load_plugin()` method
   - Configuration passing to plugin tools

3. **Update config loading**:
   - Parse `[plugins]` section
   - Parse `[plugins.{name}]` sections
   - Validate plugin configuration

4. **Write integration tests**:
   - Test plugin loading from config
   - Test tool configuration
   - Test error cases

### Phase 3.3: Documentation

**Estimated time**: 1-2 hours

1. **Update README.md**:
   - Add plugin configuration section
   - Document built-in plugin concept
   - Add configuration examples

2. **Create plugin development guide**:
   - `docs/plugins.md`
   - Plugin module structure
   - Component definitions
   - Configuration integration
   - Namespace conventions

3. **Update CLAUDE.md**:
   - Add plugin architecture notes
   - Update package structure
   - Document configuration approach

### Phase 3.4: Example Plugin

**Estimated time**: 1-2 hours

1. **Update pkgq package**:
   - Create `pkgq/yoker/` module
   - Export `TOOLS` list with configuration support
   - Export `SKILLS` list

2. **Test with yoker**:
   - Add `pkgq` to `plugins.packages` in config
   - Verify tool registration (`pkgq:find`)
   - Verify skill registration (`pkgq:create`)
   - Test configuration integration

## Concrete Examples

### Example 1: Built-in Plugin

The yoker package provides its standard tools and skills as a built-in plugin.

**File**: `src/yoker/plugins/builtin.py`

```python
"""Built-in yoker plugin providing standard tools and skills."""

from yoker.tools import ReadTool, WriteTool, ListTool, SearchTool
from yoker.skills import Skill

# Standard filesystem tools
TOOLS = [
  ReadTool(),
  WriteTool(),
  ListTool(),
  SearchTool(),
]

# Standard skills
SKILLS = [
  Skill(
    name="think",
    description="Enable/disable thinking mode",
    content="...",
    tools=["Bash"],
  ),
  Skill(
    name="help",
    description="Show available commands and tools",
    content="...",
    tools=[],
  ),
]

AGENTS = []  # Future: standard agents
```

**File**: `src/yoker/agent.py` (excerpt)

```python
def __init__(self, config: Config, plugins: list[str] | None = None):
  # Load built-in plugin first (always loaded)
  self._load_builtin_plugin(config)

  # Load configured plugins
  plugin_packages = plugins if plugins is not None else config.plugins.packages
  for package_name in plugin_packages:
    self._load_plugin(package_name, config)
```

**Result**: All built-in tools now use namespace `yoker:`:
- `yoker:read` - Read files
- `yoker:write` - Write files
- `yoker:list` - List directory contents
- `yoker:search` - Search file contents

### Example 2: Plugin Tool with Configuration

A Git tool that needs configuration for allowed operations.

**File**: `git_tool/yoker/__init__.py`

```python
"""Yoker integration for git_tool package."""

from yoker.tools import Tool, ToolResult
from dataclasses import dataclass

@dataclass
class GitToolConfig:
  """Configuration for GitTool."""
  allowed_operations: list[str] = None
  require_approval_for: list[str] = None

  def __post_init__(self):
    if self.allowed_operations is None:
      self.allowed_operations = ["status", "log", "diff"]
    if self.require_approval_for is None:
      self.require_approval_for = ["push", "reset"]

class GitTool(Tool):
  """Execute git commands with guardrails."""

  name = "git"
  description = "Execute git commands"

  def __init__(self, config: GitToolConfig = None):
    self.config = config or GitToolConfig()

  async def execute(self, operation: str, **kwargs) -> ToolResult:
    # Validate operation
    if operation not in self.config.allowed_operations:
      return ToolResult(
        success=False,
        output=f"Operation '{operation}' not allowed. "
               f"Allowed: {self.config.allowed_operations}"
      )

    # Check if approval required
    if operation in self.config.require_approval_for:
      # Prompt user for approval
      approved = await self._prompt_approval(operation)
      if not approved:
        return ToolResult(success=False, output="Operation cancelled by user")

    # Execute git command
    result = await self._run_git(operation, **kwargs)
    return ToolResult(success=True, output=result)

# Export configured tool instance
TOOLS = [
  GitTool,  # Tool class (will be instantiated by yoker with config)
]

SKILLS = []
AGENTS = []
```

**File**: `yoker.toml` (user configuration)

```toml
[plugins]
packages = ["git_tool"]

[plugins.git_tool]
allowed_operations = ["status", "log", "diff", "commit"]
require_approval_for = ["push", "reset"]

[tools.git_tool]
# Can also use shorter name in [tools] section
# yoker maps plugins.git_tool -> tools.git_tool
```

**Result**: Git tool loaded with user's allowed operations:
- Tool registered as `git_tool:git`
- Configuration applied from `plugins.git_tool` section
- Only allowed operations permitted

### Example 3: User Configuration

Complete yoker.toml with built-in and plugin tools.

**File**: `yoker.toml`

```toml
[agent]
model = "llama3.2:latest"
system_prompt = """You are a helpful AI assistant with access to tools.
Use full namespace when calling tools: yoker:read, pkgq:find, etc."""

[plugins]
# Plugin packages to load (in addition to built-in yoker plugin)
packages = ["pkgq", "c3"]

[plugins.pkgq]
# pkgq-specific configuration
package_index_url = "https://pypi.org/simple"
cache_ttl = 7200

[plugins.c3]
# c3-specific configuration (if any)
some_setting = "value"

[tools.yoker]
# Built-in tool configuration (namespace: yoker)
filesystem.allowed_paths = ["/workspace", "/home/user/projects"]
filesystem.allowed_operations = ["read", "write", "list", "search"]

[tools.pkgq]
# Alternative: shorter name for plugin tool configuration
# Maps to plugins.pkgq
# (already defined above)

# Note: All tool calls require full namespace:
# - yoker:read /path/to/file
# - pkgq:find requests
# - c3:develop-skill
```

**File**: `src/yoker/agent.py` (initialization sequence)

```python
# Initialization sequence:
# 1. Load built-in plugin (always first)
#    - Tools: yoker:read, yoker:write, yoker:list, yoker:search
#    - Skills: yoker:think, yoker:help
#    - Apply config from [tools.yoker] section
#
# 2. Load pkgq plugin
#    - Tool: pkgq:find
#    - Skills: pkgq:create, pkgq:update
#    - Apply config from [plugins.pkgq] section
#
# 3. Load c3 plugin
#    - Tools: (none)
#    - Skills: c3:develop-skill, c3:develop-agent, c3:project-manage
#    - Apply config from [plugins.c3] section
```

### Example 4: Plugin Without Configuration

Simple plugin that doesn't need configuration.

**File**: `simple_plugin/yoker/__init__.py`

```python
"""Simple plugin without configuration."""

from yoker.tools import Tool, ToolResult

class HelloTool(Tool):
  """Say hello."""

  name = "hello"
  description = "Say hello to someone"

  async def execute(self, name: str) -> ToolResult:
    return ToolResult(success=True, output=f"Hello, {name}!")

# Tool instances (no configuration needed)
TOOLS = [HelloTool()]

SKILLS = []
AGENTS = []
```

**File**: `yoker.toml`

```toml
[plugins]
packages = ["simple_plugin"]

# No configuration needed - plugin works without [plugins.simple_plugin] section
```

**Result**: Simple plugin loaded with default behavior:
- Tool registered as `simple_plugin:hello`
- No configuration required
- Direct instantiation in TOOLS list

### pkgq Plugin (Updated)

**File**: `pkgq/yoker/__init__.py`

```python
"""Yoker integration for pkgq package."""

from yoker.tools import Tool
from yoker.skills import Skill

from .tools import FindPackageTool, PkgqConfig

# Tools provided by this plugin (export class for configuration)
TOOLS: list[Tool] = [
  FindPackageTool,  # Class - yoker will instantiate with config
]

# Skills provided by this plugin
SKILLS: list[Skill] = [
  Skill(
    name="create",
    description="Generate PACKAGE.md for a Python project",
    content="""
## Purpose

Generate a PACKAGE.md file documenting the project structure and key components.

## Workflow

1. Analyze project structure
2. Identify key modules
3. Extract patterns and conventions
4. Generate PACKAGE.md

## Guidelines

- Focus on agent-relevant information
- Include common patterns
- Note important conventions
""",
    tools=["yoker:read", "yoker:Bash"],  # Note: full namespace required
  ),
  Skill(
    name="update",
    description="Update existing package documentation",
    content="...",
    tools=["yoker:read", "yoker:write"],  # Note: full namespace required
  ),
]

# Agents provided by this plugin (future)
AGENTS: list = []

# Configuration schema (optional)
# yoker will pass config from [plugins.pkgq] section
__CONFIG_CLASS__ = PkgqConfig
```

**File**: `pkgq/yoker/tools.py`

```python
"""Tool definitions for pkgq plugin."""

from yoker.tools import Tool, ToolResult
from dataclasses import dataclass

@dataclass
class PkgqConfig:
  """Configuration for pkgq tools."""
  package_index_url: str = "https://pypi.org/simple"
  cache_ttl: int = 3600

class FindPackageTool(Tool):
  """Find package documentation."""

  name = "find"
  description = "Find package documentation"

  def __init__(self, config: PkgqConfig = None):
    self.config = config or PkgqConfig()

  async def execute(self, package: str, version: str | None = None) -> ToolResult:
    """Execute tool."""
    # Use self.config.package_index_url and self.config.cache_ttl
    ...
```

**File**: `yoker.toml` (user configuration)

```toml
[plugins]
packages = ["pkgq"]

[plugins.pkgq]
package_index_url = "https://pypi.org/simple"
cache_ttl = 7200
```

### c3 Plugin (Updated)

**File**: `c3/yoker/__init__.py`

```python
"""Yoker integration for c3 (Claude Code harness)."""

from yoker.skills import Skill

# Skills provided by c3
SKILLS = [
  Skill(
    name="develop-skill",
    description="Guide creation and refinement of Claude Code skills",
    content="...",
    tools=["yoker:read", "yoker:write", "yoker:Bash"],  # Note: full namespace
  ),
  Skill(
    name="develop-agent",
    description="Develop new Claude Code agents",
    content="...",
    tools=["yoker:read", "yoker:write"],
  ),
  Skill(
    name="project-manage",
    description="Manage the entire project workflow",
    content="...",
    tools=["yoker:read", "yoker:write", "yoker:Bash"],
  ),
]

TOOLS = []  # c3 provides skills, not tools
AGENTS = []  # Future: code-reviewer agent

# No configuration needed
```

**Important**: All skill tool references must use full namespace (e.g., `yoker:read`, not `read`).

### Git Tool Plugin Example

**File**: `git_tool/yoker/__init__.py`

```python
"""Yoker integration for git_tool package."""

from yoker.tools import Tool, ToolResult
from dataclasses import dataclass

@dataclass
class GitConfig:
  """Configuration for GitTool."""
  allowed_operations: list[str] = None
  require_approval_for: list[str] = None

  def __post_init__(self):
    if self.allowed_operations is None:
      self.allowed_operations = ["status", "log", "diff"]
    if self.require_approval_for is None:
      self.require_approval_for = ["push", "reset"]

class GitTool(Tool):
  """Execute git commands with guardrails."""

  name = "git"
  description = "Execute git commands"

  def __init__(self, config: GitConfig = None):
    self.config = config or GitConfig()

  async def execute(self, operation: str, **kwargs) -> ToolResult:
    """Execute git command."""
    if operation not in self.config.allowed_operations:
      return ToolResult(
        success=False,
        output=f"Operation '{operation}' not allowed"
      )
    # ... implementation

# Export tool class for configuration
TOOLS = [GitTool]
SKILLS = []
AGENTS = []
```

**File**: `yoker.toml`

```toml
[plugins]
packages = ["git_tool"]

[plugins.git_tool]
allowed_operations = ["status", "log", "diff", "commit"]
require_approval_for = ["push", "reset"]
```

## Testing Strategy

### Unit Tests

**File**: `tests/test_plugins/test_loader.py`

```python
import pytest
from yoker.plugins import load_plugin, load_plugins, PluginComponents
from yoker.exceptions import PluginError


def test_load_plugin_with_components():
  """Test loading plugin with all components."""
  # Create mock module
  import sys
  from types import ModuleType

  module = ModuleType("test_pkg.yoker")
  module.TOOLS = [MockTool()]
  module.SKILLS = [MockSkill()]
  module.AGENTS = []

  sys.modules["test_pkg.yoker"] = module

  plugin = load_plugin("test_pkg")

  assert plugin is not None
  assert len(plugin.tools) == 1
  assert len(plugin.skills) == 1
  assert plugin.source == "test_pkg"


def test_load_plugin_without_yoker_module():
  """Test loading package without yoker submodule."""
  plugin = load_plugin("nonexistent_package")
  assert plugin is None


def test_load_plugin_import_error():
  """Test plugin that fails to import."""
  # Module exists but has import error
  with pytest.raises(PluginError):
    load_plugin("broken_plugin")
```

**File**: `tests/test_plugins/test_registration.py`

```python
import pytest
from yoker.plugins import register_tools, register_skills
from yoker.tools import ToolRegistry
from yoker.skills import SkillRegistry, Skill


def test_register_tools_with_namespace():
  """Test tool registration with namespace."""
  registry = ToolRegistry()
  tools = [MockTool(name="find")]

  registered = register_tools(tools, registry, namespace="pkgq")

  assert len(registered) == 1
  assert "pkgq:find" in registered
  assert registry.get("pkgq:find") is not None


def test_register_tools_collision():
  """Test tool name collision detection."""
  registry = ToolRegistry()
  tools = [MockTool(name="find")]

  register_tools(tools, registry, namespace="pkgq")

  # Try to register same tool again
  with pytest.raises(ValueError, match="already registered"):
    register_tools(tools, registry, namespace="pkgq")


def test_register_skills_with_namespace():
  """Test skill registration with namespace."""
  registry = SkillRegistry()
  skills = [Skill(name="create", description="Create package")]

  registered = register_skills(skills, registry, namespace="pkgq")

  assert len(registered) == 1
  assert "pkgq:create" in registered
  assert registry.get("pkgq:create") is not None
```

### Integration Tests

**File**: `tests/test_plugins/test_cli.py`

```python
import pytest
from yoker import Agent


def test_agent_with_plugin():
  """Test agent initialization with plugin."""
  agent = Agent(plugins=["pkgq"])

  # Check tools are registered
  assert agent.tool_registry.get("pkgq:find") is not None

  # Check skills are registered
  assert agent.skill_registry.get("pkgq:create") is not None


def test_agent_with_multiple_plugins():
  """Test agent with multiple plugins."""
  agent = Agent(plugins=["pkgq", "c3"])

  # Check tools from pkgq
  assert agent.tool_registry.get("pkgq:find") is not None

  # Check skills from both
  assert agent.skill_registry.get("pkgq:create") is not None
  assert agent.skill_registry.get("c3:develop-skill") is not None
```

## Migration Path

### For Plugin Authors

1. **Create yoker submodule**:
   ```
   mkdir -p package/yoker
   touch package/yoker/__init__.py
   ```

2. **Export components with configuration support**:
   ```python
   # package/yoker/__init__.py

   # If tool needs configuration
   from .tools import MyTool, MyConfig

   TOOLS = [MyTool]  # Export class, not instance
   SKILLS = [MySkill()]
   __CONFIG_CLASS__ = MyConfig  # Optional: configuration schema
   ```

3. **Use full namespace in skill tool references**:
   ```python
   # Correct: Use full namespace
   Skill(
     name="my-skill",
     tools=["yoker:read", "yoker:write"]
   )

   # Incorrect: Short name (not supported)
   Skill(
     name="my-skill",
     tools=["read", "write"]  # ✗ Won't work
   )
   ```

4. **Test with yoker**:
   ```bash
   pip install -e .

   # Add to yoker.toml
   echo '[plugins]\npackages = ["my_package"]' >> yoker.toml

   # Run yoker
   yoker
   ```

### For Yoker Users

1. **Install plugin package**:
   ```bash
   pip install pkgq
   ```

2. **Add to yoker.toml**:
   ```toml
   [plugins]
   packages = ["pkgq"]

   [plugins.pkgq]
   # Plugin-specific configuration
   package_index_url = "https://pypi.org/simple"
   ```

3. **Run yoker**:
   ```bash
   yoker
   # Plugins loaded from config automatically
   ```

4. **Invoke plugin components with full namespace**:
   ```
   > Use tool yoker:read to read the file
   > Use tool pkgq:find to find package docs
   > Use skill pkgq:create to generate PACKAGE.md
   ```

5. **Future: Clevis --with argument**:
   ```bash
   # When Clevis implements --with
   yoker --with pkgq --with c3
   ```

## Future Enhancements

### Plugin Dependencies

```python
# package/yoker/__init__.py
__REQUIRES__ = ["other-package"]
```

Note: No dependency resolution - plugins must ensure dependencies are installed.

### Plugin Lifecycle Hooks

```python
# package/yoker/__init__.py
def on_load(agent: Agent) -> None:
  """Called when plugin is loaded."""
  pass

def on_unload(agent: Agent) -> None:
  """Called when plugin is unloaded."""
  pass
```

### Clevis Integration

**Proposed for Clevis (not yoker-specific)**:

```python
# In clevis/config.py (proposed)
@dataclass
class SecurityConfig:
  plugins: list[str] = field(default_factory=list)

# In clevis/cli.py (proposed)
parser.add_argument(
  "--with",
  action="append",
  dest="plugins",
  metavar="PACKAGE",
  help="Load plugin from Python package",
)
```

Benefits:
- Consistent plugin mechanism across all Clevis applications
- Centralized argument parsing
- Future sandboxing support in Clevis

### Plugin Discovery

```bash
# List available plugins
yoker --list-plugins

# Search for plugins (future)
yoker --search-plugins "package documentation"
```

### Hot Reloading

```bash
# Reload plugins without restart (future)
yoker --reload-plugins
```

### Short Name Resolution (Future Consideration)

Currently not implemented, but could be added later if needed:

```python
# Potential future feature
# Allow: pkgq:find or find (if unique)
tool = registry.get("find")  # Would search namespaces in order

# Order could be configurable
tool = registry.get("find", search_order=["yoker", "pkgq", "c3"])
```

Note: Start with full namespace requirement, add short names later if users request it.

## Related Documents

- `analysis/api-skill-infrastructure.md` - Skill system architecture
- `analysis/architecture.md` - Overall yoker architecture
- `src/yoker/tools/registry.py` - ToolRegistry implementation
- `src/yoker/skills/registry.py` - SkillRegistry implementation
- `src/yoker/agents/loader.py` - AgentDefinition loading pattern

## Checklist

### Phase 3.1: Core Infrastructure

- [ ] Create `src/yoker/plugins/` module
- [ ] Create `src/yoker/plugins/builtin.py` (built-in plugin)
- [ ] Implement `PluginComponents` dataclass
- [ ] Implement `load_plugin()` function with config parameter
- [ ] Implement `load_plugins()` function
- [ ] Implement `register_tools()` with namespace
- [ ] Implement `register_skills()` with namespace
- [ ] Implement `_load_builtin_plugin()` in Agent
- [ ] Add `PluginError` exception
- [ ] Write unit tests for loader
- [ ] Write unit tests for registration
- [ ] Write unit tests for built-in plugin

### Phase 3.2: Configuration Integration

- [ ] Add `PluginConfig` to `config/schema.py`
- [ ] Add `plugins` section to Config
- [ ] Parse `[plugins]` section in config loader
- [ ] Parse `[plugins.{name}]` sections for tool config
- [ ] Add `plugins` parameter to `Agent.__init__()`
- [ ] Implement `_load_plugin()` method with config passing
- [ ] Update built-in tool configuration to use plugin config
- [ ] Write integration tests
- [ ] Test configuration loading from TOML

### Phase 3.3: Documentation

- [ ] Create `docs/plugins.md`
- [ ] Document built-in plugin concept
- [ ] Document configuration integration
- [ ] Document namespace conventions
- [ ] Document tool configuration for plugin authors
- [ ] Add troubleshooting guide
- [ ] Update README with plugin usage examples
- [ ] Update CLAUDE.md with plugin architecture

### Phase 3.4: Example Plugin

- [ ] Update pkgq with yoker module
- [ ] Export tools with configuration support
- [ ] Export skills with full namespace tool references
- [ ] Test with yoker config file
- [ ] Verify namespace in tool calls (pkgq:find)
- [ ] Document in README

## References

- Python importlib documentation: https://docs.python.org/3/library/importlib.html
- Plugin patterns: https://packaging.python.org/en/latest/guides/creating-and-discovering-plugins/
- Yoker skill system: `analysis/api-skill-infrastructure.md`
- Yoker architecture: `analysis/architecture.md`