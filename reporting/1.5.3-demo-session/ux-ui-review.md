# UX Review: Task 1.5.3 - Update Demo Session Script

## Review Summary

**Status: Analysis Complete - Ready for Implementation**

This is a pre-implementation UX analysis. The task requires changes to tool display format and replay capabilities.

---

## Current State Analysis

### Tool Display Format

**Current Implementation** (`src/yoker/events/handlers.py` line 154):
```python
def _handle_tool_call(self, event: ToolCallEvent) -> None:
    if self.show_tool_calls:
        args_str = ", ".join(f"{k}={v!r}" for k, v in event.arguments.items())
        self.console.print(f"\n[Tool Call] {event.tool_name}({args_str})", style=TOOL_STYLE)
```

**Current Output**:
```
[Tool Call] read(file_path='/Users/xtof/Workspace/agentic/yoker/README.md')
```

**Style**: Yellow text (`Style(color="yellow")`)

### Visual Hierarchy Assessment

| Element | Current Style | Purpose |
|---------|--------------|---------|
| Session header | Bold cyan, green accents | Application info |
| User input | Bold blue `>` | User messages |
| Thinking | Gray/dim text | LLM reasoning |
| Content | Default console | Response text |
| Tool call | Yellow `[Tool Call] read(...)` | Tool execution |
| Session footer | Bold cyan | Completion status |

### Problems Identified

1. **Visual Noise**: `[Tool Call]` prefix adds unnecessary characters
2. **Verbosity**: Full path `/Users/xtof/...` is too long for scanning
3. **Inconsistent Capitalization**: `read` is lowercase, inconsistent with UI conventions
4. **Technical Focus**: Shows implementation details over user intent

---

## UX Recommendations

### Recommended Format

```
Read tool: README.md
```

**Changes**:
1. Remove `[Tool Call]` prefix
2. Capitalize tool name: `read` → `Read`
3. Show filename only: `/full/path/to/README.md` → `README.md`
4. Change color from yellow to cyan

### Color Recommendation

**Current**: Yellow (`TOOL_STYLE = Style(color="yellow")`)

**Recommended**: Cyan (`Style(color="cyan")`)

**Rationale**:
- Cyan matches session header styling for consistency
- Provides visual connection to application branding
- Yellow is typically used for warnings in terminal UIs
- Cyan distinguishes tool calls from thinking (gray) and content (default)

### Implementation

```python
def _handle_tool_call(self, event: ToolCallEvent) -> None:
    """Handle tool call event."""
    if self.show_tool_calls:
        from pathlib import Path

        if event.tool_name == "read" and "file_path" in event.arguments:
            filepath = Path(event.arguments["file_path"])
            self.console.print(
                f"\nRead tool: {filepath.name}",
                style=Style(color="cyan")
            )
        else:
            # Fallback for other tools
            self.console.print(
                f"\n{event.tool_name.title()} tool: ...",
                style=Style(color="cyan")
            )
```

### Extensibility

For future tools:

| Tool | Display Format |
|------|----------------|
| read | `Read tool: filename.md` |
| write | `Write tool: config.yaml` |
| glob | `Glob tool: **/*.py` |
| grep | `Grep tool: pattern` |

---

## Replay Capabilities Assessment

### Current Limitations

**session.jsonl format**:
```json
{"role": "user", "content": "Summarize README.md"}
{"role": "assistant", "content": "Yoker is a Python agent harness..."}
```

**Missing**:
- Command executions (`/help`, `/think on|off`)
- Thinking events
- Tool call events
- Session metadata

**Impact**: Replay mode cannot reproduce thinking output styling, tool call formatting, or event-based visual structure.

### Current MockAgent Behavior

```python
class MockAgent:
    def process(self, message: str) -> str:
        """Return next response from the log."""
        if self.index >= len(self.responses):
            return ""
        response = self.responses[self.index]
        self.index += 1
        return response
```

**Problems**:
- Returns plain string, not events
- Bypasses `ConsoleEventHandler`
- No thinking/tool call rendering

### Requirements for Full Replay

To achieve "same visual output as live session":

1. **Event-Based Logging Format**:
```jsonl
{"event": "SESSION_START", "model": "llama3.2", "thinking_enabled": true}
{"event": "TURN_START", "message": "Summarize README.md"}
{"event": "THINKING_START"}
{"event": "THINKING_CHUNK", "text": "Let me read..."}
{"event": "THINKING_END"}
{"event": "TOOL_CALL", "tool_name": "read", "arguments": {...}}
{"event": "TOOL_RESULT", "result": "..."}
{"event": "CONTENT_START"}
{"event": "CONTENT_CHUNK", "text": "Yoker is..."}
{"event": "CONTENT_END"}
{"event": "TURN_END"}
```

2. **Event-Based Replay Agent**:
   - Read events from JSONL
   - Emit events to `ConsoleEventHandler`
   - Produce identical visual output

---

## Implementation Phases

### Phase 1: Tool Display Fix (Immediate)

**Priority**: High

**Scope**:
- Update `_handle_tool_call` in `handlers.py`
- Change format and color
- Keep existing logging/replay

**Files**:
- `src/yoker/events/handlers.py`

**Risk**: Low - visual only, no functional changes

### Phase 2: Event Logging (Future)

**Priority**: Medium

**Scope**:
- Create `EventLogger` class
- Log all events to JSONL
- Update demo script

**Files**:
- New: `src/yoker/events/logging.py`
- Update: `scripts/demo_session.py`

**Dependencies**: Event system architecture

### Phase 3: Event Replay (Future)

**Priority**: Medium

**Scope**:
- Create `EventReplayAgent`
- Emit events from JSONL log
- Full visual fidelity

**Files**:
- Update: `scripts/demo_session.py`

**Dependencies**: Phase 2 complete

---

## Acceptance Criteria

### Phase 1: Tool Display

- [ ] Tool calls display as `Read tool: <filename>`
- [ ] Tool name is capitalized
- [ ] Color is cyan (matches session header)
- [ ] Filename only shown (not full path)
- [ ] Output on separate line with preceding newline
- [ ] Works for all tool types

### Phase 2: Event Logging (Future)

- [ ] JSONL logs all event types
- [ ] Events include all necessary metadata
- [ ] Backward compatible with existing format

### Phase 3: Event Replay (Future)

- [ ] Replay produces identical visual output
- [ ] Commands are preserved
- [ ] Thinking output is preserved
- [ ] Tool calls are preserved
- [ ] No LLM calls required

---

## Manual Testing

### Tool Display Verification

1. Start yoker: `python -m yoker`
2. Enable thinking: `/think on`
3. Send message: "Summarize the README.md file"
4. Verify tool call shows as: `Read tool: README.md` (cyan)
5. Verify no `[Tool Call]` prefix
6. Verify filename only (not full path)

### Visual Consistency Check

Compare styling:
- Session header: cyan/bold
- User input: blue/bold `>`
- Thinking: gray/dim
- Tool call: cyan (should match header)
- Content: default

### Replay Testing (After Phase 2)

1. Run: `python scripts/demo_session.py --log`
2. Run: `python scripts/demo_session.py --replay`
3. Compare outputs - should be identical

---

## Documentation Updates

After implementation, update:

1. **README.md**: Add example of tool display output
2. **CLAUDE.md**: Note tool display format in current state
3. **Session screenshot**: Regenerate with new format

---

## Summary

**Immediate Action Required**:
1. Update `_handle_tool_call` method in `handlers.py`
2. Change format from `[Tool Call] read(file_path='/path')` to `Read tool: filename`
3. Change color from yellow to cyan

**Future Work**:
1. Implement event-based logging system
2. Create event-based replay agent
3. Enable full visual fidelity in replay mode

**Analysis Document**: `analysis/ux-demo-session.md`

**Task Update**: TODO.md updated with refined acceptance criteria and new task 1.5.4 for event logging system.