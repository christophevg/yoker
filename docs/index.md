# Yoker Documentation

A Python agent harness with configurable tools and guardrails.

## Current Status

**Minimal prototype available!** Basic chat loop with tool calling is working.

```bash
pip install -e .
python -m yoker
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

- **Safety First**: Guardrails prevent unintended operations
- **Configurability**: All aspects configurable via TOML
- **Simplicity**: Specific tools instead of generic shell access
- **Transparency**: Clear logging of all agent actions
- **Extensibility**: Easy to add new guarded tools
- **Compatibility**: Agent definitions compatible with Claude Code format

## Architecture

The full architecture definition is available in `analysis/architecture.md` in the repository.

## Indices and Tables

- {ref}`genindex`
- {ref}`modindex`
- {ref}`search`