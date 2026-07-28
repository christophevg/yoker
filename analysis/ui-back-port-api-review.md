# API Review: Back-port RichUIHandler Output Improvements to InteractiveUIHandler

**Date**: 2026-07-28
**Reviewer**: API Architect Agent
**Task**: Replace `InteractiveUIHandler` with a merged version: RichUIHandler's
output (stable, append-only `console.print`, no `Live` region) + old
`InteractiveUIHandler`'s input (prompt_toolkit, lazy `PromptSession`,
`erase_when_done` + `output_prompt`). Remove `LiveDisplay` (`spinner.py`).

## Summary

The back-port is API-neutral at the protocol and bridge layers. The
`UIHandler` Protocol and `UIBridge` need **no changes**. `BatchUIHandler` is
**unaffected**. The only API-surface impact is the removal of the public
re-exports `yoker.ui.LiveDisplay` and `yoker.ui.live_display`, and the
consequent test deletion/rewrite. Caller call sites (`cli/chat.py`,
`cli/init.py`) are preserved as long as `__init__` retains `history_file`
and the three `show_*` flags.

One signature deviation in RichUIHandler (`start()` with `title`/`version`
kwargs) should be dropped before merge — it is a Protocol extension that no
caller exercises and the simplicity principle says: do not add unused
indirection.

## Findings

### 1. UIHandler Protocol — no changes needed

`src/yoker/ui/handler.py` defines the Protocol. The merged handler
implements the same method set as the old `InteractiveUIHandler`:

- Lifecycle: `start(agent)`, `shutdown(reason)`
- Input: `get_input(prompt)`, `get_secret_input(prompt)`
- Wizard: `output_info(text)`, `output_step_title(step, total, title)`
- Content: `output_content`, `output_command_result`
- Diagnostics: `output_thinking`, `output_tool_call`, `output_tool_result`,
  `output_tool_content`, `output_stats`, `output_error`
- Streaming: `start_content_stream`, `stream_content`, `end_content_stream`,
  `start_thinking_stream`, `stream_thinking`, `end_thinking_stream`
- Optional (documented, guarded): `agent_spawned`, `agent_finished`,
  `confirm_approval`

No new methods are required. `output_prompt` (mentioned in the task) is an
**internal** helper for rendering the just-entered prompt inside a Panel
after `erase_when_done` clears the prompt_toolkit buffer; it is not part of
the Protocol and should be a private method on the handler, not added to
`UIHandler`.

**Compliance check**: PASS. No Protocol edit required.

### 2. UIBridge — no changes needed

`src/yoker/ui/bridge.py` dispatches events to `UIHandler` methods. The
optional `agent_spawned`/`agent_finished` dispatches are guarded with
`getattr(self.ui, method, None)` (lines 149-154). `confirm_approval` is
**not** dispatched through the bridge — it is wired directly onto
`Agent._approval_handler` by `yoker/cli/chat.py::_wire_approval_handler`
(line 137), gated by `hasattr(ui, "confirm_approval")`. None of this changes
with the back-port.

**Compliance check**: PASS. No `UIBridge` edit required.

### 3. BatchUIHandler — unaffected

`src/yoker/ui/batch.py` shares no code with `InteractiveUIHandler` beyond
the Protocol. It does not import `spinner.py`, does not implement
`agent_spawned`/`agent_finished`/`confirm_approval`, and its `start()` /
`shutdown()` are independent. Removing `LiveDisplay` does not touch it.

**Compliance check**: PASS.

### 4. LiveDisplay removal — migration impact

Within `src/`, `LiveDisplay` is used only by `interactive.py` (lines 24,
85, 149-160, 308-374, 491-528) and re-exported by `ui/__init__.py`
(lines 16, 23-24). No other production module imports it. Removing
`spinner.py` and the re-exports is safe for production code.

**Public API breakage**: `from yoker.ui import LiveDisplay, live_display`
will raise `ImportError`. These symbols are UI-internal helpers, not
advertised in the top-level `yoker` API surface (`yoker/__init__.py` does
not re-export them). Recommendation: clean removal, with a CHANGELOG note.
No deprecation shim — the simplicity principle says: do not keep dead
indirection.

**Test impact** (the only real migration cost):

| File | Action |
|------|--------|
| `tests/events/test_spinner.py` | Delete (dedicated LiveDisplay tests) |
| `tests/test_ui/test_spinner.py` | Delete (dedicated LiveDisplay tests) |
| `tests/test_ui/test_handler.py` | Drop `LiveDisplay`/`live_display` from the import block and the two `assert ... is not None` lines (22-23) |
| `tests/test_ui/test_interactive.py` | Rewrite — drop `from yoker.ui.spinner import LiveDisplay`; remove `test_shutdown_exits_live_display`, `test_start_content_stream_creates_live_display`, `test_start_thinking_stream_creates_live_display`, `test_tool_call_exits_live_display`, `test_tool_result_creates_live_display`, `test_output_stats_with_live_display`, `test_output_stats_without_live_display`, `test_output_error_exits_live_display`; drop the `assert handler._live is None` assertion in `test_init_defaults` (line 44); rewrite the streaming tests to assert against `console.print` output instead of Live region state |

### 5. Lazy PromptSession — right approach, partial CI benefit

Current `__init__` calls `self._create_session()` eagerly (line 100), which
constructs a `PromptSession` and triggers prompt_toolkit's terminal probe.
In TTY-less CI this requires the `pytest.skip(allow_module_level=True)` for
win32 (lines 17-21) and any other test-level mocking.

Lazy creation (create on first `get_input` / `get_secret_input` /
`confirm_approval` call) eliminates the need to mock the session for
**construction-only** tests (init defaults, attribute wiring, bootstrap
history-file selection). It does **not** eliminate the need for a TTY or
mock when a test actually awaits `get_input` — at that point the session is
built and probe runs. So:

- Construction-only tests: no mock needed (improvement).
- Input-reading tests: still need `set_input_messages` (which short-circuits
  before session creation — verify the lazy path still checks
  `_input_source` first) or a TTY mock.

**Recommendation**: ensure `set_input_messages`-driven input paths return
**before** touching `self._session`, so scripted tests never build a
session. The old code already does this (lines 220-225, 256-261); preserve
that ordering in the merged handler.

### 6. start() signature — drop RichUIHandler's title/version kwargs

RichUIHandler's `start()` is:
```python
async def start(self, agent: Agent, title: str = "Yoker", version: str = __version__) -> None
```

The Protocol declares `async def start(self, agent: Agent) -> None`. The
old `InteractiveUIHandler.start()` matches the Protocol exactly.

Callers (verified):
- `src/yoker/cli/chat.py:147` — `await ui.start(agent)` (no kwargs)
- `src/yoker/cli/init.py` — does not call `start()` (wizard drives its own flow)
- `examples/custom_handler.py:270` — `await ui.start(agent)` (no kwargs)
- Bootstrap wizard — drives steps directly, does not call `start()` on the handler

No caller passes `title` or `version`. The kwargs are dead surface.

**Per the simplicity principle (owner's proposal is default)**: the
RichUIHandler deviation is unused. Drop `title`/`version` from the merged
`start()` signature; keep `start(self, agent: Agent) -> None`. If banner
customization is desired later, make it an `__init__` parameter (instance
state), not a `start()` kwarg.

Note: technically a method with extra defaulted kwargs still satisfies the
Protocol (callable with `(agent)`). But "satisfies" is not "should keep" —
unused parameters are noise.

### 7. __init__ parameters — union, preserving caller-dependent ones

Old `InteractiveUIHandler.__init__`:
`history_file, show_thinking, show_tool_calls, show_stats, wrap_width, console`

RichUIHandler.__init__:
`show_thinking, show_tool_calls, show_stats, show_time, console`

Caller usage:
- `cli/chat.py:58` — `InteractiveUIHandler(history_file="none")`
- `cli/chat.py:102-106` — `InteractiveUIHandler(show_thinking=, show_tool_calls=, show_stats=)`
- `cli/init.py:118` — `InteractiveUIHandler(history_file="none")`
- `tests/test_ui/test_interactive.py` — `wrap_width=80` exercised
- `tests/test_bootstrap/test_history_security.py` — `history_file="none"`

**Required for backward compat**: `history_file` (callers depend on it),
`show_thinking`, `show_tool_calls`, `show_stats`, `console`.

**Recommended**: keep `wrap_width` — supports `_print_wrapped` (which the
task says to add back). Without it, `_print_wrapped` degrades to plain
`console.print`.

**Optional**: `show_time` is a RichUIHandler addition. Old default was
`show_stats=True`; RichUIHandler default is `show_stats=False`. Since the
CLI always passes `show_stats=config.ui.show_stats`, the default does not
matter for the CLI path. For direct API consumers, preserve the old
default `show_stats=True` to avoid silent behavior change. `show_time` is
new — add it with default `False` (opt-in) so the merged handler's default
output matches the old handler's default output as closely as possible.

**Final __init__ signature**:
```python
def __init__(
  self,
  history_file: Path | None | str = None,
  show_thinking: bool = True,
  show_tool_calls: bool = True,
  show_stats: bool = True,
  show_time: bool = False,
  wrap_width: int | None = None,
  console: Console | None = None,
) -> None:
```

### 8. Backward compatibility — caller audit

| Caller | Uses | Preserved? |
|--------|------|-----------|
| `cli/chat.py::run_chat` (bootstrap path) | `InteractiveUIHandler(history_file="none")` | YES |
| `cli/chat.py::create_ui` | `InteractiveUIHandler(show_thinking=, show_tool_calls=, show_stats=)` | YES |
| `cli/init.py::_run_interactive` | `InteractiveUIHandler(history_file="none")` | YES |
| `cli/chat.py::_wire_approval_handler` | `hasattr(ui, "confirm_approval")` | YES (method preserved) |
| `tests/test_bootstrap/test_history_security.py` | `InteractiveUIHandler(history_file="none")` | YES |
| `tests/test_ui/test_interactive.py` | `wrap_width`, `_live`, `LiveDisplay` | NO — rewrite required (see §4) |
| `tests/test_ui/test_handler.py` | `from yoker.ui import LiveDisplay, live_display` | NO — drop imports (see §4) |
| `examples/custom_handler.py::PrintUIHandler` | Does NOT implement `agent_spawned`/`agent_finished`/`confirm_approval` | YES — Protocol still marks them optional; `UIBridge` still guards with `getattr` |
| External: `from yoker.ui import LiveDisplay` | Removed | Breaks — document in CHANGELOG as internal-helper removal |

### 9. Behavioral notes worth flagging

- **`output_stats` default**: RichUIHandler defaults `show_stats=False`;
  old handler defaulted `True`. Keep old default (`True`) to avoid silent
  regression for direct API consumers. CLI path is unaffected (passes
  config value explicitly).

- **RichUIHandler `output_stats` f-string bug** (line 189):
  `self.console.print("📊 {duration_s:.1f}s, {total} tokens", style=STATS_STYLE)`
  — missing `f` prefix, so the placeholders are printed literally. The
  merged handler should fix this (add `f`) or the old handler's
  `output_stats` body should be kept. Per the simplicity principle, the
  owner's proposal (RichUIHandler body) is the default — but a literal
  `{duration_s}` in user-facing output is a bug, not a preference. Flag for
  fix during the merge.

- **`output_content`**: RichUIHandler has it commented out (lines 110-113).
  The task explicitly says "Add back: ... output_content". The merged
  handler must implement it (the Protocol requires it; `UIBridge` does not
  dispatch to it but `output_content` is part of the public handler surface
  for direct callers and tests).

- **`shutdown` behavior**: RichUIHandler's `shutdown` is `pass`; old
  handler's `shutdown` calls `self._exit_live()` and prints "Goodbye!".
  With `LiveDisplay` gone, `_exit_live()` is too. The merged `shutdown`
  should keep the "Goodbye!" print (preserves user-visible behavior) and
  drop the live-exit call. If `erase_when_done` leaves prompt_toolkit state
  to clean up, do it here.

- **`agent_spawned`/`agent_finished`**: RichUIHandler does not implement
  these. The task says "Add back: ... agent_spawned/agent_finished". Keep
  the old handler's bodies (lines 378-394), minus the `_exit_live()` calls
  (no live region to exit). Just `console.print(...)`.

- **`output_command_result`**: RichUIHandler stubs this as `pass`. The task
  says "Add back: ... output_command_result". Keep the old handler's body
  (`console.print(f"{result}\n")`), minus `_exit_live()`.

- **`output_step_title`**: RichUIHandler stubs this as `pass`. The task
  says "Add back: ... output_step_title". Keep the old handler's body
  (Step N of M with bold+underline, leading blank line for step > 1), minus
  `_exit_live()`.

## Recommendations (prioritized)

1. **Drop `title`/`version` from `start()`** — unused Protocol extension.
   Keep `start(self, agent: Agent) -> None`.
2. **Use the `__init__` signature in §7** — preserves all caller call sites
   and adds `show_time` as opt-in.
3. **Remove `spinner.py` and the `ui/__init__.py` re-exports** of
   `LiveDisplay`/`live_display`. No deprecation shim.
4. **Delete `tests/events/test_spinner.py` and
   `tests/test_ui/test_spinner.py`**; trim `tests/test_ui/test_handler.py`
   imports; rewrite `tests/test_ui/test_interactive.py` streaming/state
   tests against `console.print` output.
5. **Keep `set_input_messages` short-circuit ahead of lazy session
   creation** in `get_input` / `get_secret_input` / `confirm_approval` so
   scripted tests never build a `PromptSession`.
6. **Fix the `output_stats` f-string bug** during merge (add `f` prefix or
   port old body).
7. **Keep `show_stats=True` default** (old behavior) — RichUIHandler's
   `False` default would silently change direct-API-consumer output.
8. **Implement `output_content`** (uncomment RichUIHandler stub) — Protocol
   requires it.
9. **Keep `shutdown` printing "Goodbye!"** — preserves user-visible
   behavior; drop `_exit_live()`.
10. **Keep `agent_spawned`/`agent_finished`/`output_command_result`/
    output_step_title` bodies from old handler**, minus `_exit_live()` /
    `_ensure_live()` calls.

## Conclusion

**Approved** — the back-port is safe at the Protocol/Bridge/Batch layer.
The only required work is `LiveDisplay` removal and the corresponding test
rewrite. Two corrections to RichUIHandler before merge: drop the unused
`start()` kwargs, and fix the `output_stats` f-string. The merged
`__init__` must retain `history_file` and `wrap_width` (callers and tests
depend on them).

## Next steps

- Implementation: rewrite `src/yoker/ui/interactive.py` per §7-§9.
- Delete `src/yoker/ui/spinner.py`; update `src/yoker/ui/__init__.py`
  exports.
- Test rewrite per §4.
- Update `CLAUDE.md` module structure (remove `spinner.py` line; note
  merged handler).
- CHANGELOG entry: "Removed public re-export of `LiveDisplay` /
  `live_display` from `yoker.ui` (internal helper)."
- `make check` gate before commit.