# ContextManager Refactor Design

This document captures the agreed-upon design for a ContextManager refactor in a follow-up PR. All design decisions below are FINAL. The document is self-contained — a developer can implement it without further questions.

## 1. Problem Statement

The current ContextManager architecture has a composition problem:

- `ContextManager` inherits from `UserList[dict[str, Any]]` — it is both the interface AND the implementation.
- `SimpleContextManager` (in-memory, adds environment reminder + system prompt) and `PersistenceContextManager` (JSONL persistence, adds system prompt only) are sibling subclasses — they cannot be combined.
- Passing `PersistenceContextManager` to `Agent(context_manager=...)` gives persistence but loses the environment reminder. There is no way to get both.
- The original "a context manager is just a list" paradigm is already dead in practice — `add_message` is the real API, not `append`, and a bare `list()` does not satisfy the contract. Upholding the `UserList` interface adds complexity with no practical benefit.

## 2. Design Decisions (All FINAL)

### Decision 1: Drop UserList inheritance entirely

The `UserList` interface (list dunder methods, `append`, `data` attribute) is abandoned. `ContextManager` becomes a proper Protocol. Storage is an internal implementation detail of `BaseContextManager`.

### Decision 2: ContextManager becomes a Protocol

A `@runtime_checkable` Protocol captures the full surface. No `__getitem__`, `__len__`, `__iter__`, `append`, `data` — the list surface is gone. Code that needs messages calls `get_messages()`.

### Decision 3: Rename current ContextManager → BaseContextManager

The current concrete `ContextManager` class (the `UserList` subclass) is renamed to `BaseContextManager`. It implements the Protocol. Uses internal `self._messages: list[dict[str, Any]]` — no longer exposes `data`. `setup_initial_context` adds the agent's system prompt (minimal base behavior).

### Decision 4: SimpleContextManager inherits from BaseContextManager

Overrides `setup_initial_context` to add the collapsed environment-reminder + system-prompt message. Otherwise unchanged.

### Decision 5: ContextManagerWrapper — pure proxy implementing the Protocol

Implements the ContextManager Protocol directly (no `UserList`, no `BaseContextManager` inheritance). Holds `self._wrapped: ContextManager`. Every method forwards to `self._wrapped`. This is the no-op baseclass for all wrappers.

### Decision 6: Persisted — first concrete wrapper

Inherits from `ContextManagerWrapper`. Adds JSONL persistence by overriding mutating methods: delegate to wrapped, then persist.

### Decision 7: Change reporting — void return, always bulk-rewrite

`add_message` and other adders return `None`. The wrapper does NOT detect changes via diffing or heuristics (heuristics are dangerous — reordering + splitting can produce `n_after > n_before` with a completely changed list). After every mutating call, `Persisted` rewrites the full JSONL file with `get_messages()`. This is:

- Always correct — no heuristic can fail, no change list can be misreported.
- Simplest possible Protocol — void return, no change format to design or version.
- O(n) I/O per call — acceptable at current scale (10–100 messages, 4–10 calls per turn).
- Future-proof — if a database-backed `Persisted` later needs granular changes, an optional `get_last_changes()` method can be added without breaking the void return. NOT built now (YAGNI).

### Decision 8: Type hints use ContextManager (the Protocol)

`Agent.__init__(context_manager: ContextManager)` — both `BaseContextManager` subclasses and `ContextManagerWrapper` subclasses satisfy the Protocol structurally.

## 3. Target Architecture

```
ContextManager (Protocol)              ← the contract
├── BaseContextManager                 ← renamed from ContextManager; internal list storage
│   └── SimpleContextManager           ← adds env reminder + system prompt
└── ContextManagerWrapper              ← pure proxy, forwards all calls to _wrapped
    └── Persisted                      ← adds JSONL persistence via bulk-rewrite
```

## 4. Protocol Definition

The full `ContextManager` Protocol, with signatures taken from the current `context/manager.py`:

```python
from typing import Any, Protocol, runtime_checkable
from yoker.context.interface import ContextStatistics

class ContextManager(Protocol):
  """Pluggable context manager for conversation history."""

  # --- agent reference ---
  @property
  def agent(self) -> "Agent | None": ...

  @agent.setter
  def agent(self, new_agent: "Agent") -> None: ...

  # --- context setup ---
  def setup_initial_context(self) -> None:
    """Add the initial system prompt / context messages."""

  def add_skill_discovery_block(self) -> None:
    """Add the skill-discovery user message, if enabled."""

  # --- message mutation ---
  def add_message(
    self,
    role: str,
    content: str,
    metadata: dict[str, Any] | None = None,
    thinking: str | None = None,
  ) -> None:
    """Add a message (user / assistant / system) to the context."""

  def add_tool_result(
    self,
    tool_name: str,
    tool_id: str,
    result: str,
    success: bool = True,
  ) -> None:
    """Add a tool execution result to the context."""

  def add_tool_calls(
    self,
    tool_calls: list[dict[str, Any]],
    thinking: str | None = None,
  ) -> None:
    """Add an assistant message carrying tool_calls. Must precede add_tool_result."""

  # --- reads ---
  def get_context(self) -> list[dict[str, Any]]:
    """Full context for backend submission (includes tool results)."""

  def get_messages(self) -> list[dict[str, Any]]:
    """All recorded messages (excludes tool results)."""

  # --- turn lifecycle ---
  def start_turn(self, user_message: str) -> None:
    """Start a new conversation turn."""

  def end_turn(self, assistant_message: str, thinking: str | None = None) -> None:
    """End the current conversation turn."""

  # --- storage lifecycle ---
  def clear(self) -> None:
    """Clear in-memory context (does not delete persisted state)."""

  def save(self) -> None:
    """Persist context to storage. No-op in base."""

  def load(self) -> bool:
    """Load context from storage. Return True if loaded, False if none."""

  def delete(self) -> None:
    """Delete stored context from disk."""

  def close(self) -> None:
    """Release resources and flush pending writes."""

  # --- introspection ---
  def get_statistics(self) -> ContextStatistics:
    """Return context-usage statistics."""

  def get_session_id(self) -> str:
    """Return the unique session identifier."""
```

List-only methods (`__getitem__`, `__len__`, `__iter__`, `append`, `data`) are REMOVED from the surface.

## 5. BaseContextManager Implementation Guide

File: `src/yoker/context/manager.py` (renamed class).

- Renamed from `ContextManager` to `BaseContextManager`.
- Uses `self._messages: list[dict[str, Any]]` internally (NOT `self.data`, NOT `UserList`).
- `__init__(self, initial: list[dict[str, Any]] | None = None)` — stores `self._messages = list(initial) if initial else []`, sets `self._agent = None`.
- `agent` property getter returns `self._agent`. Setter runs `self._agent = new_agent`, then `self.clear()`, `self.setup_initial_context()`, `self.add_skill_discovery_block()`.
- `setup_initial_context()` — base behavior: if `self._agent`, `self.add_message("system", self._agent.definition.system_prompt)`.
- `add_skill_discovery_block()` — same as current: if `self._agent` has skills and `config.skills.discovery`, build the discovery block from `self._agent.skills.skills` and `add_message("user", format_discovery_block(skill_list))`.
- `add_message(role, content, metadata=None, thinking=None)` — no-op if `not content`; else construct `{"role": role, "content": content}` with optional `metadata` and `thinking` keys, and `self._messages.append(message)`.
- `add_tool_result(tool_name, tool_id, result, success=True)` — append `{"role": "tool", "name": tool_name, "tool_id": tool_id, "content": result, "success": success}` to `self._messages`.
- `add_tool_calls(tool_calls, thinking=None)` — append `{"role": "assistant", "tool_calls": tool_calls, "content": ""}` with optional `thinking`.
- `get_context()` — return `list(self._messages)` (copy).
- `get_messages()` — return `[item for item in self._messages if item.get("role") != "tool"]`.
- `start_turn(user_message)` — `self.add_message("user", user_message)`.
- `end_turn(assistant_message, thinking=None)` — `self.add_message("assistant", assistant_message, thinking=thinking)`.
- `clear()` — `self._messages.clear()` (in-place).
- `save()` — no-op.
- `load()` — `return False`.
- `delete()` — `raise NotImplementedError("delete() not supported by this context manager")`.
- `get_statistics()` — return `ContextStatistics(message_count=<non-tool count>, turn_count=<user count>, tool_call_count=0)`.
- `get_session_id()` — `return "in-memory"`.
- `close()` — no-op.

ALL list-like operations (`__getitem__`, `__len__`, `__iter__`, `append`, `data`) are REMOVED.

## 6. SimpleContextManager Implementation Guide

File: `src/yoker/context/basic.py`.

- Inherits from `BaseContextManager` (renamed import from `yoker.context.manager`).
- Overrides `setup_initial_context()` to add a single collapsed system message: `self.add_message("system", self.environment_reminder + "\n" + self.system_prompt)`.
- `environment_reminder` property: unchanged (builds the Yoker harness reminder using `self._agent.config.harness`, `Path.cwd()`, `self._agent.model`).
- `system_prompt` property: unchanged (wraps `self._agent.definition.system_prompt` in `<agent-definition>` tags).
- Otherwise unchanged.

## 7. ContextManagerWrapper Implementation Guide

File: `src/yoker/context/wrapper.py`.

- Implements `ContextManager` Protocol directly.
- Does NOT inherit from `BaseContextManager` or `UserList`.
- `__init__(self, wrapped: ContextManager)` — stores `self._wrapped = wrapped`.
- Every Protocol method forwards to `self._wrapped`:
  - `agent` property getter: `return self._wrapped.agent`.
  - `agent` setter: `self._wrapped.agent = new_agent`.
  - `setup_initial_context()`: `self._wrapped.setup_initial_context()`.
  - `add_skill_discovery_block()`: `self._wrapped.add_skill_discovery_block()`.
  - `add_message(...)`: `self._wrapped.add_message(...)`.
  - `add_tool_result(...)`: `self._wrapped.add_tool_result(...)`.
  - `add_tool_calls(...)`: `self._wrapped.add_tool_calls(...)`.
  - `get_context()`: `return self._wrapped.get_context()`.
  - `get_messages()`: `return self._wrapped.get_messages()`.
  - `start_turn(...)`: `self._wrapped.start_turn(...)`.
  - `end_turn(...)`: `self._wrapped.end_turn(...)`.
  - `clear()`: `self._wrapped.clear()`.
  - `save()`: `self._wrapped.save()`.
  - `load()`: `return self._wrapped.load()`.
  - `delete()`: `self._wrapped.delete()`.
  - `close()`: `self._wrapped.close()`.
  - `get_statistics()`: `return self._wrapped.get_statistics()`.
  - `get_session_id()`: `return self._wrapped.get_session_id()`.

## 8. Persisted Implementation Guide

File: `src/yoker/context/persisted.py` (rename or replace `persistence.py`).

- Inherits from `ContextManagerWrapper`.
- `__init__(self, wrapped: ContextManager, storage_path: str | Path | None = None, session_id: str = "auto")`:
  - Call `super().__init__(wrapped)`.
  - Validate `storage_path` (default `DEFAULT_STORAGE_PATH`) and `session_id` via existing `validate_storage_path` / `validate_session_id` from `yoker.context.validator`.
  - Store `self._storage_path`, `self._session_id`, `self._file_path = self._storage_path / f"{self._session_id}.jsonl"`.
  - Track `self._start_time = datetime.now()`, `self._last_turn_time: datetime | None = None`, `self._tool_call_count = 0`.
- `@classmethod resume(cls, session_id, storage_path=None) -> "Persisted"`: build `Persisted(BaseContextManager(), storage_path=storage_path, session_id=session_id)`, call `load()`, raise `SessionNotFoundError(session_id)` if it returns `False`. (The wrapped base is populated from disk.)
- `get_session_id()`: `return self._session_id` (overrides wrapper's forward).
- Mutating overrides — each delegates to `self._wrapped` and then rewrites the full JSONL via `self._persist_full_state(self._wrapped.get_messages())`:
  - `add_message(...)`: `self._wrapped.add_message(...)` then persist.
  - `add_tool_result(...)`: `self._wrapped.add_tool_result(...)`; increment `self._tool_call_count`; persist.
  - `add_tool_calls(...)`: `self._wrapped.add_tool_calls(...)` then persist.
  - `start_turn(user_message)`: `self._wrapped.start_turn(user_message)`; `self._last_turn_time = datetime.now()`; persist (with turn marker).
  - `end_turn(assistant_message, thinking=None)`: `self._wrapped.end_turn(...)`; `self._last_turn_time = datetime.now()`; persist (with turn marker).
  - `clear()`: `self._wrapped.clear()`; reset `self._tool_call_count = 0`, `self._last_turn_time = None`; truncate the JSONL file.
  - `save()`: `self._wrapped.save()`; `self._persist_full_state(self._wrapped.get_messages())`.
  - `load()`: read JSONL, populate `self._wrapped` by replaying records via `_process_record` (which calls the wrapped `add_message` / `add_tool_result` / `add_tool_calls`). Return `True` on success, `False` if the file does not exist. Raise `ContextCorruptionError` on bad JSON.
  - `delete()`: `self._wrapped.delete()`; then `self._file_path.unlink()` (raise `SessionNotFoundError` if the file is missing).
  - `close()`: `self._wrapped.close()`; append a `session_end` record (or rewrite with session_end marker — implementation choice; bulk-rewrite is preferred for consistency).
- `get_statistics()`: merge — start from `self._wrapped.get_statistics()`, then override `tool_call_count` with `self._tool_call_count`, `start_time` with `self._start_time`, `last_turn_time` with `self._last_turn_time`.
- `_persist_full_state(messages: list[dict[str, Any]]) -> None`:
  - Ensure the storage directory exists with `DIR_MODE` (0o700).
  - Write a fresh JSONL file atomically: a `session_start` record first, then one record per message (type derived from role via `_item_to_record`), then turn markers as needed.
  - Always rewrite the entire file. No diff, no heuristic.
  - File permissions `FILE_MODE` (0o600); use `fcntl.flock` on non-Windows.
- JSONL record shapes (types and data fields) move over from the current `PersistenceContextManager`: `session_start`, `message`, `tool_result`, `tool_call_message`, `turn_start`, `turn_end`, `session_end`.
- `_item_to_record(item)` and `_process_record(record, line_num)` move here from `persistence.py` unchanged, except they operate against `self._wrapped` instead of `self.data`.

## 9. Migration Plan

1. Define the `ContextManager` Protocol — new file `src/yoker/context/protocol.py` (or place at the top of `manager.py`; a dedicated file is preferred for clarity).
2. Rename `ContextManager` → `BaseContextManager` in `src/yoker/context/manager.py`; update all imports.
3. Remove `UserList` inheritance from `BaseContextManager`; replace `self.data` with `self._messages`; replace `self.append(...)` with `self._messages.append(...)`.
4. Update `SimpleContextManager` in `src/yoker/context/basic.py` to inherit from the renamed `BaseContextManager`.
5. Create `ContextManagerWrapper` in new file `src/yoker/context/wrapper.py`.
6. Create `Persisted` in new file `src/yoker/context/persisted.py` (rename `persistence.py` and replace the class, or delete `persistence.py` and add `persisted.py`).
7. Deprecate / remove `PersistenceContextManager`. Replace all usage with `Persisted(SimpleContextManager(), session_id="...")` or `Persisted(BaseContextManager(), session_id="...")`.
8. Update exports in `src/yoker/context/__init__.py` (add `BaseContextManager`, `ContextManagerWrapper`, `Persisted`, keep `ContextManager` re-exported as the Protocol) and `src/yoker/__init__.py` (add `SimpleContextManager` to the top-level public API).
9. Update all call sites that use list-like access:
   - `len(cm)` → `len(cm.get_messages())`
   - `cm[-1]` → `cm.get_messages()[-1]`
   - `for msg in cm:` → `for msg in cm.get_messages():`
   - `cm.data` → `cm.get_messages()` (or `get_context()` where tool results matter)
   - `cm.append(x)` → `cm.add_message(...)` (or the appropriate adder)
10. Update tests: `tests/test_context.py`, `tests/test_agent.py`; add `tests/test_context_wrapper.py`, `tests/test_context_persisted.py`.
11. Update `scripts/demo_session.py`: `PersistenceContextManager(...)` → `Persisted(SimpleContextManager(), session_id=...)`.
12. Clean stale `BasicContextManager` references in docstrings and comments.

## 10. Usage Examples

```python
# Before — can't compose:
agent = Agent(context_manager=PersistenceContextManager(session_id="x"))  # persistence, no env reminder
agent = Agent(context_manager=SimpleContextManager())                    # env reminder, no persistence

# After — composable:
agent = Agent(context_manager=Persisted(SimpleContextManager(), session_id="x"))  # both
agent = Agent(context_manager=Persisted(BaseContextManager(), session_id="x"))    # persistence only
agent = Agent(context_manager=SimpleContextManager())                             # in-memory only
```

## 11. Files to Create/Modify/Delete

| Action | File | Description |
|--------|------|-------------|
| Create | `src/yoker/context/protocol.py` | `ContextManager` `@runtime_checkable` Protocol. |
| Modify | `src/yoker/context/manager.py` | Rename `ContextManager` → `BaseContextManager`; drop `UserList`; use `self._messages`; remove list dunder/`append`/`data`. |
| Modify | `src/yoker/context/basic.py` | `SimpleContextManager` inherits from `BaseContextManager`; behavior unchanged. |
| Create | `src/yoker/context/wrapper.py` | `ContextManagerWrapper` pure proxy implementing the Protocol. |
| Create | `src/yoker/context/persisted.py` | `Persisted` wrapper: JSONL persistence via bulk-rewrite. |
| Delete | `src/yoker/context/persistence.py` | Replaced by `persisted.py`; `DEFAULT_STORAGE_PATH` re-exported from `persisted.py`. |
| Modify | `src/yoker/context/__init__.py` | Export `ContextManager` (Protocol), `BaseContextManager`, `ContextManagerWrapper`, `Persisted`, `SimpleContextManager`, `DEFAULT_STORAGE_PATH`, `ContextStatistics`, `SessionMetadata`, `list_sessions`, `load_session_metadata`. Drop `PersistenceContextManager`. |
| Modify | `src/yoker/__init__.py` | Add `SimpleContextManager` to top-level public exports. |
| Modify | `src/yoker/agent/__init__.py` | Type hint `context_manager: ContextManager`; replace list-like access with `get_messages()` / `get_context()`. |
| Modify | `src/yoker/agent/_processing.py` | No behavioral change expected; verify `agent.context.*` calls still satisfy the Protocol (start_turn, end_turn, get_context, add_tool_calls, add_tool_result, add_message). |
| Modify | `scripts/demo_session.py` | `PersistenceContextManager(...)` → `Persisted(SimpleContextManager(), session_id=...)`. |
| Modify | `tests/test_context.py` | Drop list-like assertions; add `BaseContextManager` tests against the new interface. |
| Modify | `tests/test_agent.py` | Replace any `len(cm)` / `cm.data` / `cm[-1]` usage with `get_messages()` / `get_context()`. |
| Create | `tests/test_context_wrapper.py` | Verify `ContextManagerWrapper` forwards every Protocol method. |
| Create | `tests/test_context_persisted.py` | Verify `Persisted(SimpleContextManager())` round-trips JSONL and composes with env reminder. |
| Modify | `CLAUDE.md` | Update module map and any `PersistenceContextManager` references. |
| Modify | `README.md` | Update usage examples if they reference `PersistenceContextManager`. |

## 12. Acceptance Criteria

- [ ] `ContextManager` is a `@runtime_checkable` Protocol with NO list surface (`__getitem__`, `__len__`, `__iter__`, `append`, `data`).
- [ ] `BaseContextManager` exists (renamed from `ContextManager`), uses `self._messages`, no longer inherits `UserList`.
- [ ] `SimpleContextManager` inherits from `BaseContextManager` and still emits the collapsed env-reminder + system-prompt message.
- [ ] `ContextManagerWrapper` exists, implements the Protocol, and forwards every Protocol method to `self._wrapped`.
- [ ] `Persisted` inherits from `ContextManagerWrapper`, takes a `wrapped: ContextManager`, and persists via bulk JSONL rewrite on every mutating call.
- [ ] `Persisted(SimpleContextManager(), session_id="x")` produces a JSONL file whose replayed context includes the env-reminder + system-prompt message AND survives a fresh `Persisted(BaseContextManager(), session_id="x").load()`.
- [ ] `PersistenceContextManager` is removed; no references remain in `src/` or `tests/`.
- [ ] `Agent.__init__(context_manager: ContextManager)` is typed against the Protocol; both `BaseContextManager` subclasses and wrapper subclasses satisfy it structurally.
- [ ] No call site uses `cm.data`, `len(cm)`, `cm[i]`, `for msg in cm`, or `cm.append(...)`. All use `get_messages()` / `get_context()` / the adder methods.
- [ ] `make test`, `make lint`, `make typecheck`, and `ruff format` all pass.
- [ ] `tests/test_context_wrapper.py` and `tests/test_context_persisted.py` exist and pass.
- [ ] `scripts/demo_session.py` runs and produces a JSONL session file.
- [ ] `SimpleContextManager` is exported from the top-level `yoker` package.

## 13. Out of Scope

- Change-reporting protocol (Approach 2 — granular diff returns) — NOT implemented. `add_message` and other adders return `None`.
- `Logged`, `Encrypted`, or other wrappers — NOT implemented. The architecture supports them via `ContextManagerWrapper`.
- Database-backed persistence — NOT implemented. `Persisted` is JSONL only.
- Context compaction strategies — NOT implemented.
- Any change to the `ContextStatistics` / `SessionMetadata` dataclasses.
- Any change to `yoker.context.session` (`list_sessions`, `load_session_metadata`) beyond import-path updates if needed.