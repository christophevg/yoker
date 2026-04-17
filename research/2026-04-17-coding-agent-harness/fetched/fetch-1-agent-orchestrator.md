# Agent Orchestrator (ComposioHQ) - Fetched Content

**URL**: https://gist.github.com/jeffscottward/de77a769d9e25a8ccdc92b65291b1c34
**Timestamp**: 2026-04-17T10:02:00Z
**Source**: search-1

---

## Agent Orchestrator (ComposioHQ)

### 1. Architecture Patterns

**Plugin-Everything Architecture**: Eight distinct capability slots (runtime, agent, workspace, tracker, scm, notifier, terminal, lifecycle) with clean TypeScript interfaces.

**Flat-File State**: "All session state lives in the filesystem as key=value metadata files. No SQLite, no Postgres, no Redis."

**Monorepo Structure**: Uses pnpm workspaces with packages for core, cli, web, and plugins.

**Hash-Based Namespacing**: SHA-256 hash of config directory path creates globally unique identifiers (12-char prefix).

### 2. Key Features

- Parallel AI coding agents spawning
- Web dashboard with Kanban-style view grouped by attention level
- Reaction engine with retries and escalation
- Session lifecycle management (16 distinct statuses)
- Multiple notification channels (Slack, desktop, webhook)
- Auto-merge capability for approved PRs with passing CI

### 3. Orchestration Models

**Two-Tier Meta-Agent Pattern**:
- **Tier 1 (Orchestrator)**: Special agent session receiving system prompt with all CLI commands
- **Tier 2 (Workers)**: Individual coding agents assigned to single issues

The orchestrator "communicates with AO only through the CLI — it runs `ao spawn`, `ao status`, `ao send`, etc. as shell commands."

### 4. Isolation Strategies

**Git Worktrees**: "Each agent session gets its own git worktree — a separate checkout of the same repository on a different branch."

**tmux Sessions**: Each agent runs in separate tmux session with its own PTY, environment variables, process tree, and working directory.

**What IS isolated**: Filesystem, process, environment variables, git state
**What is NOT isolated**: Network, credentials, CPU/memory, git remote

### 5. Quality Gates

- TypeScript strict mode
- Zod validation for configuration
- CI checks with fail-closed logic: "For open PRs, fail closed — report 'failing' on error"
- GitHub security workflows: gitleaks, dependency-review, npm-audit

**Missing**: No linting rules visible, no test coverage requirements, no E2E tests

### 6. Context Management

**Three-Layer Prompt Composition**:
1. Base Agent Prompt (hardcoded)
2. Config-Derived Context (from YAML)
3. User Rules (agentRules/agentRulesFile)

**Limitations**: "No conversation history... No cross-session context... No dynamic context refresh... No context window management"

### 7. Cost Governance

**What's Tracked**: Token usage and cost estimates extracted from Claude Code JSONL files.

**What's NOT Tracked**: "No aggregated cost view... No budget limits... No cost alerts... No automatic shutoff... No cost display in CLI"

### 8. Multi-Agent Coordination

**Embarrassingly Parallel**: "Each agent works on an independent issue in an independent workspace."

**No coordination mechanisms**: No shared memory, no lock coordination, no task dependency graphs, no work-stealing queues, no agent-to-agent communication.

**Resource Constraints**: "The system imposes no resource limits at the orchestration level."