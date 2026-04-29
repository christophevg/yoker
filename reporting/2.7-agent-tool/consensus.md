# Consensus Report: Agent Tool (Task 2.7)

**Date**: 2026-04-29
**Task**: 2.7 Agent Tool
**Status**: Consensus Reached

## Domain Agents Consulted

| Agent | Document | Status |
|-------|----------|--------|
| c3:api-architect | `analysis/api-agent-tool.md` | ✅ Approved |
| c3:security-engineer | `analysis/security-agent-tool.md` | ✅ Approved |

## Key Design Decisions (Agreed)

### 1. Tool API

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `agent_path` | string | Yes | - | Path to agent definition file |
| `prompt` | string | Yes | - | Task/question for subagent |
| `timeout_seconds` | integer | No | 300 | Max execution time |

### 2. Recursion Depth Tracking

- **Internal state**: Not exposed to LLM
- **Default limit**: 3 levels
- **Enforcement**: Check before spawn, return error if exceeded
- **Configuration**: `max_recursion_depth` in harness config

### 3. Timeout Enforcement

- **Default**: 300 seconds (5 minutes)
- **Maximum**: 3600 seconds (1 hour)
- **Implementation**: signal.SIGALRM (Unix), threading fallback
- **Error handling**: Return ToolResult with timeout error

### 4. Context Isolation

- **Fresh context**: Each subagent gets empty context
- **Session ID**: `{parent_session}_sub_{depth}`
- **Storage**: Separate subdirectory per subagent
- **No leakage**: Parent messages not visible to child

### 5. Permission Inheritance

- **Model**: Restrictive (child permissions ⊆ parent permissions)
- **Tool filtering**: Subagent only has tools from its definition
- **Subset enforcement**: Child tools must be subset of parent's

### 6. Result Handling

- **Size limit**: 100KB recommended
- **Sanitization**: Remove potential injection markers
- **Truncation**: Clear marker when limit exceeded

## Security Recommendations (from Security Review)

| Priority | Finding | Status |
|----------|---------|--------|
| P0 | Recursion depth enforcement | Agreed - implement RecursionGuard |
| P0 | Timeout enforcement | Agreed - multi-layer timeout |
| P0 | Context isolation | Agreed - UUID-based storage |
| P1 | Permission inheritance | Agreed - restrictive model |
| P1 | Result size limits | Agreed - 100KB limit |

## Implementation Requirements

### Files to Create

| File | Description |
|------|-------------|
| `src/yoker/tools/agent.py` | AgentTool implementation |
| `tests/test_tools/test_agent.py` | Unit tests |

### Files to Modify

| File | Changes |
|------|---------|
| `src/yoker/agent.py` | Add `_recursion_depth`, `_max_recursion_depth` |
| `src/yoker/config/schema.py` | Add `max_recursion_depth` to harness config |
| `src/yoker/tools/__init__.py` | Export AgentTool, update create_default_registry |

### Test Coverage Required

- Recursion depth enforcement
- Timeout handling
- Context isolation
- Agent definition loading
- Error handling

## No Conflicts

Both domain agents agree on all core design decisions. Security recommendations have been incorporated into the API design.

## Next Step

Proceed to **Phase 4: Implementation** with c3:python-developer.