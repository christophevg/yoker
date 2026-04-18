# Installation

## Requirements

- Python 3.10 or higher
- [Ollama](https://ollama.ai) running locally (or accessible via HTTP)

## Install from PyPI

```bash
pip install yoker
```

## Install from Source

```bash
git clone https://github.com/christophevg/yoker.git
cd yoker

# Create virtual environment (recommended)
pyenv virtualenv 3.10.13 yoker
echo "yoker" > .python-version
pyenv activate yoker

# Install with development dependencies
pip install -e ".[dev]"
```

## Verify Installation

```bash
python -m yoker
```

You should see:

```
Yoker v0.1.0
========================================
Yoker v0.1.0 - Using model: llama3.2:latest
Type your message and press Enter. Press Ctrl+D to quit.

>
```

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

- `httpx>=0.25.0` - HTTP client (async, streaming)
- `ollama>=0.6.0` - Ollama Python client
- `prompt_toolkit>=3.0.0` - Interactive input with multiline support
- `rich>=14.0.0` - Rich terminal output
- `structlog>=23.0.0` - Structured logging
- `pyyaml>=6.0` - YAML parsing (for agent definitions)
- `tomli>=2.0` - TOML parsing (Python < 3.11)

### Development Dependencies

- `pytest>=7.0.0` - Testing framework
- `pytest-cov>=4.0.0` - Coverage reporting
- `mypy>=1.0.0` - Type checking
- `ruff>=0.1.0` - Linting and formatting
- `sphinx>=7.0.0` - Documentation

## Next Steps

- {doc}`quickstart` - Get started with yoker