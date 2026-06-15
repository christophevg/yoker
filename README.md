# Yoker

[![PyPI](https://img.shields.io/pypi/v/yoker.svg)][pypi]
[![Python](https://img.shields.io/pypi/pyversions/yoker.svg)][pypi]
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)][uv]
[![CI](https://img.shields.io/github/actions/workflow/status/christophevg/yoker/test.yaml.svg)][ci]
[![Coverage](https://img.shields.io/coveralls/github/christophevg/yoker.svg)][coveralls]
[![License](https://img.shields.io/github/license/christophevg/yoker.svg)][license]
[![Agentic](https://img.shields.io/badge/workflow-agentic-blueviolet?style=flat-square)](https://christophe.vg/about/Agentic-Workflow)

A Python agent harness with configurable tools, guardrails, and Ollama backend integration.

## Installation

```bash
pip install yoker
```

## Quick Start

Run Yoker interactively (default):

```bash
python -m yoker
```

Or with an agent definition:

```bash
python -m yoker --agents-definition examples/agents/researcher.md
```

Example session:

![Yoker Session](https://raw.githubusercontent.com/christophevg/yoker/master/media/session.svg)

## Usage Modes

Yoker supports three ways to run: interactive CLI, batch/non-interactive, and as a library.

### Interactive Mode

Interactive mode is the default. It provides a rich terminal UI with multiline input, command history, streaming output, and tool call display.

```bash
python -m yoker

# With an agent definition
python -m yoker --agents-definition examples/agents/researcher.md

# Hide tool calls and statistics
python -m yoker --ui-mode interactive
```

See [Interactive Input](#interactive-input) and [Slash Commands](#slash-commands) for the available keyboard shortcuts and commands.

### Batch Mode

Batch mode reads input from stdin and writes response content to stdout. Thinking, tool calls, errors, and statistics are written to stderr. This makes Yoker usable in pipelines and scripts.

```bash
# Single prompt
python -m yoker --ui-mode batch
Hello, how can you help me?
^D

# Pipe input
printf "Hello\nWhat is 2+2?\n" | python -m yoker --ui-mode batch

# Show thinking and tool calls on stderr
printf "Hello\n" | python -m yoker --ui-mode batch --ui-show-thinking --ui-show-tool-calls
```

Batch mode options:

| Flag | Effect |
|------|--------|
| `--ui-mode batch` | Enable batch mode |
| `--ui-show-thinking` | Print thinking/trace output to stderr |
| `--ui-show-tool-calls` | Print tool call information to stderr |
| `--ui-show-stats` | Print turn statistics to stderr |

### Library Usage

Yoker is designed to be embedded as a library. The `Agent` class emits events; your application implements a `UIHandler` (or uses the built-in handlers) and wires events through `UIBridge`.

```python
import asyncio
from yoker import Agent, __version__
from yoker.config import get_yoker_config
from yoker.ui import BatchUIHandler, UIBridge

async def main():
  config = get_yoker_config(cli=False)
  agent = Agent(config=config)

  ui = BatchUIHandler(show_thinking=True, show_tool_calls=True)
  bridge = UIBridge(ui)
  agent.add_event_handler(bridge)

  await ui.start(agent.model, __version__, {})
  try:
    response = await agent.process("Hello, how can you help me?")
    print(response)
  finally:
    await ui.shutdown("complete")

asyncio.run(main())
```

See the `examples/` directory for more complete examples:

- `examples/batch_mode.py` - Batch mode with predefined messages
- `examples/library_usage.py` - Using Yoker as a library without the CLI
- `examples/custom_handler.py` - Implementing a custom `UIHandler`

## Why Yoker?

Yoker fills a unique gap in the coding agent ecosystem: a **library-first, transparent agent harness** designed for developers who want full control, visibility, and simplicity.

**Key Differentiators:**
- **Library-first** - Embed in your applications, not locked into a CLI
- **LLM-neutral** - Choose your provider, your model, your cost model
- **No hidden manipulation** - All prompts visible, editable, configurable
- **Static permissions** - Deterministic boundaries, not runtime prompts
- **Full transparency** - Event-driven, everything inspectable

See [docs/rationale.md](docs/rationale.md) for the full rationale and comparison with other solutions.

## Features

**Current Features:**
- [x] Chat loop - Interactive conversation with Ollama
- [x] Tool calling - Structured tool execution with parameters
- [x] `read` tool - Read file contents with guardrails
- [x] `list` tool - Directory listing with pattern filtering
- [x] `write` tool - Write files with overwrite protection
- [x] `update` tool - Edit existing files with replace, insert, and delete operations
- [x] `search` tool - Search file contents with regex or filenames with glob
- [x] `existence` tool - Check if files or folders exist with security hardening
- [x] `mkdir` tool - Create directories with recursive parent creation and depth limits
- [x] `git` tool - Git operations (status, log, diff, branch, show) with permission-controlled commit/push
- [x] `web_search` tool - Web search with SSRF protection, domain filtering, and rate limiting
- [x] `web_fetch` tool - Fetch web content with SSRF protection, URL validation, and size limits
- [x] `agent` tool - Spawn subagents with isolated context and recursion limits
- [x] `skill` tool - Invoke skills dynamically by name with full content loading
- [x] Slash commands - Built-in commands: `/help`, `/think on|off`
- [x] Thinking mode - LLM reasoning trace with gray output
- [x] Streaming - Real-time token streaming from Ollama
- [x] Configuration - TOML-based configuration system
- [x] Agent definitions - Load agents from Markdown files with YAML frontmatter
- [x] Multiline input - `Esc+Enter` for newlines, `Enter` to submit
- [x] Rich output - Styled terminal output with Rich
- [x] Event-driven architecture - Library-first design with event emission
- [x] Context persistence - Session resumption with JSONL storage
- [x] Event logging - Full session replay capability
- [x] Demo scripts - Generate documentation screenshots from Markdown scripts
- [x] Update tool - Edit existing files with replace, insert, and delete operations

**Planned Features:**
- [ ] Guardrails - Tool parameter validation
- [ ] Permissions - Static TOML-based access control
- [ ] Multi-agent orchestration - Run coordinated agent teams
- [ ] Backend providers - OpenAI, Anthropic, custom backends
- [ ] Tool timing metrics - Performance tracking
- [ ] Token usage tracking - Cost monitoring
- [ ] Tool result caching - Reduce redundant calls
- [ ] Parallel tool execution - Concurrent read operations

### Interactive Input

The interactive session supports:

- **Multiline input**: Press `Esc+Enter` to add newlines, `Enter` to submit
- **Command history**: Up/Down arrows navigate previous messages
- **History search**: `Ctrl+R` to search through history
- **Keyboard navigation**: Arrow keys, Ctrl+A/E for cursor positioning
- **Text selection**: Click and drag to select output, copy with Ctrl+Shift+C or Cmd+C

### Slash Commands

| Command | Description |
|---------|-------------|
| `/help` | Show available commands |
| `/think on\|off` | Enable/disable LLM thinking trace |

### Thinking Mode

When thinking is enabled, the LLM shows its reasoning process:

```
[Thinking]
Let me analyze this step by step...
First, I need to understand the file structure...

[Response]
Based on my analysis, here's what I found...
```

### Demo Session Script

Generate terminal screenshots for documentation from Markdown script files:

```bash
# Run default demo script (demos/session.md)
python scripts/demo_session.py

# Run a specific demo script
python scripts/demo_session.py --script demos/list-tool.md

# Run all demo scripts in a directory
python scripts/demo_session.py --scripts-dir demos/

# Real LLM + log conversation for replay
python scripts/demo_session.py --script demos/session.md --log

# Replay from log (no LLM calls)
python scripts/demo_session.py --script demos/session.md --replay

# With an agent definition
python scripts/demo_session.py --script demos/session.md --agent examples/agents/markdown.md
```

## Configuration

Yoker auto-discovers configuration files:

1. `./yoker.toml` (current directory)
2. `~/.yoker.toml` (user home directory)
3. Built-in defaults

```bash
# Zero-configuration startup - uses auto-discovered config
python -m yoker
```

Or create a `yoker.toml` file for explicit configuration:

```toml
[harness]
name = "my-yoke"
log_level = "INFO"

[backend]
provider = "ollama"

[backend.ollama]
base_url = "http://localhost:11434"
model = "llama3.2:latest"

[agents]
definition = "./agents/researcher.md"  # Optional: agent definition file

[tools.read]
enabled = true
allowed_extensions = [".txt", ".md", ".py"]
```

See `examples/yoker.toml` for the full configuration reference.

## Architecture

Yoker uses an **event-driven architecture** for library-first design. The Agent emits events; the UI layer receives them through `UIBridge` and decides how to present them.

![Architecture Diagram](https://raw.githubusercontent.com/christophevg/yoker/master/media/architecture-diagram.svg)

**Agent layer** (`yoker.agent`): Configuration, context management, tool execution, and event emission. It has no terminal or presentation logic.

**UI layer** (`yoker.ui`): Implements the `UIHandler` protocol. Built-in implementations:

- `InteractiveUIHandler` - Rich terminal UI with streaming output
- `BatchUIHandler` - stdin/stdout/stderr for scripts and pipelines

**Bridge** (`yoker.ui.UIBridge`): Converts agent events into `UIHandler` method calls so the agent stays independent of presentation details.

**Event Types**: Turn (start/end), Thinking (start/chunk/end), Content (start/chunk/end), Tool (call/result/content), Command

## Documentation

- [Full documentation](https://yoker.readthedocs.io/)
- [Installation guide](https://yoker.readthedocs.io/en/latest/installation.html)
- [Quick start](https://yoker.readthedocs.io/en/latest/quickstart.html)
- [Why Yoker?](docs/rationale.md) - Project rationale and comparison
- [Architecture](https://github.com/christophevg/yoker/blob/master/analysis/architecture.md)

## Development

```bash
git clone https://github.com/christophevg/yoker.git
cd yoker
make env-dev  # Create virtual environment and install dependencies

make test     # Run tests with coverage
make check    # Type checking + linting
make docs     # Build documentation
```

Requires Python 3.10+. Uses [uv](https://docs.astral.sh/uv/) for dependency management. See [CLAUDE.md](CLAUDE.md) for project conventions.

## Contributing

Contributions welcome! Please read [CLAUDE.md](CLAUDE.md) for project conventions and development guidelines.

## Changelog

See [GitHub Releases](https://github.com/christophevg/yoker/releases) for version history.

## License

MIT License - see [LICENSE](LICENSE) for details.

---

**Name**: "yoker" - One who yokes. The agent noun from "yoke" (PIE *yeug-* meaning "to join"). Pairs with "clitic" (both are joining tools). See [docs/NAME.md](docs/NAME.md) for full etymology.

[pypi]: https://pypi.org/project/yoker/
[uv]: https://docs.astral.sh/uv/
[ci]: https://github.com/christophevg/yoker/actions
[coveralls]: https://coveralls.io/github/christophevg/yoker
[license]: https://github.com/christophevg/yoker/blob/main/LICENSE
