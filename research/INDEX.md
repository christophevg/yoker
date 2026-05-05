# Research Index

This index tracks all research topics investigated for the yoker project.

---

## Coding Agent Harness Implementations

**Folder**: `2026-04-17-coding-agent-harness/`
**Date**: 2026-04-17
**Status**: Complete

**Summary**: Comprehensive analysis of coding agent harness architectures, examining top 5 implementations (Cursor, Claude Code, Aider, Windsorf, Cline) and distilling common architectural patterns across seven core components.

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

## WebSearch and WebFetch Tool Implementation

**Folder**: `2026-05-04-websearch-webfetch-tools/`
**Date**: 2026-05-04
**Status**: Complete

**Summary**: Research comparing Ollama native WebSearch/WebFetch capabilities versus custom implementations using DDGS and Trafilatura, with comprehensive security guardrail patterns.

**Key Findings**:
- Ollama 0.18.1 provides native web_search and web_fetch tools but requires cloud API key
- DDGS library offers free multi-backend search (bing, brave, duckduckgo, google) without API keys
- Trafilatura achieves 0.958 F1 score on content extraction with configurable output formats
- Custom implementation recommended for yoker's offline-first, library-first architecture
- SSRF guardrails essential: domain whitelisting, private IP blocking, redirect validation (5 hops), size limits (2MB), timeouts (10s)

**Sources**: 5 searches, 4 fetched articles (9 total sources)

**Keywords**: websearch, webfetch, ddgs, trafilatura, httpx, ssrf, guardrails, domain whitelist, content extraction

---

## Python Code Execution Safety

**Folder**: `2026-05-05-python-execution-safety/`
**Date**: 2026-05-05
**Status**: Complete

**Summary**: Comprehensive research on safe Python code execution approaches for implementing a Python Tool in yoker, covering sandbox solutions, subprocess isolation, AST validation, and kernel-level security.

**Key Findings**:
- RestrictedPython is NOT a sandbox—only restricts language subset (multiple CVEs)
- PyPy sandbox is unmaintained (v2 in development, not production-ready)
- Sandtrap provides 3-level isolation (none/process/kernel) designed for agent-generated code
- Defense-in-depth approach required: AST validation + subprocess + resource limits
- PEP 578 audit hooks are for monitoring/auditing, NOT sandboxing
- Subprocess isolation with resource limits is the recommended baseline
- uv is CLI-first; use subprocess to invoke for virtual environment management

**Sources**: 6 searches, 3 fetched articles (9 total sources)

**Keywords**: python execution, sandbox, subprocess isolation, ast validation, restrictedpython, sandtrap, seccomp, landlock, resource limits, bandit, guardrails

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