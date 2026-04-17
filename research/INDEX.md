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