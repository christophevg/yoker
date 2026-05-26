# Task 1.8: Config Auto-Discovery and Agent Definition Path

**Issue**: #7
**Date**: 2026-05-26
**Status**: Complete

## Summary

Implemented zero-configuration startup with automatic config discovery and agent definition path resolution.

## Changes

### Schema (`src/yoker/config/schema.py`)
- Added `definition: str = ""` field to `AgentsConfig` for explicit agent definition file path

### Loader (`src/yoker/config/loader.py`)
- Added `discover_config() -> tuple[Config, Path | None]` function
- Search order: `./yoker.toml` → `~/.yoker.toml` → `Config()` defaults
- Updated `_parse_agents()` to parse `definition` field
- Added structured logging for config discovery events

### Agent (`src/yoker/agent.py`)
- Updated `__init__()` to use `discover_config()` when no config/config_path provided
- Added agent definition resolution from `config.agents.definition`
- Added logging for config loading and agent definition resolution

### AgentCore (`src/yoker/base.py`)
- Updated to support auto-discovery
- Fixed logging duplication (only log when discovering, not when passed explicit config)

### Tests (`tests/test_config/test_discover_config.py`)
- 18 test methods covering:
  - Config discovery precedence (CWD → home → defaults)
  - Agent definition resolution from config
  - Edge cases (missing files, invalid TOML, etc.)

### Documentation
- Updated `README.md` with auto-discovery documentation
- Updated `docs/quickstart.md` with full search order
- Updated `examples/yoker.toml` with `agents.definition` field

## Resolution Order

### Config Resolution
1. Explicit `config` parameter → Use directly
2. Explicit `config_path` parameter → Load from path
3. Auto-discovery → Try `./yoker.toml`, `~/.yoker.toml`
4. Defaults → `Config()`

### Agent Definition Resolution
1. Explicit `agent_definition` parameter → Use directly
2. Explicit `agent_path` parameter → Load from path
3. `config.agents.definition` → Load if set and file exists
4. None → Default system prompt

## Backward Compatibility

All existing initialization patterns continue to work:
- `Agent(config=cfg)` - Uses explicit config
- `Agent(config_path=path)` - Loads from path
- `Agent()` - Auto-discovers config (NEW)

## Testing

- All 1064 tests pass
- Lint: clean
- Typecheck: clean

## Files Modified

- `src/yoker/config/schema.py`
- `src/yoker/config/loader.py`
- `src/yoker/config/__init__.py`
- `src/yoker/agent.py`
- `src/yoker/base.py`
- `tests/test_agent.py`
- `tests/test_agent_core.py`
- `tests/test_config/test_discover_config.py` (new)
- `README.md`
- `docs/quickstart.md`
- `examples/yoker.toml`
- `analysis/api-config-auto-discovery.md` (new)

## Related

- Issue: #7
- Design: `analysis/api-config-auto-discovery.md`