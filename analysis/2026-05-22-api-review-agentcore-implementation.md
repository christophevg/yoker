# API Review: AgentCore Implementation (Task 1.7.1)

**Date**: 2026-05-22
**Reviewer**: API Architect Agent
**Task**: Code-level review of AgentCore implementation from API design perspective

## Summary

Reviewed the AgentCore implementation against the design document (`analysis/api-agentcore-extraction.md`). The implementation closely follows the design with minor deviations. Overall, the composition pattern is well-implemented and maintains backward compatibility.

**Decision**: APPROVED with minor recommendations

## Findings

### Strengths

1. **Composition Pattern Well-Implemented**: Agent properly delegates to AgentCore via `self._core`, maintaining clean separation of sync-specific and shared code.

2. **Property Delegations Complete**: All designed properties are correctly delegated:
   - `config`, `model`, `thinking_mode`, `agent_definition`, `tool_registry`, `context`, `command_registry`
   - `_recursion_depth`, `_max_recursion_depth` (internal)

3. **Backward Compatibility Maintained**: All public interfaces unchanged. Existing code will work without modification.

4. **Documentation Clear**: Both classes have comprehensive docstrings with warnings about internal use for AgentCore.

5. **Type Hints Complete**: All methods and properties properly typed.

6. **Security Validation Preserved**: `_validate_guardrails_enforced()` defense-in-depth check properly moved to AgentCore.

### Issues Found

#### Issue 1: Private Member Access via Property (Low Severity)

**Location**: `agent.py` lines 198-200

```python
@property
def _guardrail(self) -> "PathGuardrail":
  """Path guardrail for filesystem tool validation."""
  return self._core._guardrail
```

**Problem**: The property exposes `AgentCore._guardrail` (a private member) through another private property. While this works, it creates a chain of private member access.

**Recommendation**: This is acceptable for internal use. The double-underscore prefix on `_guardrail` in AgentCore and the property in Agent both indicate internal use. No change required.

**Severity**: Low - Acceptable for internal use

---

#### Issue 2: Inconsistent Event Handler Access (Low Severity)

**Location**: `agent.py` lines 187-189 vs line 232

**Problem**: The `_event_handlers` property exposes the list directly:
```python
@property
def _event_handlers(self) -> list[EventCallback]:
  return self._core._event_handlers
```

But `_emit()` uses the accessor method:
```python
def _emit(self, event: Event) -> None:
  for handler in self._core.get_event_handlers():
    handler(event)
```

**Analysis**: Both approaches work, but they have different semantics:
- `self._core._event_handlers` returns the actual list (allows mutation)
- `self._core.get_event_handlers()` returns a copy (read-only snapshot)

The `_emit()` correctly uses the copy, which prevents issues if handlers are removed during iteration.

**Recommendation**: This is actually correct design. The property provides direct access for internal use, while `_emit()` uses the safe copy. No change required.

**Severity**: Low - No action needed

---

#### Issue 3: AgentTool Registration Split (Informational)

**Location**: `agent_base.py` line 310 comment, `agent.py` lines 125-130

**Observation**: AgentTool registration is split between AgentCore (tool list) and Agent (actual registration with parent_agent reference):
```python
# In agent_base.py
tools: list[Tool] = [
  # ... other tools ...
  # AgentTool is added separately below (needs parent_agent reference)
]

# In agent.py
if "agent" in allowed_tools:
  self._core.tool_registry.register(AgentTool(guardrail=self._core._guardrail, parent_agent=self))
```

**Analysis**: This is correct design - AgentTool needs a reference to the parent Agent, which can only be provided after Agent is instantiated. The comment in agent_base.py documents this clearly.

**Severity**: N/A - Correct implementation

---

#### Issue 4: Client Initialization Before Config Loaded (Low Severity)

**Location**: `agent.py` lines 94-107

**Problem**: The sync client needs `base_url` from config, but config loading happens in AgentCore. The current implementation loads config twice:
```python
# Load config temporarily to get base_url
temp_config = config
if temp_config is None and config_path is not None:
  temp_config = load_config(config_path)
elif temp_config is None:
  temp_config = Config()
base_url = temp_config.backend.ollama.base_url
```

Then AgentCore loads config again.

**Analysis**: This is a minor inefficiency but necessary due to initialization order. The client must be created before AgentCore because AgentCore's tool building needs the client.

**Recommendation**: Acceptable for now. Could be optimized in a future iteration by accepting `base_url` as a constructor parameter, but not critical.

**Severity**: Low - Minor inefficiency, acceptable trade-off

---

#### Issue 5: AgentCore Exported Publicly (Design Decision Verified)

**Location**: `__init__.py` line 9, 61

```python
from yoker.agent_base import AgentCore
# ...
__all__ = [
  "Agent",
  "AgentCore",  # Internal: shared state for Agent variants
```

**Analysis**: The design document recommended Option 3 (Internal: Public but documented as internal-use-only). The implementation follows this with:
- Public export in `__all__`
- Clear comment marking it as internal
- Warning in AgentCore docstring

**Recommendation**: Correct implementation of design decision.

**Severity**: N/A - Follows design

## Compliance Check

### RESTful Design

N/A - This is a Python library, not an HTTP API.

### Async-First Architecture

**Status**: PREPARED

The implementation correctly separates:
- **Shared state** → `AgentCore` (sync/agnostic)
- **Sync client** → `Agent` (`ollama.Client`)
- **Async client** → Future `AsyncAgent` (`ollama.AsyncClient`)

This follows the async-first principle where the architecture is designed to support both sync and async from the start.

### Public API Stability

| Check | Status |
|-------|--------|
| All existing imports work | PASS |
| All property names unchanged | PASS |
| All method signatures unchanged | PASS |
| No breaking changes | PASS |
| `python -m yoker` works | PASS (verified in tests) |

### Documentation Completeness

| Check | Status |
|-------|--------|
| AgentCore class documented | PASS |
| AgentCore properties documented | PASS |
| AgentCore methods documented | PASS |
| Agent properties documented | PASS |
| Internal use warnings present | PASS |

## Interface Contract Verification

### AgentCore Public Interface

| Property | Expected | Actual | Status |
|----------|----------|--------|--------|
| `config` | `Config` | `Config` | PASS |
| `model` | `str` | `str` | PASS |
| `thinking_mode` | `ThinkingMode` | `ThinkingMode` | PASS |
| `agent_definition` | `AgentDefinition \| None` | `AgentDefinition \| None` | PASS |
| `tool_registry` | `ToolRegistry` | `ToolRegistry` | PASS |
| `context` | `ContextManager` | `ContextManager` | PASS |
| `command_registry` | `CommandRegistry \| None` | `CommandRegistry \| None` | PASS |
| `recursion_depth` | `int` | `int` | PASS |
| `max_recursion_depth` | `int` | `int` | PASS |

| Method | Expected | Actual | Status |
|--------|----------|--------|--------|
| `add_event_handler(handler)` | `None` | `None` | PASS |
| `remove_event_handler(handler)` | `None` | `None` | PASS |
| `get_event_handlers()` | `list[EventCallback]` | `list[EventCallback]` | PASS |

### Agent Public Interface

| Property | Delegates To | Status |
|----------|--------------|--------|
| `config` | `self._core.config` | PASS |
| `model` | `self._core.model` | PASS |
| `thinking_mode` | `self._core.thinking_mode` | PASS |
| `agent_definition` | `self._core.agent_definition` | PASS |
| `tool_registry` | `self._core.tool_registry` | PASS |
| `context` | `self._core.context` | PASS |
| `command_registry` | `self._core.command_registry` | PASS |
| `client` | `self._client` (sync-specific) | PASS |

| Method | Behavior | Status |
|--------|----------|--------|
| `add_event_handler()` | Delegates to core | PASS |
| `remove_event_handler()` | Delegates to core | PASS |
| `process()` | Sync implementation | PASS |
| `begin_session()` | Sync implementation | PASS |
| `end_session()` | Sync implementation | PASS |

## Future-Proofing Assessment

### AsyncAgent Support

The design correctly prepares for AsyncAgent:

| Requirement | Implementation | Ready |
|-------------|----------------|-------|
| Shared state in AgentCore | Yes - config, model, tools, etc. | YES |
| Sync client in Agent | Yes - `ollama.Client` | YES |
| Async client placeholder | N/A - AsyncAgent not yet implemented | N/A |
| Event emission separation | Yes - `_emit()` stays in Agent | YES |
| Tool registry shared | Yes - built in AgentCore | YES |

### Extensibility

| Feature | Status |
|---------|--------|
| AgentCore can be extended | Yes (public class) |
| Properties can be overridden | Yes (delegation pattern) |
| New tools can be added | Yes (ToolRegistry) |
| New event types can be added | Yes (Event system) |

## Recommendations

### Minor Improvements (Optional)

1. **Client initialization optimization**: Consider passing `base_url` to AgentCore's `__init__` to avoid double config loading. Not critical.

2. **Consider Protocol definition**: The design document mentions an optional `AgentProtocol` for type checking. Could be added in a future iteration for better IDE support.

### No Action Required

- Private member access is acceptable for internal use
- Event handler access patterns are correct
- AgentTool registration split is necessary and documented
- AgentCore export follows design decision

## Conclusion

**APPROVED**

The AgentCore implementation is well-designed and follows the architecture document closely. The composition pattern correctly separates shared state from sync/async-specific concerns. All public interfaces maintain backward compatibility.

Minor issues found are low severity and do not affect functionality or API stability. The implementation is ready for the next phase (AsyncAgent extraction).

## Next Steps

1. Proceed to Task 1.7.2 (Refactor Sync Agent) - already complete in current implementation
2. Proceed to Task 1.7.3 (Create AsyncAgent) when ready
3. Consider adding `AgentProtocol` in future iteration for better type checking

## Artifacts Reviewed

| File | Lines | Purpose |
|------|-------|---------|
| `/Users/xtof/Workspace/agentic/yoker/src/yoker/agent_base.py` | 376 | AgentCore class implementation |
| `/Users/xtof/Workspace/agentic/yoker/src/yoker/agent.py` | 565 | Refactored Agent with composition |
| `/Users/xtof/Workspace/agentic/yoker/src/yoker/__init__.py` | 113 | Public exports |