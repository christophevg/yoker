# Installation

## Requirements

- Python 3.10 or higher
- An LLM provider account — Ollama (free tier available), OpenAI, Anthropic, or
  Google Gemini. The bootstrap wizard walks you through setting up any of them.

> **Note**: You no longer need Ollama pre-installed. On first launch, if no
> configuration is found, Yoker runs a bootstrap wizard that lets you choose
> your provider and writes `~/.yoker.toml` for you. See
> {doc}`Getting Started <guides/getting-started>` for the guided path.

## Install from PyPI

```bash
pip install yoker
```

Optional extras for content type detection using `python-magic`:

```bash
pip install yoker[magic]
```

## Install from Source

```bash
git clone https://github.com/christophevg/yoker.git
cd yoker

# Create virtual environment and install with development dependencies
make env-dev
```

## Verify Installation

```bash
python -m yoker
```

If no configuration exists, the bootstrap wizard launches to guide you through
provider selection and model setup. Once configured, you will see the welcome
banner followed by the interactive prompt.

## Development Setup

```bash
# Run tests
make test

# Type checking and linting
make check

# Build documentation
make docs
```

## Dependencies

### Core Dependencies

- `clevis[tomlev]>=0.3.3` - Configuration system with CLI auto-generation
- `httpx>=0.25.0` - HTTP client (async, streaming)
- `litellm>=1.90.0` - Unified interface for OpenAI, Anthropic, Gemini, and 100+ providers
- `ollama>=0.6.0` - Native Ollama Python client
- `prompt_toolkit>=3.0.0` - Interactive input with multiline support
- `python-dotenv>=1.0.0` - `.env` file loading
- `rich>=14.0.0` - Rich terminal output
- `structlog>=23.3.0` - Structured logging
- `pyyaml>=6.0` - YAML parsing (for agent definitions)
- `pyfiglet>=1.0.4` - ASCII art welcome banner

### Optional Extras

- `magic` - Content type detection via `python-magic` (Unix) or `python-magic-bin` (Windows)

### Development Dependencies

- `pytest>=8.0.0` - Testing framework
- `pytest-cov>=5.0.0` - Coverage reporting
- `pytest-asyncio>=0.23.0` - Async test support
- `mypy>=1.13.0` - Type checking
- `ruff>=0.8.0` - Linting and formatting
- `tox>=4.0.0` - Multi-version testing
- `build>=1.0.0` - Package building
- `twine>=5.0.0` - PyPI publishing

## Next Steps

- {doc}`quickstart` - Get started with yoker
- {doc}`guides/getting-started` - From zero to your first agent session
- {doc}`models` - Curated model lists per provider