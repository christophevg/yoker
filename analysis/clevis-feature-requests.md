# Clevis Feature Requests

**Repository**: https://github.com/christophevg/clevis
**Date**: 2026-06-09
**Context**: Yoker plugin system configuration requirements

---

## Feature Request 1: Namespace Support in configclass

### Summary

Add a `namespace` parameter to `@configclass` decorator to support namespaced configuration sections within TOML files, distinct from the existing `prefix` and `cmd` parameters.

### Problem Statement

Yoker's plugin system needs to inject plugin configurations into specific namespaces within the main configuration structure. For example, a `pkgq` plugin should be configurable under `[tools.pkgq]` and `[agents.pkgq]` sections in `yoker.toml`.

Currently, Clevis provides two mechanisms that **do not** address this use case:

#### 1. The `prefix` Parameter

The `Factory.prefix` parameter adds a prefix to CLI arguments:

```python
from clevis import get_factory

@dataclass
class PkgqToolConfig:
  cache_directory: str = "~/.cache/pkgq"

factory = get_factory(PkgqToolConfig)
factory.prefix = "pkgq"
```

This results in:
- CLI args: `--pkgq-cache-directory`
- TOML: **No namespace support** - expects flat structure

**The problem**: `prefix` only affects CLI arguments. It does NOT create namespaced sections in TOML config files.

#### 2. The `cmd` Parameter

The `@configclass(cmd="name")` decorator creates subcommands:

```python
@configclass(cmd="print", help="Print configuration")
class PrintConfig:
  output_format: str = "text"
```

This extracts a TOML section:

```toml
[print]
output_format = "json"
```

**The problem**: Subcommands are for CLI command dispatch, not configuration namespacing. The implementation clears the root config:

```python
# clevis/__init__.py:804-822
toml_key = factory.config or factory.cmd
if toml_key and toml_key in cfg:
  cmd_cfg = cfg.pop(toml_key)
  if isinstance(cmd_cfg, dict):
    cfg.clear()  # <-- ROOT CONFIG IS CLEARED!
    cfg.update(cmd_cfg)
```

This means `[print]` config is isolated from the rest of the configuration - it replaces the entire config, not merges into it.

### The Missing Feature: Namespace

Yoker needs to load plugin configs that are **nested within** the main configuration hierarchy:

```toml
# yoker.toml - Main configuration

[backend.ollama]
model = "llama3.2:latest"
base_url = "http://localhost:11434"

[tools.list]  # Built-in tool config
max_depth = 5
max_entries = 2000

[tools.pkgq]  # Plugin tool config - NAMESPACE NEEDED
enabled = true
cache_directory = "/custom/cache"
timeout_seconds = 60

[agents.default]  # Built-in agent config
max_recursion_depth = 3

[agents.pkgq]  # Plugin agent config - NAMESPACE NEEDED
max_results = 20
include_prerelease = true
```

### Proposed Solution

Add a `namespace` parameter to `@configclass` that:

1. **Extracts namespaced sections without clearing root config**
2. **Merges into existing configuration hierarchy**
3. **Works alongside prefix for CLI arguments**

#### API Design

```python
from dataclasses import dataclass
from clevis import configclass, get_config

@dataclass
class PkgqToolConfig:
  enabled: bool = True
  cache_directory: str = "~/.cache/pkgq"
  timeout_seconds: int = 30

@dataclass
class PkgqAgentConfig:
  max_results: int = 10
  include_prerelease: bool = False

@dataclass
class Config:
  backend: BackendConfig = field(default_factory=BackendConfig)
  tools: ToolsConfig = field(default_factory=ToolsConfig)
  agents: AgentsConfig = field(default_factory=AgentsConfig)

# Plugin registration with namespace
@configclass(namespace="tools.pkgq")
class PkgqToolConfig:
  enabled: bool = True
  cache_directory: str = "~/.cache/pkgq"
  timeout_seconds: int = 30

# Load main config + plugin configs
config = get_config(Config, name="yoker")
# config.tools.pkgq is now populated from [tools.pkgq] TOML section
```

#### Behavior

**TOML Structure**:
```toml
[tools.pkgq]
enabled = true
cache_directory = "/custom/cache"
timeout_seconds = 60
```

**Loading Logic**:

```python
# Pseudocode for namespace extraction
def get_config(clz, name="project", ...):
  cfg = {}  # Load from TOML files
  
  # Load main config
  user_config = load_toml(f"~/.{name}.toml")
  project_config = load_toml(f"./{name}.toml")
  cfg.update(user_config)
  cfg.update(project_config)
  
  # Process namespaced configclasses
  for field_name, field_type in get_namespaced_fields(clz):
    namespace = get_namespace(field_type)  # e.g., "tools.pkgq"
    if namespace in cfg:
      # Extract namespaced section and merge into parent
      parent_path = namespace.rsplit(".", 1)[0]  # "tools"
      parent = get_nested(cfg, parent_path)  # cfg["tools"]
      parent[field_name] = cfg.pop(namespace)
  
  return from_dict(clz, cfg)
```

**Key Difference from `cmd`**: Namespace extraction preserves parent config. With `cmd`, the root is cleared. With `namespace`, only the target section is moved.

### Comparison Table

| Feature | `prefix` | `cmd` | `namespace` (proposed) |
|---------|----------|-------|------------------------|
| Affects CLI args | ✅ Yes | ✅ Yes | ✅ Yes |
| Affects TOML structure | ❌ No | ✅ Yes (isolates) | ✅ Yes (merges) |
| Preserves parent config | ✅ Yes | ❌ No (clears root) | ✅ Yes |
| Use case | Multiple CLI configs | Subcommand dispatch | Nested configuration |
| Example | `--pkgq-enabled` | `yoker print` | `[tools.pkgq]` |

### Use Cases

#### 1. Plugin Configuration (Primary)

Plugins need to inject configs into specific namespaces:

```python
# pkgq/yoker/__init__.py

from dataclasses import dataclass
from clevis import configclass

@configclass(namespace="tools.pkgq")
class PkgqToolConfig:
  package_index_url: str = "https://pypi.org/simple"
  cache_ttl: int = 3600

@configclass(namespace="agents.pkgq")
class PkgqAgentConfig:
  max_results: int = 10
  include_prerelease: bool = False

# Main app loads these automatically when plugin is discovered
```

#### 2. Multi-tenant Configuration

Applications serving multiple tenants can namespace per-tenant config:

```python
@configclass(namespace="tenants.customer1")
class Customer1Config:
  api_key: str = ""

@configclass(namespace="tenants.customer2")
class Customer2Config:
  api_key: str = ""

# TOML:
# [tenants.customer1]
# api_key = "key1"
# 
# [tenants.customer2]
# api_key = "key2"
```

#### 3. Environment-Specific Overrides

```python
@configclass(namespace="environments.production")
class ProductionConfig:
  debug: bool = False
  log_level: str = "WARNING"

@configclass(namespace="environments.staging")
class StagingConfig:
  debug: bool = True
  log_level: str = "INFO"
```

### CLI Argument Behavior

With `namespace="tools.pkgq"`, CLI arguments should be:

```bash
# Dashed version of namespace + field
yoker --tools-pkgq-enabled false
yoker --tools-pkgq-cache-directory /custom/cache
```

This mirrors the existing `prefix` behavior but includes the full namespace path.

### Implementation Notes

1. **Merge, don't replace**: Namespace extraction should merge into parent config, not replace it.

2. **Validation**: Namespaced configs should support `__post_init__` validation just like regular configs.

3. **Multiple namespaces**: Support registering multiple configclasses to the same parent namespace:

   ```python
   @configclass(namespace="tools.pkgq")
   class PkgqToolConfig: ...
   
   @configclass(namespace="tools.git")
   class GitToolConfig: ...
   ```

4. **Conflict handling**: If a namespace already exists in the parent, merge or raise error (configurable).

5. **CLI prefix**: Namespace implicitly defines CLI prefix (`--{namespace}-{field}`).

### Breaking Changes

None. This is a new feature that adds a parameter to `@configclass`. Existing code using `cmd` and `prefix` continues to work.

### Migration Path

For users wanting namespaced configs:

**Before** (workaround):
```python
# Manual namespace handling in custom code
cfg = load_toml("config.toml")
pkgq_config = cfg.get("tools", {}).get("pkgq", {})
config = from_dict(PkgqConfig, pkgq_config)
```

**After** (with namespace):
```python
# Automatic namespace extraction
@configclass(namespace="tools.pkgq")
class PkgqToolConfig:
  ...

config = get_config(Config, name="yoker")
# config.tools.pkgq is populated automatically
```

---

## Feature Request 2: Adding Fields at Runtime

### Summary

Enable dynamic field addition to configclasses at runtime to support plugin architectures where components and their configurations are discovered dynamically.

### Problem Statement

Clevis currently requires all configuration fields to be defined at dataclass definition time. This is a fundamental constraint from Python's `dataclasses.fields()` function, which only returns fields defined in the class.

For Yoker's plugin system, this creates a chicken-and-egg problem:

1. **Static Config Definition**: Yoker defines its config structure at import time:

   ```python
   # yoker/config.py
   
   @dataclass(frozen=True)
   class ToolsConfig:
     list: ListToolConfig = field(default_factory=ListToolConfig)
     read: ReadToolConfig = field(default_factory=ReadToolConfig)
     write: WriteToolConfig = field(default_factory=WriteToolConfig)
     # ... all tools must be defined here ...
   ```

2. **Dynamic Plugin Discovery**: Plugins are discovered at runtime when the application starts:

   ```python
   # yoker/plugins/loader.py
   
   def load_plugins(plugin_list: list[str]) -> None:
     for package_name in plugin_list:
       try:
         module = importlib.import_module(f"{package_name}.yoker")
         # HOW TO ADD PLUGIN CONFIG TO ToolsConfig?
       except ImportError:
         logger.warning(f"Plugin {package_name} not found")
   ```

3. **The Conflict**: Plugins cannot add their configuration fields to `ToolsConfig` because:
   - Dataclasses are frozen (immutable after creation)
   - `fields(ToolsConfig)` only returns predefined fields
   - Clevis's `Factory.list_fields()` introspects at runtime, not definition time

### Current Limitation

```python
from dataclasses import dataclass, field, fields
from clevis import configclass, get_config

@configclass
class ToolsConfig:
  list: ListToolConfig = field(default_factory=ListToolConfig)
  read: ReadToolConfig = field(default_factory=ReadToolConfig)

# Attempt to add plugin config at runtime
# ❌ THIS DOESN'T WORK
ToolsConfig.pkgq = field(default_factory=PkgqToolConfig)  # Raises FrozenInstanceError

# ❌ THIS DOESN'T WORK EITHER
fields(ToolsConfig)  # Returns only [list, read], no pkgq
```

### Workaround: Dict[str, Dataclass]

Clevis supports dict fields with uniform dataclass values:

```python
@dataclass(frozen=True)
class PluginConfig:
  enabled: bool = True

@dataclass(frozen=True)
class ToolsConfig:
  list: ListToolConfig = field(default_factory=ListToolConfig)
  read: ReadToolConfig = field(default_factory=ReadToolConfig)
  
  # All plugins must use same schema
  plugins: dict[str, PluginConfig] = field(default_factory=dict)
```

**TOML**:
```toml
[tools.plugins.pkgq]
enabled = true
cache_directory = "/custom/cache"  # ❌ NOT ALLOWED - PluginConfig doesn't have this field
```

**Limitations**:
1. **Uniform schema**: All plugins must use the same `PluginConfig` dataclass
2. **No type-specific fields**: `PkgqConfig.cache_directory` cannot be defined
3. **Manual validation**: Cannot have plugin-specific `__post_init__` validation

### Proposed Solution: Dynamic Field Registration

Add a `register_field()` function to dynamically add fields to configclasses before configuration loading.

#### API Design

```python
from dataclasses import dataclass, field
from clevis import configclass, register_field, get_config

# Define base config
@configclass
class ToolsConfig:
  list: ListToolConfig = field(default_factory=ListToolConfig)
  read: ReadToolConfig = field(default_factory=ReadToolConfig)

# Define plugin config
@configclass
class PkgqToolConfig:
  enabled: bool = True
  cache_directory: str = "~/.cache/pkgq"
  timeout_seconds: int = 30

# Register plugin config at runtime (before get_config is called)
register_field(ToolsConfig, "pkgq", PkgqToolConfig)

# Load configuration
config = get_config(Config, name="yoker")
# config.tools.pkgq is now available and populated from [tools.pkgq]
```

#### Minimal Example

```python
# yoker/plugins/loader.py

from clevis import register_field
from yoker.config import ToolsConfig, AgentsConfig

def load_plugin(package_name: str) -> None:
  """Load a plugin and register its configuration."""
  try:
    # Import plugin module
    module = importlib.import_module(f"{package_name}.yoker")
    
    # Register tool config if provided
    if hasattr(module, "ToolConfig"):
      register_field(ToolsConfig, package_name, module.ToolConfig)
    
    # Register agent config if provided
    if hasattr(module, "AgentConfig"):
      register_field(AgentsConfig, package_name, module.AgentConfig)
    
  except ImportError as e:
    logger.warning(f"Plugin {package_name} not found: {e}")
```

**Plugin Implementation**:

```python
# pkgq/yoker/__init__.py

from dataclasses import dataclass, field
from clevis import configclass

@configclass
class ToolConfig:
  """pkgq tool configuration."""
  enabled: bool = True
  cache_directory: str = "~/.cache/pkgq"
  timeout_seconds: int = 30
  
  def __post_init__(self):
    if self.timeout_seconds < 0:
      raise ValueError("timeout_seconds must be non-negative")

@configclass
class AgentConfig:
  """pkgq agent configuration."""
  max_results: int = 10
  include_prerelease: bool = False

TOOLS = [FindPackageTool]
SKILLS = [CreatePackageSkill]
AGENTS = []

# Config classes are automatically registered by yoker's plugin loader
```

**TOML Configuration**:

```toml
# yoker.toml

[tools.list]  # Built-in tool
max_depth = 5

[tools.pkgq]  # Plugin tool - discovered at runtime
enabled = true
cache_directory = "/custom/cache"
timeout_seconds = 60
```

### When to Add Fields

Fields must be registered **before** `get_config()` is called. This gives applications control over when registration happens:

```python
# Application startup sequence
from yoker.plugins import load_plugins
from yoker.config import get_yoker_config

# 1. Load plugins (registers fields)
load_plugins(["pkgq", "c3"])

# 2. Load configuration (uses registered fields)
config = get_yoker_config(cli=True)

# ❌ TOO LATE - Cannot register after get_config
# register_field(ToolsConfig, "another", AnotherConfig)  # Error
```

### Implementation Approach

Since frozen dataclasses cannot be modified after creation, dynamic field addition requires creating a new dataclass type:

```python
# clevis/__init__.py

def register_field(
  config_class: type,
  field_name: str,
  field_type: type,
  default_factory: Callable[[], Any] | None = None
) -> None:
  """Register a new field to a configclass.
  
  Creates a new dataclass type with the field added and updates
  the factory registry.
  
  Args:
    config_class: The configclass to extend.
    field_name: Name of the new field.
    field_type: Type of the new field (must be a dataclass).
    default_factory: Factory function for default value.
  
  Raises:
    RuntimeError: If get_config has already been called.
    ValueError: If field_name already exists.
  """
  # Check if already configured
  if _configured_parsers:
    raise RuntimeError(
      "Cannot register fields after configuration has been loaded. "
      "Call register_field() before get_config()."
    )
  
  # Check for duplicate field
  if field_name in {f.name for f in fields(config_class)}:
    raise ValueError(
      f"Field '{field_name}' already exists in {config_class.__name__}"
    )
  
  # Create new dataclass with added field
  new_fields = [
    (f.name, f.type, f) if f.default != MISSING else (f.name, f.type)
    for f in fields(config_class)
  ]
  new_fields.append((
    field_name,
    field_type,
    field(default_factory=field_type) if default_factory is None 
      else field(default_factory=default_factory)
  ))
  
  # Create new class
  new_class = dataclass(
    type(
      config_class.__name__,
      config_class.__bases__,
      {"__module__": config_class.__module__},
    )
  )
  
  # Copy __post_init__ and other methods
  for attr_name in dir(config_class):
    if not attr_name.startswith("_") or attr_name == "__post_init__":
      setattr(new_class, attr_name, getattr(config_class, attr_name))
  
  # Update factory registry
  global _factories
  old_factory = _factories.pop(config_class, None)
  _factories[new_class] = Factory(new_class)
  
  return new_class
```

**Note**: This approach creates a new class type. Callers must use the returned class:

```python
# Correct usage
ExtendedToolsConfig = register_field(ToolsConfig, "pkgq", PkgqToolConfig)
config = get_config(Config, name="yoker")  # Uses ExtendedToolsConfig

# Alternative: In-place update (requires more complex implementation)
register_field(ToolsConfig, "pkgq", PkgqToolConfig)  # Modifies ToolsConfig in place
```

### Alternative: Config Inheritance

If modifying dataclasses is too complex, consider supporting config inheritance:

```python
from clevis import configclass, extend_config

@configclass
class BaseToolsConfig:
  list: ListToolConfig = field(default_factory=ListToolConfig)
  read: ReadToolConfig = field(default_factory=ReadToolConfig)

@configclass
class PkgqToolConfig:
  enabled: bool = True
  cache_directory: str = "~/.cache/pkgq"

# Create extended config at runtime
ExtendedToolsConfig = extend_config(
  BaseToolsConfig,
  pkgq=PkgqToolConfig
)

# ExtendedToolsConfig has fields: list, read, pkgq
```

### CLI Argument Generation

Registered fields should generate CLI arguments just like static fields:

```bash
# After registering PkgqToolConfig
yoker --tools-pkgq-enabled false
yoker --tools-pkgq-cache-directory /custom/cache
yoker --tools-pkgq-timeout-seconds 60
```

The `Factory.configure_parser()` method must be called **after** all fields are registered:

```python
# Correct order
load_plugins(["pkgq"])  # Registers fields
config = get_config(Config, cli=True)  # Configures parser and loads config

# Incorrect order
config = get_config(Config, cli=True)  # Parser configured without pkgq field
load_plugins(["pkgq"])  # Too late - parser already configured
```

### Validation

Registered fields should support `__post_init__` validation:

```python
@configclass
class PkgqToolConfig:
  cache_directory: str = "~/.cache/pkgq"
  timeout_seconds: int = 30
  
  def __post_init__(self):
    if self.timeout_seconds < 0:
      raise ValueError("timeout_seconds must be non-negative")
    if not os.path.isabs(self.cache_directory):
      self.cache_directory = os.path.expanduser(self.cache_directory)
```

### Use Cases

#### 1. Plugin Architecture (Primary)

Applications with plugin systems can discover and register configs at startup:

```python
# Application entry point
def main():
  # Discover plugins
  plugins = discover_plugins()
  
  # Register plugin configs
  for plugin in plugins:
    if hasattr(plugin, "Config"):
      register_field(ToolsConfig, plugin.name, plugin.Config)
  
  # Load configuration
  config = get_config(AppConfig, name="app")
  
  # Initialize plugins with config
  for plugin in plugins:
    plugin.initialize(config.tools.__getattr__(plugin.name))
```

#### 2. Optional Dependencies

Applications with optional features can conditionally register configs:

```python
try:
  from rich.console import Console
  
  @configclass
  class RichOutputConfig:
    theme: str = "monokai"
    line_numbers: bool = True
  
  register_field(OutputConfig, "rich", RichOutputConfig)
except ImportError:
  pass  # Rich not available, skip config
```

#### 3. Environment-Specific Configuration

Different environments can have different config schemas:

```python
import os

if os.environ.get("ENABLE_EXPERIMENTAL"):
  @configclass
  class ExperimentalConfig:
    feature_flags: list[str] = field(default_factory=list)
  
  register_field(Config, "experimental", ExperimentalConfig)
```

### Backward Compatibility

This feature is purely additive. Existing code continues to work without changes.

### Migration Path

**Before** (manual workaround):
```python
# Custom plugin config loading
@dataclass
class ToolsConfig:
  list: ListToolConfig = field(default_factory=ListToolConfig)
  plugins: dict[str, Any] = field(default_factory=dict)  # Manual

# Load plugin configs manually
def load_plugin_config(plugin_name: str, config_dict: dict) -> PluginConfig:
  plugin_config_dict = config_dict.get("plugins", {}).get(plugin_name, {})
  return from_dict(PluginConfig, plugin_config_dict)
```

**After** (with register_field):
```python
@configclass
class ToolsConfig:
  list: ListToolConfig = field(default_factory=ListToolConfig)

# Plugin registers itself
register_field(ToolsConfig, "pkgq", PkgqToolConfig)

# Automatic loading
config = get_config(Config, name="yoker")
# config.tools.pkgq is populated from [tools.pkgq]
```

---

## Summary

### Feature Comparison

| Feature | Current State | With Namespace Support | With Runtime Fields |
|---------|---------------|------------------------|---------------------|
| Plugin config location | Manual dict management | `[tools.pkgq]` | `[tools.pkgq]` |
| Type safety | Uniform dict schema | Full type hints | Full type hints |
| Validation | Manual | `__post_init__` | `__post_init__` |
| CLI args | N/A | `--tools-pkgq-*` | `--tools-pkgq-*` |
| Config discovery | Manual extraction | Automatic | Automatic |

### Recommended Priority

1. **Feature Request 1 (Namespace Support)**: Higher priority, simpler implementation, addresses the immediate need for namespaced TOML sections.

2. **Feature Request 2 (Runtime Fields)**: Lower priority, more complex implementation, enables fully dynamic plugin discovery but can be worked around with dict schemas.

### Alternative: Combined Solution

Both features can work together:

```python
# Define plugin config with namespace
@configclass(namespace="tools.pkgq")
class PkgqToolConfig:
  enabled: bool = True
  cache_directory: str = "~/.cache/pkgq"

# Register at runtime
register_field(ToolsConfig, "pkgq", PkgqToolConfig)

# Result:
# - TOML: [tools.pkgq]
# - CLI: --tools-pkgq-enabled
# - Config: config.tools.pkgq.enabled
```

### Testing Considerations

Both features should include:

1. **Unit tests** for registration before/after `get_config()`
2. **Integration tests** with real TOML files
3. **Error tests** for duplicate fields, invalid namespaces
4. **Performance tests** for many registered fields (100+ plugins)
5. **Thread-safety tests** for concurrent registration

---

## References

- **Clevis Repository**: https://github.com/christophevg/clevis
- **Clevis Documentation**: https://clevis.readthedocs.io
- **Yoker Plugin Architecture**: `/Users/xtof/Workspace/agentic/yoker/analysis/plugin-architecture.md`
- **Yoker Config Extension Analysis**: `/Users/xtof/Workspace/agentic/yoker/analysis/clevis-config-extension.md`
- **Python dataclasses documentation**: https://docs.python.org/3/library/dataclasses.html