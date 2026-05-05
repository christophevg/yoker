# Consensus Report: Write/Update Tool Content Display

**Task**: 1.5.5 - Show Write/Update Tool Content in CLI
**Date**: 2026-05-05
**Analysts**: c3:api-architect, c3:ui-ux-designer

## Summary

Both domain analysts agree on the core approach for displaying file content during write and update operations. The design uses a new event type for content display, configuration for verbosity control, and keeps display logic in event handlers.

## Agreed Approach

### 1. Event System: New ToolContentEvent

**Consensus**: Create a separate `ToolContentEvent` type (not extending existing events).

**Rationale**:
- Keeps content display optional
- Doesn't break existing event handlers
- Clean separation between result and content
- Aligns with event-driven architecture

**Implementation**:
```python
@dataclass(frozen=True)
class ToolContentEvent(Event):
  tool_name: str
  operation: str  # "write", "replace", "insert_before", etc.
  path: str
  content_type: str  # "full", "diff", "summary"
  content: str | None = None
  metadata: dict[str, Any] = field(default_factory=dict)
```

### 2. Configuration: ContentDisplayConfig

**Consensus**: Add new configuration section with three verbosity levels.

**Configuration Fields**:
- `verbosity`: "silent" | "summary" | "content"
- `max_content_lines`: int = 50
- `max_content_bytes`: int = 4096
- `show_diff_for_updates`: bool = True
- `max_diff_lines`: int = 30

**Default**: `verbosity = "summary"` (balance between information and noise)

### 3. Content Emission: ToolResult Metadata

**Consensus**: Tools return content metadata in ToolResult, Agent checks and emits ToolContentEvent.

**Implementation**:
```python
# In WriteTool/UpdateTool
return ToolResult(
  success=True,
  result="File written successfully",
  content_metadata={
    "operation": "write",
    "path": str(resolved),
    "content_type": "full",
    "content": truncated_content,
    "metadata": {"lines": len(lines)}
  }
)

# In Agent.process()
if tool_result.content_metadata:
  self._emit(ToolContentEvent(..., **tool_result.content_metadata))
```

### 4. Display Logic: ConsoleEventHandler

**Consensus**: Display formatting happens in ConsoleEventHandler, not in tools.

**Methods**:
- `_handle_tool_content(event: ToolContentEvent)`
- `_show_full_content(event)`
- `_show_diff_content(event)`
- `_show_summary(event)`

**Visual Consistency**:
- Cyan color for tool name (matches Read tool)
- Filename only (not full path)
- Success/failure indicator (✓/✗)
- Truncation with "... N more lines"

## Verbosity Levels

### Silent Mode
```
Write tool: example.py
  ✓ Success
```

### Summary Mode (Default)
```
Write tool: example.py
  Creating new file (24 lines)
  ✓ Success
```

```
Update tool: example.py
  Replace at line 15: "old text" → "new text"
  ✓ Success
```

### Content Mode
```
Write tool: example.py
  Creating new file:
  1: """Module docstring."""
  2: 
  3: def hello():
  4:     print("Hello, world!")
  ... (20 more lines)
  ✓ Success
```

```
Update tool: example.py
  Replace operation:
  - "print('hello')"
  + "print('Hello, World!')"
  ✓ Success
```

## Edge Cases

| Case | Handling |
|------|----------|
| Large files | Truncate with "... N more lines" |
| Binary files | Show size only (e.g., "245 KB binary") |
| Empty files | Show "(0 lines, empty)" |
| Unicode issues | Replace invalid bytes (handled by tools) |

## Implementation Plan

### Phase 1: Core Infrastructure
1. Add `ToolContentEvent` to `src/yoker/events/types.py`
2. Add `ContentDisplayConfig` to `src/yoker/config/schema.py`
3. Add `content_metadata` field to `ToolResult` in `src/yoker/tools/base.py`
4. Add `EventType.TOOL_CONTENT` to enum

### Phase 2: Tool Changes
1. Update `WriteTool.execute()` to include content metadata
2. Update `UpdateTool.execute()` to track old/new content and generate diff
3. Add `_truncate_content()` helper methods
4. Add `_generate_diff()` helper to UpdateTool

### Phase 3: Agent Integration
1. Update `Agent.process()` to check for `content_metadata`
2. Emit `ToolContentEvent` after `ToolResultEvent` when metadata present

### Phase 4: Console Handler
1. Add `_handle_tool_content()` to `ConsoleEventHandler`
2. Add `_show_full_content()` and `_show_diff_content()` methods
3. Add syntax highlighting support (Rich Syntax)
4. Add truncation indicators

### Phase 5: Testing
1. Unit tests for `ToolContentEvent` creation
2. Unit tests for content truncation logic
3. Unit tests for diff generation
4. Integration tests for event emission
5. Visual tests for console output

### Phase 6: Documentation
1. Update README.md with display configuration
2. Add demo scripts for write/update content display
3. Generate screenshots for documentation

## Files to Modify

| File | Changes |
|------|---------|
| `src/yoker/events/types.py` | Add `ToolContentEvent`, `EventType.TOOL_CONTENT` |
| `src/yoker/config/schema.py` | Add `ContentDisplayConfig`, update `ToolsConfig` |
| `src/yoker/tools/base.py` | Add `content_metadata` to `ToolResult` |
| `src/yoker/tools/write.py` | Add content metadata emission |
| `src/yoker/tools/update.py` | Add diff tracking and content metadata |
| `src/yoker/events/handlers.py` | Add `_handle_tool_content()` and display methods |
| `src/yoker/agent.py` | Check for content metadata and emit events |
| `tests/test_events/` | Add tests for content events and formatting |
| `README.md` | Document display configuration |
| `CLAUDE.md` | Update current state |

## Acceptance Criteria

- [ ] Write tool displays content with configurable verbosity
- [ ] Update tool displays diffs for changes
- [ ] Three verbosity levels work correctly (silent/summary/content)
- [ ] Large files truncated with "... N more lines"
- [ ] Binary files show size only
- [ ] Empty files show "(0 lines, empty)"
- [ ] Visual consistency with Read tool (cyan color, filename)
- [ ] All tests pass (unit, integration, visual)
- [ ] Documentation updated

## Risk Assessment

**Low Risk**: This is a pure addition with no breaking changes.

- New event type is optional (existing handlers ignore it)
- Configuration defaults preserve current silent behavior
- Tools that don't set `content_metadata` work unchanged

## Timeline Estimate

- Configuration: 1 hour
- Event types: 30 minutes
- Tool changes: 2 hours
- Agent integration: 1 hour
- Console handler: 2-3 hours
- Tests: 2 hours
- Documentation: 1 hour

**Total**: 9.5-10.5 hours

## Approval

✅ **c3:api-architect**: Recommends Option A (ToolContentEvent) with metadata emission
✅ **c3:ui-ux-designer**: Recommends Option B (Add Content to Events) with DisplayConfig

**Consensus Reached**: Both analysts agree on the core design with minor naming variations. The approach satisfies both backend (clean event architecture) and frontend (user-controllable display) requirements.