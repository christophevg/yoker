# Yoker

[![PyPI version](https://img.shields.io/pypi/v/yoker.svg)](https://pypi.org/project/yoker/)
[![PyPI downloads](https://img.shields.io/pypi/dm/yoker.svg)](https://pypistats.org/packages/yoker)
[![Python versions](https://img.shields.io/pypi/pyversions/yoker.svg)](https://pypi.org/project/yoker/)
[![License](https://img.shields.io/github/license/christophevg/yoker)](https://github.com/christophevg/yoker/blob/master/LICENSE)
[![Documentation Status](https://readthedocs.org/projects/yoker/badge/?version=latest)](https://yoker.readthedocs.io/en/latest/?badge=latest)
[![Tests](https://github.com/christophevg/yoker/actions/workflows/tests.yml/badge.svg)](https://github.com/christophevg/yoker/actions/workflows/tests.yml)
[![Coverage Status](https://img.shields.io/coveralls/github/christophevg/yoker.svg)](https://coveralls.io/github/christophevg/yoker)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-7c85a3.svg)](https://docs.astral.sh/ruff/)

A Python agent harness with configurable tools, guardrails, and Ollama backend integration.

## Installation

```bash
pip install yoker
```

## Quick Start

```bash
python -m yoker
```

Example session:

![Yoker Session](media/session.svg)

## Features

| Feature | Description |
|---------|-------------|
| **Chat loop** | Interactive conversation with Ollama |
| **Tool calling** | Structured tool execution with parameters |
| **Configuration** | TOML-based configuration system |
| **Multiline input** | Shift+Enter for multiline, command history |
| **Rich output** | Styled terminal output with Rich |
| **Read tool** | File reading with path validation |

### Interactive Input

The interactive session supports:

- **Multiline input**: Press `Shift+Enter` to add newlines, `Enter` to submit
- **Command history**: Up/Down arrows navigate previous messages
- **History search**: `Ctrl+R` to search through history
- **Mouse support**: Click to position cursor

### Demo Session Script

Generate terminal screenshots for documentation:

```bash
# Real LLM session
python scripts/demo_session.py

# Real LLM + log conversation
python scripts/demo_session.py --log

# Replay from log (no LLM calls)
python scripts/demo_session.py --replay
```

## Configuration

Create a `yoker.toml` file to configure Yoker:

```toml
[harness]
name = "my-yoke"
log_level = "INFO"

[backend]
provider = "ollama"

[backend.ollama]
base_url = "http://localhost:11434"
model = "llama3.2:latest"

[tools.read]
enabled = true
allowed_extensions = [".txt", ".md", ".py"]
```

See `examples/yoker.toml` for the full configuration reference.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                        Yoker                             │
├─────────────────────────────────────────────────────────┤
│  Configuration │ Context Manager │ Logging/Reporting     │
│       │              │                   │               │
│       ▼              ▼                   ▼               │
│  ┌─────────────────────────────────────────────────────┐ │
│  │              Tool Execution Layer                    │ │
│  │    List  │  Read  │  Write  │  Update  │  Search    │ │
│  └─────────────────────────────────────────────────────┘ │
│                          │                               │
│                          ▼                               │
│  ┌─────────────────────────────────────────────────────┐ │
│  │              Ollama Backend Client                   │ │
│  └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

**Planned features**: Context persistence, additional tools (list, write, update, search, agent), agent definitions, guardrails, permissions.

## Documentation

- [Full documentation](https://yoker.readthedocs.io/)
- [Installation guide](https://yoker.readthedocs.io/en/latest/installation.html)
- [Quick start](https://yoker.readthedocs.io/en/latest/quickstart.html)
- [Architecture](https://github.com/christophevg/yoker/blob/master/analysis/architecture.md)

## Development

```bash
git clone https://github.com/christophevg/yoker.git
cd yoker
pip install -e ".[dev]"

make test     # Run tests with coverage
make check    # Type checking + linting
make docs     # Build documentation
```

Requires Python 3.10+. See [CLAUDE.md](CLAUDE.md) for project conventions.

## Contributing

Contributions welcome! Please read [CLAUDE.md](CLAUDE.md) for project conventions and development guidelines.

## Changelog

See [GitHub Releases](https://github.com/christophevg/yoker/releases) for version history.

## License

MIT License - see [LICENSE](LICENSE) for details.

---

**Name**: "yoker" - One who yokes. The agent noun from "yoke" (PIE *yeug-* meaning "to join"). Pairs with "clitic" (both are joining tools). See [docs/NAME.md](docs/NAME.md) for full etymology.