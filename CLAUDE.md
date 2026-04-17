# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

yoker is a Python agent harness with configurable tools, guardrails, and Ollama backend integration. It provides a structured, safe environment for AI agents to execute tasks with well-defined boundaries.

**Name**: "yoker" - One who yokes. The agent noun from "yoke" (PIE *yeug-* meaning "to join"). Pairs with "clitic" (both are joining tools).

**PyPI**: https://pypi.org/project/yoker/

## Current State: Minimal Prototype

The project currently has a **minimal working prototype** that must remain functional at all times:

```
src/yoker/
  __init__.py    # Version info
  __main__.py    # Entry point: python -m yoker
  agent.py       # Agent class with chat loop + tool calling
  tools.py       # read() tool
```

**Running the prototype:**
```bash
# Activate virtual environment
pyenv activate yoker

# Run interactive chat
python -m yoker
# or
yoker
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

## Related Projects

- **clitic**: CLI/TUI framework for interactive applications (../clitic)
- **c3**: Claude Code configuration harness (../c3)

yoker provides the agent runtime; clitic provides the TUI.

## Research

See `research/` for research on coding agent harnesses:
- `research/2026-04-17-coding-agent-harness/` - Analysis of Claude Code, Aider, Cursor, Windsurf, Cline architectures