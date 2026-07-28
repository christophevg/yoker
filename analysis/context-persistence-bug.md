# Context Persistence Bug — Root-Cause Analysis

## Summary

Tool results are never persisted to the context JSONL files. The root cause is a
single-line misuse of `get_messages()` (which explicitly excludes `role=tool`
messages) inside `Persisted._persist_full_state` instead of `get_context()` (which
returns the full list). The `tool_result` serialization branch in `_item_to_record`
exists and is correct, but is dead code because its input is pre-filtered.

Three additional bugs were found in the same code path:

1. **Tool results never persisted** (critical) — root cause of the reported symptom.
2. **Assistant narration content lost on tool-call turns** (high) — contributes to
   the in-session loop; the agent cannot see its own reasoning from prior
   iterations.
3. **User messages persisted twice** (medium) — every `role=user` message is
   written as both a `turn_start` marker and a `message` record.
4. **Synthetic timestamps** (low) — all records get `datetime.now()` at persist
   time; original event timing is lost because the bulk-rewrite fires on every
   mutation.

Evidence from the on-disk files (`context/`, 11,963 JSONL files):

```
   12431  message
   11963  session_start
    6937  session_end
     277  turn_start
     137  tool_call_message
        0  tool_result        <-- ZERO across the entire corpus
```

The largest session file (`5a96feb728ae4e23a52609e5e2e4e23d-primary.jsonl`) has
**90 `tool_call_message` records and ZERO `tool_result` records** — every tool
call is followed in the file by either another `tool_call_message` or an
`assistant` `message`, never by a tool result.

---

## Bug #1 — Tool results never persisted (CRITICAL)

### The exact code path

`Persisted._persist_full_state` (the single JSONL writer) is called on every
mutating context operation. Every override in `Persisted` (`add_tool_result`,
`add_tool_calls`, `start_turn`, `end_turn`, `add_message`, `replace_messages`,
`truncate_oldest_non_system`, `save`, `close`, the `agent` setter) delegates to
the wrapped manager and then calls:

```python
# src/yoker/context/persisted.py:165 (and every other mutating override)
self._persist_full_state(self._wrapped.get_messages())
```

`get_messages()` on `BaseContextManager` is documented and implemented to
**exclude tool results**:

```python
# src/yoker/context/manager.py:140-146
def get_messages(self) -> list[dict[str, Any]]:
    """Get all recorded messages (excludes tool results)."""
    return [item for item in self._messages if item.get("role") != "tool"]
```

`get_context()` (used to build the LLM payload) returns the full list including
tool results:

```python
# src/yoker/context/manager.py:132-138
def get_context(self) -> list[dict[str, Any]]:
    return list(self._messages)
```

### Why tool results are not persisted

`_persist_full_state` iterates over the `messages` argument it receives and calls
`_item_to_record` for each item. `_item_to_record` has a correct `role == "tool"`
branch that maps to a `tool_result` record:

```python
# src/yoker/context/persisted.py:336-343
if role == "tool":
    return "tool_result", {
        "tool_name": item["name"],
        "tool_id": item.get("tool_id", item["name"]),
        "result": item["content"],
        "success": item.get("success", True),
    }
```

This branch is **dead code**: the input list passed to `_persist_full_state` is
already filtered by `get_messages()`, so no `role == "tool"` item ever reaches
`_item_to_record`.

The in-memory state is correct — `BaseContextManager.add_tool_result` appends a
`role=tool` message to `self._messages` (manager.py:100-108), and `get_context()`
returns it. The LLM sees tool results during a live session. But the persisted
JSONL file never contains them.

### Where the bug was introduced

The `get_messages()` / `get_context()` split is intentional for
`get_statistics()` (tool results should not count as "messages"). The bug is that
`Persisted` reused `get_messages()` — the statistics-view accessor — as the
persistence-view accessor. Persistence needs the full conversation including tool
results, i.e. `get_context()`.

### Why this causes the agent to loop

`Persisted.resume()` / `load()` (persisted.py:102-124, 225-247) replays the JSONL
records back into `_messages` via `_process_record`. The replay handles
`tool_result` records correctly (persisted.py:458-474) — but there are no
`tool_result` records to replay. The replayed context has `tool_call_message`
records (assistant messages with `tool_calls`) with NO matching `tool_result`
records. This breaks the tool-call/tool-result pairing invariant required by
every LLM API (OpenAI, Anthropic, Ollama): an assistant message that requests
tool calls must be followed by one tool-result message per call.

When a session is resumed with orphaned tool calls, the backend either errors or
the model re-invokes the same tools because it cannot see the prior results —
producing the exact loop the user observed (re-reading the same files,
re-deriving the same conclusions).

`Persisted.resume()` is currently not wired into `yoker chat` or `yoker run`
(`run_chat` in `cli/chat.py` never calls `load()`/`resume()`; the factory
`create_context_manager` creates a fresh `Persisted` without loading). So
today the loop on resume is latent. But:

- The persistence bug makes every JSONL file useless as a session-resume
  source — the feature is silently broken.
- Any future wiring of `--resume` / `--session-id` will immediately produce
  broken contexts and agent loops.
- The user's evidence ("things were missing ... in the context") comes from
  inspecting these JSONL files and seeing the missing tool results.

Within a single live session the in-memory state is correct, so the loop the
user saw in `local/loop.txt` (18 occurrences of "Now I have a clear picture", 8
of "Let me dig into") is amplified by Bug #2 (lost narration) and context
overflow truncation dropping older turns — the agent loses its earlier
reasoning text and re-investigates.

---

## Bug #2 — Assistant narration content lost on tool-call turns (HIGH)

When the LLM produces text content AND tool calls in the same response (e.g.
"Let me dig into the git tool implementation..." followed by tool calls),
the narration text is shown to the user via `ContentChunkEvent` but never
stored in the context.

### The code path

`process_message` consumes the stream and gets `content`, `thinking`,
`tool_calls`:

```python
# src/yoker/core/_processing.py:257
content, thinking, tool_calls, stats = await _consume_stream(agent, stream)
...
if not tool_calls:
    agent.context.end_turn(content, thinking=thinking or None)  # content stored
    ...
    return content

await _execute_tool_calls(agent, tool_calls, thinking)  # content NOT passed
```

When there ARE tool calls, `end_turn` is NOT called and `content` is discarded.
`_execute_tool_calls` calls `add_tool_calls` with only `tool_calls` and
`thinking`:

```python
# src/yoker/core/_processing.py:754
agent.context.add_tool_calls(formatted, thinking=thinking or None)
```

`BaseContextManager.add_tool_calls` hardcodes `content=""`:

```python
# src/yoker/context/manager.py:123-130
def add_tool_calls(self, tool_calls, thinking=None):
    assistant_msg: dict[str, Any] = {
        "role": "assistant",
        "tool_calls": tool_calls,
        "content": "",    # <-- narration lost
    }
```

The `content` variable from `_consume_stream` (which captured all
`CONTENT_DELTA` chunks) goes out of scope unused.

### Why this contributes to the loop

On the next iteration the LLM receives the context via `get_context()`: it sees
its own prior tool calls and the tool results, but NOT the reasoning text that
preceded them. Weaker models (the transcript shows `qwen3.5:cloud`) rely on
their own narration to maintain investigative state. Without it, the model
re-narrates and re-investigates from the same starting point. Combined with
overflow truncation that drops older turns entirely, the agent loses both its
reasoning text (Bug #2) and its earlier tool results (truncation), and restarts.

### The persistence layer also drops content (compounding the bug)

Even if `add_tool_calls` stored the content, the persistence layer would lose
it. `_item_to_record` for `tool_call_message` only serializes `tool_calls` and
`thinking`:

```python
# src/yoker/context/persisted.py:344-348
if role == "assistant" and "tool_calls" in item:
    return "tool_call_message", {
        "tool_calls": item["tool_calls"],
        "thinking": item.get("thinking"),
    }   # <-- content NOT included
```

And `_process_record` hardcodes `content=""` on replay:

```python
# src/yoker/context/persisted.py:483-490
wrapped._messages.append({
    "role": "assistant",
    "tool_calls": data["tool_calls"],
    "content": "",          # <-- always empty on replay
    "thinking": data.get("thinking"),
})
```

So fixing Bug #2 requires changes in four places (see Fix below).

---

## Bug #3 — User messages persisted twice (MEDIUM)

### The code path

`_persist_full_state` emits a `turn_start` marker for every `role=user` message
and THEN emits a `message` record for the same message:

```python
# src/yoker/context/persisted.py:302-321
for item in messages:
    if item.get("role") == "user":
        records.append({
            "type": "turn_start",
            "timestamp": datetime.now().isoformat(),
            "data": {"user_message": item.get("content", "")},
        })
    record_type, data = self._item_to_record(item)
    if record_type and data is not None:
        records.append({
            "type": record_type,
            "timestamp": datetime.now().isoformat(),
            "data": data,
        })
```

`_item_to_record` returns `("message", item)` for `role=user`, so the same
user message produces two records: a `turn_start` (with the content) and a
`message` (with the content). The data confirms this: the largest file has 11
`turn_start` records and 11 `role=user` `message` records.

### Impact

On resume, `_process_record` handles `turn_start` by only setting
`_last_turn_time` (persisted.py:492-495) and `message` by appending to
`_messages` (persisted.py:449-456). So the duplication is benign for replay —
the user message is added once from the `message` record. But it doubles the
storage for user content and makes the JSONL confusing to inspect (the user
reported "things ... double").

The `turn_start` emission is intentional: `list_sessions` counts turns via
`turn_start` records. The bug is that the SAME content is written in both the
marker and the message record.

---

## Bug #4 — Synthetic timestamps (LOW)

Every record in `_persist_full_state` gets `datetime.now().isoformat()` at
persist time (persisted.py:309, 319, 327), not at event time. Because
`_persist_full_state` is a bulk-rewrite invoked on every mutation, the entire
file is rewritten with fresh timestamps on every `add_message`, `add_tool_calls`,
`add_tool_result`, etc. The original event timestamps are lost. All records in a
file carry timestamps from the most recent persist, not from when the event
actually occurred. The user reported "things in the context that were out of
order" — this is why.

---

## Recommended Fix

All fixes are in two files: `src/yoker/context/persisted.py` and
`src/yoker/core/_processing.py`, with a signature change in
`src/yoker/context/manager.py` and `src/yoker/context/wrapper.py`.

### Fix #1 — Persist tool results (the critical fix)

In `src/yoker/context/persisted.py`, change every call site of
`self._wrapped.get_messages()` inside `_persist_full_state` invocations to
`self._wrapped.get_context()`. The nine call sites are in: `add_message`,
`add_tool_result`, `add_tool_calls`, `start_turn`, `end_turn`, the `agent`
setter, `truncate_oldest_non_system`, `replace_messages`, `save`, `close`.

The single-line change at each call site:

```python
# Before (every mutating override):
self._persist_full_state(self._wrapped.get_messages())

# After:
self._persist_full_state(self._wrapped.get_context())
```

This makes `_item_to_record`'s `role == "tool"` branch live, and tool results
will be serialized as `tool_result` records. `_process_record` already handles
`tool_result` records correctly (persisted.py:458-474), so resume will work.

No change to `_item_to_record` or `_process_record` is needed for this fix —
they are already correct; only their input was wrong.

### Fix #2 — Preserve assistant narration on tool-call turns

Four coordinated changes:

1. `src/yoker/context/manager.py` — `BaseContextManager.add_tool_calls`: accept
   `content: str = ""` and store it instead of the hardcoded empty string.

   ```python
   def add_tool_calls(self, tool_calls, content: str = "", thinking=None):
       assistant_msg = {
           "role": "assistant",
           "tool_calls": tool_calls,
           "content": content,   # was: ""
       }
       ...
   ```

2. `src/yoker/context/wrapper.py` — `ContextManagerWrapper.add_tool_calls`:
   forward the new `content` parameter.

3. `src/yoker/context/persisted.py` — `Persisted.add_tool_calls`: forward
   `content` to the wrapped call, AND in `_item_to_record` include `content` in
   the `tool_call_message` record, AND in `_process_record` restore `content`
   from the `tool_call_message` data instead of hardcoding `""`.

4. `src/yoker/core/_processing.py` — `_execute_tool_calls`: pass the `content`
   from `process_message` through to `add_tool_calls`. This requires threading
   `content` as a parameter of `_execute_tool_calls`:

   ```python
   # process_message, around line 271:
   await _execute_tool_calls(agent, tool_calls, thinking, content)

   # _execute_tool_calls:
   async def _execute_tool_calls(agent, tool_calls, thinking, content: str = ""):
       ...
       agent.context.add_tool_calls(formatted, content=content, thinking=thinking or None)
   ```

### Fix #3 — Deduplicate user-message persistence

In `src/yoker/context/persisted.py` `_persist_full_state`, keep the `turn_start`
marker (needed by `list_sessions`) but make it a pure boundary marker WITHOUT
the user content, so the content lives only in the `message` record:

```python
# Before:
if item.get("role") == "user":
    records.append({
        "type": "turn_start",
        "timestamp": ...,
        "data": {"user_message": item.get("content", "")},  # duplicate content
    })

# After:
if item.get("role") == "user":
    records.append({
        "type": "turn_start",
        "timestamp": ...,
        "data": {},  # marker only; content is in the message record below
    })
```

If `list_sessions` relies on `turn_start.data.user_message` for the preview, an
alternative is to keep the content in `turn_start` and SKIP emitting the `message`
record for `role=user` items (the `turn_start` already carries the content). In
that case `_process_record` must be updated to reconstruct the user message
from the `turn_start` record instead of from a `message` record.

### Fix #4 — Preserve event timestamps (optional, low priority)

Capture the timestamp when the message is added (in `add_message`,
`add_tool_result`, `add_tool_calls`, `start_turn`, `end_turn`) and store it in
the message dict (e.g. `item["_ts"]`). `_persist_full_state` then uses
`item["_ts"]` instead of `datetime.now()`. This requires the message dict to
carry an internal timestamp field that `get_context()` must strip before
sending to the backend (backends reject unknown fields).

Alternatively, replace the bulk-rewrite design with append-only JSONL writes:
each mutation appends one record with its event timestamp. This also fixes the
O(n^2) rewrite cost (Bug #5 below) and is the cleaner long-term direction.

### Bug #5 — O(n^2) bulk-rewrite on every mutation (not requested, noted)

`_persist_full_state` rewrites the ENTIRE file on every mutating call. With 90
tool calls in a turn, each `add_tool_result` triggers a full O(n) rewrite,
making the turn O(n^2) in file I/O. Switching to append-only writes (one record
per mutation) would fix both this and Bug #4. This is out of scope for the
immediate fix but worth noting.

---

## Verification

After Fix #1, a session that makes tool calls should produce a JSONL file with
`tool_result` records interleaved with `tool_call_message` records. The
on-disk count should show non-zero `tool_result` records.

After Fix #2, the in-memory context (and the persisted file) should contain the
assistant's narration text in the `content` field of `tool_call_message`
records, and the LLM should see its own prior reasoning on subsequent
iterations.

After Fix #3, each user message should appear exactly once in the JSONL file
(either as a `turn_start` marker without content + a `message` record with
content, or as a `turn_start` with content and no separate `message` record).

A regression test should:
1. Create a `Persisted(SimpleContextManager())`, wire an agent.
2. Drive one turn with a tool call and a tool result.
3. Call `close()` then `Persisted.resume(...)`.
4. Assert that the replayed `_messages` contains the `tool_call_message` AND its
   matching `tool_result` (pairing intact).
5. Assert that the replayed context passes `_validate_hook_output`'s pairing
   check (no orphaned tool calls, no dangling tool results).

---

## Files Touched by the Fix

| File | Change |
|------|--------|
| `src/yoker/context/persisted.py` | `get_messages()` -> `get_context()` at all 9 persist call sites (Fix #1); include `content` in `tool_call_message` record and replay (Fix #2); deduplicate `turn_start`/`message` (Fix #3) |
| `src/yoker/context/manager.py` | `add_tool_calls` accept `content` param (Fix #2) |
| `src/yoker/context/wrapper.py` | `add_tool_calls` forward `content` param (Fix #2) |
| `src/yoker/core/_processing.py` | pass `content` from `process_message` to `_execute_tool_calls` -> `add_tool_calls` (Fix #2) |

No changes to `events/types.py`, `events/recorder.py`, or
`events/session_event.py` — the event system already defines and handles
`ToolResultEvent` correctly. The bug is purely in the context-persistence
layer's choice of accessor (`get_messages` vs `get_context`) and in the
processing loop's failure to thread the assistant `content` through to
`add_tool_calls`.