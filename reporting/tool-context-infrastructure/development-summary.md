# ToolContext Infrastructure Implementation Summary

## Overview

Successfully created the `ToolContext` infrastructure to support injecting configuration and backends into tool functions that require them.

## What Was Implemented

### 1. Created `src/yoker/tools/context.py`

A new module containing the `ToolContext` dataclass:

```python
@dataclass
class ToolContext:
  """Execution context for tools.

  Injected into tool functions that have a `ctx: ToolContext` parameter.
  Provides tool-specific config, shared settings, and backends.
  """
  config: ToolConfig | None  # Tool-specific config (WriteToolConfig, etc.) or None
  shared: ToolSharedConfig    # content_display, etc.
  backends: dict[str, Any]    # {"websearch": OllamaWebSearchBackend, ...}
```

### 2. Updated `src/yoker/tools/__init__.py`

Added `ToolContext` to the public exports:

```python
from yoker.tools.context import ToolContext

__all__ = [
  ...
  "ToolContext",
  ...
]
```

### 3. Updated `src/yoker/agent/_processing.py`

Added context detection and injection logic:

- **Import**: Added `ToolContext` import
- **Detection**: Added `_tool_needs_context(spec)` function to check if a tool expects a `ctx` parameter
- **Building**: Added `_build_tool_context(agent, tool_name)` function to construct the context
- **Injection**: Modified `_run_tool()` to inject context when needed:

```python
async def _run_tool(agent: Any, tool_name: str, tool_args: dict[str, Any]) -> tuple[str, bool, Any]:
  ...
  # Check if tool expects ToolContext parameter
  kwargs = tool_args.copy()
  if _tool_needs_context(spec):
    ctx = _build_tool_context(agent, tool_name)
    kwargs["ctx"] = ctx
  tool_result = await spec.execute(**kwargs)
  ...
```

### 4. Updated `src/yoker/agent/__init__.py`

Added backends dictionary to Agent class:

```python
# tool backends for context injection (populated when tools are registered)
self._tool_backends: dict[str, Any] = {}
```

Also added `Any` import to support the type annotation.

## Files Modified

1. **Created**: `src/yoker/tools/context.py` - New ToolContext dataclass
2. **Modified**: `src/yoker/tools/__init__.py` - Export ToolContext
3. **Modified**: `src/yoker/agent/_processing.py` - Context detection and injection
4. **Modified**: `src/yoker/agent/__init__.py` - Added _tool_backends attribute

## Design Decisions

### Minimal Injection Approach

- Tools **without** a `ctx` parameter work exactly as before (no overhead)
- Tools **with** a `ctx` parameter automatically receive it
- Detection is done via `inspect.signature()` on the tool's callable
- Context is built lazily only when needed

### Namespace Handling

The `_build_tool_context` function extracts the base tool name from namespaced names:

```python
base_name = tool_name.split(":")[-1] if ":" in tool_name else tool_name
```

For example:
- `"yoker:write"` → `"write"` → `config.tools.write`
- `"websearch"` → `"websearch"` → `config.tools.websearch`

### Backends Placeholder

The `_tool_backends` dict is initialized as empty in Agent. It will be populated when websearch/webfetch tools are registered (separate concern).

### Type Safety

- Full type annotations on `ToolContext`
- TYPE_CHECKING imports for forward references
- Mypy type checking passes without errors

## Verification

All quality checks passed:

1. **Import verification**: Both `from yoker.tools.context import ToolContext` and `from yoker.tools import ToolContext` work
2. **Context creation**: ToolContext can be instantiated with real config objects
3. **Agent attribute**: Agent class has `_tool_backends` attribute
4. **Linter**: Ruff checks pass (fixed `Any` import and formatting)
5. **Type checker**: MyPy type checking passes

## Current State

The infrastructure is now in place for tools to receive configuration and backends via injection. Tools can opt-in by adding a `ctx: ToolContext` parameter to their function signature.

**Next steps** (not in this task):
- Populate `_tool_backends` when websearch/webfetch tools are registered
- Update websearch/webfetch tools to use ToolContext instead of receiving backends at factory time
- Create `yoker.agent.tools.build_tool_registry` to register built-in tools with backends

## Important Notes

- **No tool implementations were changed** - This was infrastructure only
- **Tests were already failing** before these changes (unrelated to ToolContext)
- **Backward compatible** - Existing tools continue to work without modification