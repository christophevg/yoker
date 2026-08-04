# Bug: Agent Tool Namespacing — Builtin Tools Lost for Collection-Loaded Agents

## Date
2026-07-12

## Problem

When the C3 project-manager agent spawns a release-manager sub-agent, the
release-manager only has access to `agent` and `send_message` tools — none
of its declared tools (`read`, `list`, `search`, `write`, `update`, `git`,
`github`, `make`, `skill`) are available.

## Root Cause

The bug is in `_namespace_tools()` in `src/yoker/agents/loader.py`.

When agent definitions are loaded from a config directory (e.g.
`[agents] directories = ["./agents"]`), `load_agent_definitions` defaults
the namespace to the directory name (e.g. `"agents"`). The
`_namespace_tools` function then prefixes all bare tool names with that
namespace: `read` → `agents:read`, `git` → `agents:git`, etc.

But the actual builtin tools are registered under the `yoker` namespace:
`yoker:read`, `yoker:git`, etc. At runtime, `_filter_tools_by_definition`
checks namespaced names exactly — `agents:read` ≠ `yoker:read` — so all
requested tools are removed from the registry. The Session then injects
`yoker:agent` and `yoker:send_message`, which become the only tools the
spawned agent sees.

### Affected Paths

1. **Config directory agents** (`[agents] directories`): namespace
   defaults to directory name (e.g. `"agents"`) — all builtin tool
   references broken.
2. **Single-file agents** (`agent_path`): namespace is `"file"` — same
   bug for any builtin tool referenced with a bare name.
3. **Plugin agents**: namespace is the package name — same bug for
   builtin tools referenced with bare names.

### Unaffected

- In-memory `AgentDefinition(tools=["read"])` — no namespacing applied,
  the runtime `_filter_tools_by_definition` handles bare names by also
  trying `yoker:` prefix.
- Explicitly `yoker:`-prefixed tools in definitions (e.g. `yoker:read`)
  — preserved as-is by `_namespace_tools`.

## Fix

Added a `_YOKER_BUILTIN_TOOLS` frozenset to `loader.py` containing all
known yoker builtin tool simple names. Modified `_namespace_tools` to
check: when a bare tool name matches a known yoker builtin, prefix it
with `yoker:` instead of the collection namespace. Non-builtin bare
names still get the collection namespace (for plugin-specific tools).

### Files Changed

- `src/yoker/agents/loader.py` — added `_YOKER_BUILTIN_TOOLS` set and
  new branch in `_namespace_tools`.
- `tests/agents/test_loader.py` — updated 4 assertions from
  `file:<Tool>` / `agents:<Tool>` to `yoker:<Tool>`.
- `tests/core/test_agent_tools.py` — updated 1 assertion from
  `file:read` to `yoker:read`.
- `tests/test_agent.py` — updated 1 assertion from `file:read` to
  `yoker:read`.
- `tests/test_plugin_agent_tool_namespacing.py` — updated 2 assertions
  from `examples.plugins.demo:write` / `yoker_plugin_demo:read` to
  `yoker:write` / `yoker:read`.

## Verification

All 2366 tests pass.