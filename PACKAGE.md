# Yoker

> A Python agent harness with configurable tools and guardrails - one who yokes agents together.

## Overview

Yoker is a library-first, event-driven agent harness for Python that integrates with Ollama. It provides a transparent, configurable runtime for AI agents with structured tool execution, guardrails, and event emission. Unlike CLI-first agent frameworks, Yoker is designed to be embedded in applications with full visibility into agent operations.

Key differentiators:
- **Library-first** - Embed in applications, not locked into CLI
- **Event-driven** - Subscribe to thinking, content, and tool events
- **Async-native** - All I/O operations are async
- **Static permissions** - Deterministic boundaries via configuration
- **Transparent** - All prompts visible, editable, configurable

## Installation

```bash
pip install yoker
```

## Quick Start

### Interactive CLI

```bash
python -m yoker
```

Or with an agent definition:

```bash
python -m yoker --agent examples/agents/researcher.md
```

### Library Usage (Headless)

```python
import asyncio
from yoker import Agent
from yoker.events import Event, ContentChunkEvent

# Async event handler (recommended for I/O operations)
class MyHandler:
    async def __call__(self, event: Event) -> None:
        if isinstance(event, ContentChunkEvent):
            print(event.text, end='', flush=True)

async def main():
    agent = Agent(model="llama3.2")
    agent.add_event_handler(MyHandler())

    await agent.begin_session()
    await agent.process("What is 2+2?")
    await agent.end_session()

asyncio.run(main())
```

## Key Components

### Agent

The async-first agent that chats with Ollama and uses tools.

```python
from yoker import Agent, Config

# Initialize with config
agent = Agent(
    model="llama3.2:latest",          # Override model
    config=Config(),                   # Use defaults
    agent_path="agents/researcher.md"  # Load agent definition
)

# Access properties
print(agent.model)              # Model name
print(agent.tool_registry)     # Available tools
print(agent.context)           # Conversation history
print(agent.agent_definition)  # Loaded agent (if any)
```

**Key Methods:**
- `begin_session()` - Start session, emit SESSION_START event
- `process(message)` - Process message, handle tool calls, return response
- `end_session(reason)` - End session, emit SESSION_END event
- `add_event_handler(handler)` - Subscribe to events

### Config

Frozen dataclass configuration with auto-discovery.

```python
from yoker import Config

# Auto-discover config (./yoker.toml, ~/.yoker.toml, defaults)
config = Config.discover()

# Explicit path
config = Config.discover("./custom.toml")

# Environment variables (highest priority)
# YOKER_BACKEND_OLLAMA_MODEL=llama3.2
# YOKER_TOOLS_READ_ENABLED=false
```

**Configuration hierarchy (highest to lowest):**
1. Environment variables (`YOKER_*` or `{PREFIX}_YOKER_*`)
2. Explicit config parameter
3. Explicit config_path parameter
4. Auto-discovered config files
5. Default values

### Events

Event-driven architecture for library-first design.

```python
from yoker.events import (
    Event,
    EventType,
    SessionStartEvent,
    SessionEndEvent,
    TurnStartEvent,
    TurnEndEvent,
    ThinkingStartEvent,
    ThinkingChunkEvent,
    ThinkingEndEvent,
    ContentStartEvent,
    ContentChunkEvent,
    ContentEndEvent,
    ToolCallEvent,
    ToolResultEvent,
    ErrorEvent,
)

# Handle specific event types
class ToolHandler:
    async def __call__(self, event: Event) -> None:
        if isinstance(event, ToolCallEvent):
            print(f"Tool called: {event.tool_name}")
        elif isinstance(event, ToolResultEvent):
            print(f"Result: {event.result}")
```

**Event Types:**
- `SESSION_START/END` - Session lifecycle
- `TURN_START/END` - Turn lifecycle (user message to response)
- `THINKING_START/CHUNK/END` - LLM reasoning trace
- `CONTENT_START/CHUNK/END` - Response text streaming
- `TOOL_CALL/RESULT/CONTENT` - Tool execution
- `ERROR` - Error events

### Tools

Structured tools with guardrails and validation.

```python
from yoker.tools import ToolRegistry

# Access registered tools
registry = agent.tool_registry

# List available tools
print(registry.names)  # ['read', 'list', 'write', 'update', ...]

# Get specific tool
read_tool = registry.get("read")
```

**Available Tools:**
- `read` - Read file contents with guardrails
- `list` - Directory listing with pattern filtering
- `write` - Write files with overwrite protection
- `update` - Edit files (replace, insert, delete)
- `search` - Search file contents (regex, glob)
- `existence` - Check file/folder existence
- `mkdir` - Create directories with depth limits
- `git` - Git operations (status, log, diff, branch, show)
- `agent` - Spawn subagents with recursion limits
- `web_search` - Web search with SSRF protection
- `web_fetch` - Fetch web content with URL validation

### Agent Definitions

Load agents from Markdown files with YAML frontmatter.

```markdown
---
name: Researcher
description: A research assistant
tools:
  - read
  - search
  - web_search
model: llama3.2:latest
---

You are a research assistant. Your role is to help users find
and synthesize information from various sources.
```

```python
from yoker import Agent

agent = Agent(agent_path="agents/researcher.md")
# agent.agent_definition contains parsed definition
```

### Context

Conversation history persistence (JSONL).

```python
from yoker.context import BasicPersistenceContextManager

# Create with persistence
context = BasicPersistenceContextManager(
    storage_path="./sessions",
    session_id="my-session"
)

agent = Agent(context_manager=context)

# Context auto-saves after each turn (configurable)
# Context auto-loads on session resume
```

## Common Patterns

### Configuration

```python
from yoker import Config
from yoker.config import BackendConfig, OllamaConfig

# Default configuration
config = Config()

# Custom configuration
config = Config(
    backend=BackendConfig(
        ollama=OllamaConfig(
            model="llama3.2:latest",
            base_url="http://localhost:11434"
        )
    )
)

# Auto-discover with environment overrides
config = Config.discover()
```

### Custom Event Handler

```python
from yoker.events import Event, ContentChunkEvent, ToolCallEvent

class MyHandler:
    def __init__(self):
        self.content = []

    async def __call__(self, event: Event) -> None:
        if isinstance(event, ContentChunkEvent):
            self.content.append(event.text)
        elif isinstance(event, ToolCallEvent):
            print(f"[Tool] {event.tool_name}({event.arguments})")

handler = MyHandler()
agent.add_event_handler(handler)
await agent.process("What files are in this directory?")
print("".join(handler.content))
```

### Agent Definition

```python
from yoker import Agent, load_agent_definition

# Load from file
agent = Agent(agent_path="agents/custom.md")

# Or load directly
definition = load_agent_definition("agents/custom.md")
agent = Agent(agent_definition=definition)
```

### Session Persistence

```python
from pathlib import Path
from yoker import Agent
from yoker.context import BasicPersistenceContextManager

# Create persistent context
context = BasicPersistenceContextManager(
    storage_path=Path("./sessions"),
    session_id="my-session"  # Resume this session
)

agent = Agent(context_manager=context)
await agent.begin_session()
# ... conversation ...
await agent.end_session()

# Later: resume by using same session_id
# Context is auto-loaded from ./sessions/my-session.jsonl
```

### Subagent Spawning

```python
from yoker import Agent, Config

# Parent agent
parent = Agent(model="llama3.2:latest")

# Subagent (spawned via 'agent' tool)
# Automatically tracks recursion depth to prevent infinite loops
# Inherits guardrails from parent
# Has isolated context
```

## Dependencies

**Core:**
- `httpx>=0.25.0` - Async HTTP client
- `ollama>=0.6.0` - Ollama Python client
- `prompt_toolkit>=3.0.0` - Interactive input
- `python-dotenv>=1.0.0` - Environment variables
- `rich>=14.0.0` - Terminal output
- `structlog>=23.0.0` - Structured logging
- `pyyaml>=6.0` - YAML parsing
- `tomli>=2.0` - TOML parsing (Python < 3.11)

**Development:**
- pytest, mypy, ruff, tox, build, twine, coveralls

## Version Notes

**Current Version:** 0.4.0

Recent changes:
- Added `Config.discover()` class method for auto-discovery
- Added environment variable configuration support (`YOKER_*`)
- Added agent definition path in config (`agents.definition`)
- Fixed config file discovery and agent loading

See [GitHub Releases](https://github.com/christophevg/yoker/releases) for full version history.

## References

- **PyPI**: https://pypi.org/project/yoker/
- **Documentation**: https://yoker.readthedocs.io/
- **Repository**: https://github.com/christophevg/yoker
- **Issues**: https://github.com/christophevg/yoker/issues
- **Rationale**: docs/rationale.md - Why Yoker exists and how it compares

## Architecture

```
src/yoker/
├── __init__.py          # Public API exports
├── __main__.py          # CLI entry point
├── agent.py             # Async Agent class
├── base.py              # AgentCore (shared state)
├── thinking.py          # Thinking mode enum
├── logging.py           # Structured logging
├── exceptions.py        # Exception hierarchy
├── agents/              # Agent definition parsing
├── commands/            # Slash commands
├── config/              # Configuration system
├── context/             # Context persistence
├── events/              # Event types and handlers
└── tools/               # Tool implementations
```

**Key Design Decisions:**
- **Async-first** - All I/O operations are async
- **Event-driven** - Agent emits events, handlers subscribe
- **Library-first** - Core is a library, CLI is a thin wrapper
- **Frozen config** - Immutable configuration objects
- **Guardrails** - Defense-in-depth validation for filesystem tools
- **Static permissions** - All permissions defined upfront in configuration