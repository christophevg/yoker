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
from yoker.ui import UIHandler

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

    def output_tool_call(self, tool_name: str, args: dict[str, object]) -> None:
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

    def output_stats(self, duration_ms: int, prompt_tokens: int, eval_tokens: int) -> None:
        print(f"Stats: {duration_ms}ms, {prompt_tokens} + {eval_tokens} tokens")

    def output_error(self, error: Exception, include_traceback: bool = False) -> None:
        print(f"Error: {error}")

    def start_content_stream(self) -> None:
        pass

    def stream_content(self, chunk: str, content_type: str = "text/plain") -> None:
        print(chunk, end="", flush=True)

    def end_content_stream(self, total_length: int) -> None:
        print()

    def start_thinking_stream(self) -> None:
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
from yoker.tools.annotations import Path, Text
from yoker.tools import ToolRegistry

def read_file(
    path: Annotated[str, Path("Path to the file to read")],
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
| `Path` | Filesystem paths (`PathGuardrail`) |
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

Or set the environment variable `YOKER_LOGGING_LEVEL=INFO`.

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

The `yoker:agent` tool spawns isolated subagents. Recursion depth is tracked automatically. Sub-agents inherit guardrails from their parent and get an isolated context.

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
| `yoker:write` | Write files with overwrite protection |
| `yoker:update` | Edit files (replace, insert, delete) with diff display |
| `yoker:search` | Search file contents (regex, glob) with complexity limits |
| `yoker:existence` | Check file/folder existence |
| `yoker:mkdir` | Create directories with depth limits |
| `yoker:git` | Git operations (status, log, diff, branch, show, add, commit, push, pull, tag, checkout, rm) |
| `yoker:github` | Read-only GitHub operations via `gh` CLI (issues, PRs, workflows, reviews) |
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
│   ├── __init__.py          # Manifest declaring read, write, git, github, make,
│   │                        #   websearch, webfetch, search, list, mkdir, existence, sleep, skill
│   ├── read.py              # read: file contents (offset/limit slicing)
│   ├── write.py             # write: file contents
│   ├── update.py            # update: edit existing file contents (diff-based)
│   ├── list.py              # list: directory contents
│   ├── mkdir.py             # mkdir: create directories
│   ├── existence.py         # existence: check files/folders exist
│   ├── search.py            # search: file and content search (grep-like)
│   ├── sleep.py             # sleep: pause execution (1–300s)
│   ├── git.py               # git: Git operations (status, log, diff, branch, show,
│   │                        #   add, commit, push, checkout, pull, tag, rm)
│   ├── github.py            # github: read-only GitHub operations via gh CLI
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
└── ui/                      # UI layer (strictly separated from the Agent layer)
    ├── handler.py           # UIHandler protocol
    ├── bridge.py            # UIBridge: events -> UIHandler method calls
    ├── interactive.py       # InteractiveUIHandler (Rich append-only + prompt_toolkit)
    ├── batch.py             # BatchUIHandler (stdin/stdout/stderr for pipelines)
    └── commands/            # Slash commands (/help, /agents, /skills, /tools, /think, /context, /config)
```

## References

- **PyPI**: https://pypi.org/project/yoker/
- **Documentation**: https://yoker.readthedocs.io/
- **Repository**: https://github.com/christophevg/yoker
- **Issues**: https://github.com/christophevg/yoker/issues
- **Rationale**: docs/rationale.md — Why Yoker exists and how it compares
- **Disclaimer**: DISCLAIMER.md — What Yoker is, does, and the risks involved
