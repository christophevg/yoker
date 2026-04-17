# Claude Code Architecture - Fetched Content

**URL**: https://zainhas.github.io/blog/2026/inside-claude-code-architecture/
**Timestamp**: 2026-04-17T10:07:00Z
**Source**: search-3

---

## 1. Major Subsystems

Based on the architecture diagram, Claude Code has six primary layers:

- **Entry Points**: CLI, MCP server, SDK, HTTP server, daemon/bridge
- **Bootstrap & Configuration**: init(), configs, telemetry, auth, proxy/TLS
- **UI Layer**: Ink/React TUI with App.tsx, REPL.tsx, Messages.tsx, PromptInput
- **Query Engine**: message history, session management, streaming API calls, tool orchestration
- **Tool System**: 50+ tools organized into File, Shell, Web, Agent, Plan, Task, MCP, and System categories
- **Services & State**: AppState Store, API clients, analytics, MCP manager, plugins, hooks, history

## 2. Query Engine Implementation

The QueryEngine is "the heart" of the system. It orchestrates the agentic loop:

- `QueryEngine.ts` manages message history and sessions
- `query.ts` contains `queryLoop()` as an **async generator** that yields streaming events
- The loop: send message -> stream response -> execute tools -> send results -> repeat
- Terminates when Claude responds without `tool_use` blocks
- Handles recovery paths: context compaction, output limit escalation, model fallback, user interrupt

**Key pattern**: "The query loop is an async generator — it `yield`s streaming events as they arrive from the Claude API, allowing the UI to render responses incrementally."

## 3. Tool System Design

The `Tool` interface (src/Tool.ts) is the core abstraction:

```
Tool<Input, Output, Progress>
├── Identity: name, userFacingName(), description()
├── Schema: inputSchema (Zod), outputSchema
├── Execution: call(input, context) → ToolResult
├── Concurrency: isConcurrencySafe(), isReadOnly()
├── Permissions: checkPermissions(), validateInput()
└── Rendering: prompt(), renderToolUseMessage(), renderToolResultMessage()
```

**Execution pattern**: Read-only tools run in parallel batches; write tools run sequentially to prevent race conditions.

## 4. AppState and State Management

`AppStateStore.ts` contains the single source of truth with 300+ properties organized into:

- **Core**: settings, mainLoopModel, verbose, statusLineText
- **Tasks**: tasks map, foregroundedTask, agentNameRegistry
- **Permissions**: toolPermissionContext, activeOverlays
- **MCP**: clients, tools, resources
- **Plugins**: enabled, disabled, errors
- **UI**: expandedView, fastMode, thinkingEnabled, notifications

**Access pattern**: `useAppState(selector)` for React re-render on change; `useSetAppState()` for updates.

## 5. Bridge and Remote Control

Entry points include:
- `daemon/bridge/ssh` for remote sessions
- `remote-control` mode for external control
- Session management commands: `ps`, `logs`, `attach`

Inter-agent communication uses **Unix Domain Sockets (UDS)** with inbox-based messaging between leader and teammate agents.

## 6. Sandbox System

Not explicitly detailed in the provided content. The architecture focuses on permission-based security rather than sandboxing.

## 7. Memory/Context Management (Compaction)

**Five-layer compaction pipeline** runs each turn:

1. **Tool Result Budget**: Enforce per-message size limits (20K chars), persist large results to disk
2. **Snip Compaction**: Clear old tool result contents while keeping message structure
3. **Microcompaction**: Remove old tool results via `cache_edits` API or content clearing
4. **Context Collapse**: Model-side compression (internal feature)
5. **Autocompact**: Full conversation compaction when tokens reach threshold

**Key constants**:
- Autocompact trigger: `effectiveWindow - 13,000` tokens
- Session memory init: 8,000 tokens
- Session memory update interval: 15,000 tokens

**Session Memory Extraction** runs asynchronously via post-sampling hook, maintaining `~/.claude/session_memory` with sections capped at 2,000 tokens each.

## 8. Permission System

**Four-layer cascading decision flow**:

1. **Static Rules** (settings.json): Match tool name + pattern -> allow/deny/ask
2. **Tool Logic**: `tool.checkPermissions()` for tool-specific safety checks
3. **Permission Mode**: `bypassPermissions`, `auto` (check classifier), `default` (prompt user), `plan` (deny writes)
4. **User Prompt**: Terminal dialog for explicit consent

## 9. Hooks System

Hooks are user-configured lifecycle events with 25+ event types including:
- Pre-tool use (`PreToolUse`)
- Post-tool use (`PostToolUse`)
- Session hooks

Configuration loaded via `captureHooksConfigSnapshot()` during setup. Plugin hooks loaded separately with hot-reload support.

## 10. MCP Integration

**MCP Manager** handles:
- Server connections with OAuth authentication
- Dynamic tool registration from MCP servers
- Resource management (`ListMCPRes`, `ReadMCPRes`)

MCP tools plug into the same Tool interface as built-in tools, enabling uniform handling through the permission and execution pipeline.