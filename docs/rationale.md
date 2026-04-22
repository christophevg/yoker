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
| **Vendor lock-in** | Most solutions mandate a specific LLM provider - you're locked into their pricing, limits, and terms |
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

```{image} _static/architecture-diagram.svg
:alt: Architecture Diagram
```

**Key difference**: Other solutions are applications (CLI/IDE) that you use. Yoker is a library you embed.

**Extension points**:
- **UI Layer**: Built-in CLI and TUI (via clitic), or plug in your own
- **Tools**: Simple Python functions you register, not MCP servers
- **Context Manager**: Built-in JSONL persistence, or implement your own
- **Event Handlers**: Subscribe to any event stream for custom behavior

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

### Static Permissions: Predictable Boundaries

Yoker uses **static TOML-based permissions** instead of runtime prompts:

```toml
[permissions]
file_read = ["./src/**", "./docs/**"]
file_write = ["./output/**"]
network_access = "none"
```

**Why this matters:**
- LLM-based guardrails can be **socially engineered** or bypassed
- Static rules are **deterministic** - if configured correctly, they're enforced consistently
- No runtime interruptions for "potentially dangerous" operations
- Predictable, auditable security boundaries

**Important caveat**: Static permissions protect operations **through Yoker's tools**. A determined agent could:
- Generate a Python script that reads files directly (bypassing Yoker's `read` tool)
- Use subprocess to execute shell commands
- Find other creative bypasses

**The trade-off**: Static permissions provide **clear boundaries within the framework**, but they don't replace comprehensive security practices. Tool registration and code inspection are areas for future research.

### LLM-Neutral: Choice by Design

Yoker is **LLM-neutral by design**. No preferred provider, no vendor lock-in - you choose:

```toml
[backend]
provider = "ollama"  # or "openai", "anthropic", etc.

[backend.ollama]
base_url = "http://localhost:11434"  # Local
# base_url = "https://api.ollama.ai"  # Cloud

model = "llama3.2:latest"  # Your choice
```

**Why this matters:**

| Your Choice | Cost | Privacy | Performance |
|-------------|------|---------|-------------|
| Local Ollama | $0 | 100% local | Slower (current hardware) |
| Ollama Cloud | Pay-per-use | No logging by GPU providers | Fast |
| Private infrastructure | Your cost | Your control | Configurable |
| Other providers | Varies | Varies | Varies |

**Note**: Ollama guarantees that no information is logged or used by GPU providers when running models on their infrastructure. This is stated clearly on their website.

The fundamental principle: **Yoker doesn't choose for you**. You decide:
- Which LLM to use
- Where it runs (local, cloud, private)
- What privacy/cost trade-offs to accept

**Privacy is determined by your LLM choice**, not by Yoker. Use a local model for maximum privacy, or a cloud provider for speed - Yoker supports both.

### No Hidden Manipulation: Transparent Context

Yoker has **zero hidden context manipulation**. Everything sent to the LLM is:

- **Visible** - You can see exactly what prompts the agent receives
- **Editable** - All prompts, system messages, and context are in files you control
- **Configurable** - No secret instructions injected by the framework

```yaml
# agents/researcher.md - Everything visible, everything editable
---
name: Researcher
description: Research agent for web and documentation
tools:
  - read
  - search
system_prompt: |
  You are a research agent. Your goal is to find and synthesize information.
  # This entire prompt is visible and editable - no hidden instructions
---
```

**Other solutions** inject hidden instructions you cannot see or control. Yoker's philosophy: the framework should never secretly influence LLM behavior.

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
| **Offline/air-gapped environments** | LLM-neutral, local model support |
| **Cost-sensitive workflows** | Choose your cost model (local = $0) |
| **Custom agent-based tools** | Full control, no hidden behavior |
| **Learning agent architecture** | Transparent, inspectable code |

### Not Designed For (Directly)

| Use Case | Better Alternative |
|----------|-------------------|
| **Out-of-the-box interactive coding** | Claude Code, Cursor, Aider |
| Multi-agent orchestration platforms | OpenAI Agents SDK, LangGraph |
| General AI framework needs | Microsoft Agent Framework |

**Important nuance**: Yoker's library-first design means you *can* build your own interactive experience on top of it. Many users want Yoker's features (improved permissions, flexible tools, no sub-agent restrictions, no hidden manipulation) in their interactive coding sessions - and they can have that by building a UI layer.

### The Workflow Model: Interactive ↔ Autonomous

Yoker enables a unique workflow: develop collections interactively, deploy autonomously, return for refinement.

```{image} _static/workflow-model.svg
:alt: Workflow Model
```

**This changes how you build agent systems:**
- Not "build for interactive" vs "build for autonomous"
- Build once in interactive mode, deploy to autonomous
- The UI becomes your development environment, not your runtime constraint
- Return to interactive anytime for refinement and bug fixes

## Key Differentiators Summary

| Aspect | Yoker | Others |
|--------|-------|--------|
| **Architecture** | Library | Application |
| **Visibility** | Full event stream | Black box |
| **Context** | No hidden manipulation | Secret instructions |
| **Permissions** | Static TOML (deterministic) | Runtime prompts (bypassable) |
| **Tools** | Python functions | MCP servers |
| **LLM Provider** | Your choice | Vendor's choice |
| **Cost** | Your choice | Vendor pricing |
| **Privacy** | Your choice | Vendor's terms |
| **Sub-agents** | Full instances | Function calls |
| **Workflow** | Interactive ↔ Autonomous | Fixed mode |
| **Transparency** | 100% | Varies |

## Conclusion

Yoker exists because developers need a **transparent, controllable, library-first agent harness** that respects their autonomy and intelligence. No hidden restrictions, no magic sauce - just clear, inspectable code that does exactly what you configure it to do.

> "Everything is open and clear and inspectable, configurable.
> No hidden features, no magic sauce."