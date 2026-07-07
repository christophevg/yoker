# API Reference

*API documentation will be added as implementation progresses.*

## Current Modules

### `yoker.api`

Thin Pythonic facade (MBI-003) over the real `Agent` and `Session` classes.
Exposes the one-shot helpers `process` / `do`, the reusable-agent builder
`agent`, the multi-turn `session` async context manager, and the `run_sync`
sync wrapper. `yoker.agent` is the factory function re-exported from this
module (not a module itself).

```{eval-rst}
.. automodule:: yoker.api
   :members:
   :undoc-members:
   :show-inheritance:
```

### `yoker.core`

Agent layer (no UI, no Session coupling). Provides the unified `Agent` class:
async-only, emits `Event` objects, and exposes `on_event()` (the single
event-handler registration method), `process()`, and `do()`.

```{eval-rst}
.. automodule:: yoker.core
   :members:
   :undoc-members:
   :show-inheritance:
```

### `yoker.session`

Multi-turn session construct (MBI-007): an async context manager owning a team
of agents. The primary agent is available via `Session.agent`; sub-agents can be
spawned via `Session.spawn()`. Inter-agent messaging uses
`Session.send(*, to, from_, content)` with plain strings. Event handlers are
registered via `Session.on_event(...)`.

```{eval-rst}
.. automodule:: yoker.session
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
| `ToolContentEvent` | Emitted when a tool produces display content |
| `CommandEvent` | Emitted when a slash command is replayed |

Handlers are plain callables that receive `Event` objects. Register them with `agent.on_event(...)` (or `session.on_event(...)` for session-scoped handlers).

### `yoker.ui`

User interface layer. Provides `UIHandler` implementations and the `UIBridge` that routes agent events to UI methods.

### `yoker.tools`

```{eval-rst}
.. automodule:: yoker.tools
   :members:
   :undoc-members:
   :show-inheritance:
```
