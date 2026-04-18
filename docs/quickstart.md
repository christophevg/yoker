# Quick Start

## Getting Started

Yoker provides an interactive chat interface with Ollama and tool calling capabilities.

### Prerequisites

- Python 3.10 or higher
- [Ollama](https://ollama.ai) running with at least one model

### Install

```bash
pip install -e .
```

Or from PyPI:

```bash
pip install yoker
```

### Run

```bash
python -m yoker
```

Or with a configuration file:

```bash
python -m yoker --config yoker.toml
```

### Interactive Session

```
Yoker v0.1.0 - Using model: glm-5:cloud
Type your message and press Enter. Press Ctrl+D to quit.

> What's in the README.md file?

I'll read the README.md file for you.

The README.md file describes **Yoker**, a Python-based agent harness...

> ^D
Goodbye!
```

### Interactive Input Features

The session supports:

| Feature | How to use |
|---------|------------|
| Multiline input | `Shift+Enter` adds newlines, `Enter` submits |
| Command history | `Up`/`Down` arrows navigate previous messages |
| History search | `Ctrl+R` searches through history |
| Mouse support | Click to position cursor |

### Command Line Options

```bash
python -m yoker --help

Options:
  -c, --config PATH    Path to configuration file (default: yoker.toml)
  -m, --model MODEL    Model to use (overrides config)
```

## Configuration

### Configuration File

Create a `yoker.toml` file in your project directory:

```toml
[harness]
name = "my-yoke"
log_level = "INFO"

[backend]
provider = "ollama"

[backend.ollama]
base_url = "http://localhost:11434"
model = "llama3.2:latest"
timeout_seconds = 60

[backend.ollama.parameters]
temperature = 0.7
top_p = 0.9

[tools.read]
enabled = true
allowed_extensions = [".txt", ".md", ".py", ".json"]

[logging]
format = "json"
include_tool_calls = true
```

See `examples/yoker.toml` for the full configuration reference.

### Environment Variables

Yoker automatically loads `yoker.toml` from the current directory if it exists.

## Demo Session Script

Generate terminal screenshots for documentation:

```bash
# Run with real LLM
python scripts/demo_session.py

# Run with LLM and log conversation to session.jsonl
python scripts/demo_session.py --log

# Replay from log (no LLM calls - useful for regenerating screenshots)
python scripts/demo_session.py --replay
```

### Output Files

| File | Description |
|------|-------------|
| `media/session-YYYYMMDD-HHMMSS.svg` | Timestamped session screenshot |
| `media/session.svg` | Symlink to latest screenshot |
| `media/session.jsonl` | Conversation log (with `--log`) |

## Available Tools

| Tool | Purpose |
|------|---------|
| `read` | Read file contents |

More tools (list, write, update, search, agent) will be added in future releases.

---

## Next Steps

- {doc}`installation` - Detailed installation guide
- [Architecture](https://github.com/christophevg/yoker/blob/master/analysis/architecture.md) - System design