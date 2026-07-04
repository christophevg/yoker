# MBI-003: Python API — Design Proposal

Status: Draft for owner review
Author: Functional Analyst
Date: 2026-07-03

This is a **design proposal**, not an implementation. No code in `src/` is
touched. The goal is to align on the API surface, naming, and ergonomics
before implementation begins.

---

## 1. Executive Summary

Yoker today exposes a powerful but class-oriented API: developers must
understand `Config`, `Agent`, `AgentDefinition`, `ToolRegistry`,
`SkillRegistry`, context managers, and the event system to do anything. The
resulting boilerplate is visible in `examples/library_usage.py`,
`examples/batch_mode.py`, and `examples/research_workflow.py` — every one of
them follows the same five-step ritual: load config, construct `Agent`,
optionally wire a `UIBridge`, register an event handler, `await
agent.process(...)`.

MBI-003 wraps that ritual in a small, Pythonic utility API that makes
agentic workflows feel like ordinary function calls. The unique selling point
of Yoker becomes: **agentic capabilities that read like Python code**, not a
framework bolted on top of Python.

The proposed API has three layers, each building on the previous one:

1. **One-shot functions** — `yoker.ask(...)`, `yoker.run_skill(...)`,
   `yoker.complete(...)`. Stateless, synchronous-feeling, one line of code.
2. **Agent builder** — `yoker.agent(...)` returns a configured `Agent`
   with a fluent, declarative setup. The same object is reusable across
   turns and across async tasks.
3. **Workflow primitives** — `yoker.session(...)`, sub-agent spawning,
   event hooks, and plugin loading, all expressed as ordinary Python
   constructs (context managers, async iterators, callables).

The design preserves the existing `Agent` class unchanged; the new API is a
thin facade that constructs and drives `Agent` instances. Migration is
voluntary and incremental — existing code keeps working.

---

## 2. Current State Analysis

### 2.1 What exists today

The public surface today is the `Agent` class plus a config factory:

```python
from yoker import Agent
from yoker.config import get_yoker_config

config = get_yoker_config(cli=False)
agent = Agent(config=config)
response = await agent.process("Hello")
```

Strengths:
- `Agent` is async-only and emits typed `Event` objects via
  `add_event_handler`. Clean separation between agent and UI.
- `AgentDefinition` lets you customize the system prompt, tool whitelist,
  and model. Tools, skills, and agents are registered in dedicated
  registries on the `Agent` instance.
- Plugin loading via `load_configured_plugins` and the `--with` CLI flag.
- Sub-agent spawning via the built-in `agent` tool, with recursion-depth
  limits.

Limitations for the Python API target:
- **Boilerplate.** Every usage repeats the same load-config → construct-Agent
  → wire-bridge → register-handler → process pattern. See all three
  examples in `examples/`.
- **No one-shot helpers.** There is no `yoker.ask("...")`. The user must
  construct a full `Agent` even for a single throwaway question.
- **No skill-execution helper.** `Agent.inject_skill_context` injects the
  skill content into context, but the user still has to call
  `agent.process(...)` themselves, and there is no top-level
  `yoker.run_skill(...)`.
- **No sync wrapper.** Yoker is async-only. Developers writing non-async
  scripts must write `asyncio.run(main())` boilerplate.
- **No fluent builder.** Configuring tools, skills, plugins, model, system
  prompt, and event handlers requires constructing a `Config` (frozen
  dataclass) or an `AgentDefinition` from Markdown — neither is convenient
  for programmatic use.
- **No session primitive (now resolved by MBI-007).** Multi-turn
  conversations used to require the developer to keep the `Agent` instance
  alive themselves and call `process()` in a loop. MBI-007 introduced the
  real :class:`yoker.session.Session` async context manager that owns a
  team of agents. MBI-003's `yoker.session()` is now a **facade over the
  real Session construct** (single-agent convenience: constructs a
  Session, registers one primary Agent, exposes `ask()` /
  `run_skill()` / `spawn()` / `on_event()` on top of it).
- **No discoverable entry point for skills/agents as callables.** The
  PLAN.md goal mentions `from package.skills import skill_name;
  skill_name("prompt")` as a future possibility. Today, skills are Markdown
  files; they cannot be imported as functions.

### 2.2 Constraints we must respect

- **Async-only Agent.** Any sync API must wrap async, never the reverse.
- **Frozen `Config`.** Built via dataclass + Clevis. Programmatic overrides
  use `dataclasses.replace`.
- **Event system.** The `Agent` emits events; the new API must let users
  hook into them without forcing a `UIBridge`.
- **Plugins.** Loaded via `load_configured_plugins(agent, config, extra)`.
  The `--with` mechanism must be expressible from Python.
- **Guardrails and tool config.** Tools are gated by `Config.tools.*`
  settings. The Python API should not silently bypass guardrails; it can
  provide convenience but must remain safe by default.

---

## 3. Design Principles

1. **Pythonic first.** The API should feel like `requests`, `httpx`, or
   `rich` — discoverable via IDE autocompletion, readable in a single
   glance, no surprise callbacks.
2. **Layered, not layered cake.** Three layers (one-shot, builder, workflow),
  each strictly building on the previous. A user who only needs layer 1
  never sees layer 3.
3. **Async-native, sync-friendly.** Async is the primary API. A sync wrapper
  is provided for scripts and notebooks, clearly marked as the convenience
  path.
4. **No magic.** The new API constructs `Agent` instances under the hood.
  Users can always drop down to the `Agent` class for full control.
5. **Safe by default.** Guardrails, tool config, and plugin trust checks
  are honored. Convenience never silently disables security.
6. **Composable.** Agents, skills, tools, and event handlers are ordinary
  Python objects. The user can mix and match them in their own code.
7. **Discoverable.** Heavy use of type hints, `@overload`, and
  `TypedDict` so static analysis and IDE autocompletion just work.
8. **Honest about async.** Sync wrappers are named explicitly (`ask_sync`,
  `run_skill_sync`) — never a hidden event loop.

---

## 4. Proposed API Surface

### 4.1 Module layout

A new top-level module `yoker/api.py` exposes the public surface. It is
re-exported from `yoker/__init__.py` alongside the existing classes (so
existing imports keep working).

```text
src/yoker/
├── api/
│   ├── __init__.py        # Public re-exports
│   ├── one_shot.py        # ask, complete, run_skill (+ _sync variants)
│   ├── builder.py         # agent() builder, AgentConfig dataclass
│   ├── session.py         # session() async context manager
│   └── _internal.py       # Shared helpers (config merge, async runner)
```

### 4.2 Layer 1 — One-shot functions

```python
import yoker

# Async (primary)
response: str = await yoker.ask("What is 2+2?")
response: str = await yoker.ask("Summarize README.md.", model="qwen3.5:cloud")

# Run a skill by name. The skill must be discoverable from configured
# skill directories or loaded plugins. The prompt is the user's task.
result: str = await yoker.run_skill("commit", "stage and commit current changes")

# Ask a model to complete a prompt with no tools, no skills, no context.
# Useful for pure text-completion inside Python pipelines.
text: str = await yoker.complete("Translate to French: hello", model="gpt-4o-mini")

# Sync convenience (clearly named, no hidden event loops)
response: str = yoker.ask_sync("What is 2+2?")
result: str = yoker.run_skill_sync("commit", "stage and commit current changes")
```

Design notes:
- `ask` is the everyday entry point. It loads config via
  `get_yoker_config(cli=False)`, constructs an `Agent` with the default
  agent definition, calls `process()`, and returns the string. The agent is
  discarded (stateless one-shot).
- Optional keyword arguments let the caller override `model`, `provider`,
  `system_prompt`, `tools`, `skills`, `plugins`, and `event_handler` without
  constructing a full `Config`. These are sugar over `yoker.agent(...)`.
- `run_skill` finds the skill by name in the agent's registry, calls
  `Agent.inject_skill_context(skill_name, args)`, then calls
  `agent.process(prompt)`. The `args` parameter is optional.
- `complete` is a thin text-completion helper — no tools, no skills, no
  system prompt beyond what the model provides by default. It is the
  lowest-overhead way to ask a model a question from Python.
- Sync variants are named `*_sync` and run `asyncio.run(...)` internally.
  They raise a clear error if called from inside a running event loop.

### 4.3 Layer 2 — Agent builder

```python
import yoker

# Fluent builder
agent = yoker.agent(
  model="qwen3.5:cloud",
  system_prompt="You are a concise code reviewer.",
  tools=["read", "search", "git"],
  skills=["commit", "review"],
  plugins=["pkgq"],
  thinking="on",        # "on" | "off" | "visible"
)

# Reuse across turns (async)
response1 = await agent.process("Review src/auth.py")
response2 = await agent.process("Now review tests/test_auth.py")

# Attach an event handler after construction
agent.on_event(lambda e: print(e.type.name))

# Inspect what's configured
agent.model           # "qwen3.5:cloud"
agent.tools.names     # ["yoker:read", "yoker:search", "yoker:git", ...]
agent.skills.names    # ["commit", "review"]
```

The `yoker.agent(...)` builder:
- Returns a fully constructed `yoker.Agent` instance (the existing class).
- Accepts convenience keyword arguments that map to `Config` /
  `AgentDefinition` fields without forcing the user to construct them.
- Defaults: model and provider from config, all built-in tools enabled by
  config, no skills, no plugins, the default agent definition's system
  prompt, thinking mode `ON`.
- `tools`, `skills`, `plugins` accept lists of names. The builder resolves
  them against the registries that get populated during construction.
- `system_prompt` overrides the agent definition's system prompt. If
  omitted, the configured/default agent definition is used.
- `thinking` is a string enum for ergonomics (`"on" | "off" | "visible"`),
  mapped to `ThinkingMode`.
- `event_handler` (or `on_event(...)`) registers a handler on the resulting
  `Agent`.

This is the same `Agent` class that exists today. Users can call any
existing method (`process`, `inject_skill_context`, `add_event_handler`).
The builder is purely construction sugar.

### 4.4 Layer 3 — Workflow primitives

#### 3a. Sessions

```python
import yoker

# Multi-turn conversation with automatic context persistence
async with yoker.session(id="code-review-2026-07-03") as session:
  await session.ask("Review src/auth.py for security issues.")
  await session.ask("Now suggest fixes for the top 3 issues.")
  await session.ask("Apply the fixes to the file.")

  # Access the underlying Agent for advanced operations
  session.agent.tools.names
```

A `session` is an async context manager that:
- Wraps the real :class:`yoker.session.Session` construct from MBI-007
  (the team-of-agents coordinator). MBI-003's `yoker.session()` is a
  **facade** that constructs a Session, registers one primary Agent, and
  exposes single-agent convenience methods on top of it.
- Creates an `Agent` with a `PersistenceContextManager` bound to the given
  session id (or an auto-generated one).
- Exposes `ask(prompt)` as a thin alias for `agent.process(prompt)`.
- Persists context on exit (if `persist_after_turn` is true in config).
- Accepts the same builder kwargs as `yoker.agent(...)` for configuration.
- Delegates `spawn(name, prompt, timeout_seconds=...)` to the underlying
  `Session.spawn(...)` (the canonical sub-agent API, MBI-007 Decision 8).
  This makes the same spawn machinery available to Python callers that the
  SpawnAgent tool exposes to the model.

#### 3b. Sub-agent spawning

```python
import yoker

# Spawn a sub-agent programmatically (mirrors the built-in agent tool)
researcher = yoker.agent(agent_path="examples/agents/researcher.md")
summary = await researcher.process("Find all TODO comments in src/")

# Or use the convenience: any configured agent can be spawned by name
parent = yoker.agent(tools=["read", "list"])
result = await parent.spawn("researcher", "Analyze src/ for security issues.")
```

`spawn(name, prompt, timeout_seconds=300)` is a thin wrapper over the
canonical :meth:`yoker.session.Session.spawn` API introduced in MBI-007
(Decision 8). The Session owns the sub-agent machinery (registry
resolution, recursion-depth and max_agents enforcement, backend
factory, timeout, and event aggregation) — MBI-003's `yoker.session()`
and `yoker.agent().spawn(...)` simply delegate to it. This is what makes
"agentic workflows intermixed with Python code" actually work — Python
code can drive sub-agents directly without going through the model
tool-call loop.

#### 3c. Event hooks

```python
import yoker

agent = yoker.agent(
  model="qwen3.5:cloud",
  on_event=lambda e: print(f"[{e.type.name}] {e}"),
)

# Or register a typed handler that filters by event type
from yoker.events import ToolCallEvent

def log_tools(event):
  if isinstance(event, ToolCallEvent):
    print(f"calling {event.tool_name}({event.arguments})")

agent.on_event(log_tools)

# Streaming content chunks
from yoker.events import ContentChunkEvent

def stream(event):
  if isinstance(event, ContentChunkEvent):
    print(event.text, end="", flush=True)

agent.on_event(stream)
```

`on_event` is an alias for `add_event_handler` with a more Pythonic name
and a return value (the handler, for chaining). It accepts sync or async
callables, matching the existing event system.

#### 3d. Plugin integration

```python
import yoker

# Load plugins programmatically (the --with mechanism, from Python)
agent = yoker.agent(plugins=["pkgq", "c3"])

# Plugins can also be enabled globally in config (unchanged behavior)
agent = yoker.agent()  # uses config.plugins.packages
```

The `plugins` kwarg is threaded into `load_configured_plugins` exactly as
the CLI `--with` flag is today. Plugin trust checks still apply.

---

## 5. Nice Examples

These are the showcase examples that should make a Python developer say "I
want to use this." They are realistic — the kind of code you would actually
write, not demos.

### Example 1: One-off skill execution

```python
import yoker

# Stage and commit current changes using the "commit" skill
message = await yoker.run_skill("commit", "stage and commit current changes")
print(message)
```

One line of meaningful code. The skill's full instructions are injected
into context automatically, the model runs with the configured tools, and
the response is returned as a string.

### Example 2: Quick question to a model

```python
import yoker

# Pure text completion — no tools, no skills, no agent definition
translation = await yoker.complete(
  "Translate to French: 'Hello, how are you?'",
  model="gpt-4o-mini",
)
print(translation)
```

`complete` is the lowest-friction entry point. It is what developers reach
for when they just want to ask a model a question from Python.

### Example 3: Building a custom agent with specific tools

```python
import yoker

reviewer = yoker.agent(
  model="qwen3.5:cloud",
  system_prompt=(
    "You are a security-focused code reviewer. "
    "Always cite file:line for every finding."
  ),
  tools=["read", "search", "list"],
  thinking="visible",
)

reviewer.on_event(lambda e: print(f"[{e.type.name}]"))

report = await reviewer.process("Review src/yoker/plugins/security.py for vulnerabilities.")
```

The agent is configured declaratively. `tools` is a list of names; the
builder resolves them. `thinking="visible"` makes the model's reasoning
stream to the event handler.

### Example 4: Agentic workflow intermixed with Python code (the showcase)

This is the example that defines Yoker's USP. Agentic calls are
interleaved with ordinary Python — file IO, data processing, loops,
conditionals — as if the agentic steps were just function calls.

```python
import json
import yoker
from pathlib import Path

# A real workflow: audit a Python project for security issues, then
# generate a JSON report. Agentic steps and Python steps interleave
# naturally.

analyst = yoker.agent(
  model="qwen3.5:cloud",
  system_prompt="You are a security analyst. Be specific and cite file:line.",
  tools=["read", "search", "list"],
)

# Python: gather the list of files to audit
src_files = sorted(Path("src/yoker").rglob("*.py"))
findings = []

# Agentic: analyze each file
for path in src_files:
  result = await analyst.process(
    f"Analyze {path} for security issues. "
    "Return a JSON array of {{file, line, severity, issue}}. "
    "If the file is clean, return an empty array."
  )
  try:
    file_findings = json.loads(result)
  except json.JSONDecodeError:
    # Agentic: ask the agent to fix its own output
    file_findings = json.loads(
      await analyst.process("The previous response was not valid JSON. Return only the JSON array.")
    )
  findings.extend(file_findings)

# Python: post-process and write the report
report = {
  "audited_files": len(src_files),
  "total_findings": len(findings),
  "by_severity": {
    sev: sum(1 for f in findings if f["severity"] == sev)
    for sev in {"critical", "high", "medium", "low"}
  },
  "findings": findings,
}
Path("security-report.json").write_text(json.dumps(report, indent=2))
print(f"Wrote security-report.json ({len(findings)} findings)")
```

Why this matters: the `await analyst.process(...)` call sits inside a
Python `for` loop, between `Path.rglob` and `json.loads`. The agentic step
is just a function call. The developer does not think about "the agent
framework" — they think about their workflow, and the agent is one of the
tools they reach for.

### Example 5: Multi-turn conversation

```python
import yoker

async with yoker.session(id="refactor-auth") as session:
  await session.ask("Read src/auth.py and identify the main responsibilities.")
  await session.ask("Suggest a refactor that splits authentication from session management.")
  await session.ask("Apply the refactor. Write the new files.")
  await session.ask("Update the tests to match the new structure.")
```

Context persists across turns automatically. The session id makes the
conversation resumable — re-opening the same id restores history.

### Example 6: Using plugins

```python
import yoker

# Load the pkgq plugin (provides package documentation tools)
agent = yoker.agent(
  plugins=["pkgq"],
  tools=["read", "list", "pkgq:find_package"],
)

answer = await agent.process("Find the documentation for httpx and summarize the streaming API.")
```

Plugin tools are namespaced (`pkgq:find_package`). The builder resolves
them just like built-in tools.

### Example 7: Custom event handling

```python
import yoker
from yoker.events import ContentChunkEvent, ToolCallEvent, TurnEndEvent

# Stream content to stdout while logging tool calls and stats
def handler(event):
  if isinstance(event, ContentChunkEvent):
    print(event.text, end="", flush=True)
  elif isinstance(event, ToolCallEvent):
    print(f"\n[tool] {event.tool_name}({event.arguments})")
  elif isinstance(event, TurnEndEvent):
    print(f"\n[tokens] in={event.input_tokens} out={event.output_tokens}")

agent = yoker.agent(model="qwen3.5:cloud", on_event=handler)
await agent.process("List the files in the current directory and explain what each one does.")
```

The event system is unchanged. `on_event` is the Pythonic alias for
`add_event_handler`. Typed events make filtering clean and
static-analysis-friendly.

### Example 8: Sync usage in a script

```python
import yoker

# For scripts, notebooks, and REPLs where async is awkward
answer = yoker.ask_sync("What files are in the current directory?")
print(answer)

# Or run a skill synchronously
result = yoker.run_skill_sync("commit", "stage and commit all changes")
print(result)
```

The sync wrappers are clearly named `_sync`. They raise a clear error if
called from inside a running event loop (pointing the user to the async
variant).

---

## 6. API Reference Sketch

### 6.1 One-shot functions

```python
# yoker/api/one_shot.py

async def ask(
  prompt: str,
  *,
  model: str | None = None,
  provider: str | None = None,
  system_prompt: str | None = None,
  tools: list[str] | None = None,
  skills: list[str] | None = None,
  plugins: list[str] | None = None,
  thinking: Literal["on", "off", "visible"] = "on",
  event_handler: EventCallback | None = None,
) -> str: ...

async def run_skill(
  skill_name: str,
  prompt: str = "",
  *,
  args: str = "",
  model: str | None = None,
  provider: str | None = None,
  plugins: list[str] | None = None,
  thinking: Literal["on", "off", "visible"] = "on",
  event_handler: EventCallback | None = None,
) -> str: ...

async def complete(
  prompt: str,
  *,
  model: str | None = None,
  provider: str | None = None,
  thinking: Literal["on", "off", "visible"] = "on",
) -> str: ...

def ask_sync(...) -> str: ...   # same signature, sync wrapper
def run_skill_sync(...) -> str: ...
def complete_sync(...) -> str: ...
```

Return type: `str` (the assistant's final response for the turn).

Errors: raises `NetworkError`, `ConfigurationError`, `SkillError`,
`YokerError` subclasses as appropriate. No silent failures.

### 6.2 Agent builder

```python
# yoker/api/builder.py

def agent(
  *,
  model: str | None = None,
  provider: str | None = None,
  system_prompt: str | None = None,
  tools: list[str] | None = None,
  skills: list[str] | None = None,
  plugins: list[str] | None = None,
  agent_path: str | Path | None = None,
  agent_definition: AgentDefinition | None = None,
  thinking: Literal["on", "off", "visible"] = "on",
  event_handler: EventCallback | None = None,
  config: Config | None = None,
  context_manager: ContextManager | None = None,
  **config_overrides: Any,  # passed to dataclasses.replace(config, ...)
) -> Agent: ...
```

Returns: a fully constructed `yoker.Agent`. All existing `Agent` methods
(`process`, `inject_skill_context`, `add_event_handler`,
`remove_event_handler`) work as today.

New method on `Agent` (added by the API layer as a thin wrapper):

```python
async def spawn(
  self,
  agent_name: str,
  prompt: str,
  *,
  timeout_seconds: int = 300,
) -> str: ...
```

`on_event` is added as an alias:

```python
def on_event(self, handler: EventCallback) -> EventCallback:
  self.add_event_handler(handler)
  return handler
```

### 6.3 Session

```python
# yoker/api/session.py

class Session:
  agent: Agent  # the underlying Agent instance

  async def ask(self, prompt: str) -> str: ...
  async def run_skill(self, skill_name: str, prompt: str = "", *, args: str = "") -> str: ...
  async def spawn(self, agent_name: str, prompt: str, *, timeout_seconds: int = 300) -> str: ...
  def on_event(self, handler: EventCallback) -> EventCallback: ...

@asynccontextmanager
async def session(
  id: str | None = None,
  *,
  persist: bool = True,
  # ...all agent() kwargs...
) -> AsyncIterator[Session]: ...
```

### 6.4 Top-level re-exports

`yoker/__init__.py` adds:

```python
from yoker.api import (
  ask, ask_sync,
  complete, complete_sync,
  run_skill, run_skill_sync,
  agent,
  session,
  Session,
)
```

Existing exports (`Agent`, `Config`, `AgentDefinition`, events, exceptions)
remain unchanged.

---

## 7. Integration with Existing Architecture

The new API is a **facade**. It does not duplicate logic; it constructs and
drives the existing classes.

```text
yoker.ask("...")
   │
   ├─ get_yoker_config(cli=False)         (existing)
   ├─ Agent(config=config, ...)           (existing)
   ├─ optional: agent.add_event_handler   (existing)
   ├─ optional: agent.inject_skill_context (existing)
   └─ await agent.process(prompt)         (existing)

yoker.agent(...)
   │
   ├─ get_yoker_config or provided config (existing)
   ├─ dataclasses.replace(config, ...)    for model/provider overrides
   ├─ AgentDefinition(system_prompt=...)  or load_agent_definition(path)
   ├─ Agent(config=config, agent_definition=def, plugins=plugins)
   └─ return agent  # existing Agent instance

yoker.session(...)
   │
   ├─ yoker.agent(...)                    (above)
   ├─ Session(config=config)              (MBI-007; real Session construct)
   ├─ session.register_primary_agent(agent)
   ├─ PersistenceContextManager(session_id=id) bound to the agent
   └─ async context manager wraps the Session lifecycle (async with Session)

Agent.spawn(name, prompt)  /  yoker.session().spawn(...)
   │
   ├─ session.spawn(name, prompt, ...)   (MBI-007 canonical API, Decision 8)
   ├─ session.agents.resolve(name)       (registry on Session, D10)
   ├─ allowlist enforcement               (requester.definition.agents, PR #43 Clarification 3)
   ├─ recursion depth + max_agents checks (D1, D7)
   ├─ session.get_backend(child_config)  (D9, shared or fresh)
   └─ asyncio.wait_for(child.process(prompt), timeout) (D8)
```

### What changes in the existing code

- **Nothing breaks.** All existing imports, classes, and methods keep
  working.
- **One small addition.** The `spawn` method and `on_event` alias are added.
  `spawn` delegates to :meth:`yoker.session.Session.spawn` (introduced in
  MBI-007). MBI-007 already extracted the sub-agent machinery from
  `builtin/agent.py` into the Session (the `_create_subagent` /
  `_run_with_timeout` helpers no longer exist; the canonical spawn lives
  on :class:`yoker.session.Session`). MBI-003's `yoker.session()` is a
  facade over the real Session construct.
- **One new module.** `yoker/api/` contains only the facade. No
  behavior changes in `Agent`, `Config`, `ToolRegistry`, `SkillRegistry`,
  or the plugin system.

### Config overrides

The `model` and `provider` kwargs on `ask`, `agent`, and `session` are
sugar for `dataclasses.replace(config.backend, ...)`. The frozen
`Config` dataclass is respected — we construct a new copy, we do not
mutate. This matches the existing pattern in `builtin/agent.py::_create_subagent`.

---

## 8. Migration Path

Existing code keeps working unchanged. Migration is voluntary:

| Before | After (optional) |
|--------|------------------|
| `config = get_yoker_config(); agent = Agent(config=config); await agent.process("...")` | `await yoker.ask("...")` |
| `agent = Agent(config=config, agent_path="examples/agents/researcher.md")` | `yoker.agent(agent_path="examples/agents/researcher.md")` |
| `agent = Agent(config=config); agent.add_event_handler(h)` | `yoker.agent(on_event=h)` |
| `agent = Agent(config=config, plugins=["pkgq"])` | `yoker.agent(plugins=["pkgq"])` |
| Manual loop with `agent.process()` | `async with yoker.session() as s: await s.ask(...)` |

The existing examples stay in `examples/` and continue to work. New
examples demonstrating the Python API are added under
`examples/python_api/` (one file per showcase example in section 5).

The `library_usage.py` example becomes a one-liner:

```python
import yoker
print(await yoker.ask("Hello, how can you help me?"))
```

---

## 9. Open Questions

These need owner input before implementation:

1. **Sync wrapper strategy.** Three options:
   - (a) `ask_sync` runs `asyncio.run(coro)` and raises if a loop is
     already running (clean, explicit).
   - (b) Use `nest_asyncio` to allow nested loops (magic, fragile).
   - (c) No sync wrappers — force async everywhere (purest, but hostile
     to notebooks and scripts).
   **Recommendation:** (a). The error message points the user to the
   async variant. Notebooks already have `await` via IPython.

2. **`ask` vs `process` naming.** `ask` is the friendly top-level name.
   `Agent.process` stays as the low-level method. Is the split clear
   enough, or should we rename `process` to `ask` on `Agent` too (with
   `process` kept as an alias)?

3. **Skill execution semantics.** `run_skill("commit", "stage and commit")`
   injects the skill content and then sends the user's prompt. Should the
   skill content be the *entire* user message (current `inject_skill_context`
   behavior), or should it be a system-reminder block followed by the
   user's prompt as a separate user message? The latter is closer to how
   slash commands work in the interactive UI; the former is simpler.

4. **`complete` vs `ask`.** Is `complete` (no tools, no skills, pure
   text completion) worth a separate function, or should `ask` accept a
   `tools=[]` / `skills=[]` argument that disables them? A separate
   `complete` is more discoverable but adds surface area.
   **Recommendation:** keep `complete` as a distinct function — it
   communicates intent clearly and has different defaults (no system
   prompt injection).

5. **Skills as importable callables.** The PLAN.md goal mentions
   `from package.skills import skill_name; skill_name("prompt")`. This is
   a bigger change (requires generating Python modules from Markdown at
   install time, or a `__getattr__` hook on the package). Should it be in
   scope for MBI-003, or deferred to a follow-up?
   **Recommendation:** defer. MBI-003 delivers `yoker.run_skill(...)`.
   The importable-skills pattern is a separate MBI that depends on the
   plugin manifest being extended to declare callable skill entry points.

6. **Session resumption.** Should `yoker.session(id="...")` automatically
   resume an existing persisted session, or always start fresh? Today
   `PersistenceContextManager` loads from storage if the session exists.
   **Recommendation:** auto-resume (matches existing behavior), with a
   `fresh=True` kwarg to force a new session.

7. **`spawn` return type.** Should `Agent.spawn(name, prompt)` return
   `str` (the sub-agent's final response) or a richer `SubAgentResult`
   dataclass (response, agent_name, depth, duration, token stats)?
   **Recommendation:** `str` for ergonomics; the sub-agent's events are
   observable via the parent's event handlers if the caller wants detail.

8. **Event handler on `agent()` builder.** Singular `event_handler` or
   plural `event_handlers=[...]`? Or just `on_event` (singular, chainable)?
   **Recommendation:** `on_event` (singular, returns the handler). For
   multiple handlers, call `agent.on_event(...)` repeatedly after
   construction.

9. **Config overrides via kwargs.** Should `yoker.agent(...)` accept
   arbitrary `config_overrides` as `**kwargs` (passed to
   `dataclasses.replace(config, ...)`), or should each override be a
   named parameter on `agent()`? `**kwargs` is flexible but undiscoverable;
   named parameters are verbose but autocomplete well.
   **Recommendation:** named parameters for the common cases (`model`,
   `provider`, `system_prompt`, `tools`, `skills`, `plugins`,
   `thinking`), plus `config=` for full control. No `**kwargs` magic.

10. **Naming: `yoker.agent()` vs `yoker.create_agent()` vs
    `yoker.Agent()`.** Using `agent()` (lowercase) as a factory function
    is Pythonic (cf. `httpx.Client()` vs `httpx.client()` — but
    `requests.get()` / `httpx.get()` are the precedents for lowercase
    factories). It does shadow the `Agent` class name slightly. Is this
    acceptable, or should the factory be `yoker.build_agent()` /
    `yoker.create_agent()`?
    **Recommendation:** `yoker.agent(...)` — it reads naturally
    (`agent = yoker.agent(...)`) and the `Agent` class is still available
    for those who want it.

---

## 10. Out of Scope

- Auto-generating Python callables for skills and agents (the
  `from package.skills import skill_name` pattern). Deferred to a
  follow-up MBI.
- A REPL or interactive shell. That is MBI-004 (yoker Commands).
- Web UI / REST API. Future MBIs.
- Changing the `Agent` class internals, the event system, or the config
  schema. The new API is purely additive.
- Removing the existing examples. They stay as low-level references.

---

## 11. Acceptance Criteria for the Implementation

These are the measurable criteria for the implementation phase, derived
from the design above:

- [ ] `import yoker; await yoker.ask("...")` works with no other imports.
- [ ] `yoker.ask_sync("...")` works from a synchronous script.
- [ ] `yoker.run_skill("commit", "stage and commit")` injects the skill
      and returns the response.
- [ ] `yoker.complete("...", model="gpt-4o-mini")` does pure text
      completion with no tools.
- [ ] `yoker.agent(tools=["read", "search"], skills=["commit"])`
      returns a configured `Agent` with exactly those tools and skills.
- [ ] `yoker.agent(plugins=["pkgq"])` loads the plugin and its tools are
      available on the agent.
- [ ] `async with yoker.session(id="x") as s: await s.ask("...")`
      persists and resumes context.
- [ ] `agent.spawn("researcher", "analyze src/")` runs a sub-agent by
      name and returns the response.
- [ ] `agent.on_event(handler)` registers a handler that receives typed
      events.
- [ ] All existing examples (`library_usage.py`, `batch_mode.py`,
      `research_workflow.py`) continue to work unchanged.
- [ ] `make check` green.
- [ ] New examples under `examples/python_api/` demonstrate each
      showcase use case from section 5.
- [ ] Type hints pass strict mypy; IDE autocompletion works for all
      public functions.