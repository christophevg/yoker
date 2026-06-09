# Clevis Config Extension Analysis

## Executive Summary

**Current Clevis Version**: 0.3.3

Clevis is a configuration management library that provides:
- Dataclass-based configuration schemas
- TOML file loading with layered merging (user < project < CLI)
- CLI argument auto-generation from dataclass fields
- Environment variable interpolation in TOML files

**Key Finding**: Clevis currently **does not support dynamic field addition** at runtime. All configuration fields must be defined statically in dataclass definitions. This is a fundamental architectural constraint that requires workarounds or feature requests for plugin config injection.

---

## 1. Dynamic Field Addition

### Current Behavior

**Clevis requires all fields to be defined at dataclass definition time.**

The architecture uses Python's `dataclasses.fields()` to introspect the schema:

```python
# clevis/__init__.py:325-332
def list_fields(self, clz: type | None = None, path: list[str] | None = None):
    clz = self.config_class if clz is None else clz
    path = [] if path is None else path
    result = []
    for f in fields(clz):  # <-- Requires pre-defined fields
      concrete_type = unpack_type(f.type)
      if is_dataclass(concrete_type):
        result.extend(self.list_fields(concrete_type, path=path + [f.name]))
      else:
        result.append((f, path))
    return result
```

**Implications**:
- Cannot add fields to a configclass at runtime
- Cannot dynamically inject plugin configurations
- All tools and their configs must be known at import time

### Workaround: Dict[str, Dataclass] Pattern

Clevis **does support** dict fields with dataclass values:

```python
@dataclass(frozen=True)
class PluginConfig:
  enabled: bool = True
  priority: int = 100

@dataclass(frozen=True)
class Config:
  plugins: dict[str, PluginConfig] = field(default_factory=dict)
```

TOML:
```toml
[plugins.pkgq]
enabled = true
priority = 50

[plugins.another_plugin]
enabled = false
```

**Limitations**:
- All plugin configs must use the same schema (PluginConfig)
- Cannot have type-specific configurations per plugin
- Validation in `__post_init__` applies uniformly to all plugins

**This is what Yoker already uses** for `handlers: dict[str, HandlerConfig]`:

```python
# yoker/config.py:237
handlers: dict[str, HandlerConfig] = field(default_factory=dict)
```

---

## 2. Config Merging

### Current Merging Behavior

Clevis merges configs in this order (lowest to highest priority):

1. Dataclass defaults
2. User-level TOML (`~/.{name}.toml`)
3. Project-level TOML (`./{name}.toml`)
4. CLI arguments

The merge uses `dict.update()` for TOML files, then `dacite.from_dict()` for final conversion:

```python
# clevis/__init__.py:766-799
cfg: dict[str, Any] = {}
if user:
  cfg.update(_load_toml_from_fd(user_fd))
if project:
  cfg.update(_load_toml_from_fd(project_fd))
# ...
apply_to_dict(get_factory(clz).get_args(args), cfg)
return from_dict(data_class=clz, data=cfg, config=Config(cast=[tuple, set]))
```

### Namespace Support

**Clevis has NO built-in namespace support** for config sections. The subcommand feature (`@configclass(cmd="print")`) extracts a section but doesn't preserve hierarchical merging:

```python
# clevis/__init__.py:804-822
toml_key = factory.config or factory.cmd
if toml_key and toml_key in cfg:
  cmd_cfg = cfg.pop(toml_key)
  if isinstance(cmd_cfg, dict):
    cfg.clear()  # <-- Clears root config!
    cfg.update(cmd_cfg)
```

**For plugins**, this means:
- Each plugin would need its own `@configclass(cmd="plugin_name")` decorator
- But subcommands are for CLI command dispatch, not namespacing
- No support for nested plugin configs like `[tools.pkgq]`, `[agents.pkgq]`

---

## 3. CLI Argument Generation

### Current Behavior

CLI args are generated from dataclass fields using dotted notation:

```python
# clevis/__init__.py:269-288
for f, path in self.list_fields():
  name = ".".join(path + [f.name])
  cli_name = name.replace(".", "-").replace("_", "-")
  # Result: --backend-ollama-model, --context-session-id
```

### Dynamic Fields Problem

Since fields must be pre-defined, CLI arguments cannot be generated for plugin configs. The `Factory.configure_parser()` method is called once at first config load:

```python
# clevis/__init__.py:244-288
def configure_parser(self) -> None:
  if self._configured:
    return
  # ... configure once ...
  self._configured = True
```

---

## 4. What Yoker Needs

Based on the current Yoker config structure (`/Users/xtof/Workspace/agentic/yoker/src/yoker/config.py`), plugins need to inject configuration under specific namespaces:

### Required Pattern

```python
@dataclass(frozen=True)
class PkgqToolConfig:
  """Configuration for pkgq tool plugin."""
  enabled: bool = True
  cache_directory: str = "~/.cache/pkgq"
  timeout_seconds: int = 30

@dataclass(frozen=True)
class PkgqAgentConfig:
  """Configuration for pkgq agent plugin."""
  max_results: int = 10
  include_prerelease: bool = False

# Desired config injection:
@dataclass(frozen=True)
class ToolsConfig:
  list: ListToolConfig = field(default_factory=ListToolConfig)
  read: ReadToolConfig = field(default_factory=ReadToolConfig)
  # ... existing tools ...
  pkgq: PkgqToolConfig = field(default_factory=PkgqToolConfig)  # <-- Dynamic
```

### TOML Structure

```toml
[tools.pkgq]
enabled = true
cache_directory = "/custom/cache"
timeout_seconds = 60

[agents.pkgq]
max_results = 20
include_prerelease = true
```

---

## 5. Proposed Feature Requests for Clevis

### Feature Request 1: Dynamic Field Registration

**Summary**: Allow registering new fields to a configclass at runtime.

**API**:
```python
from clevis import configclass, register_field, get_config

@configclass
class ToolsConfig:
  list: ListToolConfig = field(default_factory=ListToolConfig)
  read: ReadToolConfig = field(default_factory=ReadToolConfig)

# Plugin registers its config at import time
@register_field(ToolsConfig, "pkgq", PkgqToolConfig)
def _register_pkgq():
  from yoker.tools.pkgq import PkgqToolConfig
  return PkgqToolConfig
```

**Use Case**: Plugin discovery loads plugins, which register their configs before `get_config()` is called.

**Implementation Complexity**: HIGH
- Requires modifying frozen dataclasses (impossible in pure Python)
- Alternative: Generate new dataclass types dynamically
- Alternative: Use `__init_subclass__` to accumulate fields

---

### Feature Request 2: Plugin Namespace Pattern

**Summary**: Built-in support for plugin-style config sections with dynamic schemas.

**API**:
```python
from clevis import configclass, PluginConfig, get_config

@configclass
class ToolsConfig(PluginConfig):
  list: ListToolConfig = field(default_factory=ListToolConfig)
  read: ReadToolConfig = field(default_factory=ReadToolConfig)

  @classmethod
  def register_plugin(cls, name: str, config_class: type) -> None:
    """Register a plugin configuration."""
    cls._plugins[name] = config_class

# Plugin registration
from yoker.tools.pkgq import PkgqToolConfig
ToolsConfig.register_plugin("pkgq", PkgqToolConfig)
```

**Implementation Complexity**: MEDIUM
- Requires `PluginConfig` base class with plugin registry
- `get_config()` would need to dynamically build the schema
- dacite already supports dict[str, Dataclass], but we need type-specific per-key schemas

---

### Feature Request 3: Dict[str, Union[...]] Support

**Summary**: Allow dict fields to specify different dataclass types per key.

**Current Limitation**:
```python
plugins: dict[str, PluginConfig]  # All values must be PluginConfig
```

**Proposed**:
```python
plugins: dict[str, Union[PkgqConfig, AnotherConfig, DefaultConfig]]
```

**Implementation Complexity**: LOW (may already work)
- dacite might support this, but validation would be tricky
- Need to specify discriminator field for type selection

---

### Feature Request 4: Config Extension/Mixin

**Summary**: Allow composing configs from multiple sources.

**API**:
```python
from clevis import configclass, extend_config

@configclass
class BaseToolsConfig:
  list: ListToolConfig = field(default_factory=ListToolConfig)
  read: ReadToolConfig = field(default_factory=ReadToolConfig)

@configclass
class PkgqToolConfig:
  enabled: bool = True

# Extend at runtime
ExtendedToolsConfig = extend_config(BaseToolsConfig, pkgq=PkgqToolConfig)
```

**Implementation Complexity**: MEDIUM
- Generate new dataclass type dynamically
- Update Factory registry

---

## 6. Recommended Workaround for Yoker (Without Clevis Changes)

### Approach: Pre-defined Plugin Slots with Dict[str, PluginConfig]

Yoker already uses this pattern for handlers. Extend it:

```python
# yoker/config.py

@dataclass(frozen=True)
class PluginConfig:
  """Base configuration for all plugins."""
  enabled: bool = True

@dataclass(frozen=True)
class ToolsConfig:
  list: ListToolConfig = field(default_factory=ListToolConfig)
  read: ReadToolConfig = field(default_factory=ReadToolConfig)
  # ... existing tools ...

  # Plugin configurations
  # Each plugin defines its own PluginConfig subclass
  # Plugins register by adding to this dict
  _plugins: dict[str, PluginConfig] = field(default_factory=dict)
```

### Plugin Registration Pattern

```python
# yoker/tools/pkgq/__init__.py

from yoker.config import PluginConfig

@dataclass(frozen=True)
class PkgqPluginConfig(PluginConfig):
  """pkgq-specific configuration."""
  cache_directory: str = "~/.cache/pkgq"
  timeout_seconds: int = 30

# Register at import time
def register_plugin(config: dict[str, Any]) -> None:
  """Called by yoker during plugin initialization."""
  # Plugin-specific config validation
  if "tools" not in config:
    config["tools"] = {}
  if "_plugins" not in config["tools"]:
    config["tools"]["_plugins"] = {}

  # Convert TOML dict to dataclass
  from dacite import from_dict, Config
  pkgq_config = from_dict(
    PkgqPluginConfig,
    config["tools"].get("_plugins", {}).get("pkgq", {}),
    config=Config(cast=[tuple, set])
  )
  config["tools"]["_plugins"]["pkgq"] = pkgq_config
```

### TOML Structure

```toml
# yoker.toml
[tools._plugins.pkgq]
enabled = true
cache_directory = "/custom/cache"
timeout_seconds = 60
```

### Pros
- Works with current Clevis (no changes needed)
- Type-safe per-plugin config validation
- Plugin configs are isolated from core config

### Cons
- Non-standard TOML structure (`_plugins` namespace)
- Requires manual registration in plugin `__init__.py`
- Dict[str, PluginConfig] doesn't allow type-specific per-plugin configs

---

## 7. Alternative: Fork Clevis with Dynamic Config

If Yoker needs truly dynamic configs, consider:

### Option A: Contribute to Clevis

1. Implement Feature Request 2 (Plugin Namespace Pattern)
2. Submit as PR to Clevis repository
3. Yoker upgrades when merged

**Estimated effort**: 1-2 weeks for implementation + tests

### Option B: Internal Clevis Fork

1. Fork Clevis inside Yoker repository
2. Add `PluginConfig` base class
3. Implement dynamic field registration

**Pros**: Full control, can optimize for Yoker needs
**Cons**: Maintenance burden, divergence from upstream

### Option C: Separate Plugin Config System

1. Keep core config in Clevis
2. Build separate plugin config system in Yoker
3. Merge both at runtime

```python
# yoker/config.py

@dataclass(frozen=True)
class Config:
  harness: HarnessConfig = field(default_factory=HarnessConfig)
  # ... core config ...

  # Separate system for plugins
  _plugins: PluginRegistry = field(default_factory=PluginRegistry)

  def get_plugin_config(self, plugin_name: str) -> Any:
    return self._plugins.get(plugin_name)
```

---

## 8. Recommended Path for Yoker

### Short-term (No Clevis changes)

1. **Use dict[str, PluginConfig] pattern** for plugin configs
2. Define `PluginConfig` base class in Yoker
3. Plugins extend base class with type-specific fields
4. Manual registration during plugin initialization

**Example**:
```python
# yoker/config.py
@dataclass(frozen=True)
class PluginConfig:
  enabled: bool = True

@dataclass(frozen=True)
class ToolsConfig:
  # ... existing tools ...
  plugins: dict[str, PluginConfig] = field(default_factory=dict)

# yoker/tools/pkgq/config.py
@dataclass(frozen=True)
class PkgqConfig(PluginConfig):
  cache_directory: str = "~/.cache/pkgq"
  timeout_seconds: int = 30

# yoker/tools/pkgq/__init__.py
def initialize(config_dict: dict) -> PkgqConfig:
  from dacite import from_dict, Config
  return from_dict(
    PkgqConfig,
    config_dict.get("tools", {}).get("plugins", {}).get("pkgq", {}),
    config=Config(cast=[tuple, set])
  )
```

### Medium-term (Clevis contribution)

1. **Submit Feature Request 2** (Plugin Namespace Pattern) to Clevis
2. Implement in Clevis fork
3. Test with Yoker
4. Contribute PR upstream

### Long-term (Clevis evolution)

1. Work with Clevis maintainer on plugin architecture
2. Add official `PluginConfig` support to Clevis
3. Yoker adopts standard when available

---

## 9. Summary Table

| Requirement | Clevis Support | Workaround | Feature Request |
|-------------|---------------|------------|-----------------|
| Dynamic field addition | ❌ No | Dict[str, PluginConfig] | FR1: register_field |
| Plugin namespacing | ❌ No | _plugins sub-key | FR2: PluginConfig base |
| Type-specific plugin configs | ❌ No | Manual dacite conversion | FR3: Union dicts |
| CLI args for plugins | ❌ No | N/A (plugins don't need CLI) | N/A |
| Config merging | ✅ Yes | Already supported | N/A |

---

## 10. Action Items

1. **Immediate**: Implement dict[str, PluginConfig] pattern in Yoker
2. **Next**: Define PluginConfig base class with `enabled: bool = True`
3. **Next**: Create plugin initialization hook for config registration
4. **Future**: Submit Feature Request 2 to Clevis repository
5. **Future**: Consider contributing Plugin Namespace implementation

---

## Appendix: Clevis Source Code References

### Key Files

- `/Users/xtof/Workspace/agentic/clevis/src/clevis/__init__.py` - Main implementation
- `/Users/xtof/Workspace/agentic/clevis/tests/test_yoker_schema.py` - Yoker schema compatibility tests
- `/Users/xtof/Workspace/agentic/clevis/tests/test_subcommand_config.py` - Subcommand extraction tests

### Key Functions

- `get_config()` - Main entry point for config loading
- `Factory.configure_parser()` - CLI argument generation
- `Factory.list_fields()` - Field introspection (requires static fields)
- `apply_to_dict()` - Merges CLI args into config dict
- `from_dict()` - dacite dict-to-dataclass conversion

### Constraints

1. **Frozen dataclasses cannot be modified after creation**
   - All fields must be known at class definition time
   - `__post_init__` is the only hook for validation

2. **Field introspection uses `dataclasses.fields()`**
   - Only returns fields defined in the class
   - Cannot discover dynamically added fields

3. **CLI args are generated once**
   - `configure_parser()` is called on first `get_config()`
   - Cannot add args after first config load

4. **TOML merging is dict-based**
   - Uses `dict.update()` for layering
   - No namespace preservation