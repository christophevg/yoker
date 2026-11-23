# Yoker

> A Python-first agent harness framework — one who yokes agents together.

## Overview

Yoker is a library-first, event-driven agent harness for Python that integrates with multiple LLM providers. It provides a transparent, configurable runtime for AI agents with structured tool execution, guardrails, event emission, and a pluggable UI layer. Unlike CLI-first agent frameworks, Yoker is designed to be embedded in applications with full visibility into agent operations.

Key differentiators:
- **Library-first** — Embed in applications, not locked into a CLI
- **Multi-provider** — Ollama (native SDK), OpenAI, Anthropic, Gemini, and 100+ providers via LiteLLM
- **Event-driven** — Subscribe to thinking, content, and tool events
- **UI layer** — Swap interactive TUI, batch mode, or custom handlers
- **Plugin system** — Load namespaced tools, skills, and agents from Python packages
- **Async-native** — All I/O operations are async
- **Static permissions** — Deterministic boundaries via configuration
- **Transparent** — All prompts visible, editable, configurable

## Version Notes

### 0.13.0

**New Features:**
- **Configurable compaction pipeline**: context overflow no longer drops
  messages outright — a stage pipeline runs first (`prune_tool_results`
  stubs old large tool-result bodies, `prune_thinking` flags old
  reasoning payloads, `force_stub_tool_results` age-blind stubs any
  remaining oversized tool result, `cutoff` drops the oldest non-setup
  messages as a backstop), stopping as soon as the estimate is under
  `max_tokens * context.compact_ratio`. Stages and thresholds are
  configured via the new `[context.compaction]` TOML section (empty
  `strategies` disables compaction); cutoff protects setup windows and
  clamps its target to a floor (`floor_tokens`, default 10% of
  `max_tokens`). Each run is recorded in the session JSONL as a
  `compaction` record; inspect with
  `python scripts/context_report.py <session.jsonl> [--json]`.
- **Run statistics (telemetry + `yoker:stats` tool)**: the
  `~/.yoker/usage.jsonl` log becomes the harness telemetry log — every
  record gains `agent_id` + `parent_agent_id` and a `kind` (`llm_call`,
  `tool_call`, `turn`, `spawn`, `release`, `compaction`, `error`), so tool
  calls (success/duration/I-O bytes), turn wall-clock, spawn/release
  lifecycle, compaction runs and operational errors are attributable
  per-agent. The new Session-injected `yoker:stats` tool reports
  per-scope (`self` / `subtree` / `session`) counts with an optional ISO
  `since` watermark for delta mode, plus spawn/release counts and peak
  agent concurrency on `session` scope; every `Session` writes a
  `run_start`/`run_end` bracket — a bare `run_start` means the process
  crashed.
- **Turn abort (Esc+Esc)**: in the interactive CLI, pressing `Esc` twice
  within ~0.6 s while a turn runs aborts it cleanly — the agent stays
  alive and the session returns to the prompt; a running tool finishes
  and its result is kept while the remaining tool calls of the batch are
  recorded as aborted. New public API surface: `Agent.abort() -> bool`,
  `Session.abort_foreground()`, exception `yoker.TurnAbortedError` and
  event `yoker.TurnAbortedEvent`; `Ctrl+C` during a turn requests the
  same clean abort (a second press force-exits).
- **Harness-provided bindings channel**: embedding code (the harness) can
  feed live operating-context resources (e.g. a provider session) to the
  tools an agent executes, without per-agent tool re-registration — new
  `Binding` frozen key/value protocol in `yoker.tools.context`,
  `Agent(context_vars=...)` plus chainable `bind()`, merged and
  propagated (copy-not-reference) to spawned agents via
  `Session(context_vars=...)`.
- **Host-side tool-argument hook**: `Agent` gains an optional
  `tool_args_hook` constructor kwarg (sync or async callable) invoked on
  every dispatched tool call; it may replace the arguments or keep them,
  and runs after tool-spec resolution but before coercion/tilde-expansion
  so hook-injected values get the same normalizing treatment. Fail-safe
  by design: a missing, raising or invalid-return hook never breaks a
  tool call. `Session` propagates it to spawned agents; the `agent()` /
  `session()` facades accept the kwarg.
- **Image file reading for vision models**: `read` on an image file
  (png/jpg/jpeg/gif/webp/bmp) attaches it as a path reference on the tool
  message — the Ollama backend serializes to base64 at submission time,
  so only the path is persisted (the litellm backend strips the `images`
  key for cross-backend resume safety). Image refs are sent once: refs
  from tool messages predating the most recent assistant message are
  dropped, so long conversations stop re-sending the base64 payload
  every turn.
- **Websearch output-size protection**: every result's snippet is capped
  at 500 chars with a visible `… (+N chars truncated — use webfetch on
  the URL for full content)` marker, and the total serialized result is
  capped by the new `tools.websearch.max_output_kb` knob (default 50KB) —
  when the budget is hit, `truncated` + `total_hits` are set and a remedy
  hint names the options (fewer results, more specific query, webfetch a
  URL).
- **Search output-size protection**: every rendered content/context line
  is capped at 500 chars with a visible `… (+N chars truncated)` marker,
  and the total serialized result is capped by the new
  `tools.search.max_output_kb` knob (default 50KB) — closes the hole
  where a single giant line (minified JS, data URIs) produced a
  352K-char result consuming the context.
- **Calling-agent identity in `ToolContext`**: tools can identify their
  caller via `ctx.agent` — a new `AgentInfo` frozen dataclass (re-exported
  from `yoker.tools`) carrying the runtime `id` and the agent definition
  name; strings only, so `ToolContext` stays Session-agnostic.
- **Plugin tool config bootstrap**: plugins declare a typed
  `config_class` in their manifest; a bootstrap probe augments the config
  schema with one field per plugin before the normal config load, and
  plugin tools receive the plugin's config instance as `ctx.config`
  (`config.tools.<plugin>.<tool>`), with `enabled` gating via the
  `ToolConfig` base class.
- **Schema-aware per-value argument coercion at dispatch**: degraded
  argument shapes emitted by models (stringified scalars like
  `{"limit": "100"}`, JSON-stringified objects) are coerced to the
  declared schema type at the dispatch choke point, while legitimate
  JSON-string payloads (e.g. `write(content='{"key": "value"}')`) pass
  through verbatim — replacing the blunt Ollama workaround that mangled
  such content ("Invalid content parameter").
- **Generic tool-result preview on success lines**: a successful tool
  call renders a compact preview of its result under the
  `✓ Success (N chars)` line (first 3 lines by default, long single-line
  results collapse to `head…tail`), configurable via the new
  `[content] tool_result_preview_lines` setting (0 disables) and
  suppressed when the tool also emits rich owner-facing content.
- **`--resume last`**: `yoker chat --resume last` resumes the most
  recently active session.
- **Primary agent as a real definition file**: the default primary agent
  loads from `yoker/agents/definitions/primary.md` inside the package
  (registered as `yoker:primary`) instead of a synthetic definition, so
  it can be fine-tuned like any other agent definition; a user/config/
  plugin definition named `primary` overrides the built-in.
- **`update` anchor-duplication guard**: ambiguous (repeated) anchors are
  rejected loudly with their match line numbers, an explicit
  `allow_duplicate_anchor` escape hatch covers intentional duplication,
  and inserts terminate cleanly at EOF.
- **Weekday in the system prompt date**: e.g. "Thursday, 2026-09-10", so
  agents know the day of week.

**Changes:**
- **`make` tool accepts path-style targets**: target names may contain
  `/` (e.g. `docs/html`, `build/all`) — previously rejected. The target
  pattern is now the public shared constant `yoker.config.MAKE_TARGET_RE`,
  used by both the make tool and the `[tools.make.allowed_env_vars]` key
  validation. Security surface unchanged: leading character must be
  alphanumeric, shell metacharacters are rejected, and the invocation
  remains a no-shell list-argv subprocess.
- **Python 3.10 dropped, 3.13 and 3.14 added** (breaking — see the
  migration guide): `requires-python` is now `>=3.11`; CI and tox run
  3.11/3.12/3.13/3.14. Dropping 3.10 unlocks equivalent modernizations
  (builtin `TimeoutError`, `datetime.UTC`, `enum.StrEnum`) and removes
  the `tomli` backport dev-dependency.
- **Tool descriptions use the docstring's first paragraph**: registration
  no longer cuts the description at the first physical docstring line, so
  tools whose summary sentence wraps keep their stated behavioral
  contracts.
- **Agent-feedback triage improvements**: the no-shell reminder names the
  Makefile/`make` tool as the execution environment (while barring shell
  smuggling into targets); `make` results lead with `verdict`/`outcome`
  fields exempt from `post_filter`; `update`/`write` distinguish a true
  no-op from "applied but identical"; content search skips cache dirs and
  binary junk (`include_binaries=true` is the explicit opt-in, floor
  suppressions counted in `hidden_by_ignore`).
- **`read` offset error states 1-indexed numbering**: the out-of-range
  error explicitly states line numbers are 1-indexed and that 1 is the
  first line.

**Removed:**
- **`update` tool flexible matching** (breaking — see the migration
  guide): the `require_exact_match` tool parameter and the
  `tools.update.require_exact_match` config field are gone; matching is
  now always byte-exact and unique-occurrence, and configs setting the
  removed field hard-fail. Near-matches are refused with the closest real
  line as feedback instead of being applied.
- **Dead `permissions.network_access` config field**: never enforced by
  any tool, guardrail or setup code — its only runtime effect was
  rendering a false reminder; remove it from `yoker.toml` if present.

**Fixed:**
- **Path guardrails never matched on Windows**: glob denylists compiled
  to regexes that only understand `/` while match candidates kept
  backslashes — writes to protected files were silently allowed on
  Windows. Absolute candidates are now POSIX-normalized (`as_posix()`)
  and `**/` compiles to zero-or-more segments; pinned by
  `TestGlobToRegexSemantics`.
- **Guardrail denylist depth bypass**: bare default-denylist patterns
  (`Makefile`, `.git`, `.env`, ...) only matched at the top level of an
  allowed root; all security-sensitive defaults now use the `**/` prefix
  so they protect at any depth (bare patterns keep their root-only
  semantics).
- **Ollama backend ignored `backend.ollama.parameters`**: configured
  parameters (temperature, top_p, top_k, num_ctx, ...) were parsed and
  documented but never forwarded; `chat_stream` now flattens them into
  the request's `options` mapping.
- **Context-log append timestamps**: context JSONL records carried the
  file-rewrite time, so every line in a resumed session shared one
  timestamp; records now carry their true append time, and a bare resume
  no longer bumps the session's last activity (`list_sessions` /
  `--resume last` sort by real conversation activity).
- **Rich markup injection via filenames**: filenames containing square
  brackets (e.g. `report[red].txt`) were interpolated unescaped into
  display headers, so Rich interpreted them as style tags; filenames are
  now escaped via a shared `escape_rich_markup` helper.
- **Compaction panel contradicted itself on dropped messages**: the
  headline counted only the `cutoff` stage while the per-stage total
  summed all stages; with stage data both handlers now headline the
  all-stage total ("Trimmed N message(s)").
- **Bare-generic tool annotations destroyed parameter typing**: a bare
  generic annotation (`dict[str, str] | None`) collapsed to `str` and
  declared the wrong JSON type; the `Annotated`-strip is now gated on
  `__metadata__` (root cause of the tool-parameter schema bug chain).
- **Leading `~` in path-guarded arguments is expanded before the
  guardrails**: `~/...` paths previously stayed relative and failed with
  "Path not found"; expansion happens before the approval hook and
  guardrails, so the allowlist validates the real post-expansion path.
- **Session-injected tools respect `tools:` grants**: `agent`,
  `send_message` and `release_agent` were registered after the definition
  filter ran, so every session agent saw them regardless of declared
  grants — breaking least-privilege; the filter is re-applied after
  injection (see the migration guide).
- **`write`/`update` type-mismatch errors are self-correcting**: the
  error names the actual runtime type and the remedy instead of causing
  blind retry loops.
- **Session listing reports the bare session id** (not the JSONL file
  stem) and sorts by last activity.

### 0.12.0

**New Features:**
- **`update` tool anchor-based insert**: new `anchor` + `position`
  (`after`/`before`) parameters insert content relative to a unique
  anchor; ambiguous anchors are rejected with their match line numbers,
  and an explicit anchor overrides `line_number`.
- **GitHub write operations expanded**: new `issue_comment`, `issue_edit`
  (labels, assignees, state changes), and `label_create` operations; and
  `repo` is now optional for all write operations — like the read
  operations, gh auto-detects the repository from the current git remote.
- **Token usage tracking**: every LLM API call appends a JSONL record
  (timestamp, session, model, agent, input/output tokens, duration) to
  `~/.yoker/usage.jsonl` (`[usage]` config, enabled by default).
- **Effective-configuration summary**: the environment reminder embeds a
  curated, redacted snapshot of the effective configuration — permission
  grants, filesystem paths, write-protection, backend + model, trusted
  plugins — so agents see config effects instead of discovering them via
  tool rejections.
- **Retry-limit escalation**: after `agent.max_consecutive_tool_failures`
  (default 3, `0` disables) consecutive failed tool calls, a one-time
  system-side note tells the model to stop retrying and reconsider
  strategy or ask the user.

**Changes:**
- **`write` tool `create_parents` defaults to True**: writing to a path
  with non-existing parents creates them automatically (`mkdir -p`
  semantics); pass `create_parents=false` for strict behavior.
- **`update`/`write` results include a diff** — a stat line (+N −M) plus
  a unified diff (60-line cap) of the applied change, so callers can
  validate the edit without a read-after-write round trip.
- **Agent boundary awareness**: spawned agents start with a FRESH context
  (context files and system prompt pre-loaded, no conversation history —
  prompts must be fully self-contained), and persistent agents
  (`ephemeral=False`) occupy a session slot until released.
- **Generic approval prompts**: tools can provide an approval-prompt
  builder via `__yoker_approval__` (discovered into
  `ToolSpec.approval_prompt`); the protected-path approval flow is fully
  generic with an honest default for provider-less tools.
- **Descriptive invalid-argument errors**: tool calls failing on wrong
  or missing arguments state what was wrong and list the expected
  arguments, so the model can self-correct instead of blind-retrying.

**Removed:**
- **`session.default_isolation_policy` config field** — declared but
  fork was never implemented; the spawn path always builds a fresh
  context manager. Remove it from `yoker.toml` if present.

**Fixed:**
- **list/search hidden-entry reporting**: a bare "0 entries"/"no
  matches" now appends visible reporting of entries suppressed by ignore
  rules (`list`: hidden-entries note + `hidden_entries` metadata;
  `search`: `hidden_by_ignore` + a retry hint with `include_ignored=true`).
- **Bare-name tool dispatch**: a bare tool name (`list`) now resolves
  via `ToolRegistry.resolve()` fallback; ambiguous matches raise an
  error listing the full namespaced names.
- **update tool `line_range` inference fix**: line-based replaces are no
  longer silently appended at end of file; inferred operations name
  themselves in the result.

## Migration Guides

### From 0.12.x to 0.13.x

Three breaking changes; most installations also need one agent-definition
check. Everything else is opt-in.

**Breaking Changes:**
- **Python 3.10 support dropped**: `requires-python` is now `>=3.11`
  (CI/tox run 3.11/3.12/3.13/3.14). Upgrade Python before upgrading;
  no code changes are needed on 3.11+ — the unlocked modernizations
  (builtin `TimeoutError`, `datetime.UTC`, `enum.StrEnum`) are verified
  equivalent for all consumers.
- **`update` tool flexible matching removed**: the `require_exact_match`
  tool parameter and the `tools.update.require_exact_match` config field
  are gone; matching is now always byte-exact and unique-occurrence.
  Configs setting the removed field hard-fail.
  Near-matches are refused with the closest real line as feedback
  instead of being applied.
- **`permissions.network_access` config field removed**: the field was
  never enforced by any tool, guardrail or setup code — remove it from
  `yoker.toml` if present.

```toml
# Before (0.12.x)
[permissions]
network_access = false

[tools.update]
require_exact_match = true

# After (0.13.x)
# (both sections removed)
```

**Behavior change to verify:**
- **Session-injected tools now respect `tools:` grants**: `agent`,
  `send_message` and `release_agent` were previously registered after
  the definition filter, so every session agent had them regardless of
  its declared grants. Definitions without a `tools:` list keep the
  default all-granted behavior; definitions with an **explicit**
  `tools:` list must now name these tools to retain them, and
  `tools: []` agents get none.

## Overview

## Installation

```bash
pip install yoker
```

Optional extras for content type detection using `python-magic`:

```bash
pip install yoker[magic]
```

## Quick Start

### Interactive CLI

```bash
python -m yoker
```

Loads `yoker.toml` from the current directory if present, then `~/.yoker.toml`,
then built-in defaults.

### Batch mode

```bash
echo "Summarize README.md" | python -m yoker --ui-mode batch
```

### With an agent definition

```bash
python -m yoker --agents-definition examples/agents/researcher.md
```

### With a plugin

```bash
printf "Summarize README.md" | python -m yoker --ui-mode batch --agents-definition examples/agents/researcher.md --with pkgq
```

## Library Usage

### Python API (recommended)

The top-level `yoker` package exposes a thin Pythonic facade over the `Agent`
and `Session` classes:

| Function | Use |
|----------|-----|
| `yoker.process(prompt, **kwargs)` | One-shot turn; returns the response string. |
| `yoker.do(skill_name, prompt, args="", **kwargs)` | One-shot skill invocation. |
| `yoker.agent(**kwargs) -> Agent` | Builder that returns a reusable `Agent`. |
| `yoker.session(id=..., *, persist=True, fresh=False, **kwargs)` | Async context manager yielding a multi-turn `Session` with context persistence. |
| `yoker.run_sync(coro)` | Wraps `asyncio.run` for synchronous callers (scripts, notebooks, REPLs). |

All builder kwargs (`model`, `provider`, `system_prompt`, `tools`, `skills`,
`plugins`, `thinking`, `event_handler`, `config`, ...) are accepted by `process`,
`do`, `agent`, and `session`.

One-shot, single response:

```python
import asyncio
import yoker

async def main():
    answer = await yoker.process("What is 2+2?")
    print(answer)

asyncio.run(main())
```

Synchronous caller (scripts, notebooks):

```python
import yoker

answer = yoker.run_sync(yoker.process("What files are in the current directory?"))
print(answer)
```

A reusable, configured agent:

```python
import asyncio
import yoker
from yoker.events import ToolCallEvent

async def main():
    reviewer = yoker.agent(
        model="qwen3.5:cloud",
        system_prompt="You are a security-focused code reviewer. Cite file:line.",
        tools=["read", "search", "list"],
        thinking="visible",
    )

    def log_tools(event):
        if isinstance(event, ToolCallEvent):
            print(f"[tool] {event.tool_name}({event.arguments})")

    reviewer.on_event(log_tools)

    report = await reviewer.process("Review src/yoker/plugins/security.py for vulnerabilities.")
    print(report)

asyncio.run(main())
```

Multi-turn conversation with automatic context persistence:

```python
import asyncio
import yoker

async def main():
    async with yoker.session(id="refactor-auth") as session:
        await session.agent.process("Read src/auth.py and identify the main responsibilities.")
        await session.agent.process("Suggest a refactor that splits authentication from session management.")

asyncio.run(main())
```

Invoke a skill by name as a one-shot command:

```python
import asyncio
import yoker

async def main():
    result = await yoker.do("commit", "stage and commit current changes")
    print(result)

asyncio.run(main())
```

For the full set of examples, see `examples/python_api/` (`one_shot.py`,
`agent_builder.py`, `session.py`, `run_skill.py`, `workflow.py`,
`event_handling.py`, `sync_usage.py`).

### Low-level event-driven API (advanced)

For full control — custom rendering, non-terminal surfaces, or when you need
to drive the UI lifecycle yourself — use the `Agent` class directly with a
`UIHandler` and `UIBridge`.

```python
import asyncio
from yoker import Agent
from yoker.config import get_yoker_config
from yoker.ui import BatchUIHandler, UIBridge

async def main():
    config = get_yoker_config(cli=False)
    agent = Agent(config=config)

    ui = BatchUIHandler(show_thinking=True, show_tool_calls=True)
    bridge = UIBridge(ui)
    agent.on_event(bridge)

    await ui.start(agent)
    try:
        await agent.process("What is 2+2?")
    finally:
        await ui.shutdown("complete")

asyncio.run(main())
```

### Direct event handler

```python
import asyncio
from yoker import Agent
from yoker.events import ContentChunkEvent, Event, ToolCallEvent

async def handler(event: Event) -> None:
    if isinstance(event, ContentChunkEvent):
        print(event.text, end="", flush=True)
    elif isinstance(event, ToolCallEvent):
        print(f"\n[tool] {event.tool_name}({event.arguments})")

async def main():
    agent = Agent()
    agent.on_event(handler)
    await agent.process("What is 2+2?")

asyncio.run(main())
```

### Custom UI handler

Implement the `UIHandler` protocol and wire it to the agent with `UIBridge`:

```python
from typing import Any
from yoker import Agent
from yoker.ui import AgentDisplay, UIHandler

class MyUIHandler:
    """A minimal UIHandler implementation for custom integrations."""

    async def start(self, agent: Agent) -> None:
        print(f"Session started: {agent.model}")

    async def shutdown(self, reason: str) -> None:
        print(f"Session ended: {reason}")

    async def get_input(self, prompt: str = "> ") -> str | None:
        return input(prompt)

    async def get_secret_input(self, prompt: str = "> ") -> str | None:
        return input(prompt)

    def output_info(self, text: str) -> None:
        print(text)

    async def output_step_title(self, step: int, total: int, title: str) -> None:
        print(f"Step {step}/{total}: {title}")

    def output_content(self, content: str, content_type: str = "text/plain") -> None:
        print(content)

    def output_command_result(self, result: str) -> None:
        print(result)

    def output_thinking(self, text: str) -> None:
        print(text)

    def output_tool_call(self, tool_name: str, args: dict[str, object], agent: AgentDisplay | None = None) -> None:
        print(f"Tool: {tool_name}({args})")

    def output_tool_result(self, tool_name: str, success: bool, result: str) -> None:
        status = "OK" if success else "FAIL"
        print(f"Result: {status} {tool_name} -> {result}")

    def output_tool_content(
        self,
        tool_name: str,
        operation: str,
        path: str,
        content: str | None,
        content_type: str,
        metadata: dict[str, object],
    ) -> None:
        print(f"{tool_name} {operation} {path}")

    def output_stats(self, duration_ms: int, prompt_tokens: int, eval_tokens: int, usage_limits: dict[str, object] | None = None, agent: AgentDisplay | None = None) -> None:
        print(f"Stats: {duration_ms}ms, {prompt_tokens} + {eval_tokens} tokens")

    def output_error(self, error: Exception, include_traceback: bool = False) -> None:
        print(f"Error: {error}")

    def start_content_stream(self, agent: AgentDisplay | None = None) -> None:
        pass

    def stream_content(self, chunk: str, content_type: str = "text/plain") -> None:
        print(chunk, end="", flush=True)

    def end_content_stream(self, total_length: int) -> None:
        print()

    def start_thinking_stream(self, agent: AgentDisplay | None = None) -> None:
        pass

    def stream_thinking(self, chunk: str) -> None:
        print(chunk, end="", flush=True)

    def end_thinking_stream(self, total_length: int) -> None:
        print()
```

## Key Components

### `yoker.Agent` (from `yoker.core`)

The async agent that chats with model backends and uses tools.

```python
from yoker import Agent

agent = Agent(agent_path="agents/researcher.md")

print(agent.model)          # Resolved model name
print(agent.tools.names)    # Available tools (namespaced)
print(agent.context)        # Conversation history
print(agent.definition)     # Loaded agent definition (if any)
print(agent.skills.names)   # Available skills (namespaced)
```

**Key methods:**
- `process(message)` — Process a message, handle tool calls, return response
- `do(skill_name, prompt, args="")` — Inject a skill and process the prompt
- `on_event(handler)` — Subscribe to events (returns the handler for chaining)
- `inject_skill_context(skill_name, args)` — Inject a skill into the conversation

### `yoker.Session` (from `yoker.session`)

Multi-turn session construct: an async context manager owning a team of agents.
The primary agent is available via `Session.agent`; sub-agents can be spawned
via `Session.spawn()`. Inter-agent messaging uses
`Session.send(*, to, from_, content)` with plain strings.

```python
from yoker import Session
from yoker.config import get_yoker_config

config = get_yoker_config(cli=False)

async with Session(config=config) as session:
    await session.agent.process("Analyze the codebase.")
    # Spawn a sub-agent for a specialized task
    researcher = await session.spawn("researcher")
    response = await researcher.process("Summarize README.md")
    # Inter-agent messaging
    reply = await session.send(to=researcher, from_=session.agent, content="Follow up?")
```

### UI layer

- `yoker.ui.UIHandler` — Protocol defining the UI interface
- `yoker.ui.UIBridge` — Event dispatcher that converts agent events into UI method calls
- `yoker.ui.InteractiveUIHandler` — Terminal UI using `prompt_toolkit` and Rich
- `yoker.ui.BatchUIHandler` — Non-interactive UI using stdin/stdout/stderr
- `yoker.ui.commands.CommandRegistry` — Slash-command registry

Attach a UI to an agent:

```python
from yoker.ui import UIBridge

bridge = UIBridge(ui)
agent.on_event(bridge)
```

### `yoker.config.get_yoker_config`

Load configuration via Clevis. Use this only when you need to customize configuration programmatically; otherwise `Agent()` discovers `yoker.toml` automatically.

```python
from yoker.config import get_yoker_config

# Library mode (no CLI args)
config = get_yoker_config(cli=False)

# CLI mode (parse sys.argv)
config = get_yoker_config(cli=True)
```

Configuration discovery order (highest to lowest priority):
1. CLI arguments (when `cli=True`)
2. `./yoker.toml` — current directory
3. `~/.yoker.toml` — user home directory
4. Default values from `Config`

### `yoker.context.ContextManager`

- `SimpleContextManager` — In-memory conversation history (from `yoker.context.basic`)
- `Persisted` — JSONL-persisted session context (wraps a base context manager, from `yoker.context.persisted`)

```python
from yoker import Agent
from yoker.context import SimpleContextManager, Persisted

# In-memory context
context = SimpleContextManager()

# Persisted JSONL context
context = Persisted(SimpleContextManager(), session_id="my-session")

agent = Agent(context_manager=context)
```

### `yoker.events`

```python
from yoker.events import (
    Event,
    EventType,
    TurnStartEvent,
    TurnEndEvent,
    ThinkingStartEvent,
    ThinkingChunkEvent,
    ThinkingEndEvent,
    ContentStartEvent,
    ContentChunkEvent,
    ContentEndEvent,
    ToolCallEvent,
    ToolContentEvent,
    ToolResultEvent,
    CommandEvent,
)
```

**Event types:**
- `TURN_START/END` — Turn lifecycle (user message to response)
- `THINKING_START/CHUNK/END` — LLM reasoning trace
- `CONTENT_START/CHUNK/END` — Response text streaming
- `TOOL_CALL/RESULT/CONTENT` — Tool execution and display
- `COMMAND` — Slash-command result

Handlers are plain callables that receive `Event` objects. Register them with
`agent.on_event(...)` (or `session.on_event(...)` for session-scoped handlers).

### Tools

Yoker tools are plain Python functions or callable classes. There is no base class to inherit from. The framework introspects the callable's signature and `Annotated` parameter markers to derive the tool name, description, JSON schema, and guardrail mapping.

```python
from typing import Annotated
from yoker.tools.annotations import ReadPath, Text
from yoker.tools import ToolRegistry

def read_file(
    path: Annotated[str, ReadPath("Path to the file to read")],
    encoding: Annotated[str, Text("File encoding")] = "utf-8",
) -> str:
    """Read a file and return its contents."""
    with open(path, encoding=encoding) as f:
        return f.read()

registry = ToolRegistry()
registry.register(read_file)
```

A callable class works the same way: `registry.register(MyTool())` reads the instance's `__call__` signature. Use the optional `@tool(name=..., description=...)` decorator from `yoker.tools.annotations` to override the name or description inferred from the callable.

Built-in tools are registered under the `yoker:` namespace. See the [Tools List](#tools-list) for all available tools.

### Guardrails

Yoker uses a schema-driven guardrail system. String parameters are annotated with a marker from `yoker.tools.annotations`:

| Marker | Guardrail applies to |
|--------|----------------------|
| `ReadPath` | Filesystem paths used read-only (`ReadPathGuardrail`) |
| `WritePath` | Filesystem paths used for writing (`WritePathGuardrail`) |
| `Url`  | URLs (`WebGuardrail.validate_url`) |
| `Query` | Web search queries (`WebGuardrail.validate`) |
| `Text` | Plain text; no guardrail |

When a callable is registered, `build_tool_spec()` extracts the marker from each `Annotated[str, Marker(...)]` parameter and stores its functional type in the resulting `ToolSpec.guards`. The marker description is kept in the JSON schema; the guardrail metadata is stripped before the schema is sent to the model. At execution time, the harness dispatches the matching guardrail centrally, so the tool itself stays a plain function.

Plugin and custom tool authors should annotate all string parameters with the appropriate marker. Plain `str` parameters without a marker are accepted but produce a warning, indicating that the parameter is not covered by a guardrail.

### Agent Definitions

Markdown files with YAML frontmatter:

```markdown
---
name: Researcher
description: A research assistant
tools:
  - yoker:read
  - yoker:search
  - yoker:websearch
model: qwen3.5:cloud
---

You are a research assistant. Your role is to help users find
and synthesize information from various sources.
```

```python
from yoker import Agent

agent = Agent(agent_path="agents/researcher.md")
```

Tool references in agent definitions follow these rules:

- **Built-in tools** may be referenced with or without the `yoker:` prefix (e.g., `read` or `yoker:read`).
- **Built-in tool matching is case-insensitive** (e.g., `Read`, `READ`, and `read` all resolve to the same tool).
- **Plugin tools** must always be referenced with their full namespace prefix (e.g., `pkgq:search`).
- A warning is logged at agent load time for any requested tool that is not available in the final registry.

Agent definitions can also be loaded from plugins. Load the plugin with
`--with <pkg>` and reference the agent by name (resolved through the
agent registry populated from configured directories and loaded plugins):

```bash
python -m yoker --with pkgq --agent researcher
```

A bare name matches a unique agent `simple_name` across namespaces; a
namespaced name (`pkgq:researcher`) matches exactly. Loading a plugin
requires `[plugins] enabled = true` and the package to be trusted (see
`[plugins.trusted]`).

### Plugins

Plugins are Python packages that expose tools, skills, and agents through a top-level `__YOKER_MANIFEST__` object. Tools are provided as functions or callable class instances.

```python
from typing import Annotated
from yoker.tools.annotations import Text
from yoker.plugins import PluginManifest

def echo(message: Annotated[str, Text("Message to echo")]) -> str:
    """Echo back the input message."""
    return f"Echo: {message}"

__YOKER_MANIFEST__ = PluginManifest(
    tools=[echo],
)
```

Load via CLI:

```bash
python -m yoker --with pkgq --with c3
```

Or via `yoker.toml`:

```toml
[plugins]
enabled = true

[plugins.trusted]
pkgq = true
```

Plugin components are namespaced:

- Tools: `pkgq:search`
- Skills: `pkgq:commit`
- Agents: `pkgq:researcher`

## Common Patterns

### Logging

By default, both library and CLI usage are quiet (WARNING level and above).
`Agent()` automatically applies the `[logging]` settings from the loaded
`yoker.toml` (or defaults) the first time it initializes, unless logging has
already been configured explicitly (for example by `python -m yoker`).

To enable informational logs, set the level in `yoker.toml`:

```toml
[logging]
level = "INFO"
```

Programmatically:

```python
from yoker.logging import configure_logging
configure_logging(level="INFO")
```

### Loading configuration programmatically

```python
from yoker import Agent
from yoker.config import get_yoker_config

config = get_yoker_config(cli=False)
agent = Agent(config=config)
```

### Custom UI handler

Implement the `UIHandler` protocol, implement the methods, and wire with `UIBridge`. See the [Custom UI handler](#custom-ui-handler) example above.

### Batch processing

```python
from yoker import Agent
from yoker.ui import BatchUIHandler, UIBridge

agent = Agent()
ui = BatchUIHandler(show_tool_calls=True)
agent.on_event(UIBridge(ui))

ui.set_input_messages([
    "Read README.md",
    "Summarize it in one paragraph",
])
```

### Plugin skill invocation

Skills can be invoked via slash command or by the LLM through the `yoker:skill` tool:

```text
/commit write a concise commit message
```

Or programmatically:

```python
agent.inject_skill_context("pkgq:commit", "write a concise commit message")
```

### Subagent spawning

The `yoker:agent` tool spawns subagents with a FRESH context — project
context files and the agent's system prompt are pre-loaded, but there is
no conversation history, so prompts must be fully self-contained.
Sub-agents inherit guardrails from their parent. Persistent agents
(`ephemeral=False`) occupy a session slot until `release_agent` is
called; ephemeral agents (`ephemeral=True`) are released automatically
after their response.

```python
parent = Agent()
# Subagent is spawned via the agent tool (called by the LLM)
# or programmatically via Session.spawn()
```

## Slash Commands

Commands are handled by `yoker.ui.commands.CommandRegistry`.

| Command | Description |
|---------|-------------|
| `/help` | Show available commands |
| `/think [on\|off\|silent]` | Set or show thinking mode |
| `/skills` | List all loaded skills with sources |
| `/context` | Show current session context |
| `/tools` | List all known tools with availability |
| `/agents` | Show loaded agent and known agents |
| `/<skill-name>` | Invoke a skill by name |

Thinking modes: `on` (visible reasoning trace), `off` (no trace), `silent`
(trace consumed by the agent but not displayed).

## Tools List

All built-in tools are registered with the `yoker:` namespace.

| Tool | Description |
|------|-------------|
| `yoker:read` | Read file contents with guardrails and content type detection |
| `yoker:list` | Directory listing with pattern filtering and depth limits |
| `yoker:write` | Write files with overwrite protection; creates parent directories automatically (`create_parents=True` default) and returns a diff of the applied change |
| `yoker:update` | Edit files (replace, insert incl. anchor-based, append, delete) and return a diff of the applied change |
| `yoker:search` | Search file contents (regex, glob) with complexity limits and hidden-match reporting |
| `yoker:existence` | Check file/folder existence |
| `yoker:mkdir` | Create directories with depth limits |
| `yoker:file` | Filesystem operations (copy, move, delete) with recursive support |
| `yoker:notify` | Send macOS notifications to alert the user |
| `yoker:git` | Git operations (status, log, diff, branch, show, add, commit, push, pull, tag, checkout, rm, rebase) with auto-approved and approval-required command sets |
| `yoker:github` | GitHub operations via `gh` CLI (issues, PRs, workflows, reviews, releases, labels); read ops always available, write ops (`issue_create`, `issue_comment`, `issue_edit`, `label_create`, `pr_create`, `pr_comment`, `release_create`, ...) require config opt-in via `tools.github.allowed_operations` |
| `yoker:make` | Execute Makefile targets with per-target env var allowlist and timeout enforcement |
| `yoker:websearch` | Web search with SSRF protection and rate limiting |
| `yoker:webfetch` | Fetch web content with URL validation and guardrails |
| `yoker:agent` | Spawn subagents with recursion limits |
| `yoker:skill` | Invoke registered skills by name |
| `yoker:sleep` | Pause execution (1–300s) for polling intervals |

## Architecture

```
src/yoker/
├── __init__.py              # Public API exports (Agent, Session, Config, process, do,
│                            #   agent, session, run_sync, ThinkingLiteral)
├── __main__.py              # CLI entry point — dispatches to subcommand handlers
├── api.py                   # Thin Pythonic API facade: process(), do(), agent(),
│                            #   session(), run_sync() — no private helpers
├── exceptions.py            # Exception hierarchy (NetworkError, ValidationError, ...)
├── logging.py               # Structured logging (structlog)
├── markdown.py              # MarkdownStreamer — block-buffered Markdown streaming
├── resources.py             # Resource location for definition files (skills, agents)
├── schema.py                # NameSpaced base class for namespaced dataclasses
├── py.typed                 # PEP 561 typed-package marker
│
├── core/                    # Agent layer (no UI, no Session coupling)
│   ├── __init__.py          # Unified Agent class — async, event-emitting, Session-agnostic
│   ├── _processing.py       # Message processing, streaming, tool loop
│   ├── _setup.py            # Client, guardrail, registry setup
│   └── thinking.py          # Thinking mode enum
│
├── agents/                  # Agent definition parsing (schema, loader, registry)
│   ├── schema.py            # AgentDefinition frozen dataclass (from Markdown+frontmatter)
│   ├── loader.py            # Parse Markdown+YAML frontmatter; load from dirs/packages
│   ├── registry.py          # AgentRegistry (UserDict keyed by namespaced name)
│   └── validator.py         # validate_agent_definition against config constraints
│
├── backends/                # Provider-neutral backend layer
│   ├── protocol.py          # ModelBackend Protocol, ChatChunk, UsageStats
│   ├── factory.py           # create_backend() dispatch from Config
│   ├── ollama.py            # OllamaBackend (native SDK)
│   ├── litellm.py           # LitellmBackend (OpenAI, Anthropic, Gemini, 100+)
│   └── trust.py             # Custom base URL trust validation
│
├── bootstrap/               # First-run bootstrap wizard
│   ├── wizard.py            # Wizard orchestration
│   ├── steps.py             # Provider-specific setup steps
│   ├── providers.py         # Curated model lists and provider metadata
│   ├── detect.py            # Existing-config detection
│   └── modellist.py         # Model list rendering
│
├── builtin/                 # Built-in tools registered via __YOKER_MANIFEST__
│   ├── __init__.py          # Manifest declaring existence, file, git, github, list,
│   │                        #   make, mkdir, notify, read, search, sleep, update,
│   │                        #   webfetch, websearch, write (skill via factory)
│   ├── _validators.py       # Shared validators for builtin tool arguments
│   ├── read.py              # read: file contents (offset/limit slicing)
│   ├── write.py             # write: file contents (create_parents, result diff)
│   ├── update.py            # update: edit existing file contents (diff-based,
│   │                        #   anchor-based insert, result diff)
│   ├── list.py              # list: directory contents (ignore-rule aware)
│   ├── mkdir.py             # mkdir: create directories
│   ├── existence.py         # existence: check files/folders exist
│   ├── file.py              # file: filesystem operations (copy, move, delete)
│   ├── notify.py            # notify: macOS notifications
│   ├── search.py            # search: file and content search (grep-like)
│   ├── sleep.py             # sleep: pause execution (1–300s)
│   ├── git.py               # git: Git operations (status, log, diff, branch, show,
│   │                        #   add, commit, push, checkout, pull, tag, rm, rebase)
│   ├── github.py            # github: GitHub operations via gh CLI (read ops +
│   │                        #   opt-in write ops)
│   ├── make.py              # make: Makefile target execution
│   ├── webfetch.py          # webfetch: fetch web content through a backend
│   ├── websearch.py         # websearch: search the web through a backend
│   └── skill.py            # make_skill_tool factory (skill invocation tool)
│
├── config/                  # Configuration system (Clevis-based)
│   ├── __init__.py          # Config dataclasses, get_yoker_config()
│   ├── providers.py         # Provider configs (Ollama, OpenAI, Anthropic, Gemini, Generic)
│   ├── validators.py        # Field validators
│   └── writer.py            # TOML writer with chmod 600
│
├── context/                 # Context managers (Protocol-based)
│   ├── protocol.py          # ContextManager @runtime_checkable Protocol
│   ├── manager.py           # BaseContextManager (in-memory base)
│   ├── basic.py             # SimpleContextManager (env reminder + system prompt)
│   ├── config_summary.py    # render_config_summary() — redacted config snapshot
│   ├── wrapper.py           # ContextManagerWrapper (pure proxy)
│   ├── persisted.py         # Persisted (JSONL persistence via bulk-rewrite)
│   ├── factory.py           # Context manager factory — agent-scoped from Config
│   ├── interface.py         # ContextStatistics, SessionMetadata dataclasses
│   ├── session.py           # list_sessions, load_session_metadata (JSONL utilities)
│   └── validator.py         # validate_session_id, validate_storage_path, is_safe_path
│
├── events/                  # Event types and serialization
│   ├── types.py             # Event dataclasses (Message, Tool, Error, Stats, ...)
│   ├── session_event.py     # SessionEvent envelope (tags Event with agent_id)
│   └── recorder.py          # EventRecorder, serialize/deserialize_event (JSONL)
│
├── plugins/                 # Plugin system (discover, manifest, trust)
│   ├── loader.py            # Plugin package discovery via __YOKER_MANIFEST__
│   ├── manifest.py          # PluginManifest dataclass (tools, skills, agents declarations)
│   ├── file_manifest.py     # File-based manifest (agent.toml) parser
│   └── security.py          # Plugin trust checks (global opt-in + per-plugin trust table)
│
├── skills/                  # Skill definitions and registry
│   ├── schema.py            # Skill dataclass (from Markdown+frontmatter)
│   ├── loader.py            # Parse Markdown+YAML frontmatter into Skill objects
│   ├── registry.py          # SkillRegistry: lookup skills by name
│   └── injection.py         # Skill discovery + invocation context blocks
│
├── tools/                   # Tool framework
│   ├── annotations.py       # Path, Url, Query, Text markers + @tool decorator
│   ├── schema.py            # ToolSpec, build_tool_spec() (function→tool introspection)
│   ├── registry.py          # ToolRegistry (UserDict of ToolSpec)
│   ├── context.py           # Tool execution context (config/backends without exposing Agent)
│   ├── content_type.py      # Content type detection from file content and path extension
│   ├── diff.py              # generate_diff() — shared unified-diff helper
│   ├── ignore.py            # IgnoreMatcher — gitignore-style pattern matching for search/list
│   ├── guardrails/          # Guardrail framework
│   │   ├── env.py           # EnvGuardrail (env var allowlist + hard denylist)
│   │   └── path.py          # PathGuardrail (traversal, size, extension, protected_files)
│   └── web/                 # Web tool backends and guardrails
│       ├── backend.py       # Web search/fetch backend protocol and implementations
│       ├── guardrail.py     # Web guardrail (SSRF, domain allow/deny lists)
│       └── types.py         # SearchResult dataclass, WebSearchError
│
├── session/                 # Session construct (team-of-agents coordinator)
│   ├── __init__.py          # Session: async context manager owning a team of agents;
│   │                        #   spawn(), release(), send(), agent property, inject_tools()
│   └── tools.py             # Session-injected tools: agent + send_message factories
│
├── cli/                     # CLI subcommand config classes + handlers
│   ├── commands.py          # @configclass(cmd=...) subcommand configs registered with Clevis
│   ├── shared.py            # load_subcommand_config() + manifest variant
│   ├── chat.py              # yoker chat: interactive REPL (default subcommand)
│   ├── run.py               # yoker run: load source + trust gate + non-interactive execution
│   ├── config_cmd.py        # yoker config: display effective config
│   ├── init.py              # yoker init: generate default config
│   ├── inspect.py           # yoker inspect: read-only source report
│   ├── loop.py              # yoker loop: interval execution
│   ├── container.py         # yoker container: Dockerfile/Containerfile generation
│   └── sources.py           # resolve_source() + load_source() — two-phase source resolution
│
├── ui/                      # UI layer (strictly separated from the Agent layer)
│   ├── handler.py           # UIHandler protocol
│   ├── bridge.py            # UIBridge: events -> UIHandler method calls
│   ├── agent_display.py     # AgentDisplay — minimal agent info for UI rendering
│   ├── formatting.py        # Shared output formatting helpers
│   ├── interactive.py       # InteractiveUIHandler (Rich append-only + prompt_toolkit)
│   ├── batch.py             # BatchUIHandler (stdin/stdout/stderr for pipelines)
│   └── commands/            # Slash commands (/help, /agents, /skills, /tools, /think, /context, /config, /session)
│
└── usage/                   # Token usage tracking
    ├── logger.py            # UsageRecord + atomic JSONL append to ~/.yoker/usage.jsonl
    └── report.py            # load/aggregate/format per-model token and cost report
```

## References

- **PyPI**: https://pypi.org/project/yoker/
- **Documentation**: https://yoker.readthedocs.io/
- **Repository**: https://github.com/christophevg/yoker
- **Issues**: https://github.com/christophevg/yoker/issues
- **Rationale**: docs/rationale.md — Why Yoker exists and how it compares
- **Disclaimer**: DISCLAIMER.md — What Yoker is, does, and the risks involved
