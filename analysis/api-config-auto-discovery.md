# API Design: Config Auto-Discovery and Agent Definition Path

**Date**: 2026-05-26
**Issue**: #7
**Reviewer**: API Architect Agent
**Context**: Implement zero-configuration startup with auto-discovery

## Summary

This document defines the API changes for config auto-discovery and agent definition path configuration. The goal is to enable `Agent()` to work without explicit configuration while maintaining backward compatibility with explicit paths.

## Current State

### Config Loading (`src/yoker/config/loader.py`)

```python
def load_config(path: Path | str) -> Config:
    """Load from explicit path, raise FileNotFoundError if missing."""

def load_config_with_defaults(path: Path | str | None = None) -> Config:
    """Load from path if provided, return Config() defaults if None or missing."""
```

### Config Schema (`src/yoker/config/schema.py`)

```python
@dataclass(frozen=True)
class AgentsConfig:
    directory: str = ""        # Directory containing agent definitions
    default_type: str = "main" # Default agent type
```

### Agent Initialization (`src/yoker/agent.py`)

```python
def __init__(
    self,
    model: str | None = None,
    config: "Config | None" = None,
    config_path: Path | str | None = None,
    ...
):
    # Precedence: config > config_path > Config()
    if config is not None:
        loaded_config = config
    elif config_path is not None:
        loaded_config = load_config(config_path)
    else:
        loaded_config = Config()
```

## Proposed Changes

### 1. Config Schema: Add `definition` to `AgentsConfig`

**Location**: `src/yoker/config/schema.py`

```python
@dataclass(frozen=True)
class AgentsConfig:
    """Agent definition settings.

    Attributes:
        directory: Directory containing agent definition files (empty = no directory).
        definition: Path to a specific agent definition file (overrides default_type).
        default_type: Default agent type (used if definition not set).
    """

    directory: str = ""
    definition: str = ""  # NEW: Path to specific agent definition file
    default_type: str = "main"
```

**Rationale**:
- `definition` provides explicit path to a single agent definition file
- Takes precedence over `default_type` when set
- Empty string (default) means no agent definition loaded
- Path can be relative or absolute
- Enables configuration-driven agent selection without CLI flags

### 2. Config Loader: Auto-Discovery Function

**Location**: `src/yoker/config/loader.py`

```python
def discover_config() -> tuple[Config, Path | None]:
    """Auto-discover configuration file.

    Search order:
        1. ./yoker.toml (current directory)
        2. ~/.yoker.toml (user home directory)
        3. Config() defaults

    Returns:
        Tuple of (Config, Path | None). Path is the discovered config file,
        or None if using defaults.

    Raises:
        ConfigurationError: If config file exists but is invalid.
    """
    from pathlib import Path

    # Try current directory
    cwd_config = Path.cwd() / "yoker.toml"
    if cwd_config.exists():
        log.info("config_discovered", path=str(cwd_config), location="cwd")
        return load_config(cwd_config), cwd_config

    # Try user home directory
    home_config = Path.home() / ".yoker.toml"
    if home_config.exists():
        log.info("config_discovered", path=str(home_config), location="home")
        return load_config(home_config), home_config

    # Fallback to defaults
    log.info("config_defaults")
    return Config(), None
```

**Key Design Decisions**:

1. **Return Type**: `(Config, Path | None)` - Returns both config and the path it came from
   - Path enables logging which file was loaded
   - `None` indicates defaults used
   - Caller can decide what to do with path information

2. **Logging**: Uses structured logging to record which file was loaded
   - Helpful for debugging configuration issues
   - Clear audit trail of config source

3. **Error Handling**: Invalid config files raise `ConfigurationError`
   - Silent fallback only for missing files, not invalid files
   - Forces user to fix malformed configs

4. **No `load_config_auto()` Alternative**: Considered but rejected
   - Would duplicate existing `load_config_with_defaults()` logic
   - `discover_config()` is clearer about discovery behavior
   - Existing `load_config_with_defaults()` remains for explicit override scenarios

### 3. Agent Initialization: Use Auto-Discovery

**Location**: `src/yoker/agent.py`

```python
def __init__(
    self,
    model: str | None = None,
    config: "Config | None" = None,
    config_path: Path | str | None = None,
    thinking_mode: ThinkingMode = ThinkingMode.ON,
    command_registry: "CommandRegistry | None" = None,
    agent_definition: "AgentDefinition | None" = None,
    agent_path: Path | str | None = None,
    context_manager: "ContextManager | None" = None,
    _recursion_depth: int = 0,
) -> None:
    """Initialize the agent.

    Config/Agent Resolution (in order of precedence):
        1. Explicit `config` parameter
        2. Explicit `config_path` parameter
        3. Auto-discovered config (./yoker.toml, ~/.yoker.toml)
        4. Config() defaults

    Agent Definition Resolution (in order of precedence):
        1. Explicit `agent_definition` parameter
        2. Explicit `agent_path` parameter
        3. Config's `agents.definition` (if set and file exists)
        4. None (default system prompt)

    Args:
        ...
    """
    from yoker.config import Config, discover_config

    # Config resolution
    if config is not None:
        loaded_config = config
        config_source = "explicit"
    elif config_path is not None:
        from yoker.config import load_config
        loaded_config = load_config(config_path)
        config_source = "explicit_path"
    else:
        loaded_config, discovered_path = discover_config()
        config_source = "discovered" if discovered_path else "defaults"

    log.info(
        "config_loaded",
        source=config_source,
        path=str(discovered_path) if discovered_path else None,
    )

    # ... rest of initialization
```

**Resolution Order for Config**:

| Precedence | Source | Behavior |
|------------|--------|----------|
| 1 | `config` parameter | Use directly, skip discovery |
| 2 | `config_path` parameter | Load from path, error if missing |
| 3 | Auto-discovery | Try `./yoker.toml`, `~/.yoker.toml` |
| 4 | Defaults | `Config()` with all defaults |

**Resolution Order for Agent Definition**:

| Precedence | Source | Behavior |
|------------|--------|----------|
| 1 | `agent_definition` parameter | Use directly |
| 2 | `agent_path` parameter | Load from path |
| 3 | `config.agents.definition` | Load if set and exists |
| 4 | None | Default system prompt |

### 4. Update Config Loader Parser

**Location**: `src/yoker/config/loader.py`

```python
def _parse_agents(data: dict[str, object]) -> AgentsConfig:
    """Parse agents configuration section."""
    agents = _get_nested(data, "agents")
    if agents is None:
        return AgentsConfig()

    return AgentsConfig(
        directory=agents.get("directory", "./agents"),  # type: ignore
        definition=agents.get("definition", ""),  # NEW
        default_type=agents.get("default_type", "main"),  # type: ignore
    )
```

## Auto-Discovery Algorithm

```
┌─────────────────────────────────────────────────────────┐
│                     Agent.__init__                      │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │ Config Resolution                                │   │
│  │                                                   │   │
│  │  config param?                                   │   │
│  │    └─ YES → Use config, skip discovery          │   │
│  │    └─ NO                                         │   │
│  │        config_path param?                        │   │
│  │          └─ YES → Load from path (error if fail)│   │
│  │          └─ NO                                   │   │
│  │              ./yoker.toml exists?                │   │
│  │                └─ YES → Load, log discovery     │   │
│  │                └─ NO                             │   │
│  │                    ~/.yoker.toml exists?        │   │
│  │                      └─ YES → Load, log         │   │
│  │                      └─ NO → Use defaults        │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │ Agent Definition Resolution                      │   │
│  │                                                   │   │
│  │  agent_definition param?                         │   │
│  │    └─ YES → Use definition                       │   │
│  │    └─ NO                                         │   │
│  │        agent_path param?                         │   │
│  │          └─ YES → Load from path                 │   │
│  │          └─ NO                                   │   │
│  │              config.agents.definition set?       │   │
│  │                └─ YES → Load if file exists     │   │
│  │                └─ NO → Use None (default)        │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

## Backward Compatibility

| Scenario | Current Behavior | New Behavior |
|----------|-----------------|--------------|
| `Agent()` | Uses `Config()` defaults | Auto-discovers config, then defaults |
| `Agent(config=cfg)` | Uses provided config | Uses provided config (unchanged) |
| `Agent(config_path=path)` | Loads from path | Loads from path (unchanged) |
| `Agent(config_path=missing)` | Returns defaults | Returns defaults (unchanged via `load_config_with_defaults`) |
| `yoker.toml` in CWD | Ignored | Auto-loaded |
| `~/.yoker.toml` | Ignored | Auto-loaded if no CWD config |

**Breaking Changes**: None

- All existing initialization patterns continue to work
- New behavior only when no config/config_path provided
- Config discovery is additive, not replacing

## Edge Cases

### 1. Invalid Config File

**Scenario**: `./yoker.toml` exists but has syntax error

**Behavior**: Raise `ConfigurationError` (not silent fallback)

**Rationale**: Invalid config indicates user error, should not silently ignore

```python
# ./yoker.toml has syntax error
agent = Agent()  # Raises ConfigurationError
agent = Agent(config_path="custom.toml")  # Could load different file
```

### 2. Both CWD and Home Configs

**Scenario**: Both `./yoker.toml` and `~/.yoker.toml` exist

**Behavior**: CWD config takes precedence (project-specific over global)

```python
# ./yoker.toml exists, ~/.yoker.toml exists
agent = Agent()  # Loads ./yoker.toml
```

### 3. Agent Definition Path in Config

**Scenario**: `config.agents.definition` set but file doesn't exist

**Behavior**: Log warning, use default system prompt (graceful degradation)

```python
# yoker.toml has:
# [agents]
# definition = "./agents/missing.md"

agent = Agent()  # Logs warning, uses default prompt
```

### 4. Agent Definition Path Relative vs Absolute

**Scenario**: Relative path in config

**Behavior**: Relative to CWD (not config file location)

```python
# ~/.yoker.toml has:
# [agents]
# definition = "./agents/researcher.md"

# CWD is /home/user/project
agent = Agent()  # Loads /home/user/project/agents/researcher.md
```

### 5. Empty Config File

**Scenario**: `./yoker.toml` exists but empty

**Behavior**: Valid TOML (empty), returns `Config()` defaults

```python
# ./yoker.toml is empty or "{}"
agent = Agent()  # Uses Config() defaults
```

### 6. Permission Errors

**Scenario**: Config file exists but not readable

**Behavior**: Propagate `PermissionError` (don't catch)

**Rationale**: Permission issues indicate environment problems user must fix

### 7. Symlinked Config Files

**Scenario**: `./yoker.toml` is a symlink

**Behavior**: Follow symlink, load target file

**Rationale**: Symlinks are legitimate for shared configs

### 8. Agent Definition in Home Config

**Scenario**: `~/.yoker.toml` has `agents.definition = "~/agents/researcher.md"`

**Behavior**: `~` is expanded to home directory

```python
# ~/.yoker.toml has:
# [agents]
# definition = "~/agents/researcher.md"

agent = Agent()  # Loads /home/user/agents/researcher.md
```

## Security Considerations

### Path Traversal

Agent definition path is validated by existing `load_agent_definition()`:

- Uses `Path.resolve()` to normalize
- Checks against configured `agents.directory`
- Applies guardrails if needed

**No additional security concerns** from auto-discovery itself.

### Config File Tampering

Config files should be user-writable only:

- `./yoker.toml` - Project directory (user controlled)
- `~/.yoker.toml` - Home directory (user controlled)

**No special protection needed** - same threat model as existing explicit paths.

## Logging

Structured logging for configuration discovery:

```python
# Config discovered in CWD
log.info("config_discovered", path=str(path), location="cwd")

# Config discovered in home
log.info("config_discovered", path=str(path), location="home")

# Using defaults
log.info("config_defaults")

# Agent definition loaded from config
log.info(
    "agent_definition_loaded",
    path=str(path),
    source="config",
)

# Agent definition not found (warning)
log.warning(
    "agent_definition_not_found",
    path=str(path),
    fallback="default_prompt",
)
```

## Testing Strategy

### Unit Tests for `discover_config()`

1. **No config files exist** → Returns `Config(), None`
2. **CWD config exists** → Returns loaded config, CWD path
3. **Home config exists** → Returns loaded config, home path
4. **Both exist** → Returns CWD config (precedence)
5. **CWD config invalid** → Raises `ConfigurationError`
6. **Empty config file** → Returns `Config()` defaults

### Unit Tests for Agent Initialization

1. **Explicit config** → Uses config, no discovery
2. **Explicit config_path** → Loads from path, no discovery
3. **No config provided, CWD config exists** → Uses discovered config
4. **No config provided, home config exists** → Uses discovered config
5. **No config provided, no configs** → Uses defaults
6. **Config has agents.definition** → Loads agent definition
7. **Config has agents.definition, file missing** → Logs warning, uses default

### Integration Tests

1. **End-to-end zero-config startup** → `Agent()` works without args
2. **Config-driven agent selection** → `Agent()` with `agents.definition` in config
3. **CLI integration** → `python -m yoker` uses auto-discovery

## Implementation Checklist

- [ ] Add `definition: str = ""` to `AgentsConfig` dataclass
- [ ] Update `_parse_agents()` to parse `definition` field
- [ ] Create `discover_config()` function in `loader.py`
- [ ] Update `Agent.__init__()` to use `discover_config()`
- [ ] Add agent definition resolution from `config.agents.definition`
- [ ] Add logging for config discovery and agent definition loading
- [ ] Write unit tests for `discover_config()`
- [ ] Write unit tests for agent definition resolution
- [ ] Write integration tests for zero-config startup
- [ ] Update documentation (README.md, docs/quickstart.md)
- [ ] Add `agents.definition` to example config files

## Example Config File

```toml
# yoker.toml - Project configuration

[harness]
name = "my-project-agent"
version = "1.0"
log_level = "INFO"

[backend]
provider = "ollama"

[backend.ollama]
base_url = "http://localhost:11434"
model = "llama3.2:latest"

[agents]
directory = "./agents"
definition = "./agents/researcher.md"  # NEW: Explicit agent definition
default_type = "main"

[permissions]
filesystem_paths = [".", "./src"]
network_access = "none"

[tools.read]
allowed_extensions = [".py", ".md", ".txt", ".json", ".yaml", ".toml"]
```

## Open Questions

1. **Should `definition` accept URLs?**
   - **Decision**: No. Keep it simple for MVP. URLs would require async fetching, caching, and security validation.
   - **Future**: Could be added as a separate feature with proper security controls.

2. **Should we support XDG config paths?**
   - **Decision**: No for MVP. `~/.yoker.toml` is sufficient for user-level config.
   - **Future**: Could add `$XDG_CONFIG_HOME/yoker/config.toml` support if requested.

3. **Should `definition` path be relative to config file location?**
   - **Decision**: No. Relative paths resolve from CWD, matching existing behavior for `agents.directory`.
   - **Rationale**: Consistent with how paths work elsewhere in the config. Users can use absolute paths if needed.

## Action Items

1. Implement schema changes (`AgentsConfig.definition`)
2. Implement `discover_config()` function
3. Update `Agent.__init__()` to use auto-discovery
4. Add agent definition resolution from config
5. Add comprehensive logging
6. Write unit and integration tests
7. Update documentation
8. Add example configs to repository