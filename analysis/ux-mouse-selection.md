# UX Analysis: Mouse Selection in Interactive Mode

## Task Context

**Task 1.5.2**: Fix mouse selection in terminal output area (scrollback buffer) and input area.

## Current Implementation Analysis

### Architecture Overview

The yoker TUI has a split architecture:

1. **Input Layer** (`prompt_toolkit` in `__main__.py`)
   - Uses `PromptSession` with `mouse_support=True` (line 72)
   - Multiline input with custom keybindings
   - History navigation and search

2. **Output Layer** (`Rich Console` in `events/handlers.py`)
   - `ConsoleEventHandler` renders events to stdout
   - No buffer management - prints directly to terminal
   - Styled output with colors and formatting

### Mouse Support Configuration

```python
# From __main__.py line 69-74
session: PromptSession[str] = PromptSession(
  history=FileHistory(str(HISTORY_FILE)),
  multiline=True,
  mouse_support=True,  # <-- This is the problem area
  key_bindings=kb,
)
```

### Root Cause Analysis

The `mouse_support=True` parameter in `prompt_toolkit` has specific behavior:

1. **What it enables**: Mouse click to position cursor in the input buffer
2. **What it interferes with**: Terminal-native mouse selection (click-drag to select text)
3. **Why**: `prompt_toolkit` captures mouse events globally when the prompt is active

### The UX Problem

When `mouse_support=True` is enabled:

- **Input area**: Mouse clicks work for cursor positioning, but selection behavior may be inconsistent
- **Output area (scrollback)**: Terminal-native selection is blocked because `prompt_toolkit` intercepts mouse events
- **Copy/paste workflow**: Users cannot select previous output text to copy

This violates user expectations for terminal applications where:
- Click and drag should select text
- Selected text should be copyable (via Ctrl+Shift+C, Cmd+C, or right-click)
- Selection should show visual highlight

## UX Requirements

### User Expectations

1. **Text Selection in Output (Critical)**
   - Users expect to select any previously output text
   - Common use case: Copy code snippets, file paths, or responses
   - Should work with standard terminal selection (click-drag)

2. **Text Selection in Input (Important)**
   - Users may want to select part of their input to delete or modify
   - Cursor positioning via mouse click is useful
   - Selection within input buffer should work

3. **No Unexpected Behavior (Critical)**
   - Mouse interactions should be predictable
   - No interference with keyboard navigation
   - No conflicts with terminal emulator features

### Priority Matrix

| Feature | Priority | Current State | Target State |
|---------|----------|---------------|--------------|
| Select output text | Critical | Broken | Working |
| Copy selected text | Critical | Broken | Working |
| Click to position cursor | High | Working | Working |
| Select input text | Medium | Inconsistent | Working |

## Recommendations

### Option 1: Disable mouse_support (Recommended)

Set `mouse_support=False` in `PromptSession` creation.

**Pros:**
- Restores native terminal selection behavior immediately
- No changes to existing keybindings
- Users can select and copy any text
- Minimal code change

**Cons:**
- Loses click-to-position-cursor feature in input
- Users must use keyboard for cursor movement

**UX Impact:**
- Most terminal users are keyboard-focused anyway
- Keyboard navigation (arrows, Ctrl+A, Ctrl+E) still works
- Selection/copy is more valuable than mouse cursor positioning

**Implementation:**
```python
session: PromptSession[str] = PromptSession(
  history=FileHistory(str(HISTORY_FILE)),
  multiline=True,
  mouse_support=False,  # Disable to allow terminal selection
  key_bindings=kb,
)
```

### Option 2: Conditional Mouse Support

Toggle mouse support based on user preference or context.

**Pros:**
- Gives users control over behavior
- Can document trade-offs in help

**Cons:**
- More complex implementation
- Adds configuration overhead
- Still has the fundamental conflict

**Implementation:**
```python
# Add to configuration
mouse_support: bool = False  # Default to off for selection

# In create_prompt_session
session: PromptSession[str] = PromptSession(
  history=FileHistory(str(HISTORY_FILE)),
  multiline=True,
  mouse_support=config.mouse_support,
  key_bindings=kb,
)
```

### Option 3: Custom Mouse Handler (Advanced)

Implement custom mouse handling that:
- Allows selection in scrollback area
- Enables cursor positioning in input area only

**Pros:**
- Best of both worlds
- Professional TUI experience

**Cons:**
- Complex implementation
- Requires understanding terminal mouse protocols
- May not work consistently across terminals

**Not recommended for current phase** - this is a Phase 2+ enhancement.

## Recommended Approach

**For Task 1.5.2, implement Option 1 (Disable mouse_support)**.

### Rationale

1. **User Value**: Text selection and copy is more valuable than mouse cursor positioning
2. **Terminal Convention**: Most terminal apps prioritize selection over mouse interaction
3. **Keyboard Users**: Target users (developers) prefer keyboard navigation
4. **Simplicity**: Single-line change, no regression risk
5. **Quick Win**: Unblocks a critical UX issue immediately

### Acceptance Criteria

- [ ] `mouse_support=False` is set in `PromptSession`
- [ ] User can click-drag to select any text in terminal output
- [ ] User can copy selected text (Ctrl+Shift+C / Cmd+C)
- [ ] Keyboard navigation still works (arrows, Home, End, Ctrl+A, Ctrl+E)
- [ ] No conflicts with existing keybindings
- [ ] Multiline input still works (Esc+Enter)
- [ ] History navigation still works (Up/Down arrows)
- [ ] History search still works (Ctrl+R)

### Testing

1. **Manual Testing**:
   - Start yoker: `python -m yoker`
   - Send a message, wait for response
   - Click and drag to select text in output
   - Verify text is highlighted
   - Copy selected text (Ctrl+Shift+C or Cmd+C)
   - Paste to verify content is correct

2. **Input Testing**:
   - Type multi-line input (Esc+Enter for newlines)
   - Use arrow keys for navigation
   - Use Ctrl+A / Ctrl+E for start/end
   - Verify keyboard navigation works

3. **Cross-Terminal Testing**:
   - Test in iTerm2 (macOS)
   - Test in GNOME Terminal (Linux)
   - Test in Windows Terminal

## Additional Considerations

### Future Enhancements (Phase 2+)

1. **Configuration Option**: Add `mouse_support` to TOML config
2. **Help Text**: Update `/help` to document mouse behavior
3. **Custom Handler**: Implement scrollback-aware mouse handling

### Documentation Updates

Update README.md to reflect mouse behavior:

```markdown
### Interactive Input

- **Mouse support**: Disabled by default to allow text selection
- **Cursor movement**: Use arrow keys or Ctrl+A/E
- **Text selection**: Click and drag in terminal, then copy with Ctrl+Shift+C
```

### Known Limitations

- `prompt_toolkit` does not support split mouse handling (input vs scrollback)
- Terminal mouse protocols vary by emulator
- Selection visual feedback depends on terminal emulator

## Summary

The mouse selection issue is a fundamental conflict between `prompt_toolkit`'s mouse capture and terminal-native text selection. The recommended fix is to disable `mouse_support`, restoring standard terminal selection behavior while maintaining keyboard navigation for cursor positioning.

**Change Required**: Set `mouse_support=False` in `create_prompt_session()` function.

**Files to Modify**:
- `src/yoker/__main__.py` (line 72)

**Risk**: Low - removes a feature that blocks critical functionality.

**Impact**: High - unblocks essential copy/paste workflow.