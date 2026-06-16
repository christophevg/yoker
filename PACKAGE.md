# Yoker

> A Python agent harness with configurable tools and guardrails - one who yokes agents together.

## Overview

Yoker is a library-first, event-driven agent harness for Python that integrates with Ollama. It provides a transparent, configurable runtime for AI agents with structured tool execution, guardrails, event emission, and a pluggable UI layer. Unlike CLI-first agent frameworks, Yoker is designed to be embedded in applications with full visibility into agent operations.

Key differentiators:
- **Library-first** - Embed in applications, not locked into CLI
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

Load an agent definition:

```bash
python -m yoker --agents-definition examples/agents/researcher.md
```

Run in batch mode with a plugin:

```bash
printf "Summarize README.md" | python -m yoker --ui-mode batch --agents-definition examples/agents/researcher.md --with pkgq
```

CLI arguments are auto-generated from the `Config` dataclass by Clevis:

```bash
python -m yoker --backend-ollama-model llama3.2:latest --ui-mode batch --ui-show-tool-calls true
```

## Library Usage

### Agent with UIBridge and BatchUIHandler

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
  agent.add_event_handler(bridge)

  await ui.start(agent.model, "0.4.0", {"thinking_enabled": True})
  await agent.process("What files are in this directory?")
  await ui.shutdown("complete")

asyncio.run(main())
```

### InteractiveUIHandler for TUI

```python
import asyncio

from yoker import Agent
from yoker.config import get_yoker_config
from yoker.ui import InteractiveUIHandler, UIBridge
from yoker.ui.commands import create_default_registry

async def main():
  config = get_yoker_config(cli=False)
  agent = Agent(config=config)
  ui = InteractiveUIHandler()
  bridge = UIBridge(ui)
  agent.add_event_handler(bridge)
  commands = create_default_registry()

  await ui.start(agent.model, "0.4.0", {"thinking_enabled": True})

  while True:
    user_input = await ui.get_input()
    if user_input is None:
      break
    if user_input.startswith("/"):
      result = await commands.dispatch(user_input, agent, ui)
      if result:
        ui.output_command_result(result)
    else:
      await agent.process(user_input)

  await ui.shutdown("quit")

asyncio.run(main())
```

### Implementing a Custom UIHandler

```python
from typing import Any

from yoker.ui.base import BaseUIHandler

class MyUIHandler(BaseUIHandler):
  async def start(self, model: str, version: str, config: dict[str, Any]) -> None:
    print(f"Session started: {model}")

  async def shutdown(self, reason: str) -> None:
    print(f"Session ended: {reason}")

  async def get_input(self, prompt: str = "> ") -> str | None:
    return input(prompt)

  def output_command_result(self, result: str) -> None:
    print(result)

  def output_tool_call(self, tool_name: str, args: dict[str, Any]) -> None:
    print(f"Tool: {tool_name}({args})")

  def output_tool_result(self, tool_name: str, success: bool, result: str) -> None:
    print(f"Result: {tool_name} -> {result}")

  def output_tool_content(
    self,
    tool_name: str,
    operation: str,
    path: str,
    content: str | None,
    content_type: str,
    metadata: dict[str, Any],
  ) -> None:
    print(f"{tool_name} {operation} {path}")

  def output_stats(self, duration_ms: int, prompt_tokens: int, eval_tokens: int) -> None:
    print(f"Stats: {duration_ms}ms, {prompt_tokens} + {eval_tokens} tokens")

  def output_error(self, error: Exception) -> None:
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

### Direct Event Handler (Lower-Level)

```python
import asyncio

from yoker import Agent
from yoker.config import get_yoker_config
from yoker.events import ContentChunkEvent, Event, ToolCallEvent

async def handler(event: Event) -> None:
  if isinstance(event, ContentChunkEvent):
    print(event.text, end="", flush=True)
  elif isinstance(event, ToolCallEvent):
    print(f"\n[tool] {event.tool_name}({event.arguments})")

async def main():
  config = get_yoker_config(cli=False)
  agent = Agent(config=config)
  agent.add_event_handler(handler)
  await agent.process("What is 2+2?")

asyncio.run(main())
```

## Key Components

### `yoker.agent.Agent`

The async agent that chats with Ollama and uses tools.

```python
from yoker import Agent
from yoker.config import get_yoker_config

config = get_yoker_config(cli=False)
agent = Agent(config=config, agent_path="agents/researcher.md")

print(agent.model)              # Resolved model name
print(agent.tool_registry.names)  # Available tools (namespaced)
print(agent.context)            # Conversation history
print(agent.agent_definition)   # Loaded agent (if any)
print(agent.skill_registry.names)  # Available skills (namespaced)
```

**Key methods:**
- `process(message)` - Process a message, handle tool calls, return response
- `add_event_handler(handler)` - Subscribe to events
- `remove_event_handler(handler)` - Unsubscribe from events
- `inject_skill_context(skill_name, args)` - Inject a skill into the conversation

### `yoker.agent.AgentCore`

Internal shared state holder for `Agent`. Not intended for direct use.

### `yoker.ui.UIHandler`

Protocol defining the UI interface. All UI implementations satisfy this protocol.

### `yoker.ui.BaseUIHandler`

Abstract base class with state management. Subclass this for custom UI handlers.

### `yoker.ui.UIBridge`

Event dispatcher that converts `Agent` events into `UIHandler` method calls. Attach it as an event handler:

```python
from yoker.ui import UIBridge

bridge = UIBridge(ui)
agent.add_event_handler(bridge)
```

### `yoker.ui.InteractiveUIHandler`

Terminal UI using `prompt_toolkit` and Rich. Supports multiline input, history, and live streaming.

### `yoker.ui.BatchUIHandler`

Non-interactive UI using stdin/stdout/stderr. Supports predefined input messages.

```python
ui = BatchUIHandler(show_thinking=True, show_tool_calls=True, show_stats=True)
ui.set_input_messages(["Hello", "What is 2+2?"])
```

### `yoker.ui.commands.CommandRegistry`

Registry for slash-commands in the UI layer.

```python
from yoker.ui.commands import create_default_registry

commands = create_default_registry()
result = await commands.dispatch("/help", agent, ui)
```

### `yoker.config.get_yoker_config`, `UIConfig`

Load configuration via Clevis:

```python
from yoker.config import Config, get_yoker_config

# Library mode (no CLI args)
config = get_yoker_config(cli=False)

# CLI mode (parse sys.argv)
config = get_yoker_config(cli=True)

print(config.backend.ollama.model)
print(config.ui.mode)
print(config.plugins.packages)
```

Configuration hierarchy (highest to lowest):
1. Environment variables (`YOKER_*`)
2. CLI arguments (when `cli=True`)
3. `./yoker.toml`
4. `~/.yoker.toml`
5. Default values from `Config`

### `yoker.context.ContextManager`, `BasicContextManager`, `PersistenceContextManager`

```python
from yoker.context import BasicContextManager, PersistenceContextManager

# In-memory context
context = BasicContextManager()

# Persisted JSONL context
context = PersistenceContextManager(session_id="my-session")

# Resume existing session
context = PersistenceContextManager.resume("my-session")

agent = Agent(config=config, context_manager=context)
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

## Common Patterns

### Loading Configuration

```python
from yoker.config import get_yoker_config

config = get_yoker_config(cli=False)
```

### Custom UI Handler

Subclass `BaseUIHandler` and override the abstract methods. Wire with `UIBridge`.

### Batch Processing

```python
from yoker.ui import BatchUIHandler

ui = BatchUIHandler(show_tool_calls=True)
ui.set_input_messages([
  "Read README.md",
  "Summarize it in one paragraph",
])
```

### Plugin Loading

Plugins are Python packages that expose tools, skills, and agents through a `yoker` submodule or `__YOKER_MANIFEST__`.

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
model: llama3.2:latest
---

You are a research assistant. Your role is to help users find
and synthesize information from various sources.
```

```python
from yoker import Agent

agent = Agent(config=config, agent_path="agents/researcher.md")
```

Agent definitions support plugin URLs:

```bash
python -m yoker --agents-definition plugin://pkgq/agents/researcher
```

### Subagent Spawning

The `yoker:agent` tool spawns isolated subagents. Recursion depth is tracked automatically:

```python
# Parent agent
parent = Agent(config=config)

# Subagent is spawned via the agent tool
# Inherits guardrails, has isolated context, respects max_recursion_depth
```

### Skill Invocation

Skills can be invoked via slash command or by the LLM through the `yoker:skill` tool:

```text
/commit write a concise commit message
```

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

## Architecture

```
src/yoker/
├── __init__.py          # Public API exports
├── __main__.py          # CLI entry point
├── agent/               # Agent implementation
│   ├── agent.py         # Public Agent class
│   ├── core.py          # AgentCore shared state
│   ├── processing.py    # Message/tool processing
│   └── tools.py         # Agent-specific tool setup
├── agents/              # Agent definition parsing
├── commands/            # Core command definitions
├── config.py            # Configuration system (Clevis)
├── content_type.py      # MIME content type detection
├── context/             # Context management
│   ├── basic.py
│   ├── interface.py
│   ├── manager.py
│   └── persistence.py
├── events/              # Event types and recording/replay
├── exceptions.py        # Exception hierarchy
├── logging.py           # Structured logging
├── plugins/             # Plugin loading and registration
│   ├── builtin.py
│   ├── loader.py
│   ├── manifest.py
│   ├── registration.py
│   └── security.py
├── skills/              # Skill definitions and registry
├── thinking.py          # Thinking mode enum
├── tools/               # Tool implementations
└── ui/                  # UI layer
    ├── base.py
    ├── batch.py
    ├── bridge.py
    ├── handler.py
    ├── interactive.py
    ├── spinner.py
    └── commands/        # UI slash-command registry
```

**Key design decisions:**
- **Async-first** - All I/O operations are async
- **Event-driven** - Agent emits events, handlers subscribe
- **UI layer** - Terminal, batch, and custom UIs are interchangeable
- **Library-first** - Core is a library, CLI is a thin wrapper
- **Plugin system** - Namespaced tools, skills, and agents from packages
- **Frozen config** - Immutable configuration objects
- **Guardrails** - Defense-in-depth validation for filesystem and network tools
- **Static permissions** - All permissions defined upfront in configuration

## Dependencies

**Core:**
- `clevis>=0.3.3` - Configuration management with auto-generated CLI
- `httpx>=0.25.0` - Async HTTP client
- `ollama>=0.6.0` - Ollama Python client
- `prompt_toolkit>=3.0.0` - Interactive input
- `python-dotenv>=1.0.0` - Environment variables
- `rich>=14.0.0` - Terminal output
- `structlog>=23.0.0` - Structured logging
- `pyyaml>=6.0` - YAML parsing

**Optional:**
- `python-magic` / `python-magic-bin` - Content type detection (`yoker[magic]`)

**Development:**
- pytest, pytest-asyncio, pytest-cov, mypy, ruff, tox, build, twine

## Version Notes

**Current stable version:** 0.4.0

**Pending:** 0.5.0 - Major architecture refresh including:
- Removed `begin_session()` / `end_session()` and `SessionStartEvent` / `SessionEndEvent` / `ErrorEvent`
- New UI layer (`yoker/ui/`) with `UIHandler`, `UIBridge`, `InteractiveUIHandler`, and `BatchUIHandler`
- Plugin system (`yoker/plugins/`) with `--with`, `__YOKER_MANIFEST__`, and namespaced tools/skills/agents
- Content type detection with optional `[magic]` extras
- Config loading through `get_yoker_config()` from Clevis
- CLI flag `--agents-definition` replaces `--agent`

See [GitHub Releases](https://github.com/christophevg/yoker/releases) for full version history.

## References

- **PyPI**: https://pypi.org/project/yoker/
- **Documentation**: https://yoker.readthedocs.io/
- **Repository**: https://github.com/christophevg/yoker
- **Issues**: https://github.com/christophevg/yoker/issues
- **Rationale**: docs/rationale.md - Why Yoker exists and how it compares

