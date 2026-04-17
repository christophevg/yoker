# Quick Start

## Minimal Prototype

The current prototype provides a basic interactive chat with Ollama and tool calling.

### Prerequisites

- Python 3.10 or higher
- [Ollama](https://ollama.ai) running with at least one model

### Install

```bash
pip install -e .
```

### Run

```bash
python -m yoker
```

### Example Session

```
Yoker v0.1.0 - Using model: glm-5:cloud
Type your message and press Enter. Press Ctrl+D to quit.

> What's in the README.md file?

I'll read the README.md file for you.

[13:49:49] INFO yoker.agent - Tool call: read({'path': 'README.md'})
[13:49:49] INFO yoker.agent - Tool result: # Yoker...

The README.md file describes **Yoker**, a Python-based agent harness...

> ^D
Goodbye!
```

### Available Tools

The prototype includes:

| Tool | Purpose |
|------|---------|
| `read` | Read file contents |

More tools (list, write, update, search, agent) will be added in future releases.

---

## Planned Full Usage

### Create Configuration

Create a `yoker.toml` file:

```toml
[ollama]
model = "llama3.2"
base_url = "http://localhost:11434"

[tools.list]
allowed_paths = ["/workspace"]
max_depth = 5

[tools.read]
allowed_paths = ["/workspace"]
max_size_kb = 100

[tools.agent]
max_recursion_depth = 3

[agents]
directory = "./agents"
```

### Create Agent Definition

Create `agents/main.md`:

```markdown
---
name: main
description: Default assistant
tools: List, Read, Write, Update, Search, Agent
---

You are a helpful assistant that can work within the allowed directories.
```

### Run Yoker

```bash
yoker --config yoker.toml
```

### Guardrails

Each tool will have configurable guardrails:

- **Path restrictions**: Only operate within allowed directories
- **Size limits**: Prevent reading/writing large files
- **Recursion limits**: Control subagent depth
- **Pattern filters**: Limit search complexity