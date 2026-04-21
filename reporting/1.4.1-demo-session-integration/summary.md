# Context Manager Integration in demo_session.py

## Summary

Extended Task 1.4.1 (Context Manager Integration) to include session persistence in demo_session.py with --persist and --resume flags.

## Implementation

### Changes to demo_session.py

Added two new command-line flags:

| Flag | Description |
|------|-------------|
| `--persist` | Enable session persistence for later resumption |
| `--resume <session_id>` | Resume a previous session by ID |

### Session Continuity

When `--persist` is used:
1. Creates a `BasicPersistenceContextManager` with auto-generated session ID
2. Saves session to `context/<session_id>.jsonl`
3. Displays session ID and statistics at session end

When `--resume <session_id>` is used:
1. Loads existing context from `context/<session_id>.jsonl`
2. Displays "Resumed: X turns, Y tool calls" message
3. Continues conversation with full context history

### Bug Fixes

Fixed three bugs discovered during implementation:

1. **Double user message**: `Agent.process()` called both `start_turn()` (which adds user message) and `add_message("user", message)`. Fixed by removing redundant call.

2. **Double assistant message**: `Agent.process()` called both `add_message("assistant", content)` and `end_turn()` (which adds assistant message). Fixed by removing redundant call.

3. **System message duplication on resume**: `Agent.__init__` always added system message, causing duplicates when resuming sessions. Fixed by checking for existing system message first.

## Files Modified

| File | Changes |
|------|---------|
| `scripts/demo_session.py` | Added --persist and --resume flags, context manager integration |
| `src/yoker/agent.py` | Fixed duplicate message bugs, added system message check |
| `TODO.md` | Updated Task 1.4.1 with demo_session integration details |

## Testing

All tests pass (213 tests). Verified:
- `--persist` creates session and shows statistics
- `--resume` loads previous session and continues conversation
- Context file structure correct (5 messages for 2 turns)
- Model correctly references previous context ("You just said 'Hello'")