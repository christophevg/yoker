# Event Logging System Implementation Summary

## Task

Task 1.5.4: Formalize the Event Logging System that was already implemented in demo_session.py into the library.

## Implementation

### Files Created

| File | Purpose |
|------|---------|
| `src/yoker/logging/__init__.py` | Public API for logging module |
| `src/yoker/logging/event_logger.py` | `EventLogger` class and serialize/deserialize functions |
| `src/yoker/logging/event_replay.py` | `EventReplayAgent` class for replaying sessions |

### Files Modified

| File | Changes |
|------|---------|
| `src/yoker/__init__.py` | Added logging exports to public API |
| `scripts/demo_session.py` | Removed inline implementations, now uses library |
| `tests/test_demo_session.py` | Updated imports to use library classes |
| `TODO.md` | Marked task 1.5.4 as complete |

### Public API

```python
from yoker.logging import (
  EventLogger,          # Event handler that logs to JSONL
  EventReplayAgent,     # Agent that replays from JSONL
  serialize_event,      # Serialize Event to dict
  deserialize_event,    # Deserialize dict to Event
)
```

### EventLogger

Logs all events to a JSONL file for later replay:

```python
from yoker.logging import EventLogger
from pathlib import Path

logger = EventLogger(Path("session.jsonl"))
agent.add_event_handler(logger)
# ... run session ...
logger.close()
```

### EventReplayAgent

Replays recorded sessions without LLM calls:

```python
from yoker.logging import EventReplayAgent
from pathlib import Path

agent = EventReplayAgent(Path("session.jsonl"))
agent.add_event_handler(ConsoleEventHandler(console))
response = agent.process("Hello")  # Replays events for "Hello" turn
```

## Design Decisions

1. **Type narrowing**: Used `isinstance()` checks instead of match/cast for better mypy compatibility
2. **JSONL format**: One JSON object per line for easy streaming and append operations
3. **Event serialization**: All event types are serialized with `type`, `timestamp`, and `data` fields
4. **Replay interface**: `EventReplayAgent` provides same interface as `Agent` for drop-in replacement

## Testing

- All 213 tests pass
- Type checking passes (`mypy --strict`)
- Linting passes (`ruff check`)
- Test coverage: 93-99% for new modules

## Usage

The `--log` flag in demo_session.py uses EventLogger:

```bash
python scripts/demo_session.py --log           # Logs to media/events.jsonl
python scripts/demo_session.py --replay        # Replays from events.jsonl
```