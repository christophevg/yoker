# Back-port RichUIHandler Output Improvements to InteractiveUIHandler

## Design Analysis

### Owner's Confirmed Design Decisions (verbatim)

> 1. **Base**: Take RichUIHandler (from ../yoker-assistant/src/yoker_assistant/handler.py) as the new base for InteractiveUIHandler — it already has the stable, append-only console.print output, no Live region, no spinner, no state flags
> 2. **Input**: Add prompt_toolkit input from old InteractiveUIHandler — PromptSession, key bindings, FileHistory/InMemoryHistory, multiline input, set_input_messages — but make PromptSession **lazy** (create on first get_input call, not in __init__)
> 3. **Input rendering**: Use `erase_when_done=True` on prompt_async so input is erased after Enter → then output_prompt renders it in a styled Panel
> 4. **Output improvements kept from RichUIHandler**: inline tool args (all key=value pairs), result size "(N chars)", output_prompt Panel, tools list in banner
> 5. **Removed**: LiveDisplay (src/yoker/ui/spinner.py), _exit_live/_ensure_live, state flags (_thinking_shown, _content_shown, _streaming_*, _end_turn), spinner with elapsed-time status
> 6. **Added back from old InteractiveUIHandler**: output_step_title, output_command_result, output_content, confirm_approval, agent_spawned/agent_finished, _print_wrapped, shutdown — adapted to stable console.print approach (no _exit_live needed)

This plan satisfies each one — see the method-by-method table below.

---

## Source Files Reviewed

| File | Role |
|------|------|
| `../yoker-assistant/src/yoker_assistant/handler.py` | RichUIHandler — output-only, stable `console.print`, no Live, no spinner |
| `src/yoker/ui/interactive.py` | Old InteractiveUIHandler — prompt_toolkit input + Live region + state flags |
| `src/yoker/ui/spinner.py` | LiveDisplay — to be removed |
| `src/yoker/ui/handler.py` | UIHandler Protocol — the contract both must satisfy |
| `src/yoker/ui/bridge.py` | UIBridge — dispatches events; not changed |
| `src/yoker/ui/__init__.py` | Re-exports `LiveDisplay`/`live_display` — must drop them |
| `src/yoker/cli/chat.py` | Consumer — `create_ui`, `_wire_approval_handler` (uses `hasattr(ui, "confirm_approval")`) |
| `src/yoker/cli/init.py` | Consumer — `InteractiveUIHandler(history_file="none")` for bootstrap |
| `scripts/demo_session.py` | Consumer — uses `set_input_messages`, `ui.console.print` |

---

## LiveDisplay Usage Audit

`grep -rn` over the codebase (excluding `.venv`/`site-packages`) shows **LiveDisplay is referenced only inside the UI layer and its tests**. No core, cli, bootstrap, or session code touches it.

| Location | Usage | Action |
|----------|-------|--------|
| `src/yoker/ui/interactive.py` | Imports `LiveDisplay`; `_live`, `_ensure_live`, `_exit_live` | **Removed** (rewrite handler) |
| `src/yoker/ui/__init__.py` | Re-exports `LiveDisplay`, `live_display` | **Drop exports** |
| `src/yoker/ui/spinner.py` | The module itself | **Delete file** |
| `tests/test_ui/test_spinner.py` | Tests LiveDisplay | **Delete file** |
| `tests/events/test_spinner.py` | Tests LiveDisplay | **Delete file** |
| `tests/test_ui/test_handler.py` | Imports `LiveDisplay`, `live_display` from `yoker.ui` | **Drop imports + assertions** |
| `tests/test_ui/test_interactive.py` | Asserts `handler._live is None / not None` | **Rewrite tests** (see Test Strategy) |

No callers outside the UI layer need updating. The `yoker.ui` public surface shrinks by two symbols (`LiveDisplay`, `live_display`); nothing else in the repo imports them.

---

## PromptSession Lazy Initialization

### Why lazy

Old `__init__` calls `self._create_session()` eagerly, which constructs a `PromptSession`. On CI runners without a real TTY this hangs (macOS) or raises `NoConsoleScreenBufferError` (Windows). The `tests/test_ui/test_confirm_approval.py` workaround patches `yoker.ui.interactive.PromptSession` at module level before constructing the handler. Lazy init removes this fragility: `__init__` only stores config; the `PromptSession` is built on the first `get_input` (or `get_secret_input` / `confirm_approval`) call.

### What stays separate from PromptSession

The pieces currently built inside `_create_session` split cleanly:

| Piece | Built where | Notes |
|-------|-------------|-------|
| `KeyBindings` (enter / escape+enter) | Inside `_create_session` — stays there | Only used by `PromptSession`; build inline when constructing the session |
| `History` (`FileHistory` / `InMemoryHistory`) | Inside `_create_session` — stays there | Needs `self.history_file` (already an `__init__` field); build inline |
| `PromptSession` itself | **Lazy** — built in `_get_or_create_session()` on first call | Stored as `self._session: PromptSession[str] | None = None` |

### Implementation shape

```python
def __init__(self, ...):
  ...
  self._session: PromptSession[str] | None = None
  # _input_source / _input_index remain; predefined input bypasses the session
  # entirely so demo_session.py keeps working without a TTY.

def _get_or_create_session(self) -> PromptSession[str]:
  if self._session is None:
    self._session = self._create_session()
  return self._session
```

`get_input`, `get_secret_input`, and `confirm_approval` all call `self._get_or_create_session()` before `prompt_async`. When `self._input_source is not None`, they short-circuit before touching the session (same as today), so scripted demos never build a `PromptSession`.

### Lazy-init impact on existing tests

| Test | Current behavior | With lazy init |
|------|------------------|----------------|
| `test_prompt_session_created` | Asserts `handler._session is not None` right after `__init__` | **Rewrite** — assert `handler._session is None` after `__init__`; assert non-None after first `get_input` |
| `test_history_security.*` | Inspects `handler._session.history` from `__init__` | **Rewrite** — call `_get_or_create_session()` (or a public `_ensure_session()`) before inspecting, OR assert on `history_file` only |
| `test_confirm_approval._make_interactive_handler` | Patches `PromptSession` around `__init__` | With lazy init the patch must remain until the first `confirm_approval` call. Simplest: keep the `with patch(...)` around the whole test, or patch once at module level per test. The patch target stays `yoker.ui.interactive.PromptSession` because `_create_session` still calls `PromptSession(...)`. The CI fix is preserved, just no longer strictly needed for non-approval tests. |

---

## erase_when_done Integration

### Where

`get_input` and `get_secret_input`. After `prompt_async` returns, prompt_toolkit erases the input line (including the prompt) from the terminal. The handler then immediately calls `self.output_prompt(text)` to render the user's message as a styled Panel — the same content the user typed, now persisted in the scrollback as a stable block.

### Shape

```python
async def get_input(self, prompt: str = "> ") -> str | None:
  if self._input_source is not None:
    ...  # unchanged predefined path
  try:
    result = await self._get_or_create_session().prompt_async(
      prompt, is_password=False, erase_when_done=True
    )
  except (EOFError, KeyboardInterrupt):
    self.console.print()
    return None
  self.output_prompt(result)
  return result
```

`get_secret_input` does **not** call `output_prompt` — secrets must not be re-rendered. `erase_when_done` still applies so the masked prompt line disappears.

### Edge cases

- **Empty input** (`""`): `erase_when_done` erases the prompt line; `output_prompt("")` renders an empty Panel. Decision: skip `output_prompt` when `result.strip() == ""` to avoid an empty Panel. Confirm with owner (see Questions).
- **EOF / Ctrl+C**: `erase_when_done` is irrelevant; we just print a newline and return `None`. No Panel.
- **`confirm_approval`**: does **not** use `erase_when_done` — the y/N answer should not be erased (it's a visible audit trail of the user's choice). Keep its existing prompt without `erase_when_done`.

---

## Method-by-Method Merge Plan

Legend: **K** = keep from RichUIHandler as-is, **A** = add/adapt from old InteractiveUIHandler, **R** = remove (Live/state), **N** = new.

| Method | Action | Source / change |
|--------|--------|-----------------|
| `__init__` | **A** | Merge: keep RichUIHandler's `show_*` + `console`; add old InteractiveUIHandler's `history_file`, `wrap_width`, `_input_source`/`_input_index`. Drop `_live`, `_thinking_shown`, `_content_shown`, `_streaming_*`. Set `self._session: PromptSession[str] \| None = None` (lazy). Drop `_create_session()` call. Add styles `PROMPT_STYLE`, `CONTENT_STYLE`, `TOOL_RESULT_STYLE`, `STATS_STYLE`, `STEP_TITLE_STYLE` (RichUIHandler has all but STEP_TITLE). |
| `_create_session` | **A** | Same as old InteractiveUIHandler's body (KeyBindings + History + `PromptSession(multiline=True, mouse_support=False, key_bindings=kb)`). Unchanged logic; just no longer called from `__init__`. |
| `_get_or_create_session` | **N** | Lazy-init helper — see above. |
| `set_input_messages` | **A** | Verbatim from old InteractiveUIHandler. |
| `_ensure_live` / `_exit_live` / `_end_turn` | **R** | Delete. No Live region. |
| `start` | **K (RichUIHandler)** | Adopt RichUIHandler's `start`: includes the `Tools: ...` line in the banner (decision #4). The old InteractiveUIHandler banner lacks the tools line. Keep RichUIHandler's `Thinking: <mode>` line without the `(use /think ...)` hint, OR keep the old hint — see Questions. |
| `shutdown` | **A** | Old InteractiveUIHandler prints `"\nGoodbye!"`. RichUIHandler's `shutdown` is `pass`. Use old's body but drop `self._exit_live()`: just `self.console.print("\nGoodbye!")`. |
| `get_input` | **A** | Old InteractiveUIHandler + `erase_when_done=True` + `output_prompt(result)` (see erase_when_done). |
| `get_secret_input` | **A** | Old InteractiveUIHandler + `erase_when_done=True`. No `output_prompt`. |
| `output_info` | **K (RichUIHandler)** | `self.console.print(text)` — no `_exit_live`. |
| `output_step_title` | **A** | Old InteractiveUIHandler body but drop `self._exit_live()`. Keep `STEP_TITLE_STYLE`. |
| `output_prompt` | **K (RichUIHandler)** | `console.print(); console.print(Panel(text, style=PROMPT_STYLE, box=box.SIMPLE_HEAD))`. |
| `output_content` | **A** | Re-enable the commented-out RichUIHandler body: `start_content_stream(); stream_content(); end_content_stream(len(content))`. Old InteractiveUIHandler already does this; RichUIHandler commented it out. |
| `output_command_result` | **A** | Old InteractiveUIHandler body but drop `_exit_live`: `self.console.print(f"{result}\n")`. |
| `start_content_stream` | **K (RichUIHandler)** | `console.print("⏺ ", end="", style=CONTENT_STYLE)`. |
| `stream_content` | **K (RichUIHandler)** | `console.print(chunk, end="", style=CONTENT_STYLE)`. |
| `end_content_stream` | **K (RichUIHandler)** | `console.print()`. |
| `start_thinking_stream` | **K (RichUIHandler)** | `if show_thinking: console.print()`. |
| `stream_thinking` | **K (RichUIHandler)** | `if show_thinking: console.print(chunk, style=THINKING_STYLE, end="")`. |
| `end_thinking_stream` | **K (RichUIHandler)** | `if show_thinking: console.print()`. |
| `output_thinking` | **K (RichUIHandler)** | Inline stream trio. |
| `output_tool_call` | **K (RichUIHandler)** | `console.print(f"⏺ {tool_name}", end="", style=TOOL_STYLE); console.print(f"({details})")`. Decision #4: inline all key=value pairs (RichUIHandler's `_format_tool_details` already does this for non-git/websearch tools). Drop old InteractiveUIHandler's `"\n⏺ Read tool: ..."` style and `_exit_live`. |
| `output_tool_result` | **K (RichUIHandler)** | Includes `(N chars)` size suffix (decision #4). Drop old's `_ensure_live()` after. |
| `output_tool_content` | **K (RichUIHandler)** | Drop old's `_exit_live` / `_ensure_live` bracket. |
| `output_stats` | **K (RichUIHandler)** | `if show_stats: console.print("📊 ...")`. Old's tokens/sec format is *not* kept — RichUIHandler's simpler form wins. Confirm with owner (see Questions). |
| `output_error` | **K (RichUIHandler)** | Identical NetworkError/ToolError/generic dispatch. Drop `_exit_live`. |
| `_print_error` | **K (RichUIHandler)** | Identical Panel + traceback logic. Drop old's trailing `console.print()` (RichUIHandler doesn't add it). |
| `_capitalize` | **K** | Identical in both. |
| `_extract_filename` | **K (RichUIHandler)** | RichUIHandler's version drops the "first arg value" fallback (commented out). Use RichUIHandler's. |
| `_format_tool_details` | **K (RichUIHandler)** | Inline `key=value` for all non-special tools (decision #4). Old's `_extract_filename` fallback is replaced. |
| `_show_summary` / `_show_full_content` / `_show_diff_content` | **K (RichUIHandler)** | Identical in both; keep one copy. |
| `_print_wrapped` | **A** | Old InteractiveUIHandler only. Keep (it supports `wrap_width`). Unchanged — it already uses `console.print` directly, no `_exit_live`. |
| `agent_spawned` | **A** | Old InteractiveUIHandler body, drop `_exit_live`: `console.print(f"[cyan]↳ Agent spawned:[/cyan] {name}")`. |
| `agent_finished` | **A** | Old InteractiveUIHandler body, drop `_exit_live`: `console.print(f"[dim]↳ Agent finished:[/dim] {name}")`. |
| `confirm_approval` | **A** | Old InteractiveUIHandler body, drop `_exit_live`. Uses `_get_or_create_session()` instead of `self._session` (lazy). No `erase_when_done` (audit trail). Reuses `_show_diff_content` (still present). |

### Imports after merge

```python
from prompt_toolkit.history import FileHistory, History, InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings, KeyPressEvent
from prompt_toolkit.shortcuts import PromptSession
from pyfiglet import Figlet
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.style import Style
```

`from yoker.ui.spinner import LiveDisplay` is gone. `rich.live`, `rich.status`, `rich.table`, `rich.text`, `rich.padding` (only used by spinner.py) leave with the module.

---

## Test Strategy

### Tests to delete

- `tests/test_ui/test_spinner.py` — LiveDisplay unit tests
- `tests/events/test_spinner.py` — LiveDisplay unit tests (duplicated location)

### Tests to rewrite

`tests/test_ui/test_interactive.py`:

| Existing test | New behavior |
|---------------|-------------|
| `test_init_defaults` asserts `handler._live is None` | Replace with: assert `handler._session is None` (lazy); assert no `_live` attribute; assert `_thinking_shown`/`_content_shown`/`_streaming_*` absent. |
| `test_prompt_session_created` asserts `handler._session is not None` post-`__init__` | Flip: assert `_session is None` post-`__init__`; assert non-None after `_get_or_create_session()` or first `get_input`. |
| `test_shutdown_exits_live_display` | Remove (no Live). Replace with `test_shutdown_prints_goodbye` only (already exists). |
| `TestInteractiveUIHandlerContentStreaming.*` (5 tests assert on `handler._live._response_text`) | Rewrite to assert on console output captured via `StringIO` — streaming now appends directly to the console. |
| `TestInteractiveUIHandlerThinkingStreaming.*` (4 tests assert on `handler._live._thinking_text` / `_spinner_active`) | Same — rewrite against console output. |
| `test_tool_call_exits_live_display`, `test_tool_result_creates_live_display` | Remove (no Live). Add: `test_output_tool_call_prints_inline_args` (assert `read path=/tmp/file.txt` style per decision #4), `test_output_tool_result_prints_size`. |
| `test_output_command_result` asserts `handler._live is None` | Drop the Live assertion; keep the `command output` substring assertion. |
| `test_output_stats_with_live_display` / `test_output_stats_resets_state` | Remove (no Live, no state flags). Keep `test_output_stats_without_live_display` and `_no_timing_data`; update expected format to RichUIHandler's `📊 1.5s, 150 tokens` if owner confirms (see Questions). |
| `test_output_error_exits_live_display` | Remove. |
| `test_output_tool_call_*` | Update expected text from `"\n⏺ Read tool: file.txt"` to RichUIHandler's `"⏺ read(path=/tmp/file.txt)"` form (decision #4). |

`tests/test_ui/test_handler.py`:

- Drop `LiveDisplay`, `live_display` imports and the two `assert ... is not None` lines.
- Keep `UIHandler`, `UIBridge`, `InteractiveUIHandler`, `BatchUIHandler` assertions.

`tests/test_bootstrap/test_history_security.py`:

- `assert handler._session is not None` after `__init__` → call `handler._get_or_create_session()` first, OR inspect `handler.history_file` only (the FileHistory/InMemoryHistory distinction can be checked via `_create_session()` directly, or via a new test-only hook). Simplest: call `_get_or_create_session()` then assert `isinstance(handler._session.history, InMemoryHistory)`. For `history_file=None` default test, just assert `handler.history_file == Path.home() / ".yoker_history"`.

`tests/test_ui/test_confirm_approval.py`:

- The `with patch("yoker.ui.interactive.PromptSession", return_value=stub_session)` around `__init__` no longer captures anything during `__init__` (lazy). The patch must remain active until `confirm_approval` calls `_get_or_create_session()`. Two options:
  1. Keep the `with patch(...)` block around the whole test body (not just `_make_interactive_handler`).
  2. Patch at module level for the test function and unpatch via `pytest` fixture.
- Recommended: change `_make_interactive_handler` to return the handler and have each test wrap its `await handler.confirm_approval(...)` call in `with patch(...)`. Cleaner: introduce a fixture that patches `PromptSession` for the whole test scope. The CI fix (the reason the patch exists) is still needed because `confirm_approval` does build a real `PromptSession` if not patched.
- With lazy init, the non-approval tests in `test_interactive.py` that previously needed the CI workaround no longer need it — they can construct `InteractiveUIHandler()` freely. Only tests that actually drive `get_input`/`get_secret_input`/`confirm_approval` need the patch.

### New tests

- `test_get_input_lazy_session`: `__init__` does not create a session; first `get_input` does.
- `test_get_input_predefined_does_not_create_session`: when `_input_source` is set, no session is built even after many `get_input` calls.
- `test_get_input_erases_and_renders_panel`: assert that `output_prompt` is called (or that the Panel appears in console output) after `get_input` returns a non-empty string.
- `test_get_secret_input_no_panel`: assert no Panel rendered for secret input.
- `test_get_input_empty_does_not_render_panel` (if owner confirms the empty-skip rule).
- `test_start_lists_tools_in_banner`: assert `Tools:` line present when `agent.tools` non-empty (decision #4).
- `test_output_tool_call_inline_args`: assert `read(path=/tmp/file.txt content=...)` style.
- `test_output_tool_result_shows_size`: assert `(N chars)` suffix.
- `test_shutdown_no_live_attribute`: `assert not hasattr(handler, "_live")`.

---

## File List

### Modified

- `src/yoker/ui/interactive.py` — rewrite as described.
- `src/yoker/ui/__init__.py` — drop `LiveDisplay`, `live_display` from imports and `__all__`.
- `tests/test_ui/test_interactive.py` — rewrite per table above.
- `tests/test_ui/test_handler.py` — drop LiveDisplay/live_display imports + assertions.
- `tests/test_bootstrap/test_history_security.py` — adapt to lazy `_session`.
- `tests/test_ui/test_confirm_approval.py` — extend patch scope to cover `confirm_approval` call.

### Deleted

- `src/yoker/ui/spinner.py`
- `tests/test_ui/test_spinner.py`
- `tests/events/test_spinner.py`

### New

- (None — no new modules.)

### Unchanged (verified not to touch LiveDisplay/_session internals)

- `src/yoker/cli/chat.py` — uses `hasattr(ui, "confirm_approval")`; works as-is.
- `src/yoker/cli/init.py` — `InteractiveUIHandler(history_file="none")`; works as-is.
- `scripts/demo_session.py` — uses `set_input_messages` + `ui.console.print`; works as-is (predefined path never builds a session).
- `src/yoker/ui/batch.py`, `bridge.py`, `handler.py` — untouched.

---

## Acceptance Criteria

1. `InteractiveUIHandler` no longer imports `LiveDisplay` or references `_live`, `_ensure_live`, `_exit_live`, `_end_turn`, `_thinking_shown`, `_content_shown`, `_streaming_content`, `_streaming_thinking`.
2. `src/yoker/ui/spinner.py` is deleted; `from yoker.ui import LiveDisplay, live_display` raises `ImportError`.
3. `tests/test_ui/test_spinner.py` and `tests/events/test_spinner.py` are deleted.
4. `InteractiveUIHandler.__init__` does not construct a `PromptSession` — `handler._session is None` immediately after `__init__`.
5. First `get_input` / `get_secret_input` / `confirm_approval` call constructs the session; subsequent calls reuse it. Predefined-input path (`set_input_messages`) never constructs one.
6. `get_input` uses `erase_when_done=True` and renders `output_prompt(result)` for non-empty input; `get_secret_input` uses `erase_when_done=True` and does not render a Panel.
7. `output_tool_call` prints inline `key=value` args (RichUIHandler format), not the old `"\n⏺ Read tool: <filename>"` form.
8. `output_tool_result` prints `(N chars)` size suffix on success.
9. `start` banner includes a `Tools: ...` line when `agent.tools` is non-empty.
10. `shutdown` prints `Goodbye!` and does not call `_exit_live`.
11. `output_step_title`, `output_command_result`, `output_content`, `confirm_approval`, `agent_spawned`, `agent_finished`, `_print_wrapped` are all present and use `console.print` directly (no Live).
12. `make check` passes (format, lint, typecheck, test).
13. `make test` passes with the rewritten/removed test files.
14. Manual: `python -m yoker` (interactive) on a TTY shows the banner with Tools, accepts input, erases the input line on Enter, renders the user's message as a Panel, streams content without a spinner, and exits cleanly with `Goodbye!`.

---

## Questions for the Owner

1. **Empty input Panel**: When `get_input` returns `""` (user hits Enter with no text), should `output_prompt` render an empty Panel, or should we skip the Panel for empty input? Default proposal: skip when `result.strip() == ""` to avoid an empty Panel cluttering the scrollback.

2. **Stats format**: RichUIHandler's `output_stats` prints `"📊 1.5s, 150 tokens"` (no tokens/sec). Old InteractiveUIHandler prints `"⏱ 1.5s | 50+100=150 tokens | 100 tok/s"`. Decision #4 says "output improvements kept from RichUIHandler" — does that include the simpler stats line, or should the richer `⏱ ... | tok/s` form be preserved? Default per decision #4: keep RichUIHandler's simpler form.

3. **Banner thinking hint**: RichUIHandler's banner shows `Thinking: <mode>` only. Old InteractiveUIHandler shows `Thinking: <mode> (use /think on|off|silent to toggle)`. Keep the hint, or drop it for parity with RichUIHandler? Default: drop it (RichUIHandler as base).

4. **`confirm_approval` patch scope in tests**: With lazy init, the existing `with patch("yoker.ui.interactive.PromptSession", ...)` in `test_confirm_approval.py` must widen to cover the `confirm_approval` call (not just `__init__`). Acceptable to change `_make_interactive_handler` to a fixture that patches for the whole test, or prefer the inline `with patch(...)` per test?

5. **`yoker.ui` public API**: Removing `LiveDisplay`/`live_display` from `yoker.ui.__init__` is a (minor) breaking change to the public surface. No internal caller uses it. Confirm acceptable, or keep a shim that re-raises a clear `ImportError` with a migration message for one release?