# API Reference

*API documentation will be added as implementation progresses.*

## Current Modules

### `yoker.agent`

```{eval-rst}
.. automodule:: yoker.agent
   :members:
   :undoc-members:
   :show-inheritance:
```

### `yoker.events`

Event system for library-first design. The Agent emits events that handlers can subscribe to.

```{eval-rst}
.. automodule:: yoker.events
   :members:
   :undoc-members:
   :show-inheritance:
```

**Event Types:**

| Event | Description |
|-------|-------------|
| `SessionStartEvent` | Emitted when agent session begins |
| `SessionEndEvent` | Emitted when agent session ends |
| `TurnStartEvent` | Emitted when processing a user message begins |
| `TurnEndEvent` | Emitted when processing a user message completes |
| `ThinkingStartEvent` | Emitted when LLM thinking output begins |
| `ThinkingChunkEvent` | Emitted for each chunk of thinking output |
| `ThinkingEndEvent` | Emitted when thinking output ends |
| `ContentStartEvent` | Emitted when content output begins |
| `ContentChunkEvent` | Emitted for each chunk of content output |
| `ContentEndEvent` | Emitted when content output ends |
| `ToolCallEvent` | Emitted when a tool is called |
| `ToolResultEvent` | Emitted when a tool returns a result |
| `ErrorEvent` | Emitted when an error occurs |

**EventHandler Protocol:**

```python
from yoker.events import EventHandler, Event

class MyHandler:
    def __call__(self, event: Event) -> None:
        if hasattr(event, 'text'):
            print(event.text)

agent.add_event_handler(MyHandler())
```

### `yoker.tools`

```{eval-rst}
.. automodule:: yoker.tools
   :members:
   :undoc-members:
   :show-inheritance:
```