# Research Index

This index tracks all research topics investigated for the yoker project.

---

## Coding Agent Harness Implementations

**Folder**: `2026-04-17-coding-agent-harness/`
**Date**: 2026-04-17
**Status**: Complete

**Summary**: Comprehensive analysis of coding agent harness architectures, examining top 5 implementations (Cursor, Claude Code, Aider, Windsurf, Cline) and distilling common architectural patterns across seven core components.

**Key Findings**:
- Brain-hands-session decoupling is the most robust architecture pattern
- Git worktrees are the universal isolation mechanism for parallel execution
- Context management uses multi-layer compaction across all implementations
- Model routing (fast for routine, frontier for complex) is essential
- Cost governance is a universal gap across all examined tools
- Permission systems follow a four-layer cascading pattern
- AST-based understanding via tree-sitter is standard

**Sources**: 9 sources (2 fetched articles, 7 search result summaries)

**Keywords**: coding agent, harness, architecture, cursor, claude code, aider, windsurf, cline, sandbox, tool registry, context management, agentic loop, guardrails

---

## Coding Agent Rationale

**Folder**: `2026-04-22-coding-agent-rationale/`
**Date**: 2026-04-22
**Status**: Complete

**Summary**: Research to define yoker's unique value proposition, identifying gaps in existing coding agent solutions (library-first design, static permissions, offline operation, recursive composition) and positioning yoker as an embeddable coding agent harness.

**Key Findings**:
- No existing solution combines library-first design with coding-specific capabilities
- Static permissions enable non-interrupted autonomous operation (0.00% violation rate)
- Ollama-first design eliminates API costs and enables offline operation
- Recursive composition (sub-agents as full instances) is unique to yoker
- Event-driven architecture allows consumers full control over UI
- 2026 research emphasizes deterministic guardrails and hierarchical architectures

**Sources**: 20 sources (5 searches, prior research reference)

**Keywords**: rationale, value proposition, library-first, static permissions, ollama, offline, recursive composition, event-driven, embeddable

---

<!-- Template for new research entries -->
<!--
### {Topic Name}

**Folder**: `{date}-{slug}/`
**Date**: YYYY-MM-DD
**Status**: Complete | In Progress

**Summary**: One-sentence description.

**Key Findings**:
- Finding 1
- Finding 2
- Finding 3

**Sources**: N sources

**Keywords**: keyword1, keyword2, keyword3
-->