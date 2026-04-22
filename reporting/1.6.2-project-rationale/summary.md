# Project Rationale Summary

**Task**: 1.6.2 Define Project Rationale
**Status**: Completed
**Date**: 2026-04-22

## Overview

Defined yoker's unique value proposition by researching existing coding agent solutions and interviewing the project creator about their goals and vision.

## Key Findings

### Yoker's Unique Position

Yoker fills a unique gap in the coding agent ecosystem: the **library layer** between generic frameworks and end-user applications.

| Layer | Solutions | Yoker's Position |
|-------|-----------|------------------|
| Application (CLI/IDE) | Claude Code, Cursor, Aider, Windsurf | Not competing |
| Framework (Generic) | OpenAI Agents SDK, Microsoft Agent Framework | Adjacent - generic vs coding-specific |
| **Library (Coding-Specific)** | **Gap** | **Yoker fills this** |

### Core Differentiators

1. **Library-First Design** - Emits events for any application to consume
2. **Static Permissions** - TOML-based, 0% violation rate vs 26.67% for LLM-based
3. **Ollama-First Backend** - Zero API cost, complete offline capability
4. **Developer-Friendly Tools** - Simple Python functions, no MCP servers
5. **Full Transparency** - Open, clear, inspectable, configurable
6. **Recursive Composition** - Sub-agents are full instances with isolated context

### Creator's Vision

From user interview:
> "Full control, visibility, developer-friendly approach. Tools are simple Python functions that can be registered, not needing MCP servers. Full transparency - everything is open and clear and inspectable, configurable, no hidden features, no magic sauce."

## Deliverables

1. **Rationale Document**: `docs/rationale.md`
   - Why yoker exists
   - Key differentiators
   - Target use cases
   - Positioning in ecosystem

2. **Research Report**: `research/2026-04-22-coding-agent-rationale/README.md`
   - Competitive landscape analysis
   - Gap analysis
   - Source citations

## Files Created

| File | Purpose |
|------|---------|
| `docs/rationale.md` | Project rationale document |
| `research/2026-04-22-coding-agent-rationale/README.md` | Research report |
| `research/2026-04-22-coding-agent-rationale/SOURCES.md` | Source citations |
| `research/INDEX.md` | Updated research index |

## Task Completion

- [x] Research existing coding agent solutions
- [x] Interview user to understand goals and vision
- [x] Document unique selling factors
- [x] Create rationale document
- [x] Identify gaps in existing solutions