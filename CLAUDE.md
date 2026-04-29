# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

yoker is a Python agent harness with configurable tools, guardrails, and Ollama backend integration. It provides a structured, safe environment for AI agents to execute tasks with well-defined boundaries.

**Name**: "yoker" - One who yokes. The agent noun from "yoke" (PIE *yeug-* meaning "to join"). Pairs with "clitic" (both are joining tools).

**PyPI**: https://pypi.org/project/yoker/

## Current State: Working Prototype

The project has a **working prototype** with event-driven architecture and interactive chat:

```
src/yoker/
  __init__.py          # Public API exports
  __main__.py          # Entry point with prompt_toolkit (application layer)
  agent.py             # Agent class with event emission (library layer)
  agents/
    __init__.py        # Agents public API
    schema.py          # AgentDefinition frozen dataclass
    loader.py          # Markdown + YAML frontmatter parsing
    validator.py       # Agent definition validation
  commands/
    __init__.py        # Commands public API
    base.py            # Command dataclass
    registry.py        # Command registry
    help.py            # /help command
    think.py           # /think command
  config/
    __init__.py        # Config public API
    loader.py          # TOML configuration loading
    schema.py          # Frozen dataclass configuration schema
    validator.py       # Configuration validation
  events/
    __init__.py        # Events public API
    types.py           # Event dataclasses (Session, Turn, Thinking, Content, Tool, Error)
    handlers.py        # EventHandler protocol and ConsoleEventHandler
  exceptions.py        # Custom exception hierarchy
  tools/
    __init__.py        # Tools public API
    base.py            # Tool ABC and ToolResult
    guardrails.py      # Guardrail protocol
    path_guardrail.py  # PathGuardrail implementation
    registry.py        # ToolRegistry
    read.py            # ReadTool
    list.py            # ListTool
    write.py           # WriteTool
    update.py          # UpdateTool
    search.py          # SearchTool
```

**Running the prototype:**
```bash
# Activate virtual environment
pyenv activate yoker

# Run interactive chat
python -m yoker

# Run with configuration file
python -m yoker --config yoker.toml

# Run with specific model
python -m yoker --model llama3.2:latest

# Run with an agent definition
python -m yoker --agent examples/agents/researcher.md
```

**Interactive Features:**
- Multiline input: `Esc+Enter` adds newlines, `Enter` submits
- Command history: Up/Down arrows navigate previous messages
- History search: `Ctrl+R` to search through history
- Mouse support: Click to position cursor
- Slash commands: `/help`, `/think on|off`
- Thinking mode: LLM reasoning trace in gray
- Streaming: Real-time token output from Ollama

**Demo Script:**
```bash
# Generate terminal screenshot
python scripts/demo_session.py

# With logging (for replay)
python scripts/demo_session.py --log

# Replay from log (no LLM)
python scripts/demo_session.py --replay
```

**IMPORTANT: Development Approach**

When implementing features from the architecture, **refactor the minimal prototype incrementally**:
1. Extract functionality from the prototype into proper modules
2. Add tests for new functionality
3. Verify the prototype still works after each change
4. Never break the working `python -m yoker` command

The prototype is the foundation - all architecture components will be extracted from it, not built separately.

## Architecture

See `analysis/architecture.md` for the full architecture definition including:
- Pluggable components (Context Manager, Backend Provider, Observation Layer, Permissions)
- Roadmap phases (MVP → Phase 1 → Phase 2 → Phase 3 → Phase 4)
- Component decision rationale

### Target Package Structure

```
src/yoker/
  __init__.py          # Public API exports
  config/              # TOML loading and validation
  context/             # Context persistence (JSONL, pluggable)
  backend/             # Ollama client (pluggable)
  permissions/         # Permission enforcement
  tools/               # Tool implementations with guardrails
  observation/         # Observation layer (pluggable)
  agents/              # Agent definition parser and runner
  statistics.py        # Token and time tracking
  logging.py           # Structured logging setup
  __main__.py          # CLI entry point
```

### Key Design Decisions

- **Pluggable architecture**: Every major component is an interface with swappable implementations
- **No generic Bash tool**: Specific tools with explicit guardrails
- **Static permissions**: All permissions defined upfront in configuration
- **Per-agent model configuration**: Each agent can use a different model
- **Sequential tool execution**: Tools run one at a time (parallel reads in Phase 1)
- **Library-first design**: Core is a library, CLI/TUI is a thin wrapper

## Development Setup

Uses pyenv for virtual environment management. A virtual environment is required for all development operations.

```bash
# Create pyenv virtualenv
make setup

# Activate the virtual environment
pyenv activate yoker

# Install dependencies (includes dev dependencies)
make install
```

For automatic activation, a `.python-version` file is already present.

## Makefile Targets

| Target | Description |
|--------|-------------|
| `make setup` | Create pyenv virtualenv |
| `make activate` | Show activation instructions |
| `make install` | Install dev dependencies (venv required) |
| `make test` | Run tests with coverage |
| `make test-all` | Run tests against all Python versions |
| `make docs` | Build HTML documentation |
| `make docs-view` | Build and open documentation in browser |
| `make typecheck` | Run mypy type checking |
| `make lint` | Run ruff linting |
| `make format` | Format code with ruff |
| `make check` | Run all checks (typecheck + lint) |
| `make build` | Build package distributions |
| `make publish` | Build and publish to PyPI |
| `make clean` | Remove build artifacts |
| `make demo` | Generate main session screenshot (`media/session.svg`) |
| `make demos` | Generate all demo screenshots in `demos/` |

## Pre-Commit Requirements

Before any commit, the following must be verified:

1. **All tests pass:** `make test`
2. **Type checking passes:** `make typecheck`
3. **Linting passes:** `make lint`

**IMPORTANT**: The minimal prototype must remain working. After any refactoring, run:
```bash
python -m yoker
```
And verify it starts correctly.

## Code Style

- Two-space indentation
- 100 character max line length
- Full type hints required (mypy strict mode)
- Public API explicitly exported via `__init__.py`
- One public class per file
- Private members prefixed with `_`

## Testing

- Test coverage target: >80%
- Tests located in `tests/` directory
- pytest with asyncio mode enabled
- Coverage reporting via pytest-cov

## Dependencies

**Core:**
- `httpx>=0.25.0` - HTTP client (async, streaming)
- `ollama>=0.6.0` - Ollama Python client
- `prompt_toolkit>=3.0.0` - Interactive input with multiline support
- `rich>=14.0.0` - Rich terminal output
- `structlog>=23.0.0` - Structured logging
- `pyyaml>=6.0` - Frontmatter parsing
- `tomli>=2.0` - TOML parsing (Python < 3.11)

**Dev:**
- pytest, mypy, ruff, sphinx, tox, build, twine

## Documentation

- `README.md` - Project overview and quick start
- `docs/` - Sphinx documentation (build with `make docs`)
- `analysis/functional.md` - Full functional analysis
- `analysis/architecture.md` - Architecture definition and roadmap
- `analysis/interview.md` - Requirements interview notes

## Session Screenshot & Documentation Maintenance

**IMPORTANT**: When making changes that affect visible features or documentation, follow these steps:

### Session Screenshot Workflow

The project maintains a visual record of improvements in `media/`:

1. **Generate screenshots from demo scripts:**
   ```bash
   make demo                                # Generate main session screenshot
   make demos                               # Generate all demo screenshots
   python scripts/demo_session.py --script demos/session.md --log
   python scripts/demo_session.py --script demos/session.md --replay
   ```

2. **Output files:**
   - `media/demo-{feature}.svg` - Feature-specific screenshots (used in docs)
   - `media/session.svg` - Main session screenshot (used in README)
   - `media/events-{feature}.jsonl` - Conversation logs (with `--log`)

3. **Update documentation when features change:**
   - Regenerate screenshots: `make demos`
   - Update `docs/_static/session.svg` for Sphinx docs
   - Ensure README.md and docs reflect current capabilities

### Demo Script Writing Strategy

Each feature/tool gets its own focused demo script in `demos/`:

- **One feature per script** — keep screenshots small and focused
- **Explicit brevity constraints** — add instructions like "Reply in 2 lines or less" or "Output only those lines, no commentary" to keep images concise
- **Single-message scripts preferred** — avoid multi-turn demos unless necessary to show interaction
- **Avoid unconstrained questions** — never ask open-ended questions that trigger long LLM responses
- **Use pattern-based file queries** — e.g. `List files matching "CLAUDE*"` instead of broad directory listings

See existing scripts (`demos/list-tool.md`, `demos/write-tool.md`) for examples.

### Documentation Update Checklist

When adding or modifying features, update:

- [ ] `README.md` - Add to features table, update examples
- [ ] `docs/quickstart.md` - Update usage examples
- [ ] `docs/installation.md` - Add new dependencies
- [ ] `CLAUDE.md` - Update current state, package structure
- [ ] `media/session.svg` - Regenerate if UI/output changes
- [ ] `docs/_static/session.svg` - Copy from media for docs

### Demo Script Features

| Flag | Description |
|------|-------------|
| `--script PATH` | Run a specific demo script |
| `--scripts-dir PATH` | Run all demo scripts in directory |
| `--log` | Log conversation to script's events file |
| `--replay` | Replay from events file (no LLM calls) |
| `--output PATH` | Override output SVG path |

Use `--log` when making non-LLM improvements to capture conversation for replay.

## Related Projects

- **clitic**: CLI/TUI framework for interactive applications (../clitic)
- **c3**: Claude Code configuration harness (../c3)

yoker provides the agent runtime; clitic provides the TUI.

## Research

See `research/` for research on coding agent harnesses:
- `research/2026-04-17-coding-agent-harness/` - Analysis of Claude Code, Aider, Cursor, Windsurf, Cline architectures