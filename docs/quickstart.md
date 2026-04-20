# Quick Start

## Getting Started

Yoker provides an interactive chat interface with Ollama and tool calling capabilities.

**Architecture**: Yoker uses an event-driven, library-first design. The Agent emits events (thinking chunks, content, tool calls) that handlers subscribe to. This makes the library usable in headless, web, and GUI contexts.

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

### Library Usage (Headless)

```python
from yoker import Agent
from yoker.events import Event, ContentChunkEvent

# Create a custom event handler
class MyHandler:
    def __call__(self, event: Event) -> None:
        if hasattr(event, 'text'):
            print(event.text, end='', flush=True)

# Create agent and attach handler
agent = Agent(model="llama3.2")
agent.add_event_handler(MyHandler())

# Use the agent programmatically
agent.begin_session()
agent.process("What is 2+2?")
agent.end_session()
```

### Interactive Session

```
Yoker v0.1.0 - Using model: glm-5:cloud
Thinking mode: enabled (use /think on|off to toggle)
Type /help for available commands.
Press Ctrl+D (or Ctrl+Z on Windows) to quit.

> /help

Available commands:

  /help - Show available commands
  /think - Enable/disable thinking mode: /think [on|off]

Type a message without / prefix to chat with the LLM.

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
| Multiline input | `Esc+Enter` adds newlines, `Enter` submits |
| Command history | `Up`/`Down` arrows navigate previous messages |
| History search | `Ctrl+R` searches through history |
| Mouse support | Click to position cursor |

### Slash Commands

| Command | Description |
|---------|-------------|
| `/help` | Show available commands |
| `/think on\|off` | Enable/disable LLM thinking trace |

### Thinking Mode

When enabled, the LLM shows its reasoning process in gray:

```
[Thinking]
Let me analyze this request...
I should check the file structure first...

[Response]
Based on my analysis, here's what I found...
```

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