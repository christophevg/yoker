# Plugin Security Implementation Summary

## Overview

Implemented a two-level plugin security system for yoker as specified in the requirements.

## Implementation

### 1. Config Structure

Updated `PluginsConfig` in `src/yoker/config.py`:

```python
@dataclass(frozen=True)
class PluginsConfig:
  """Plugin configuration.

  Attributes:
    enabled: Whether plugins are enabled globally. Default: False.
    packages: List of plugin packages to load (from config).
    trusted: Dictionary of trusted plugin names. Key is package name, value is True.
  """

  enabled: bool = False
  packages: tuple[str, ...] = ()
  trusted: dict[str, bool] = field(default_factory=dict)
```

**Example config:**
```toml
[plugins]
enabled = true

[plugins.trusted]
yoker_plugin_demo = true
pkgq = true
```

### 2. Security Module

Created `src/yoker/plugins/security.py` with:

- `is_trusted(plugin_name, config)` - Check if plugin is trusted (session or config)
- `confirm_plugin(plugin_name, plugin)` - Interactive confirmation for untrusted plugins
- `check_plugins_enabled(config)` - Level 1: Global opt-in check
- `check_plugin_allowed(plugin_name, config, plugin)` - Level 2: Per-plugin trust check
- `reset_session_trusted()` - Reset session cache (for testing)

**Session Trust Tracking:**
- `_session_trusted: set[str]` tracks plugins confirmed during current session
- Once confirmed, user won't be asked again for the same plugin

**Non-Interactive Mode:**
- When stdin is not a TTY, confirmation prompts fail gracefully
- Shows clear error message with config snippet to add

**Interactive Confirmation Display:**
```
╔══════════════════════════════════════════════════════════╗
║ Plugin: some_yoker_plugin                                ║
║                                                          ║
║ Tools:     some_tool, another_tool                       ║
║ Skills:    some_skill, other_skill                       ║
║ Agents:    some_agent                                    ║
║                                                          ║
║ Plugins can execute code on your system.                 ║
║ Only load plugins you trust.                             ║
║                                                          ║
║ Load this plugin? [y/N]: _                               ║
╚══════════════════════════════════════════════════════════╝
```

### 3. Agent Integration

Updated `src/yoker/agent.py` `_load_plugins()` method to:

1. Always load built-in `yoker` plugin (Level 0 - no security check)
2. Check `config.plugins.enabled` before loading external plugins
3. For each external plugin:
   - Check if trusted (config or session)
   - If not trusted, prompt for confirmation (interactive) or fail (non-interactive)
   - Only load if allowed

### 4. Tests

Created comprehensive test suite in `tests/test_plugins/test_security.py`:

**Test Classes:**
- `TestPluginsConfig` - Config structure tests (defaults, enabled, trusted)
- `TestIsTrusted` - Trust checking logic
- `TestConfirmPlugin` - Interactive/non-interactive confirmation
- `TestCheckPluginsEnabled` - Global opt-in check
- `TestCheckPluginAllowed` - Per-plugin authorization
- `TestIntegration` - End-to-end security workflow

**Test Coverage:**
- Default disabled state (plugins disabled by default)
- Enabled but untrusted (prompts for confirmation)
- Trusted plugins (load silently)
- Session trust (don't ask twice)
- Non-interactive mode (fail without trust)
- Session reset (for testing)

Updated existing tests to use:
```python
Config(plugins=PluginsConfig(enabled=True, trusted={"yoker_plugin_demo": True}))
```

### 5. Backward Compatibility

- Default `enabled=False` - plugins disabled by default
- Default `trusted={}` - empty trusted list
- Existing code without `[plugins]` section works correctly (plugins disabled)

## Files Modified

1. `src/yoker/config.py` - Added `enabled` and `trusted` to `PluginsConfig`
2. `src/yoker/agent.py` - Integrated security checks in `_load_plugins()`
3. `src/yoker/plugins/__init__.py` - Exported security functions
4. `src/yoker/plugins/security.py` - New module with security logic
5. `tests/test_plugins/test_security.py` - New test file
6. `tests/test_plugin_integration.py` - Updated to enable plugins
7. `tests/test_plugin_skill_discovery.py` - Updated to enable plugins

## Security Flow

```
┌─────────────────────────────────────────────────┐
│              Load Built-in Plugin               │
│                  (yoker)                        │
│          Always loaded, no security             │
└────────────────────┬────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────┐
│         Check if plugins enabled globally?      │
│         [plugins] enabled = true/false          │
└────────────────────┬────────────────────────────┘
                     │
        ┌────────────┴────────────┐
        │                         │
   No   │                         │ Yes
        ▼                         ▼
   ┌─────────┐           ┌─────────────────────┐
   │  Error  │           │  For each plugin:   │
   │  Exit   │           └──────────┬──────────┘
   └─────────┘                      │
                              ┌─────┴─────┐
                              │           │
                         Trusted?    Untrusted
                              │           │
                              ▼           ▼
                         ┌───────┐   ┌──────────────┐
                         │ Load  │   │   Confirm?   │
                         │Plugin │   │  Interactive │
                         └───────┘   └────┬─────────┘
                                           │
                                   ┌───────┴────────┐
                                   │                │
                              Yes  │                │ No
                                   ▼                ▼
                              ┌─────────┐      ┌──────────┐
                              │Session   │      │  Error   │
                              │Trust     │      │  Skip    │
                              │Load      │      └──────────┘
                              └─────────┘
```

## Usage Example

**Config file (`yoker.toml`):**
```toml
[plugins]
enabled = true

[plugins.trusted]
yoker_plugin_demo = true
pkgq = true
```

**CLI with untrusted plugin:**
```bash
$ python -m yoker --with some_plugin

Error: Plugin 'some_plugin' is not trusted.
Add to your yoker.toml:
  [plugins.trusted]
  some_plugin = true
```

**Interactive confirmation:**
```bash
$ python -m yoker --with some_plugin

Loading plugin: some_plugin
╔══════════════════════════════════════════════════════════╗
║ Plugin: some_plugin                                      ║
║                                                          ║
║ Tools:     tool1, tool2                                  ║
║ Skills:    skill1                                        ║
║ Agents:    agent1                                       ║
║                                                          ║
║ Plugins can execute code on your system.                 ║
║ Only load plugins you trust.                             ║
║                                                          ║
║ Load this plugin? [y/N]: _                               ║
╚══════════════════════════════════════════════════════════╝

Load this plugin? [y/N]: y
  Loaded plugin some_plugin: 2 tools, 1 skills, 1 agents
```

## Test Results

All tests pass:
- Plugin security tests: 22 passed
- Plugin integration tests: 10 passed
- Total: 1319 passed, 1 skipped

## Coverage

- `src/yoker/plugins/security.py`: 89% coverage
- Overall project: 83% coverage