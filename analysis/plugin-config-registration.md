# Plugin Config Registration Architecture

**Date:** 2026-06-22
**Status:** Design Required
**Priority:** P5 (Post-MVP Architectural Improvement)

## Executive Summary

This document analyzes two deferred refactoring items from the src/ tree refactor:
1. **WebGuardrailConfig duplication**: Multiple config classes for web guardrails
2. **Plugin config registration**: Need for dynamic config field registration

These items are architecturally related and should be tackled together as part of the plugin config registration system.

## Current State

### Config Class Duplication

The codebase currently has overlapping configuration classes for web tools:

```python
# tools/web/guardrail.py
@dataclass
class WebGuardrailConfig:
  """Runtime guardrail configuration (unfrozen)."""
  max_query_length: int = 500
  domain_allowlist: tuple[str, ...] = ()
  domain_blocklist: tuple[str, ...] = ()
  requests_per_minute: int = 60
  requests_per_hour: int = 1000
  max_concurrent_requests: int = 0
  block_private_cidrs: bool = True
  timeout_seconds: int = 30
  require_https: bool = True
```

```python
# config/__init__.py
@dataclass(frozen=True)
class WebSearchToolConfig(ToolConfig):
  """TOML configuration for web search (frozen)."""
  backend: str = "ollama"
  max_results: int = 10
  max_query_length: int = 500
  timeout_seconds: int = 30
  requests_per_minute: int = 60
  requests_per_hour: int = 1000
  domain_allowlist: tuple[str, ...] = ()
  domain_blocklist: tuple[str, ...] = ()
  block_private_cidrs: bool = True

@dataclass(frozen=True)
class WebFetchToolConfig(ToolConfig):
  """TOML configuration for web fetch (frozen)."""
  backend: str = "ollama"
  timeout_seconds: int = 30
  max_size_kb: int = 2048
  max_redirects: int = 5
  content_type: str = "markdown"
  domain_allowlist: tuple[str, ...] = ()
  domain_blocklist: tuple[str, ...] = ()
  block_private_cidrs: bool = True
  block_metadata_endpoints: bool = True
  require_https: bool = True
  follow_redirects: bool = True
  validate_redirects: bool = True
```

### Config Translation Layer

The `agent/_setup.py` module translates between these configs:

```python
# agent/_setup.py
if config.tools.websearch.enabled:
  query_config = WebGuardrailConfig(
    max_query_length=config.tools.websearch.max_query_length,
    domain_allowlist=config.tools.websearch.domain_allowlist,
    domain_blocklist=config.tools.websearch.domain_blocklist,
    requests_per_minute=config.tools.websearch.requests_per_minute,
    requests_per_hour=config.tools.websearch.requests_per_hour,
    block_private_cidrs=config.tools.websearch.block_private_cidrs,
    timeout_seconds=config.tools.websearch.timeout_seconds,
  )
  query_guardrail = QueryWebGuardrail(config=query_config)
```

### Why This Duplication Exists

1. **Frozen dataclasses for TOML config**
   - Clevis requires frozen dataclasses for config schema
   - Frozen dataclasses cannot be modified at runtime
   - Enables validation at load time

2. **Unfrozen dataclasses for runtime**
   - Guardrails need mutable runtime state
   - Rate limiting tracks state per user/session
   - Unfrozen allows dynamic updates

3. **Hardcoded tool configs**
   - Each built-in tool has a hardcoded config class
   - `ToolsConfig` has a field for each tool
   - No mechanism for plugins to add config fields

## Problem Statement

### Current Architecture Limitation

```python
# config/__init__.py
@dataclass(frozen=True)
class ToolsConfig:
  """All tool configurations."""
  
  list: ListToolConfig = field(default_factory=ListToolConfig)
  read: ReadToolConfig = field(default_factory=ReadToolConfig)
  write: WriteToolConfig = field(default_factory=WriteToolConfig)
  # ... each tool hardcoded ...
  websearch: WebSearchToolConfig = field(default_factory=WebSearchToolConfig)
  webfetch: WebFetchToolConfig = field(default_factory=WebFetchToolConfig)
```

**Problem:** When a plugin like `pkgq` needs configuration:

```toml
# yoker.toml
[plugins]
packages = ["pkgq"]

[tools.pkgq]  # <-- This field doesn't exist in frozen ToolsConfig!
package_index_url = "https://pypi.org/simple"
cache_ttl = 3600
```

The frozen `ToolsConfig` class cannot have `pkgq` added as a field at runtime.

### Plugin Design Document

The plugin architecture document (`analysis/plugin-architecture.md`) describes the intended design:

```python
# pkgq/yoker/__init__.py
from yoker.tools import Tool, ToolResult
from dataclasses import dataclass

@dataclass
class PkgqConfig:
  """Configuration for pkgq tools."""
  package_index_url: str = "https://pypi.org/simple"
  cache_ttl: int = 3600

class FindPackageTool(Tool):
  name = "find"
  
  def __init__(self, config: PkgqConfig | None = None):
    self.config = config or PkgqConfig()
  
  async def execute(self, package: str) -> ToolResult:
    # Use self.config.package_index_url
    ...

# Export tool class (yoker instantiates with config)
TOOLS = [FindPackageTool]
__CONFIG_CLASS__ = PkgqConfig
```

**Challenge:** How does yoker register `PkgqConfig` into `ToolsConfig` dynamically?

## Proposed Solution

### Option 1: Clevis `register_field` Mechanism

Clevis already has the infrastructure for this. The approach would be:

```python
# plugins/loader.py
from clevis import register_field

def load_plugin(package_name: str, config: Config) -> PluginComponents | None:
  """Load plugin with configuration."""
  module = importlib.import_module(f"{package_name}.yoker")
  
  # Get config class if plugin defines one
  config_class = getattr(module, "__CONFIG_CLASS__", None)
  if config_class:
    # Register config field dynamically
    register_field(ToolsConfig, package_name, config_class)
  
  # Load plugin components
  tools = _extract_list(module, "TOOLS")
  
  # Get plugin-specific config
  plugin_config = getattr(config.tools, package_name, None)
  
  # Instantiate tools with config
  for i, tool_class in enumerate(tools):
    if isinstance(tool_class, type):
      tools[i] = tool_class(config=plugin_config)
  
  return PluginComponents(tools=tools, source=package_name)
```

**Benefits:**
- Leverages existing Clevis infrastructure
- Consistent with Clevis design philosophy
- No frozen dataclass workarounds needed

**Challenges:**
- Requires Clevis to support this (may need changes to Clevis)
- May need to change `ToolsConfig` from frozen to unfrozen

### Option 2: Local Registration API

Implement config registration in yoker:

```python
# config/registry.py
from dataclasses import fields, make_dataclass
from typing import Any

_config_registry: dict[str, type] = {}

def register_tool_config(tool_name: str, config_class: type) -> None:
  """Register a tool configuration class.
  
  Args:
    tool_name: Tool namespace (e.g., "pkgq", "git")
    config_class: Configuration class (dataclass)
  """
  _config_registry[tool_name] = config_class

def build_tools_config(base_config: ToolsConfig) -> Any:
  """Build a dynamic config with all registered tools.
  
  Args:
    base_config: Frozen base configuration
  
  Returns:
    Dynamic config with additional fields
  """
  # Copy base config fields
  field_list = [(f.name, f.type, f.default) for f in fields(base_config)]
  
  # Add registered tool configs
  for tool_name, config_class in _config_registry.items():
    field_list.append((tool_name, config_class, field(default_factory=config_class)))
  
  # Create dynamic unfrozen dataclass
  return make_dataclass("DynamicToolsConfig", field_list)
```

**Benefits:**
- No Clevis changes required
- Works with frozen base config
- Maintains plugin isolation

**Challenges:**
- Duplicates Clevis functionality
- Must maintain two code paths (frozen base + dynamic extension)
- Type checking is harder with dynamic classes

### Option 3: Config Composition Pattern

Use composition instead of dynamic fields:

```python
# config/__init__.py
@dataclass(frozen=True)
class ToolsConfig:
  """All tool configurations."""
  
  # Built-in tools
  list: ListToolConfig = field(default_factory=ListToolConfig)
  read: ReadToolConfig = field(default_factory=ReadToolConfig)
  # ...
  
  # Plugin tools (dynamic)
  plugins: dict[str, Any] = field(default_factory=dict)
  
  def get_plugin_config(self, plugin_name: str) -> Any | None:
    """Get configuration for a plugin."""
    return self.plugins.get(plugin_name)
```

```toml
# yoker.toml
[plugins]
packages = ["pkgq"]

[tools.plugins.pkgq]
package_index_url = "https://pypi.org/simple"
cache_ttl = 3600
```

**Benefits:**
- No dynamic field registration needed
- Frozen dataclass still works
- Clevis-friendly

**Challenges:**
- Type safety reduced (dict[str, Any])
- Config file structure changes (`[tools.plugins.pkgq]` vs `[tools.pkgq]`)
- Less intuitive for users

## Recommended Approach

**Recommended: Option 1 (Clevis `register_field`)**

Rationale:
1. Aligns with Clevis philosophy (configuration-driven)
2. Centralizes config registration logic
3. Type checking can be preserved with proper typing
4. Consistent with other Clevis applications

**Implementation Path:**

1. **Phase 7.1: Design (4-6 hours)**
   - Investigate Clevis `register_field` implementation
   - Design yoker-specific registration API
   - Document config schema for plugins
   - Create prototype for review

2. **Phase 7.2: Implement (8-12 hours)**
   - Change `ToolsConfig` from frozen to unfrozen (or use Clevis mechanism)
   - Implement `register_tool_config()` API
   - Update existing hardcoded tool configs to use registration
   - Add plugin config loading to `plugins/loader.py`

3. **Phase 7.3: Consolidate (2-4 hours)**
   - Remove duplicate `WebGuardrailConfig` classes
   - Create unified guardrail config pattern
   - Update all web tools to use new config pattern
   - Clean up translation layer in `agent/_setup.py`

## Impact Analysis

### Files Affected

**Config system:**
- `src/yoker/config/__init__.py` - Remove hardcoded web tool configs
- `src/yoker/config/registry.py` - New: registration API

**Plugin system:**
- `src/yoker/plugins/loader.py` - Add config registration
- `src/yoker/plugins/registration.py` - Handle tool instantiation with config

**Tools:**
- `src/yoker/tools/web/guardrail.py` - Consolidate config classes
- `src/yoker/builtin/websearch.py` - Update config usage
- `src/yoker/builtin/webfetch.py` - Update config usage

**Agent setup:**
- `src/yoker/agent/_setup.py` - Simplify guardrail creation

### Breaking Changes

**Config file format:**
- Before: `[tools.websearch]` (hardcoded)
- After: Same format, but extensible to `[tools.pkgq]`

**Plugin interface:**
- Before: `TOOLS = [FindPackageTool()]` (instantiated)
- After: `TOOLS = [FindPackageTool]` (class, yoker instantiates)

**Internal API:**
- Before: `config.tools.websearch` (hardcoded field)
- After: Same access, but can also use `config.tools.pkgq` (dynamic)

**Migration path:**
1. Support both patterns temporarily (old hardcoded + new dynamic)
2. Deprecate hardcoded tool configs
3. Remove old pattern in next major version

## Dependency Rationale

### Why Item 7.3 Depends on 7.2

**Current duplication is a symptom, not the root cause.**

The reason `WebGuardrailConfig` exists separately from `WebSearchToolConfig` is because:
1. `ToolsConfig` is frozen (cannot add fields)
2. Web tools need runtime configuration (unfrozen)
3. Translation layer bridges frozen TOML config to unfrozen runtime config

**Consolidating now would be premature:**
1. Would create a new pattern that contradicts plugin architecture
2. Would need to be refactored again when plugins add configs
3. Would establish a pattern of hardcoded tool configs (anti-pattern)

**Proper sequence:**
1. Implement plugin config registration (7.2)
2. Use the new mechanism for ALL tool configs (built-in + plugin)
3. Consolidate web configs using the unified approach (7.3)

This ensures:
- Single consistent pattern for all tool configs
- No special handling for built-in vs plugin tools
- Clean separation of concerns (TOML config vs runtime config)

## Conclusion

The two deferred refactoring items are deeply connected:
- WebGuardrailConfig duplication is a workaround for frozen config limitations
- Plugin config registration will eliminate the need for this workaround
- Tackling them together ensures a consistent architecture

**Recommendation:**
- Do NOT fix WebGuardrailConfig duplication separately
- Implement plugin config registration first (Phases 7.1, 7.2)
- Then consolidate all tool configs (Phase 7.3)

This approach creates a clean, extensible architecture that supports both built-in and plugin tools with a single configuration pattern.