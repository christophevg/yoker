# Coding Agent Harness Implementations - Research Report

**Research Date:** 2026-04-17
**Purpose:** Compile a book of knowledge about Coding Agent Harness implementations for functional analysis
**Previous Research:** none

---

## Executive Summary

This research provides a comprehensive analysis of coding agent harness architectures, examining the top 5 implementations (Cursor, Claude Code, Aider, Windsurf, Cline) and distilling common architectural patterns. Key findings reveal a convergence toward specific design patterns: brain-hands-session decoupling, permission-gated tool execution, git worktree isolation, and multi-tier context management. The research covers seven core architectural components: Sandboxed Execution, Tool Registry, Observation Service, Memory/Context Management, Agentic Loop, Guardrails, and Guides.

---

## 1. Top 5 Coding Agent Harnesses

### 1.1 Cursor

**Architecture Highlights:**
- **Three-Layer System**: Intelligence Layer (model routing), Context Awareness Engine, Execution Layer
- **Model Routing**: Composer (proprietary MoE) for routine tasks, frontier models (Claude 4.5, GPT-5) for complex decisions
- **Performance Engineering**: Speculative edits at 250 tokens/sec, MXFP8 MoE kernels for NVIDIA B200
- **Context Management**: Merkle tree synchronization for differential sync, AST-based chunking via tree-sitter
- **Multi-Agent**: Up to 8 parallel agents using git worktrees with isolated shadow workspaces
- **Safety**: Network blocked by default, filesystem limited to workspace and /tmp/

**Key Innovation**: Four-tier memory architecture with in-context (128-200K), Redis short-term cache, vector store (Chroma/Pinecone), and parametric memory.

**Sources:**
- [Designing high-performance agentic systems](https://medium.com/@khayyam.h/designing-high-performance-agentic-systems-an-architectural-case-study-of-the-cursor-agent-ab624e4a0a64)

### 1.2 Claude Code

**Architecture Highlights:**
- **Six Primary Layers**: Entry Points, Bootstrap/Config, UI Layer (Ink/React TUI), Query Engine, Tool System, Services/State
- **Query Engine**: Async generator pattern that yields streaming events
- **Tool System**: 50+ tools organized into File, Shell, Web, Agent, Plan, Task, MCP, System categories
- **AppState**: Single source of truth with 300+ properties
- **Context Compaction**: Five-layer pipeline (Tool Result Budget, Snip, Microcompaction, Context Collapse, Autocompact)
- **Permission System**: Four-layer cascading decision (Static Rules, Tool Logic, Permission Mode, User Prompt)

**Key Innovation**: Hooks system with 25+ lifecycle events for extensibility.

**Sources:**
- [Inside Claude Code: An Architecture Deep Dive](https://zainhas.github.io/blog/2026/inside-claude-code-architecture/)

### 1.3 Aider

**Architecture Highlights:**
- **Coder Class**: Central orchestrator managing file management, message history, repository integration, model communication
- **Model Flexibility**: ModelSettings dataclass with edit_format, use_repo_map, weak_model_name, editor_model_name
- **Git Integration**: GitRepo class with commit attribution logic (author, committer, co-authored-by)
- **Edit Formats**: Whole-file, Diff, Udiff (custom micro-diff format)
- **Architect/Editor Pattern**: Two-model system separating reasoning from editing
- **History Summarization**: Background thread with weak model when messages exceed threshold

**Key Innovation**: Model-agnostic design supporting any LLM via simple configuration.

**Sources:**
- [Core Architecture | Aider-AI/aider](https://deepwiki.com/Aider-AI/aider/2-core-architecture)

### 1.4 Windsurf Cascade

**Architecture Highlights:**
- **Flow-Aware Context Engine**: Tracks all actions in real-time, infers intent without explicit prompting
- **Multi-Stage Pipeline**: User Intent → Context Assembly → Task Planning → Step Execution → Review
- **IDE Shell**: VS Code fork with deep AI hooks (not just extension-level)
- **Context Layers**: Codebase Indexer (local embeddings), Terminal Integration, AI Models (auto-routing), Cascade Agent, Supercomplete Engine
- **Capabilities**: Multi-file editing (20+ files), terminal execution, tool calling (up to 20 calls/prompt), checkpoints

**Key Innovation**: "Shared timeline" concept - continuous action loop with flow awareness vs single-turn chat.

**Sources:**
- [Windsurf - Cascade](https://docs.codeium.com/windsurf/cascade/cascade)

### 1.5 Cline (Roo Code)

**Architecture Highlights:**
- **Human-in-the-Loop**: Explicit approval for every file change and terminal command
- **Model Support**: Anthropic, OpenAI, Google Gemini, AWS Bedrock, Azure, Groq, Cerebras, local via Ollama/LM Studio
- **Plan Mode**: Read-only analysis and action plan generation
- **Act Mode**: Executes changes with full tool access after approval
- **Repository Context**: Indexes entire repo at startup for holistic understanding
- **MCP Integration**: Extends capabilities through Model Context Protocol

**Roo Code Fork:**
- Role-specific modes: Architect, Code, Debug, Ask, Test, Custom
- Each mode constrains what AI can do (e.g., Architect mode cannot edit files)
- Cloud agents for team collaboration via Slack, GitHub, web

**Key Innovation**: Governance through `.clinerules` policies and enterprise audit trails.

**Sources:**
- [Roo Code vs Cline: Best AI Coding Agents for VS Code (2026)](https://www.qodo.ai/blog/roo-code-vs-cline/)

---

## 2. Architectural Components Analysis

### 2.1 Sandboxed Execution Environment

**Isolation Strategies:**

| Tool | Linux Backend | macOS Backend | Network | Filesystem |
|------|--------------|---------------|---------|------------|
| Claude Code | OS-level isolation | macOS Seatbelt | HTTP/SOCKS5 proxy | Configurable mount points |
| Cursor | Custom VM scheduler | Container-based | Blocked by default | Workspace + /tmp |
| ExitBox | Podman/Docker | - | DNS cutoff, Squid proxy | Layered isolation |
| scode | bubblewrap | Seatbelt | `--unshare-net` | 35+ blocked paths |
| ai-jail | bwrap + Landlock + Seccomp | sandbox-exec | Namespace isolation | Strict read-only |

**Key Patterns:**

1. **Git Worktrees**: Universal isolation primitive across all projects
   - Each agent gets separate checkout on different branch
   - Changes stay isolated until developer reviews and merges
   - Supports up to 8 parallel agents (Cursor)

2. **Defense-in-Depth Layers**:
   - Namespace isolation
   - Landlock LSM
   - Seccomp-bpf filters
   - Resource limits

3. **Credential Protection**:
   - Block `~/.aws`, `~/.ssh`, `~/.gnupg`
   - Block password manager directories (1Password, Bitwarden)
   - Block cloud credential paths (`~/.config/gcloud`, `~/.kube`)

**Anthropic's Managed Agents Approach:**
- Brain (Claude + harness) decoupled from Hands (sandboxes/tools)
- Session (event log) lives outside context window
- Credentials never reach harness (vault-based auth)
- Sandbox is "cattle not pet" - interchangeable, reprovisioned on failure

**Sources:**
- [Scaling Managed Agents](https://www.anthropic.com/engineering/managed-agents)
- [Introducing ExitBox](https://medium.com/@cloud-exit/introducing-exitbox-run-ai-coding-agents-in-complete-isolation-6013fb5bdd06)
- [scode: A Seatbelt for AI Coding](https://binds.ch/blog/scode-sandbox-for-ai-coding-tools)

### 2.2 Tool Registry / Action Service

**Tool Interface Pattern (Claude Code):**
```
Tool<Input, Output, Progress>
├── Identity: name, userFacingName(), description()
├── Schema: inputSchema (Zod), outputSchema
├── Execution: call(input, context) → ToolResult
├── Concurrency: isConcurrencySafe(), isReadOnly()
├── Permissions: checkPermissions(), validateInput()
└── Rendering: prompt(), renderToolUseMessage(), renderToolResultMessage()
```

**Tool Categories:**
- **File Operations**: Read, Write, Update, List, Search
- **Shell Execution**: Terminal commands with output capture
- **Web**: HTTP requests, browser automation (Playwright)
- **Agent**: Subagent spawning with context isolation
- **Plan**: Task planning and decomposition
- **MCP**: Model Context Protocol extensions

**Execution Pattern:**
- Read-only tools run in parallel batches
- Write tools run sequentially to prevent race conditions
- Permission gates at boundaries

**Tool Result Budget:**
- Enforce per-message size limits (20K chars in Claude Code)
- Persist large results to disk
- Clear old tool result contents while keeping message structure

**Sources:**
- [Inside Claude Code: An Architecture Deep Dive](https://zainhas.github.io/blog/2026/inside-claude-code-architecture/)

### 2.3 Observation Service

**Feedback Collection:**

| Observation Type | Source | Processing |
|-----------------|--------|------------|
| Code diffs | Git operations | Diff generation, conflict detection |
| Compiler errors | Build tools | Error parsing, location extraction |
| Stack traces | Runtime | Trace analysis, root cause mapping |
| Test results | Test runners | Pass/fail classification, coverage |
| Linting output | Linters | Error categorization, auto-fix suggestions |
| Type errors | Type checkers | Error location, type inference |

**Observation Loop:**
1. Execute tool → capture output
2. Parse output → extract structured data
3. Feed to model → context for next action
4. Model decides → continue, retry, or escalate

**Compaction Strategies:**
- **Tool-Result Clearing**: Remove large outputs once processed
- **Snip Compaction**: Clear old tool result contents, keep structure
- **Microcompaction**: Remove old results via `cache_edits` API

**Sources:**
- Mission.md initial overview

### 2.4 Memory & Context Management

**Four-Tier Memory Architecture (Cursor):**
1. **Tier 1 - In-Context Memory**: Active context window (128K-200K tokens)
2. **Tier 2 - External Short-Term Cache**: Redis-based session state
3. **Tier 3 - Long-Term Vector Store**: Chroma/Pinecone for persistent embeddings
4. **Tier 4 - Parametric Memory**: Model weights (static until retrain)

**Five-Layer Compaction Pipeline (Claude Code):**
1. **Tool Result Budget**: Enforce per-message size limits (20K chars)
2. **Snip Compaction**: Clear old tool result contents
3. **Microcompaction**: Remove old results via `cache_edits` API
4. **Context Collapse**: Model-side compression
5. **Autocompact**: Full conversation compaction when tokens reach threshold (`effectiveWindow - 13,000`)

**Context Engineering Techniques:**

| Technique | Implementation | Purpose |
|-----------|---------------|---------|
| Repository Map | Tree-sitter parsing, PageRank ranking | Provide codebase structure overview |
| AST Chunking | Semantic grouping (function, class) | Maintain code meaning |
| Merkle Trees | Cryptographic fingerprints | Differential sync in milliseconds |
| Workspace Summary | Git status, folder structure | Initialize prompt with environment |
| Context Isolation | Sub-agent with empty context | Prevent pollution for complex tasks |

**Session Memory (Claude Code):**
- Session memory extraction runs asynchronously
- Maintains `~/.claude/session_memory`
- Sections capped at 2,000 tokens each
- Update interval: every 15,000 tokens

**Persistent Memory:**
- `CLAUDE.md` / `.claude/CLAUDE.md` for project context
- `~/.claude/settings.json` for user preferences
- `.windsurfrules` / `.clinerules` for project-specific instructions

**Sources:**
- [Designing high-performance agentic systems](https://medium.com/@khayyam.h/designing-high-performance-agentic-systems-an-architectural-case-study-of-the-cursor-agent-ab624e4a0a64)
- [Inside Claude Code: An Architecture Deep Dive](https://zainhas.github.io/blog/2026/inside-claude-code-architecture/)
- Mission.md context management overview

### 2.5 Agentic Loop (Orchestration)

**ReAct Loop Pattern:**
```
while (response.has_tool_calls) {
    results = execute_tools(response.tool_calls)
    response = call_model(history + results)
}
display(response.text)
```

**Loop Components:**
1. **Observe**: Collect environment state, tool outputs, user input
2. **Plan**: Decompose task, determine next action
3. **Act**: Execute tools, make changes
4. **Reflect**: Verify results, handle errors, decide continuation

**Recovery Paths:**
- Context compaction when window fills
- Output limit escalation
- Model fallback (weak → strong)
- User interrupt handling

**Multi-Agent Patterns:**

| Pattern | Description | Use Case |
|---------|-------------|----------|
| Single-Agent Loop | One model manages all tools | Simple tasks |
| Initializer-Executor | One agent sets up, another updates | Complex setup |
| Multi-Agent Coordination | Specialized agents for research, write, review | Large-scale changes |
| Two-Tier Meta-Agent | Orchestrator dispatches to workers (Agent Orchestrator) | Parallel issue handling |

**Session Lifecycle (Agent Orchestrator):**
16 distinct statuses: pending, running, completed, failed, killed, etc.

**Sources:**
- [AI Harness Comparative Analysis](https://gist.github.com/jeffscottward/de77a769d9e25a8ccdc92b65291b1c34)
- [Inside Claude Code: An Architecture Deep Dive](https://zainhas.github.io/blog/2026/inside-claude-code-architecture/)

### 2.6 Guardrails and Governance

**Permission System (Claude Code - Four Layers):**
1. **Static Rules** (settings.json): Match tool name + pattern → allow/deny/ask
2. **Tool Logic**: `tool.checkPermissions()` for tool-specific safety checks
3. **Permission Mode**: `bypassPermissions`, `auto` (check classifier), `default` (prompt), `plan` (deny writes)
4. **User Prompt**: Terminal dialog for explicit consent

**Safety Constraints:**

| Constraint | Implementation |
|------------|---------------|
| Infinite loops | Max iterations, timeout |
| Network access | Allowlist/blocklist, proxy |
| Token costs | Budget tracking, automatic shutoff |
| File system | Allowed paths, deny patterns |
| Command execution | Allowed commands list |

**Cost Governance Gap:**
All examined projects lack comprehensive cost governance:
- Token usage tracked but no aggregated cost view
- No budget limits or automatic shutoff in most tools
- No cost alerts or CLI display

**Sources:**
- [AI Harness Comparative Analysis](https://gist.github.com/jeffscottward/de77a769d9e25a8ccdc92b65291b1c34)
- [Inside Claude Code: An Architecture Deep Dive](https://zainhas.github.io/blog/2026/inside-claude-code-architecture/)

### 2.7 Guides (Feedforward Controls)

**Project Context Files:**
- `CLAUDE.md` / `.claude/CLAUDE.md` (Claude Code)
- `.windsurfrules` (Windsurf)
- `.clinerules` (Cline)
- `AGENTS.md` (generic)

**Purpose:**
- Provide project context before agent acts
- Define coding conventions and rules
- Specify allowed/disallowed patterns
- Document architecture decisions

**Three-Layer Prompt Composition (Agent Orchestrator):**
1. **Base Agent Prompt**: Hardcoded system prompt
2. **Config-Derived Context**: From YAML configuration
3. **User Rules**: `agentRules/agentRulesFile`

**LSP Configuration:**
- Provide language server context
- Enable code completion intelligence
- Support semantic understanding

---

## 3. Architecture Patterns Comparison

### 3.1 Orchestration Models

| Pattern | Cursor | Claude Code | Aider | Windsurf | Cline | Agent Orchestrator |
|---------|--------|-------------|-------|----------|-------|-------------------|
| Single-Agent | ✓ | ✓ | ✓ | - | ✓ | - |
| Multi-Agent | ✓ (8 parallel) | ✓ (subagents) | - | - | - | ✓ (workers) |
| Meta-Agent | - | - | - | - | - | ✓ (two-tier) |

### 3.2 Isolation Strategies

| Tool | Git Worktrees | Containers | OS Sandboxing | Network Isolation |
|------|--------------|------------|---------------|-------------------|
| Cursor | ✓ | Custom VM | ✓ | ✓ |
| Claude Code | ✓ | - | Seatbelt/bwrap | ✓ (proxy) |
| Agent Orchestrator | ✓ | - | tmux | - |
| ExitBox | - | ✓ Podman | - | ✓ (DNS cutoff) |

### 3.3 Context Management

| Tool | Repository Map | AST Chunking | Session Persistence | Cross-Session Context |
|------|---------------|--------------|-------------------|----------------------|
| Cursor | ✓ (Merkle tree) | ✓ (tree-sitter) | ✓ | ✓ |
| Claude Code | ✓ | ✓ | ✓ (JSONL) | ✓ (session_memory) |
| Aider | ✓ (PageRank) | ✓ | Optional | - |
| Windsurf | ✓ (embeddings) | ✓ | Session-scoped | - |

---

## 4. Key Design Principles

### From Anthropic's Managed Agents:

1. **Decouple Brain from Hands**: Harness calls sandbox as a tool, never co-located
2. **Session as Context Object**: Lives outside context window, durably stored
3. **Security Boundary**: Tokens never reachable from sandbox
4. **Many Brains, Many Hands**: Scalable architecture supporting multiple execution environments
5. **Opinionated About Interfaces**: Stable interfaces allow implementation changes

### From Cursor:

1. **Autonomy Requires Verification**: Agent's value depends on self-testing
2. **Latency is Success Metric**: Slow agents break human flow, reduce trust
3. **Context Grounded in Structure**: AST-based chunking maintains semantic meaning
4. **Isolation Enables Parallelism**: Separate worktrees prevent conflicts

### From Claude Code:

1. **Tools as API Surface**: Typed, single-purpose functions with Zod schemas
2. **Centralized State**: Single AppState store with DeepImmutable wrapper
3. **Permission Gates at Boundaries**: All tool calls pass through permission checks
4. **Built for Interruption**: Tracked task lifecycles (pending, running, completed, failed, killed)

---

## 5. Common Patterns Across Implementations

### 5.1 Universal Patterns

1. **Git Worktrees for Isolation**: All examined tools use git worktrees for parallel agent execution
2. **Model Routing**: Fast/small models for routine tasks, frontier models for complex decisions
3. **Context Compaction**: Multi-layer strategies to manage context window limits
4. **Permission Systems**: Cascading decision flows from static rules to user prompts
5. **AST-Based Understanding**: Tree-sitter parsing for semantic code comprehension

### 5.2 Quality Gaps

| Gap | Prevalence |
|-----|-----------|
| Cost Governance | Universal - no tool has comprehensive cost tracking |
| Quality Gate Enforcement | Limited - verification exists but not enforced at scale |
| Cross-Session Context | Inconsistent - some tools reset on close |
| Network Isolation | Incomplete - many tools lack full network sandboxing |

---

## 6. Near-Miss Tier

### ExitBox — Container-First Isolation
- **Why it nearly made the cut**: Open-source, focuses purely on isolation, AGPL-3.0 licensed
- **Why it ranked below**: Not a complete agent harness, only provides sandboxing layer
- **Best for**: Teams needing strict isolation for existing agent tools

### scode — Lightweight Sandbox Wrapper
- **Why it nearly made the cut**: Agent-agnostic, single policy for all tools, MIT licensed
- **Why it ranked below**: Beta software, relies on deprecated macOS Seatbelt
- **Best for**: Quick deployment of sandboxing without container overhead

### ai-jail — Defense-in-Depth
- **Why it nearly made the cut**: Rust-based, multi-OS support, Landlock LSM + Seccomp
- **Why it ranked below**: GPL-3.0 license, more complex setup than alternatives
- **Best for**: Security-focused environments requiring multiple isolation layers

---

## 7. Key Takeaways

1. **Brain-Hands-Session Decoupling**: The most robust architectures separate the LLM (brain) from execution (hands) with a durable session layer - enabling scalability and security

2. **Git Worktrees Are Universal**: Every examined implementation uses git worktrees as the primary isolation mechanism for parallel agent execution

3. **Context Management is Complex**: All implementations struggle with context window limits - using multi-layer compaction, summarization, and selective injection

4. **Model Routing is Essential**: Fast models for routine work, frontier models for complex decisions - this pattern appears across all implementations

5. **Permission Systems are Cascading**: From static rules through tool logic to user prompts - the four-layer pattern ensures safety without blocking legitimate operations

6. **Cost Governance is a Universal Gap**: No examined tool provides comprehensive cost tracking, budget limits, or automatic shutoff

7. **AST-Based Understanding is Standard**: Tree-sitter parsing for semantic code comprehension is the universal approach

8. **Latency Directly Impacts Trust**: Slow agents feel unreliable even when correct - performance engineering is not optional

---

## Sources

[1] AI Harness Comparative Analysis - https://gist.github.com/jeffscottward/de77a769d9e25a8ccdc92b65291b1c34 - Accessed 2026-04-17

[2] Scaling Managed Agents - https://www.anthropic.com/engineering/managed-agents - Accessed 2026-04-17

[3] Designing high-performance agentic systems - https://medium.com/@khayyam.h/designing-high-performance-agentic-systems-an-architectural-case-study-of-the-cursor-agent-ab624e4a0a64 - Accessed 2026-04-17

[4] Inside Claude Code: An Architecture Deep Dive - https://zainhas.github.io/blog/2026/inside-claude-code-architecture/ - Accessed 2026-04-17

[5] Core Architecture | Aider-AI/aider - https://deepwiki.com/Aider-AI/aider/2-core-architecture - Accessed 2026-04-17

[6] Windsurf - Cascade - https://docs.codeium.com/windsurf/cascade/cascade - Accessed 2026-04-17

[7] Roo Code vs Cline - https://www.qodo.ai/blog/roo-code-vs-cline/ - Accessed 2026-04-17

[8] Introducing ExitBox - https://medium.com/@cloud-exit/introducing-exitbox-run-ai-coding-agents-in-complete-isolation-6013fb5bdd06 - Accessed 2026-04-17

[9] scode: A Seatbelt for AI Coding - https://binds.ch/blog/scode-sandbox-for-ai-coding-tools - Accessed 2026-04-17