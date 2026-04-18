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

Run `python scripts/demo_session.py` to regenerate this screenshot with your configuration.

## Features

| Feature | Description |
|---------|-------------|
| Chat loop | Interactive conversation with Ollama |
| Tool calling | Structured tool execution with parameters |
| Streaming | Real-time response streaming |
| Logging | Structured logging for observability |
| Read tool | File reading with path validation |

**Planned features**: Configuration system, context persistence, additional tools (list, write, update, search, agent), guardrails, permissions.

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