# Consensus: Read Tool Hardening (Task 2.3)

**Date**: 2026-04-28
**Agents**: api-architect, security-engineer
**Status**: Consensus Reached

---

## Consensus

Both domain agents agree on the core design approach and approve proceeding to implementation.

### Approved Design: Defense-in-Depth with Optional Guardrail

ReadTool shall accept an **optional `Guardrail` via `__init__`** and validate parameters in `execute()` when one is provided. `Agent.process()` continues to validate at the orchestration layer as the primary enforcement point. This provides standalone safety without duplicating the primary boundary.

**Rationale**: Relying solely on Agent.process() for security is insecure design (OWASP A06). Any direct invocation of tool.execute() bypasses all controls. Embedding the guardrail in the tool creates defense-in-depth.

---

## Design Decisions

### 1. Guardrail Injection Pattern

```python
class ReadTool(Tool):
  def __init__(self, guardrail: Guardrail | None = None) -> None:
    self._guardrail = guardrail

  def execute(self, **kwargs: Any) -> ToolResult:
    if self._guardrail is not None:
      validation = self._guardrail.validate(self.name, kwargs)
      if not validation.valid:
        return ToolResult(success=False, error=validation.reason)
    # proceed with read
```

Agent injects the guardrail when building the tool registry:
```python
guardrail = PathGuardrail(config)
registry.register(ReadTool(guardrail=guardrail))
```

### 2. Schema: No New Parameters

The `read` tool schema remains with only `path` (string, required). Extension filtering, size limits, and blocked patterns are policy concerns enforced by the guardrail, not tool interface parameters.

### 3. ListTool Consistency

ListTool shall be updated to match the same pattern (accept optional guardrail, validate in execute).

### 4. Additional Security Measures

Beyond the core guardrail integration, the following security hardening shall be applied:

| Priority | Measure | Rationale |
|----------|---------|-----------|
| HIGH | Stream-read with byte limit | Prevents size TOCTOU (file swapped between stat and read) |
| HIGH | Re-resolve path before read | Prevents symlink swap TOCTOU |
| HIGH | Reject symlinks by default | Prevents symlink traversal when guardrail bypassed |
| MEDIUM | Explicit UTF-8 encoding with replacement | Prevents decoding errors on binary files |
| LOW | Sanitize error messages | Prevents path information leakage to LLM |
| LOW | Add audit logging inside tool | Prevents repudiation if guardrail bypassed |

### 5. Test Strategy

Two test layers:

1. **Unit tests** (`tests/test_tools/test_read.py`) with a `FakeGuardrail` mock to test the integration pattern and error handling
2. **Integration tests** (`tests/test_tools/test_read_guardrail.py`) with real `PathGuardrail` to prove hardening works for traversal, blocked patterns, extension filtering, and size limits

### 6. What Is Out of Scope for This Task

The following security findings are deferred to future tasks:

- Changing default `filesystem_paths` from `(".",)` to `()` (requires broader config changes)
- Expanding default blocked patterns (config concern, not tool-specific)
- Full TOCTOU elimination via atomic open (platform-specific, complex)

---

## Agent Agreement

| Agent | Approved | Conditions |
|-------|----------|------------|
| api-architect | Yes | Guardrail optional in tool, primary enforcement stays in Agent |
| security-engineer | Yes | With additional security measures (stream-read, symlink check, encoding) |

---

## Next Steps

1. Enter Plan Mode and create detailed implementation plan
2. Implement ReadTool hardening per consensus design
3. Update ListTool to match pattern
4. Update Agent tool registry building to inject guardrails
5. Write unit and integration tests
6. Run review cycle
