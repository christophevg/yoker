# Yoker Project Rationale

## Why Yoker Exists

Yoker fills a unique gap in the coding agent ecosystem: a **library-first, transparent agent harness** designed for developers who want full control, visibility, and simplicity.

## The Problem

Existing coding agent solutions share common limitations:

| Problem | Examples |
|---------|----------|
| **Black box operation** | Claude Code, Cursor, Aider operate opaquely - you can't see what's happening inside |
| **Hidden restrictions** | Claude Code adds "safety" restrictions without transparency |
| **Complex tool integration** | MCP servers, complex protocols, steep learning curve |
| **Runtime prompts** | Every dangerous operation requires approval, interrupting autonomous workflows |
| **API dependencies** | Most solutions require cloud API access, incurring costs and privacy concerns |
| **Framework vs Application** | Generic frameworks (OpenAI Agents SDK) require significant coding-specific development |

## The Yoker Approach

### Core Philosophy: Transparency Over Magic

```
Everything is open and clear and inspectable, configurable.
No hidden features, no magic sauce.
```

Yoker believes developers should:
- **See everything** - Full visibility into agent decisions and actions
- **Configure everything** - All behavior controlled via TOML configuration
- **Understand everything** - No hidden features, no opaque restrictions

### Architecture: Library-First Design

Yoker is a **library**, not an application:

```
┌─────────────────────────────────────────────────────────┐
│                    Your Application                       │
│                         │                                 │
│                    Event Handler                          │
│                         │                                 │
│    ┌───────────────────┴───────────────────┐            │
│    │              Yoker Library              │            │
│    │                                         │            │
│    │  ┌──────────┐  ┌──────────┐  ┌────────┐ │            │
│    │  │  Agent   │  │  Tools   │  │ Context│ │            │
│    │  │          │←→│ Registry │←→│Manager │ │            │
│    │  └──────────┘  └──────────┘  └────────┘ │            │
│    │        │                                   │            │
│    │        ▼                                   │            │
│    │   Event Emission                           │            │
│    └───────────────────────────────────────────┘            │
│                         │                                 │
│                         ▼                                 │
│              Your Custom Handler                          │
│           (Console, File, UI, API...)                     │
└─────────────────────────────────────────────────────────┘
```

**Key difference**: Other solutions are applications (CLI/IDE) that you use. Yoker is a library you embed.

### Developer-Friendly Tool Registration

```python
# Yoker: Simple Python function
@tool
def read_file(path: str) -> str:
    """Read a file from disk."""
    return open(path).read()

# Other solutions: MCP servers
# - Define server protocol
# - Implement JSON-RPC
# - Handle transport layer
# - Manage server lifecycle
```

Tools in Yoker are **simple Python functions** that can be registered with a decorator. No MCP servers, no complex protocols.

### Static Permissions: Uninterrupted Autonomy

Yoker uses **static TOML-based permissions** instead of runtime prompts:

```toml
[permissions]
file_read = ["./src/**", "./docs/**"]
file_write = ["./output/**"]
network_access = "none"
```

**Why this matters:**
- LLM-based guardrails have **26.67% violation rate** (research shows)
- Static deterministic rules have **0.00% violation rate**
- No runtime interruptions for "potentially dangerous" operations
- Predictable, auditable security boundaries

### Ollama-First: Zero Cost, Maximum Privacy

Yoker is designed for **local-first operation**:

| Feature | Yoker | Others |
|---------|-------|--------|
| API Cost | $0 (local) | $0.15-3.00 per million tokens |
| Internet Required | No | Yes |
| Data Privacy | 100% local | Cloud processing |
| Offline Operation | Full support | Limited/none |

### Recursive Composition: True Sub-Agents

When yoker spawns a sub-agent, it creates a **full library instance**:

```python
# Sub-agent in yoker
sub_agent = Agent(
    config=child_config,      # Isolated configuration
    context=child_context,    # Isolated context
    model="llama3.2:latest",  # Configurable model
)
```

**Other solutions** treat sub-agents as function calls. Yoker treats them as **complete agent instances** with:
- Isolated context (no message leakage)
- Configurable model (cheaper model for sub-tasks)
- Scoped permissions (sub-agent can't access parent's files)
- Own event stream (traceable operations)

## Target Use Cases

### Designed For

| Use Case | Why Yoker |
|----------|-----------|
| **Embedding in applications** | Library-first design, event emission |
| **CI/CD automation** | Static permissions, no runtime prompts |
| **Offline/air-gapped environments** | Ollama backend, zero internet |
| **Cost-sensitive workflows** | Zero API cost |
| **Custom agent-based tools** | Full control, no hidden behavior |
| **Learning agent architecture** | Transparent, inspectable code |

### Not Designed For

| Use Case | Better Alternative |
|----------|-------------------|
| Interactive coding sessions | Claude Code, Cursor, Aider |
| Multi-agent orchestration platforms | OpenAI Agents SDK, LangGraph |
| General AI framework needs | Microsoft Agent Framework |

## Positioning in the Ecosystem

```
┌─────────────────────────────────────────────────────────────┐
│                      Layer Analysis                          │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  APPLICATION LAYER (CLI/IDE)                                 │
│  ├── Claude Code ←──── You use these                         │
│  ├── Cursor                                                  │
│  ├── Aider                                                   │
│  └── Windsurf, Cline, Continue                               │
│                                                              │
│  FRAMEWORK LAYER (Generic)                                   │
│  ├── OpenAI Agents SDK ←──── You build on these             │
│  ├── Microsoft Agent Framework                               │
│  └── LangGraph, AutoGen                                      │
│                                                              │
│  LIBRARY LAYER (Coding-Specific)                             │
│  └── Yoker ←──── The gap we fill                            │
│       • Event-driven library                                  │
│       • Static permissions                                    │
│       • Ollama-first                                          │
│       • Full transparency                                     │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## Key Differentiators Summary

| Aspect | Yoker | Others |
|--------|-------|--------|
| **Architecture** | Library | Application |
| **Visibility** | Full event stream | Black box |
| **Permissions** | Static TOML | Runtime prompts |
| **Tools** | Python functions | MCP servers |
| **Backend** | Ollama-first | API-dependent |
| **Cost** | $0 | $0.15-3.00/M tokens |
| **Offline** | Full support | Limited |
| **Sub-agents** | Full instances | Function calls |
| **Transparency** | 100% | Varies |

## Conclusion

Yoker exists because developers need a **transparent, controllable, library-first agent harness** that respects their autonomy and intelligence. No hidden restrictions, no magic sauce - just clear, inspectable code that does exactly what you configure it to do.

> "Everything is open and clear and inspectable, configurable.
> No hidden features, no magic sauce."