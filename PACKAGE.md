# Yoker

> A Python agent harness with configurable tools and guardrails - one who yokes agents together.

## Overview

Yoker is a library-first, event-driven agent harness for Python that integrates with multiple LLM providers. It provides a transparent, configurable runtime for AI agents with structured tool execution, guardrails, event emission, and a pluggable UI layer. Unlike CLI-first agent frameworks, Yoker is designed to be embedded in applications with full visibility into agent operations.

Key differentiators:
- **Library-first** - Embed in applications, not locked into CLI
- **Multi-provider** - Ollama (native SDK), OpenAI, Anthropic, Gemini, and 100+ providers via LiteLLM
- **Event-driven** - Subscribe to thinking, content, and tool events
- **UI layer** - Swap interactive TUI, batch mode, or custom handlers
- **Plugin system** - Load namespaced tools, skills, and agents from Python packages
- **Async-native** - All I/O operations are async
- **Static permissions** - Deterministic boundaries via configuration
- **Transparent** - All prompts visible, editable, configurable

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

Loads `yoker.toml` from the current directory if present.

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

### Default usage

```python
import asyncio

from yoker import Agent

async def main():
  agent = Agent()  # loads yoker.toml configuration by default
  response = await agent.process("What files are in this directory?")
  print(response)

asyncio.run(main())
```

### Batch mode

```python
import asyncio

from yoker import Agent
from yoker.ui import BatchUIHandler, UIBridge

async def main():
  agent = Agent()
  ui = BatchUIHandler(show_tool_calls=True)
  bridge = UIBridge(ui)
  agent.add_event_handler(bridge)

  await ui.start(agent)
  await agent.process("Summarize README.md")
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
  agent.add_event_handler(handler)
  await agent.process("What is 2+2?")

asyncio.run(main())
```

### Custom UI handler

Implement the `UIHandler` protocol and wire it to the agent with `UIBridge`:

```python
from typing import Any

from yoker.agent import Agent
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

### `yoker.agent.Agent`

The async agent that chats with model backends and uses tools.

```python
from yoker import Agent

agent = Agent(agent_path="agents/researcher.md")

print(agent.model)          # Resolved model name
print(agent.tools.names)    # Available tools (namespaced)
print(agent.context)        # Conversation history
print(agent.definition)    # Loaded agent definition (if any)
print(agent.skills.names)  # Available skills (namespaced)
```

**Key methods:**
- `process(message)` - Process a message, handle tool calls, return response
- `add_event_handler(handler)` - Subscribe to events
- `remove_event_handler(handler)` - Unsubscribe from events
- `inject_skill_context(skill_name, args)` - Inject a skill into the conversation

### UI layer

- `yoker.ui.UIHandler` - Protocol defining the UI interface
- `yoker.ui.UIBridge` - Event dispatcher that converts agent events into UI method calls
- `yoker.ui.InteractiveUIHandler` - Terminal UI using `prompt_toolkit` and Rich
- `yoker.ui.BatchUIHandler` - Non-interactive UI using stdin/stdout/stderr
- `yoker.ui.commands.CommandRegistry` - Slash-command registry

Attach a UI to an agent:

```python
from yoker.ui import UIBridge

bridge = UIBridge(ui)
agent.add_event_handler(bridge)
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

Configuration hierarchy (highest to lowest):
1. Environment variables (`YOKER_*`)
2. CLI arguments (when `cli=True`)
3. `./yoker.toml`
4. `~/.yoker.toml`
5. Default values from `Config`

### `yoker.context.ContextManager`

- `BasicContextManager` - In-memory conversation history
- `PersistenceContextManager` - JSONL-persisted session context

```python
from yoker import Agent
from yoker.context import BasicContextManager, PersistenceContextManager

# In-memory context
context = BasicContextManager()

# Persisted JSONL context
context = PersistenceContextManager(session_id="my-session")

# Resume existing session
context = PersistenceContextManager.resume("my-session")

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
- `TURN_START/END` - Turn lifecycle (user message to response)
- `THINKING_START/CHUNK/END` - LLM reasoning trace
- `CONTENT_START/CHUNK/END` - Response text streaming
- `TOOL_CALL/RESULT/CONTENT` - Tool execution and display
- `COMMAND` - Slash-command result

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

When a callable is registered, `build_tool_spec()` extracts the marker from each `Annotated[str, Marker(...)]` parameter and stores its functional type in the resulting `ToolSpec.guards`. The marker description is kept in the JSON schema; the guardrail metadata is stripped before the schema is sent to the model, keeping it Ollama-compatible. At execution time, the harness dispatches the matching guardrail centrally, so the tool itself stays a plain function.

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
packages = ["pkgq"]
trusted = { pkgq = true }
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
from yoker import configure_logging
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
agent.add_event_handler(UIBridge(ui))

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

The `yoker:agent` tool spawns isolated subagents. Recursion depth is tracked automatically.

```python
parent = Agent()
# Subagent is spawned via the agent tool
# Inherits guardrails, has isolated context, respects max_recursion_depth
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
| `yoker:git` | Git operations (status, log, diff, branch, show) |
| `yoker:agent` | Spawn subagents with recursion limits |
| `yoker:websearch` | Web search with SSRF protection and rate limiting |
| `yoker:webfetch` | Fetch web content with URL validation and guardrails |
| `yoker:skill` | Invoke registered skills by name |

## Architecture

```
src/yoker/
├── __init__.py          # Public API exports
├── __main__.py          # CLI entry point
├── agent/               # Agent implementation
│   ├── __init__.py      # Public Agent class
│   ├── _plugins.py      # Plugin loading helpers
│   ├── _processing.py   # Message/tool processing
│   ├── _setup.py        # Client, guardrail, registry setup
│   ├── _tools.py        # Built-in tool filtering
│   └── thinking.py      # Thinking mode enum
├── agents/              # Agent definition parsing
├── backends/            # Provider-neutral backend layer
│   ├── protocol.py      # ModelBackend Protocol, ChatChunk, UsageStats
│   ├── factory.py       # create_backend() dispatch
│   ├── ollama.py        # OllamaBackend (native SDK)
│   ├── litellm.py       # LitellmBackend (OpenAI, Anthropic, Gemini, 100+)
│   └── trust.py         # Custom base URL trust validation
├── bootstrap/           # First-run bootstrap wizard
│   ├── wizard.py        # Wizard orchestration
│   ├── steps.py         # Provider-specific setup steps
│   ├── providers.py     # Curated model lists and provider metadata
│   ├── detect.py        # Config detection
│   └── modellist.py     # Model list rendering
├── builtin/             # Built-in tools (read, write, git, websearch, ...)
├── config/              # Configuration system (Clevis)
│   ├── __init__.py      # Config dataclasses, get_yoker_config()
│   ├── providers.py     # Provider configs (Ollama, OpenAI, Anthropic, Gemini, Generic)
│   ├── validators.py    # Field validators
│   └── writer.py        # TOML writer with chmod 600
├── context/             # Context management
│   ├── basic.py
│   ├── interface.py
│   ├── manager.py
│   └── persistence.py
├── events/              # Event types and recording/replay
├── exceptions.py        # Exception hierarchy (incl. NetworkError)
├── logging.py           # Structured logging
├── plugins/             # Plugin loading and registration
│   ├── __init__.py
│   ├── agents.py        # Agent definition loading
│   ├── builtin.py       # Built-in yoker plugin manifest
│   ├── loader.py        # Plugin package discovery
│   ├── manifest.py
│   ├── registration.py  # Component registration
│   ├── resources.py     # Package resource helpers
│   ├── security.py      # Plugin trust checks
│   ├── skills.py        # Plugin skill discovery
│   └── urls.py          # plugin:// URL parsing
├── schema.py            # NameSpaced base class
├── skills/              # Skill definitions and registry
├── tools/               # Tool framework
│   ├── annotations.py   # Path, Url, Query, Text markers + @tool decorator
│   ├── schema.py        # ToolSpec, build_tool_spec()
│   ├── registry.py      # ToolRegistry
│   ├── guardrails/      # PathGuardrail, WebGuardrail
│   └── web/             # Web tool backends
└── ui/                  # UI layer
    ├── base.py
    ├── batch.py
    ├── bridge.py
    ├── handler.py
    ├── interactive.py
    ├── spinner.py
    └── commands/        # UI slash-command registry
```

## Version Notes

**Current stable version:** 0.5.0

Major features in 0.5.0:
- Multi-provider backend architecture: Ollama (native SDK), OpenAI, Anthropic,
  Gemini, and any LiteLLM-supported provider
- Bootstrap wizard for interactive first-run setup (writes `~/.yoker.toml`)
- Dual backend: `OllamaBackend` (native SDK) and `LitellmBackend` (100+ providers)
- Provider configs: `OllamaConfig`, `OpenAIConfig`, `AnthropicConfig`,
  `GeminiConfig`, `GenericConfig`
- Removed `begin_session()` / `end_session()` and session lifecycle events
- UI layer (`yoker/ui/`) with `UIHandler`, `UIBridge`, `InteractiveUIHandler`,
  and `BatchUIHandler`
- Plugin system (`yoker/plugins/`) with `--with`, `__YOKER_MANIFEST__`, and
  namespaced tools/skills/agents
- Content type detection with optional `[magic]` extras
- Config loading through `get_yoker_config()` from Clevis
- CLI flag `--agents-definition` replaces `--agent`
- `NetworkError` with user-friendly messages (`__str__`) and debug messages
  (`get_debug_message()`)
- Secure API key handling: masked input during bootstrap, `chmod 600` on config
  files
- `OLLAMA_API_KEY` env var removed; configure `backend.ollama.api_key` instead

See [GitHub Releases](https://github.com/christophevg/yoker/releases) for full
version history.

## References

- **PyPI**: https://pypi.org/project/yoker/
- **Documentation**: https://yoker.readthedocs.io/
- **Repository**: https://github.com/christophevg/yoker
- **Issues**: https://github.com/christophevg/yoker/issues
- **Rationale**: docs/rationale.md - Why Yoker exists and how it compares
