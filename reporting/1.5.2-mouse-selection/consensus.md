# Consensus Summary: Task 1.5.2 - Fix Mouse Selection in Interactive Mode

## Domain Review Results

### Agents Invoked
- **ui-ux-designer**: Frontend/UX review (only agent required for frontend-only task)

### UX Analysis Summary

**Root Cause**: `mouse_support=True` in `prompt_toolkit` captures mouse events globally, blocking the terminal's native text selection functionality.

**Key Finding**: This is a fundamental conflict between `prompt_toolkit`'s mouse handling and terminal-native selection. The library does not support split mouse handling (input vs scrollback).

### Consensus Decision

**Option 1: Disable mouse_support** (unanimously approved)

#### Rationale

1. **User Value**: Text selection and copy is more valuable than mouse cursor positioning
2. **Terminal Convention**: Most terminal apps prioritize selection over mouse interaction
3. **Keyboard Users**: Target users (developers) prefer keyboard navigation
4. **Simplicity**: Single-line change, no regression risk
5. **Quick Win**: Unblocks a critical UX issue immediately

#### Trade-off Accepted

| Feature | Value | After Fix |
|---------|-------|-----------|
| Select/copy output text | Critical | Working |
| Click to position cursor | Nice-to-have | Not available |
| Keyboard navigation | Essential | Working |

The trade-off is clear: text selection is more valuable than mouse cursor positioning, especially for developer users who prefer keyboard navigation anyway.

### Implementation Approach

**Change**: Set `mouse_support=False` in `PromptSession` creation.

**File**: `src/yoker/__main__.py` (line 72)

```python
session: PromptSession[str] = PromptSession(
  history=FileHistory(str(HISTORY_FILE)),
  multiline=True,
  mouse_support=False,  # Disable to allow terminal selection
  key_bindings=kb,
)
```

### Acceptance Criteria

- [ ] `mouse_support=False` is set in `PromptSession`
- [ ] User can click-drag to select any text in terminal output
- [ ] User can copy selected text (Ctrl+Shift+C / Cmd+C)
- [ ] Keyboard navigation still works (arrows, Home, End, Ctrl+A, Ctrl+E)
- [ ] No conflicts with existing keybindings
- [ ] Multiline input still works (Esc+Enter)
- [ ] History navigation still works (Up/Down arrows)
- [ ] History search still works (Ctrl+R)

### Agents Approval

- [x] **ui-ux-designer**: Approved Option 1 - Disable mouse_support

## Next Steps

Proceed to Phase 4: Implementation with the approved approach.