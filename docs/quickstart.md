# Quick Start

## Create Configuration

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

## Create Agent Definition

Create `agents/main.md`:

```markdown
---
name: main
description: Default assistant
tools: List, Read, Write, Update, Search, Agent
---

You are a helpful assistant that can work within the allowed directories.
```

## Run Yoker

```bash
yoker --config yoker.toml
```

## Available Tools

| Tool | Purpose |
|------|---------|
| List | Directory listing |
| Read | File reading |
| Write | File writing |
| Update | File editing |
| Search | Content/filename search |
| Agent | Spawn subagents |

## Guardrails

Each tool has configurable guardrails:

- **Path restrictions**: Only operate within allowed directories
- **Size limits**: Prevent reading/writing large files
- **Recursion limits**: Control subagent depth
- **Pattern filters**: Limit search complexity