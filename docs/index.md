# Yoker Documentation

A Python agent harness with configurable tools, guardrails, and Ollama backend integration.

## Why Yoker?

Yoker is a **library-first, transparent agent harness** designed for developers who want full control, visibility, and simplicity.

**Key Differentiators:**
- **Library-first design** - Embed in your applications, not locked into a CLI
- **LLM-neutral** - Choose your provider, model, and cost model
- **No hidden manipulation** - All prompts visible, editable, configurable
- **Static permissions** - Deterministic boundaries, not runtime prompts
- **Full transparency** - Event-driven, everything inspectable

See [Why Yoker?](rationale.md) for the full rationale and comparison with other solutions.

## Quick Start

```bash
pip install yoker
python -m yoker
```

## Example Session

```{image} _static/session.svg
:alt: Yoker Session Example
:width: 100%
```

## Overview

**yoker** - One who yokes. The harness coordinates agents with structured tool access.

```{toctree}
:maxdepth: 2
:caption: Contents

installation
quickstart
rationale
NAME
api/index
```

## Current Features

- [x] Chat loop - Interactive conversation with Ollama
- [x] Tool calling - Structured tool execution with parameters
- [x] `read` tool - Read file contents with guardrails
- [x] `list` tool - Directory listing with pattern filtering
- [x] `write` tool - Write files with overwrite protection
- [x] Slash commands - Built-in commands: `/help`, `/think on|off`
- [x] Thinking mode - LLM reasoning trace with gray output
- [x] Streaming - Real-time token streaming from Ollama
- [x] Configuration - TOML-based configuration system
- [x] Agent definitions - Load agents from Markdown files
- [x] Multiline input - `Esc+Enter` for newlines
- [x] Rich output - Styled terminal output
- [x] Event-driven architecture - Library-first design
- [x] Context persistence - Session resumption
- [x] Event logging - Full session replay
- [x] Demo scripts - Generate documentation screenshots from Markdown scripts

## Architecture

The full architecture definition is available in `analysis/architecture.md` in the repository.

## Indices and Tables

- {ref}`genindex`
- {ref}`modindex`
- {ref}`search`