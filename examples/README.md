# Examples

This directory contains examples showing how to use Yoker as a library, as a
CLI tool, and how to extend it with custom agents, skills, and plugins.

## Python API Examples (`python_api/`)

These examples demonstrate the high-level Pythonic facade (`yoker.process`,
`yoker.do`, `yoker.agent`, `yoker.session`, `yoker.run_sync`).

| Example | What it demonstrates |
|---------|---------------------|
| `one_shot.py` | Simplest usage — one prompt, one answer via `yoker.process()` |
| `agent_builder.py` | Building a reusable `Agent` with a tool whitelist and event handler |
| `session.py` | Multi-turn conversation with `yoker.session()` and context persistence |
| `run_skill.py` | One-shot skill invocation via `yoker.do()` |
| `workflow.py` | A multi-step research workflow with JSON extraction |
| `event_handling.py` | Subscribing to fine-grained events (content chunks, tool calls, turn end) |
| `sync_usage.py` | Synchronous usage via `yoker.run_sync()` — no asyncio boilerplate |

### Running

```bash
# From the yoker project root (after `make env-dev`):
python examples/python_api/one_shot.py
python examples/python_api/agent_builder.py
python examples/python_api/session.py
python examples/python_api/run_skill.py
python examples/python_api/workflow.py
python examples/python_api/event_handling.py
python examples/python_api/sync_usage.py
```

All examples require a configured backend (run `python -m yoker` first to
launch the bootstrap wizard, or create a `yoker.toml`).

## Standalone Examples

| Example | What it demonstrates |
|---------|---------------------|
| `batch_mode.py` | Batch mode with predefined messages using `BatchUIHandler` |
| `library_usage.py` | Using Yoker as a library with event logging (no CLI) |
| `custom_handler.py` | Implementing a custom `UIHandler` from scratch |
| `research_workflow.py` | Running a researcher agent programmatically |
| `session_demo.py` | Multi-agent session with sub-agent spawning via `Session` |

### Running

```bash
python examples/batch_mode.py
python examples/library_usage.py
python examples/custom_handler.py
python examples/research_workflow.py
python examples/session_demo.py
```

## Agent Definitions (`agents/`)

Markdown files with YAML frontmatter that define agent personas, tool
whitelists, and system prompts.

| File | Description |
|------|-------------|
| `main.md` | Default assistant with read-only tools |
| `markdown.md` | Assistant that formats all responses as structured Markdown |
| `researcher.md` | Research assistant that explores and analyzes files |

### Using

```bash
# Load an agent definition via CLI
python -m yoker --agents-definition examples/agents/researcher.md

# Use in code
import yoker

agent = yoker.agent(definition="examples/agents/researcher.md")
result = yoker.run_sync(agent.process("Analyze the current directory structure."))
```

## Skills (`skills/`)

Markdown files with YAML frontmatter that define reusable instruction sets
the agent can invoke on demand.

| File | Description |
|------|-------------|
| `example.md` | Simple demonstration skill |
| `sing.md` | A fun skill that makes the agent reply with a song |

### Using

```bash
# Invoke a skill via CLI (in interactive mode)
> /example

# Invoke programmatically
import yoker

result = yoker.run_sync(yoker.do("sing", "Write a song about Python."))
```

## Plugin Example (`plugins/demo/`)

A complete demonstration plugin showing how to package tools, skills, and
agents as a Python package with a `__YOKER_MANIFEST__` declaration.

### Structure

```
plugins/demo/
  pyproject.toml              # Package configuration
  README.md                    # Detailed plugin development guide
  yoker_plugin_demo/           # Plugin package (name avoids conflict with yoker)
    __init__.py                # __YOKER_MANIFEST__ declaration
    tools.py                   # echo tool implementation
    agents/
      demo.md                  # Demo agent definition
    skills/
      greeting/
        SKILL.md               # Greeting skill definition
```

### Installing and Running

```bash
# Install the demo plugin
uv pip install -e examples/plugins/demo

# Run yoker with the plugin (requires [plugins] enabled = true in config)
python -m yoker --with yoker_plugin_demo --agent demo
```

See [plugins/demo/README.md](plugins/demo/README.md) for the full development
guide.

## Configuration Reference (`yoker.toml`)

A complete configuration file with all options, inline comments, and
alternative provider configs (commented out). Copy this file to `./yoker.toml`
or `~/.yoker.toml` as a starting point.

```bash
cp examples/yoker.toml ./yoker.toml
# Edit as needed, then:
python -m yoker
```

## Context Directory (`context/`)

An empty directory used by examples that enable context persistence. Session
JSONL files are written here when examples use `Persisted` or
`yoker.session(persist=True)`.