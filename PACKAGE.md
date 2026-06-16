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

  await ui.start(agent.model, "0.4.0", {"thinking_enabled": True})
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

Subclass `BaseUIHandler` and wire it to the agent with `UIBridge`:

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
    status = "OK" if success else "FAIL"
    print(f"Result: {status} {tool_name} -> {result}")

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

## Key Components

### `yoker.agent.Agent`

The async agent that chats with Ollama and uses tools.

```python
from yoker import Agent

agent = Agent(agent_path="agents/researcher.md")

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

### UI layer

- `yoker.ui.UIHandler` - Protocol defining the UI interface
- `yoker.ui.BaseUIHandler` - Abstract base class with state management
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

Built-in tools are registered under the `yoker:` namespace. See the [Tools List](#tools-list) for all available tools.

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

agent = Agent(agent_path="agents/researcher.md")
```

Agent definitions can also be loaded from plugins:

```bash
python -m yoker --agents-definition plugin://pkgq/agents/researcher
```

### Plugins

Plugins are Python packages that expose tools, skills, and agents through a `yoker` submodule or `__YOKER_MANIFEST__`.

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

### Loading configuration programmatically

```python
from yoker import Agent
from yoker.config import get_yoker_config

config = get_yoker_config(cli=False)
agent = Agent(config=config)
```

### Custom UI handler

Subclass `BaseUIHandler`, implement the abstract methods, and wire with `UIBridge`. See the [Custom UI handler](#custom-ui-handler) example above.

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
