# Yoker

[![PyPI](https://img.shields.io/pypi/v/yoker.svg)][pypi]
[![Python](https://img.shields.io/pypi/pyversions/yoker.svg)][pypi]
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)][uv]
[![CI](https://img.shields.io/github/actions/workflow/status/christophevg/yoker/test.yaml.svg)][ci]
[![Coverage](https://img.shields.io/coveralls/github/christophevg/yoker.svg)][coveralls]
[![License](https://img.shields.io/github/license/christophevg/yoker.svg)][license]
[![Agentic](https://img.shields.io/badge/workflow-agentic-blueviolet?style=flat-square)](https://christophe.vg/about/Agentic-Workflow)

A Python agent harness with configurable tools, guardrails, and multi-provider LLM backend integration.

## Installation

```bash
pip install yoker
```

## Quick Start

Run Yoker interactively (default — equivalent to `yoker chat`):

```bash
python -m yoker
```

Or with an agent definition:

```bash
python -m yoker --agents-definition examples/agents/researcher.md
```

Run an agentic package non-interactively:

```bash
python -m yoker run pkgq
```

Example session:

![Yoker Session](https://raw.githubusercontent.com/christophevg/yoker/master/media/session.svg)

## CLI Commands

Yoker provides seven subcommands. When no subcommand is given, `chat` is assumed
for backward compatibility — `yoker --backend-ollama-model X` routes to
`yoker chat --backend-ollama-model X`.

| Command | Description |
|---------|-------------|
| `yoker chat` | Start the interactive REPL (default subcommand) |
| `yoker run <source>` | Run an agentic package non-interactively |
| `yoker loop <source>` | Run an agentic package at intervals |
| `yoker inspect <source>` | Display a read-only report about a source |
| `yoker init` | Generate a default configuration file |
| `yoker config` | Display the effective configuration |
| `yoker container <source>` | Generate container setup for an agentic package |

```bash
yoker --help            # list all subcommands
yoker run --help        # show flags for a specific subcommand
```

### `yoker chat` — Interactive REPL

The default subcommand. Provides a rich terminal UI with multiline input,
command history, streaming output, and tool call display. Runs the bootstrap
wizard on first use when no config file exists.

```bash
yoker                           # same as `yoker chat`
yoker chat                      # explicit
yoker chat --ui-mode batch       # batch mode (stdin/stdout)
yoker chat --with pkgq           # load a plugin
yoker chat --agents-definition examples/agents/researcher.md
```

Key flags (all Config flags are available — see `yoker chat --help`):

| Flag | Effect |
|------|--------|
| `--ui-mode {interactive,batch}` | Select UI handler |
| `--ui-show-thinking` | Show LLM reasoning trace |
| `--ui-show-tool-calls` | Show tool call details |
| `--ui-show-stats` | Show turn statistics |
| `--with <package>` | Load a plugin package |
| `--agents-definition <path>` | Load an agent definition file |

### `yoker run <source>` — Run an Agentic Package

The flagship capability. Loads a source (Python module, GitHub URL, folder, or
zip file) containing an `agent.toml` manifest and runs it non-interactively.
The manifest specifies which agent to use and what initial prompt to send.

```bash
yoker run pkgq                                       # Python module
yoker run https://github.com/christophevg/pkgq        # GitHub URL
yoker run ./my-folder                                 # local folder
yoker run ./my-package.zip                            # zip file

yoker run pkgq --agent researcher --prompt "analyze"  # override manifest
yoker run pkgq --dry-run                             # preview without executing
yoker run pkgq --persist --session-id my-run          # persist session
```

Key flags:

| Flag | Effect |
|------|--------|
| `<source>` | Source to run (module, URL, folder, or zip) |
| `--agent <name>` | Override the manifest's agent |
| `--prompt <text>` | Override the manifest's prompt |
| `--dry-run` | Resolve and print manifest info without executing |
| `--persist` | Enable context persistence (saves session to JSONL) |
| `--session-id <id>` | Session ID for persistence |

**Trust model:** sources must pass the trust gate before any code is executed.
The trust gate uses your own config (not the source's manifest overrides), so a
source cannot influence its own trust decision. Trust a source by adding it to
your `yoker.toml`:

```toml
[plugins]
enabled = true

[plugins.trusted]
pkgq = true  # or "github:owner/repo@sha", "folder:/abs/path", "zip:<sha256>"
```

Use `yoker inspect <source>` to safely preview a source before trusting it.

See [Creating Agentic Packages](docs/guides/creating-agentic-packages.md) for
the `agent.toml` manifest format and how to create your own runnable packages.

### `yoker loop <source>` — Interval Execution

Runs an agentic package at intervals, reusing the `yoker run` execution path.
The source is resolved, trusted, and loaded once; each iteration sends the same
prompt through the agent.

```bash
yoker loop pkgq --interval 60                        # run every 60 seconds
yoker loop pkgq --interval 60 --max-iterations 3    # stop after 3 runs
yoker loop pkgq --persist --session-id loop-1       # reuse context across runs
yoker loop pkgq --max-duration 3600                 # stop after 1 hour
```

Key flags (in addition to all `yoker run` flags):

| Flag | Default | Effect |
|------|---------|--------|
| `--interval <seconds>` | 300 | Seconds between iterations |
| `--max-iterations <n>` | 100 | Stop after N iterations |
| `--max-duration <seconds>` | none | Stop after a wall-clock time limit |

The loop stops on `--max-iterations`, `--max-duration`, 3 consecutive failures
(with exponential backoff), or `Ctrl+C` (graceful shutdown with a summary).

### `yoker inspect <source>` — Read-Only Source Report

Displays a human-readable report about a source without executing any code. No
trust gate is required — this is safe to run on untrusted sources. For module
sources, the Python `__YOKER_MANIFEST__` cannot be discovered without importing
the package, so the report notes that trust is required.

```bash
yoker inspect pkgq                    # inspect a Python module
yoker inspect ./my-folder             # inspect a local folder
yoker inspect https://github.com/x/y # clone and inspect (read-only)
```

The report shows:

- **What it contains**: skills (names), agent definitions (names), tools (declared `tools_module` — listed but not imported)
- **What it uses**: dependencies from `pyproject.toml`, `tools_module` declaration
- **What it does**: the agent and prompt from the manifest's `[run]` section
- **Config overrides**: any config fields the manifest overrides

### `yoker init` — Generate Configuration

Creates a `~/.yoker.toml` configuration file. Interactive mode (default) runs
the bootstrap wizard for guided first-run setup. Non-interactive mode writes a
default config with all values at defaults.

```bash
yoker init                          # interactive wizard (default)
yoker init --no-interactive         # write defaults without prompting
yoker init --path ./my-config.toml  # write to a custom location
yoker init --force                  # overwrite an existing file
```

Key flags:

| Flag | Effect |
|------|--------|
| `--no-interactive` | Write a default config without the wizard |
| `--path <path>` | Write to a custom location instead of `~/.yoker.toml` |
| `--force` | Overwrite an existing config file |

Written files always have `chmod 600` permissions. The `--path` flag rejects
forbidden system prefixes (e.g. `/etc`, `/usr`).

### `yoker config` — Display Effective Configuration

Loads the merged config (user TOML + project TOML + CLI args) and prints it.
API keys are masked by default; use `--reveal` to show them in full.

```bash
yoker config              # print config as TOML
yoker config --json       # print config as JSON
yoker config --show-path  # print config file paths
yoker config --reveal     # show API keys unmasked
```

Key flags:

| Flag | Effect |
|------|--------|
| `--json` | Output as JSON instead of TOML |
| `--show-path` | Print the config file paths that were found |
| `--reveal` | Show API key values in full (masked by default) |

### `yoker container <source>` — Generate Container Setup

Generates a Dockerfile (or Containerfile for podman) and ignore file for
running a yoker agentic package in a container. The generated Dockerfile uses
JSON-array form exclusively, includes a non-root `USER` directive, pins the
yoker version, and does not bake API keys into the image.

```bash
yoker container pkgq                          # generate Dockerfile
yoker container pkgq --engine podman          # generate Containerfile
yoker container pkgq --output-dir ./container/ # write to a custom directory
yoker container pkgq --compose                # also generate docker-compose.yml
```

Key flags:

| Flag | Default | Effect |
|------|---------|--------|
| `<source>` | — | Source to containerize (module, URL, folder, zip) |
| `--engine {docker,podman}` | docker | Container engine |
| `--output-dir <path>` | `.` | Where to write generated files |
| `--base-image <image>` | `python:3.12-slim` | Base image for the Dockerfile |
| `--compose` | off | Also generate a `docker-compose.yml` |

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

Yoker is designed to be embedded as a library. The top-level `yoker` package
exposes a thin Pythonic facade (MBI-003) as the recommended high-level API,
plus a lower-level `Agent` + `UIBridge` path for full control.

#### Python API (recommended)

| Function | Use |
|----------|-----|
| `yoker.process(prompt, **kwargs)` | One-shot turn; returns the response string. |
| `yoker.do(skill_name, prompt, args="", **kwargs)` | One-shot skill invocation. |
| `yoker.agent(**kwargs) -> Agent` | Builder that returns a reusable `Agent`. |
| `yoker.session(id=..., *, persist=True, fresh=False, **kwargs)` | Async context manager yielding a multi-turn `Session` with context persistence. |
| `yoker.run_sync(coro)` | Wraps `asyncio.run` for synchronous callers (scripts, notebooks, REPLs). |

```python
import asyncio

import yoker


async def main():
  # One-shot turn.
  answer = await yoker.process("What is 2+2?")
  print(answer)

  # Reusable agent with a tool whitelist and event handler.
  reviewer = yoker.agent(
    model="qwen3.5:cloud",
    system_prompt="You are a security-focused code reviewer. Cite file:line.",
    tools=["read", "search", "list"],
  )
  report = await reviewer.process("Review src/yoker/plugins/security.py for vulnerabilities.")
  print(report)

  # Multi-turn conversation with automatic context persistence.
  async with yoker.session(id="refactor-auth") as session:
    await session.agent.process("Read src/auth.py and identify the main responsibilities.")
    await session.agent.process("Suggest a refactor that splits authentication from session management.")


asyncio.run(main())
```

Sync callers (scripts, notebooks):

```python
import yoker

answer = yoker.run_sync(yoker.process("What files are in the current directory?"))
print(answer)
```

See `examples/python_api/` for the full set of facade examples (`one_shot.py`,
`agent_builder.py`, `session.py`, `run_skill.py`, `workflow.py`,
`event_handling.py`, `sync_usage.py`) and the [Quick start](https://yoker.readthedocs.io/en/latest/quickstart.html) docs.

#### Low-level event-driven API (advanced)

The `Agent` class emits events; your application implements a `UIHandler` (or uses the built-in handlers) and wires events through `UIBridge`.

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
- `examples/research_workflow.py` - Running a researcher agent programmatically

## Plugins

Yoker can load tools, skills, and agents from external Python packages via the plugin system.

### Quick Start

Plugins are **disabled by default** for security. Enable them in your configuration:

```bash
# Create yoker.toml
cat > yoker.toml << EOF
[plugins]
enabled = true
EOF

# Secure the configuration file
chmod 600 yoker.toml
```

Load plugins with `--with`:

```bash
# Using uvx (recommended)
uvx --with pkgq yoker --with pkgq

# Or install first
pip install pkgq
python -m yoker --with pkgq
```

### Security Workflow

When you load a plugin for the first time, Yoker shows a confirmation dialog with the plugin's components (tools, skills, agents). Review them carefully—plugins can execute arbitrary code.

After accepting, Yoker displays instructions to trust the plugin permanently:

```toml
[plugins.trusted]
pkgq = true
```

### Using Plugin Components

Verify loaded components with:

```
> /skills     # List all skills (including plugin skills)
> /tools      # List all tools (including plugin tools)
> /pkgq:create  # Invoke a plugin skill directly
```

### Available Plugins

- **pkgq** - Package documentation tools (PyPI: `pip install pkgq`)
  - `pkgq:find` tool - Find Python package documentation
  - `pkgq:create` skill - Generate PACKAGE.md for a project
  - `pkgq:update` skill - Update documentation for new versions

### Developing Plugins

See `examples/plugins/demo/README.md` for a complete plugin development guide.

For comprehensive plugin documentation including security best practices, configuration reference, and troubleshooting, see [docs/plugins.md](docs/plugins.md).

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
- [x] CLI subcommands - `chat`, `run`, `loop`, `inspect`, `init`, `config`, `container`
- [x] Agentic packages - Run sources (module, GitHub, folder, zip) via `yoker run` with `agent.toml` manifest
- [x] Chat loop - Interactive conversation with any configured provider
- [x] Multi-provider backends - Ollama (native SDK), OpenAI, Anthropic, Google Gemini, and 100+ providers via LiteLLM
- [x] Bootstrap wizard - Interactive first-run setup that writes `~/.yoker.toml` for you
- [x] Tool calling - Structured tool execution with parameters
- [x] `read` tool - Read file contents with guardrails
- [x] `list` tool - Directory listing with pattern filtering
- [x] `write` tool - Write files with overwrite protection
- [x] `update` tool - Edit existing files with replace, insert, and delete operations
- [x] `search` tool - Search file contents with regex or filenames with glob
- [x] `existence` tool - Check if files or folders exist with security hardening
- [x] `mkdir` tool - Create directories with recursive parent creation and depth limits
- [x] `git` tool - Git operations (status, log, diff, branch, show) with permission-controlled commit/push
- [x] `make` tool - Execute Makefile targets (e.g., `make check`, `make test`) with target validation, per-target env var allowlist, and process-group timeout enforcement.
- [x] `websearch` tool - Web search with SSRF protection, domain filtering, and rate limiting
- [x] `webfetch` tool - Fetch web content with SSRF protection, URL validation, and size limits
- [x] `agent` tool - Spawn subagents with isolated context and recursion limits
- [x] `skill` tool - Invoke skills dynamically by name with full content loading
- [x] Slash commands - Built-in commands: `/help`, `/think on|off|silent`, `/skills`, `/context`, `/tools`, `/agents`
- [x] Thinking mode - LLM reasoning trace with gray output (on/off/silent)
- [x] Streaming - Real-time token streaming from any provider
- [x] Configuration - TOML-based configuration system via Clevis
- [x] Agent definitions - Load agents from Markdown files with YAML frontmatter
- [x] Package plugins - Load tools, skills, and agents from Python packages with `--with`
- [x] Multiline input - `Esc+Enter` for newlines, `Enter` to submit
- [x] Rich output - Styled terminal output with Rich
- [x] Event-driven architecture - Library-first design with event emission
- [x] Context persistence - Session resumption with JSONL storage
- [x] Event logging - Full session replay capability
- [x] Demo scripts - Generate documentation screenshots from Markdown scripts
- [x] Schema-driven guardrails - Tool parameters are annotated with `yoker.tools.annotations` markers (`Path`, `Url`, `Query`, `Text`); the harness strips the metadata before sending schemas to the model and dispatches the matching guardrail at execution time
- [x] Permissions - Static TOML-based access control
- [x] Secure API key handling - Masked input during bootstrap, config files written with `chmod 600`

**Planned Features:**
- [ ] Multi-agent orchestration - Run coordinated agent teams
- [ ] Keyring integration - Store API keys in the OS keychain instead of config files (TODO S.1)
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
| `/skills` | List available skills |
| `/context` | Show current conversation context |
| `/tools` | List available tools and their availability |
| `/agents` | Show loaded and available agents |

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

Or create a `yoker.toml` file for explicit configuration. Yoker supports multiple
providers — Ollama (native SDK), and OpenAI, Anthropic, Google Gemini, plus any
LiteLLM-supported provider (e.g. Groq, Cohere, Azure, Mistral) via the LiteLLM backend:

```toml
[harness]
name = "my-yoke"

[logging]
level = "INFO"

[backend]
provider = "ollama"  # or "openai", "anthropic", "gemini", or any litellm provider

[backend.ollama]
base_url = "http://localhost:11434"
api_key = ""  # Optional API key for authenticated Ollama endpoints
model = "qwen3.5:cloud"

[agents]
definition = "./agents/researcher.md"  # Optional: agent definition file

[tools.read]
enabled = true
allowed_extensions = [".txt", ".md", ".py"]
```

### `make` tool configuration

The `make` tool executes Makefile targets with target validation, a
per-target env var allowlist, and process-group timeout enforcement.

```toml
[tools.make]
timeout_ms = 300000       # default per-call timeout
max_output_kb = 100       # per-stream (stdout/stderr) truncation limit
max_env_var_bytes = 4096  # per-env-var value byte limit

# Per-target env var allowlist (deny-by-default). Keys are Makefile
# target names; values are the env var names that target may receive.
# Targets not listed deny all env vars.
[tools.make.allowed_env_vars]
test = ["TEST"]
lint = ["LINT_FLAGS", "LINT_CONFIG"]
```

The same `allowed_env_vars` may also be written as inline tables:

```toml
[tools.make]
timeout_ms = 300000
allowed_env_vars = {test = ["TEST"], lint = ["LINT_FLAGS", "LINT_CONFIG"]}
```

**Env-inheritance residual risk:** Makefile recipes inherit the yoker
process env, so any secret present in yoker's env (API keys, tokens) is
readable by recipes. The per-target allowlist and framework hard-denylist
only govern agent-supplied `env_vars` — they do not filter the inherited
env. Load sensitive API keys from a secrets store (not plain env vars)
when running untrusted agents.

Example for OpenAI:

```toml
[backend]
provider = "openai"

[backend.openai]
api_key = "${OPENAI_API_KEY}"  # Interpolated from environment variables
model = "gpt-4o-mini"
```

The bootstrap wizard (run `python -m yoker` with no config present) writes
`~/.yoker.toml` for you interactively, including masked API key entry and
`chmod 600` file permissions. See [Model Catalog](docs/models.md) for the
curated model lists per provider.

See `examples/yoker.toml` for the full configuration reference.

## Architecture

Yoker uses an **event-driven architecture** for library-first design. The Agent emits events; the UI layer receives them through `UIBridge` and decides how to present them.

![Architecture Diagram](https://raw.githubusercontent.com/christophevg/yoker/master/media/architecture-diagram.svg)

**Agent layer** (`yoker.core`): Configuration, context management, tool execution, and event emission. It has no terminal or presentation logic.

**Backend layer** (`yoker.backends`): Provider-neutral streaming chat backend. `OllamaBackend` uses the native Ollama SDK; `LitellmBackend` unifies OpenAI, Anthropic, Gemini, and 100+ LiteLLM-supported providers. The `ModelBackend` Protocol normalizes streaming into provider-agnostic `ChatChunk` events.

**UI layer** (`yoker.ui`): Implements the `UIHandler` protocol. Built-in implementations:

- `InteractiveUIHandler` - Rich terminal UI with streaming output
- `BatchUIHandler` - stdin/stdout/stderr for scripts and pipelines

**Bridge** (`yoker.ui.UIBridge`): Converts agent events into `UIHandler` method calls so the agent stays independent of presentation details.

**Event Types**: Turn (start/end), Thinking (start/chunk/end), Content (start/chunk/end), Tool (call/result/content), Command

## Providers

Yoker supports multiple LLM providers through a dual backend architecture:

| Provider | Backend | API key required | Free tier |
|----------|---------|-----------------|-----------|
| Ollama | Native Ollama SDK | No (app path) or yes (API key) | Yes |
| OpenAI | LiteLLM | Yes | No |
| Anthropic | LiteLLM | Yes | No |
| Google Gemini | LiteLLM | Yes | Yes (limited) |
| Any LiteLLM provider | LiteLLM | Varies | Varies |

The bootstrap wizard offers curated model lists for each provider. See
[Model Catalog](docs/models.md) for the full list, or run `python -m yoker`
with no config to launch the wizard.

**Security**: API keys are collected via masked input during bootstrap, and
config files are written with `chmod 600` permissions. API keys can also be
injected from environment variables using Clevis interpolation
(`${OPENAI_API_KEY}`). Keyring integration for OS keychain storage is planned
(TODO S.1).

## Documentation

- [Full documentation](https://yoker.readthedocs.io/)
- [Installation guide](https://yoker.readthedocs.io/en/latest/installation.html)
- [Quick start](https://yoker.readthedocs.io/en/latest/quickstart.html)
- [CLI reference](docs/cli.md) - Subcommands, flags, and examples
- [Creating agentic packages](docs/guides/creating-agentic-packages.md) - `agent.toml` manifest format and trust model
- [Model catalog](docs/models.md) - Curated models per provider
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
