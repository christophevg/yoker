# UX Analysis: Demo Session Tool Display

## Task Context

**Task 1.5.3**: Update demo session script to improve tool display formatting and replay capabilities.

## Current Implementation Analysis

### Tool Display Format

**Current Output** (from `handlers.py` line 154):
```
[Tool Call] read(file_path='/Users/xtof/Workspace/agentic/yoker/README.md')
```

**Style**: Yellow text on its own line, prefixed with `[Tool Call]`

### Visual Hierarchy Analysis

The current output has these elements:

| Element | Style | Purpose |
|---------|-------|---------|
| Session header | Bold cyan, green accents | Application info |
| User input | Bold blue `>` | User messages |
| Thinking | Gray/dim text | LLM reasoning |
| Content | Default console | Response text |
| Tool call | Yellow | Tool execution |
| Session footer | Bold cyan | Completion status |

### Problems with Current Format

1. **Visual Noise**: The `[Tool Call]` prefix adds visual clutter
2. **Verbosity**: Full argument representation `file_path='/path/to/file'` is verbose
3. **Inconsistent Capitalization**: `read` is lowercase (tool name), while other elements use title case
4. **Technical Focus**: Format emphasizes implementation details over user understanding

## UX Requirements

### User Expectations for Tool Display

1. **Clarity (Critical)**
   - User needs to understand what action is being performed
   - Technical details should be secondary to intent
   - Reading paths should be scannable at a glance

2. **Consistency (High)**
   - Tool display should match styling of other output elements
   - Consistent capitalization and formatting
   - Visual weight appropriate to importance

3. **Signal-to-Noise Ratio (High)**
   - Show essential information prominently
   - Reduce visual clutter from implementation details
   - Distinguish between different tools meaningfully

### Design Recommendations

#### Option A: Action-First Format (Recommended)

```
Read tool: README.md
```

**Rationale**:
- Action-oriented: "Read" is what's happening
- File-focused: Shows just the filename, not full path
- Clean: Minimal punctuation, no brackets
- Matches command-style output pattern

**Style Suggestions**:
- Use cyan or blue for tool name (matches action-oriented headers)
- Use default style for file path
- Indent slightly if needed for visual separation

#### Option B: Hierarchical Format

```
> Reading: README.md
```

**Rationale**:
- Uses `>` prefix to match user input style
- Present tense verb indicates ongoing action
- Filename focus

**Concern**: The `>` prefix is currently used for user input, may cause confusion

#### Option C: Minimal Format

```
Reading README.md...
```

**Rationale**:
- Simple, conversational
- Ellipsis indicates in-progress action

**Concern**: May blend too much with thinking output

### Recommended Implementation

**Format**: `Read tool: <filename>`

**Style Options**:

```python
# Option 1: Cyan tool name (matches session header style)
self.console.print(f"\nRead tool: {filename}", style=Style(color="cyan"))

# Option 2: Bold default (matches user input weight)
self.console.print(f"\nRead tool: {filename}", style=Style(bold=True))

# Option 3: Keep yellow but simplify (current color, new format)
self.console.print(f"\nRead tool: {filename}", style=TOOL_STYLE)
```

**Recommendation**: Option 1 (cyan) - provides visual connection to session header while distinguishing from content.

### Argument Display

For tools with multiple arguments, prioritize:

1. **Primary argument** (path, query, content) - always shown
2. **Secondary arguments** (line numbers, offsets) - shown when relevant
3. **Tertiary arguments** (flags, options) - hidden unless verbose mode

**Example for Read tool**:
```
Read tool: README.md
```

**Example for Write tool** (future):
```
Write tool: config.yaml
```

**Example for complex arguments** (if needed):
```
Read tool: README.md (lines 1-50)
```

## Replay Capabilities Analysis

### Current Limitations

The `session.jsonl` format only captures:
```json
{"role": "user", "content": "..."}
{"role": "assistant", "content": "..."}
```

**Missing elements**:
- Command executions (`/help`, `/think on|off`)
- Thinking events (reasoning traces)
- Tool call events
- Timing/metadata

### Impact on Replay

Current `MockAgent`:
1. Loads only user/assistant messages from JSONL
2. Returns assistant response as plain string
3. Does NOT emit events
4. Bypasses `ConsoleEventHandler` entirely

This means replay mode cannot reproduce:
- Thinking output styling
- Tool call formatting
- Event-based visual structure

### Enhanced Replay Requirements

To achieve "same visual output as live session", replay needs:

1. **Full Event Log Format**
   ```jsonl
   {"event": "SESSION_START", "model": "...", "thinking_enabled": true}
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
   {"event": "SESSION_END", "reason": "quit"}
   ```

2. **Event-Based Replay Agent**
   - Read events from JSONL
   - Emit same events as live session
   - Use same `ConsoleEventHandler`
   - Produce identical visual output

3. **Command Preservation**
   - Log command invocations
   - Replay command results from log
   - Maintain visual consistency

### Implementation Recommendations

#### Phase 1: Tool Display Fix (Immediate)

**Files to modify**:
- `src/yoker/events/handlers.py` - Update `_handle_tool_call` method

**Changes**:
```python
def _handle_tool_call(self, event: ToolCallEvent) -> None:
    """Handle tool call event."""
    if self.show_tool_calls:
        # Extract primary argument
        if event.tool_name == "read" and "file_path" in event.arguments:
            filepath = Path(event.arguments["file_path"])
            self.console.print(
                f"\nRead tool: {filepath.name}",
                style=Style(color="cyan")
            )
        else:
            # Fallback for other tools
            args_str = ", ".join(f"{k}={v!r}" for k, v in event.arguments.items())
            self.console.print(
                f"\n{event.tool_name.title()} tool: {args_str}",
                style=Style(color="cyan")
            )
```

#### Phase 2: Event Logging (Future)

**New logging format**:
- Create `EventLogger` class similar to `ConversationLogger`
- Log all events with their data
- Enable full replay capability

**Files to create**:
- `src/yoker/events/logging.py` - EventLogger class
- Update `scripts/demo_session.py` to use event logging

#### Phase 3: Event Replay (Future)

**New replay mechanism**:
- Create `EventReplayAgent` that emits events from log
- Use same `ConsoleEventHandler`
- Produce identical visual output

**Files to create**:
- Update `scripts/demo_session.py` with `EventReplayAgent`

## Acceptance Criteria

### Tool Display (Immediate)

- [ ] Tool calls display as `Read tool: <filename>` format
- [ ] Tool name uses cyan color (matches session header)
- [ ] Filename-only display (not full path)
- [ ] Tool display is on separate line with preceding newline
- [ ] Format works for all tool types (extensible)

### Replay Mode (Future)

- [ ] JSONL logs all event types
- [ ] Replay produces identical visual output to live session
- [ ] Commands are logged and replayed
- [ ] Thinking output is preserved in replay
- [ ] Tool calls are preserved in replay
- [ ] No LLM calls required in replay mode

## Testing

### Manual Testing - Tool Display

1. Start yoker: `python -m yoker`
2. Enable thinking: `/think on`
3. Send message requiring file read: "Summarize the README.md file"
4. Verify tool call shows as: `Read tool: README.md`
5. Verify color is cyan (matches session header)
6. Verify no `[Tool Call]` prefix
7. Verify no full path shown

### Visual Consistency Check

Compare tool display styling with:
- Session header: `[bold cyan]Yoker v0.1.0[/]`
- User input: `[bold blue]>[/]`
- Thinking: `[dim]` gray text
- Content: Default console

Tool display should be visually distinct but harmonious.

### Replay Testing (After Phase 2)

1. Run demo with logging: `python scripts/demo_session.py --log`
2. Run replay: `python scripts/demo_session.py --replay`
3. Compare outputs - should be visually identical
4. Verify thinking output appears in replay
5. Verify tool calls appear in replay

## Migration Notes

### Breaking Changes

None - this is purely visual improvement.

### Backward Compatibility

- Existing `session.jsonl` files will still work with current replay
- Enhanced logging will be opt-in (new flag)
- Old replay mode will continue to work

## Summary

**Immediate Priority**: Fix tool display format to be cleaner and more user-friendly.

**Recommended Change**:
- Replace `[Tool Call] read(file_path='/path/to/file')`
- With `Read tool: README.md`
- Use cyan color for visual consistency

**Future Work**: Implement full event logging and replay to preserve visual fidelity.

**Files to Modify**:
1. `src/yoker/events/handlers.py` - Update `_handle_tool_call` method
2. `scripts/demo_session.py` - Add event logging (Phase 2)

**Impact**: Improves readability and visual consistency without breaking existing functionality.