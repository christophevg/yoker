# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

yoker is a Python agent harness with configurable tools, guardrails, and Ollama backend integration. It provides a structured, safe environment for AI agents to execute tasks with well-defined boundaries.

**Name**: "yoker" - One who yokes. The agent noun from "yoke" (PIE *yeug-* meaning "to join"). Pairs with "clitic" (both are joining tools).

## Development Setup

Uses pyenv for virtual environment management. A virtual environment is required for all development operations.

```bash
# Create pyenv virtualenv
make setup

# Activate the virtual environment
pyenv activate yoker

# Install dependencies
make install
```

For automatic activation, create `.python-version`:
```bash
echo 'yoker' > .python-version
```

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

## Architecture

### Package Structure

```
src/yoker/
  __init__.py          # Public API exports
  config/               # TOML loading and validation
  context/              # Context persistence (JSONL)
  tools/                # Tool implementations (List, Read, Write, Update, Search, Agent)
  guardrails/           # Guardrail enforcement
  agents/               # Agent definition parser and runner
  backend/              # Ollama client
  main.py               # CLI entry point
```

### Core Components

1. **Configuration System**: TOML config file, Markdown agent definitions with YAML frontmatter
2. **Tool System**: 6 specific tools with guardrails (List, Read, Write, Update, Search, Agent)
3. **Context Manager**: JSONL-based conversation persistence
4. **Ollama Integration**: HTTP client with streaming support

### Key Design Decisions

- **No generic Bash tool**: Specific tools with explicit guardrails
- **Guardrails are global**: Same rules for all agents, tool availability can be reduced per agent
- **Fresh context for subagents**: Each subagent starts with empty context
- **Depth tracking is internal**: Agents don't know their depth, they handle errors

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

- `httpx>=0.25.0` - HTTP client (async, streaming)
- `structlog>=23.0.0` - Structured logging
- `pyyaml>=6.0` - Frontmatter parsing

## Documentation

See `analysis/` for:
- `functional.md` - Full functional analysis
- `interview.md` - Requirements interview notes

## Related Projects

- **clitic**: CLI/TUI framework for interactive applications
- **c3**: Claude Code configuration harness

yoker provides the agent runtime; clitic provides the TUI.