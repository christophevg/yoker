# Yoker Documentation

A Python agent harness with configurable tools, guardrails, and Ollama backend integration.

## Current Status

**Working prototype with configuration system!** Interactive chat with multiline input, command history, and tool calling.

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
NAME
api/index
```

## Key Features

- **Configuration System**: TOML-based configuration for all aspects
- **Multiline Input**: Shift+Enter for multiline, command history support
- **Rich Output**: Styled terminal output with Rich
- **Tool Calling**: Structured tool execution with parameters
- **Safety First**: Guardrails prevent unintended operations
- **Extensibility**: Easy to add new guarded tools
- **Compatibility**: Agent definitions compatible with Claude Code format

## Architecture

The full architecture definition is available in `analysis/architecture.md` in the repository.

## Indices and Tables

- {ref}`genindex`
- {ref}`modindex`
- {ref}`search`