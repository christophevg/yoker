# Yoker

A Python-based agent harness with configurable tools, guardrails, and Ollama backend integration.

## Name

**"yoker"** - One who yokes. A person or device that joins or attaches things together, specifically one who yokes oxen or links things together.

From the agent noun of "yoke", which derives from PIE *\yeug-* meaning "to join" (same root as yoga, conjugate, junction).

Pairs beautifully with "clitic" (both are joining tools - clitic joins words, yoker joins agents).

See `docs/NAME.md` for full naming documentation.

## Vision

Create a lightweight, configurable agent harness that provides a structured environment for AI agents to operate within defined boundaries. The harness manages tool access, enforces guardrails, handles context persistence, and integrates with Ollama as the LLM backend.

## Goals

1. **Safety First**: Guardrails prevent agents from performing unintended operations
2. **Configurability**: All tools, parameters, and limits configurable via TOML
3. **Simplicity**: Specific tools instead of generic shell access
4. **Transparency**: Clear logging and reporting of all agent actions
5. **Extensibility**: Easy to add new tools while maintaining guardrails
6. **Compatibility**: Agent definitions compatible with Claude Code format

## Core Components

### 1. Configuration System

- **TOML configuration file**: Harness settings, tool guardrails, Ollama parameters
- **Markdown agent definitions**: With YAML frontmatter (compatible with Claude Code)

### 2. Tool System

MVP tools (no generic Bash):

| Tool | Purpose | Guardrails |
|------|---------|------------|
| List | Directory listing | Path restrictions, pattern filters |
| Read | File reading | Path restrictions, size limits |
| Write | File writing | Path restrictions, overwrite protection |
| Update | File editing | Path restrictions, diff validation |
| Search | Grep/glob-like | Path restrictions, pattern limits |
| Agent | Spawn subagents | Recursion depth, tool subset |

### 3. Context Manager

Persists context for consecutive LLM calls:
- Conversation history (JSONL format - append-friendly)
- Agent state
- Working memory
- Per-session files in configurable location

### 4. Ollama Integration

- Assumes Ollama is running externally
- All configurable parameters exposed
- Model selection per agent possible

### 5. Agent Definitions

Markdown files with YAML frontmatter:

```markdown
---
name: researcher
description: Research assistant
tools: List, Read, Search
---

# Researcher Agent

You are a research assistant...
```

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                        Yoker                             │
├─────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐  │
│  │  Config     │  │  Context    │  │  Logging/       │  │
│  │  Loader     │  │  Manager    │  │  Reporting      │  │
│  │  (TOML)     │  │  (JSONL)    │  │                 │  │
│  └──────┬──────┘  └──────┬──────┘  └────────┬────────┘  │
│         │                │                  │           │
│         ▼                ▼                  ▼           │
│  ┌─────────────────────────────────────────────────────┐│
│  │              Tool Execution Layer                   ││
│  │  ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌───────┐  ││
│  │  │List │ │Read │ │Write│ │Update│ │Search│ │Agent  │  ││
│  │  └─────┘ └─────┘ └─────┘ └─────┘ └─────┘ └───────┘  ││
│  └─────────────────────────────────────────────────────┘│
│                          │                              │
│                          ▼                              │
│  ┌─────────────────────────────────────────────────────┐│
│  │              Ollama Backend Client                  ││
│  │      (HTTP API, configurable parameters)            ││
│  └─────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────┘
```

## Project Structure

```
yoker/
├── src/yoker/           # Main package
├── tests/               # Test suite
├── docs/               # Sphinx documentation
├── examples/           # Example configurations
├── analysis/           # Functional analysis
├── pyproject.toml      # Package configuration
└── README.md
```

## Quick Start (Planned)

```bash
# Create config
cat > yoker.toml << EOF
[ollama]
model = "llama3.2"
base_url = "http://localhost:11434"

[tools.list]
allowed_paths = ["/workspace"]

[tools.read]
allowed_paths = ["/workspace"]
max_size_kb = 100

[tools.agent]
max_recursion_depth = 3

[agents]
directory = "./agents"
EOF

# Create agent definition
mkdir agents
cat > agents/main.md << EOF
---
name: main
description: Default assistant
tools: List, Read, Write, Update, Search, Agent
---

You are a helpful assistant.
EOF

# Run harness
yoker --config yoker.toml
```

## Documentation

- Name documentation: `docs/NAME.md`
- Functional analysis: `analysis/functional.md`
- Interview notes: `analysis/interview.md`

## Integration with Clitic

Yoker provides the agent runtime, Clitic provides the TUI:

- Build agents using Yoker APIs
- Optionally add Clitic-based CLI interface
- Deploy agents with or without UI (daemon mode)