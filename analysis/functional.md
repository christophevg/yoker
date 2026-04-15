# Functional Analysis: Yoker

**Document Version**: 1.2
**Date**: 2026-04-14
**Status**: Revised Analysis

> **Naming**: "yoker" is the package name - one who yokes, the agent noun from "yoke". Etymology: from PIE *\yeug-* meaning "to join" - same root as yoga (union), conjugate, junction. Pairs beautifully with "clitic" (both are joining tools). Available on PyPI. See `docs/NAME.md` for full naming documentation.

## 1. Vision and Goals

### 1.1 Vision Statement

Yoker provides a structured, safe environment for AI agents to execute tasks with well-defined boundaries. Unlike generic agent frameworks that grant broad system access, Yoke operates on the principle of **explicit permissions and specific tools**.

### 1.2 Primary Goals

| Goal | Description | Priority |
|------|-------------|----------|
| Safety | Prevent unintended operations through guardrails | Critical |
| Configurability | All aspects configurable via single TOML file | Critical |
| Simplicity | Specific tools, no generic shell access | Critical |
| Transparency | Complete audit trail of all operations | High |
| Extensibility | Easy to add new guarded tools | Medium |

### 1.3 Non-Goals (MVP)

- Auto-starting Ollama (assumed running)
- Dynamic configuration reload
- Multi-user authentication
- Token optimization (Phase 2)
- Web UI (Phase 2)

---

## 2. Core Architecture Components

### 2.1 Component Overview

```
┌────────────────────────────────────────────────────────────────┐
│                          Yoker                                  │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                    Configuration Layer                    │  │
│  │  ┌─────────────────┐    ┌─────────────────────────────┐   │  │
│  │  │  Config Loader   │    │  Config Validator           │   │  │
│  │  │  (TOML Parser)   │───▶│  (Schema + Semantics)        │   │  │
│  │  └─────────────────┘    └─────────────────────────────┘   │  │
│  └──────────────────────────────────────────────────────────┘  │
│                              │                                  │
│                              ▼                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                    Execution Layer                        │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐     │  │
│  │  │  Context    │  │  Tool       │  │  Guardrail      │     │  │
│  │  │  Manager    │  │  Dispatcher │  │  Enforcer        │     │  │
│  │  │             │  │             │  │                 │     │  │
│  │  └──────┬──────┘  └──────┬──────┘  └────────┬────────┘     │  │
│  │         │                │                  │              │  │
│  │         ▼                ▼                  ▼              │  │
│  │  ┌─────────────────────────────────────────────────────┐  │  │
│  │  │              Tool Implementations                     │  │  │
│  │  │  [List] [Read] [Write] [Update] [Search] [Agent]      │  │  │
│  │  └─────────────────────────────────────────────────────┘  │  │
│  └──────────────────────────────────────────────────────────┘  │
│                              │                                  │
│                              ▼                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                    Backend Layer                          │  │
│  │  ┌─────────────────────────────────────────────────────┐ │  │
│  │  │              Ollama Client                           │ │  │
│  │  │  (HTTP API, streaming, configurable params)           │ │  │
│  │  └─────────────────────────────────────────────────────┘ │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                    Support Layer                          │  │
│  │  [Logging] [Reporting] [Error Handling]                   │  │
│  └──────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────┘
```

### 2.2 Component Details

#### 2.2.1 Configuration Layer

**Purpose**: Load, parse, and validate the single TOML configuration file.

**Responsibilities**:
- Parse TOML file into structured config object
- Validate schema (required fields, types)
- Validate semantics (paths exist, URLs reachable)
- Provide typed config access to other components

**Error Handling**:
- Invalid TOML syntax: Fail fast with clear error message
- Missing required fields: Fail fast listing missing fields
- Invalid paths/URLs: Warning or fail depending on severity

#### 2.2.2 Context Manager

**Purpose**: Persist and restore agent context across LLM calls.

**Responsibilities**:
- Store conversation history (user messages, assistant responses, tool calls)
- Track agent state (current task, working variables)
- Persist to JSONL file after each turn (append-friendly)
- Load context on startup/handoff

**Storage Format (JSONL)**:

Each line is a JSON object, making the format append-friendly for growing conversations:

```jsonl
{"type": "metadata", "session_id": "uuid", "created_at": "ISO timestamp", "agent_type": "main"}
{"type": "message", "role": "system", "content": "..."}
{"type": "message", "role": "user", "content": "..."}
{"type": "message", "role": "assistant", "content": "...", "tool_calls": [...]}
{"type": "tool_result", "tool_call_id": "...", "content": "..."}
{"type": "state", "working_directory": "...", "custom_vars": {}}
```

**Benefits of JSONL**:
- Append-only: Each new turn appends a line, no need to rewrite entire file
- Streamable: Can process context line-by-line for large histories
- Debuggable: Easy to inspect with `tail -f` or line-by-line JSON parsing
- Resilient: Corrupted line doesn't break the entire file

#### 2.2.3 Tool Dispatcher

**Purpose**: Route tool calls to appropriate implementations with guardrail enforcement.

**Responsibilities**:
- Parse tool call requests from LLM response
- Validate tool is available to current agent
- Forward to guardrail enforcer for permission check
- Execute tool if permitted
- Format result for LLM consumption
- Handle tool errors gracefully

#### 2.2.4 Guardrail Enforcer

**Purpose**: Enforce tool-specific and global guardrails.

**Responsibilities**:
- Check path restrictions (read/write operations)
- Enforce size limits
- Validate patterns (search operations)
- Track recursion depth (agent spawning)
- Log all guardrail decisions

#### 2.2.5 Ollama Client

**Purpose**: Communicate with Ollama backend.

**Responsibilities**:
- Build API requests with configurable parameters
- Handle streaming responses
- Parse responses for tool calls
- Manage connection errors and retries

---

## 3. Tool System Design

### 3.1 Tool Interface

All tools implement a common interface:

```python
class Tool(ABC):
    name: str
    description: str  # For LLM tool definition

    @abstractmethod
    def get_schema(self) -> dict:
        """Return JSON Schema for tool parameters."""
        pass

    @abstractmethod
    def execute(self, params: dict, config: ToolConfig) -> ToolResult:
        """Execute tool with parameters and configuration."""
        pass

    @abstractmethod
    def validate_guardrails(self, params: dict, config: ToolConfig) -> ValidationResult:
        """Check if operation is permitted."""
        pass
```

### 3.2 MVP Tools

#### 3.2.1 List Tool

**Purpose**: List directory contents.

**Schema**:
```json
{
  "name": "list",
  "parameters": {
    "path": {"type": "string", "description": "Directory path to list"},
    "pattern": {"type": "string", "description": "Optional glob pattern filter"},
    "recursive": {"type": "boolean", "default": false}
  }
}
```

**Guardrails**:
| Guardrail | Description | Default |
|-----------|-------------|---------|
| `allowed_paths` | List of path prefixes that are allowed | `[]` (deny all) |
| `max_depth` | Maximum recursion depth for recursive listing | `3` |
| `max_entries` | Maximum entries to return | `1000` |

**Result Format**:
```json
{
  "success": true,
  "entries": [
    {"name": "file.txt", "type": "file", "size": 1024},
    {"name": "subdir", "type": "directory"}
  ],
  "truncated": false
}
```

#### 3.2.2 Read Tool

**Purpose**: Read file contents.

**Schema**:
```json
{
  "name": "read",
  "parameters": {
    "path": {"type": "string", "description": "File path to read"},
    "offset": {"type": "integer", "description": "Start line (optional)"},
    "limit": {"type": "integer", "description": "Max lines to read (optional)"}
  }
}
```

**Guardrails**:
| Guardrail | Description | Default |
|-----------|-------------|---------|
| `allowed_paths` | List of path prefixes | `[]` (deny all) |
| `allowed_extensions` | List of allowed file extensions | `[".txt", ".md", ".json", ".py", ...]` |
| `max_size_kb` | Maximum file size in KB | `100` |
| `blocked_patterns` | Patterns to deny (e.g., `.env`, `credentials`) | `[]` |

**Result Format**:
```json
{
  "success": true,
  "content": "...",
  "line_count": 50,
  "truncated": false
}
```

#### 3.2.3 Write Tool

**Purpose**: Create new files.

**Schema**:
```json
{
  "name": "write",
  "parameters": {
    "path": {"type": "string", "description": "File path to write"},
    "content": {"type": "string", "description": "Content to write"}
  }
}
```

**Guardrails**:
| Guardrail | Description | Default |
|-----------|-------------|---------|
| `allowed_paths` | List of path prefixes for writes | `[]` (deny all) |
| `allow_overwrite` | Whether existing files can be overwritten | `false` |
| `max_size_kb` | Maximum content size in KB | `500` |
| `blocked_extensions` | Extensions that cannot be created | `[".exe", ".sh", ...]` |

**Result Format**:
```json
{
  "success": true,
  "path": "/workspace/output/result.txt",
  "bytes_written": 1024,
  "created": true
}
```

#### 3.2.4 Update Tool

**Purpose**: Edit existing files with precise changes.

**Schema**:
```json
{
  "name": "update",
  "parameters": {
    "path": {"type": "string", "description": "File path to update"},
    "operation": {
      "type": "string",
      "enum": ["replace", "insert_before", "insert_after", "delete"],
      "description": "Type of edit operation"
    },
    "search": {"type": "string", "description": "Text to search for"},
    "replacement": {"type": "string", "description": "Replacement text"},
    "line_number": {"type": "integer", "description": "Line number for insert ops"}
  }
}
```

**Guardrails**:
| Guardrail | Description | Default |
|-----------|-------------|---------|
| `allowed_paths` | List of path prefixes for updates | `[]` (deny all) |
| `require_exact_match` | Search must match exactly | `true` |
| `max_diff_size_kb` | Maximum size of change | `50` |

**Result Format**:
```json
{
  "success": true,
  "lines_modified": 3,
  "diff_preview": "..."
}
```

#### 3.2.5 Search Tool

**Purpose**: Search for patterns in files.

**Schema**:
```json
{
  "name": "search",
  "parameters": {
    "path": {"type": "string", "description": "Directory to search in"},
    "pattern": {"type": "string", "description": "Search pattern (regex)"},
    "type": {"type": "string", "enum": ["content", "filename"], "default": "content"},
    "max_results": {"type": "integer", "default": 100}
  }
}
```

**Guardrails**:
| Guardrail | Description | Default |
|-----------|-------------|---------|
| `allowed_paths` | List of path prefixes | `[]` (deny all) |
| `max_regex_complexity` | Prevent ReDoS attacks | `medium` |
| `max_results` | Maximum results returned | `100` |
| `timeout_ms` | Search timeout | `5000` |

**Result Format**:
```json
{
  "success": true,
  "matches": [
    {"file": "src/main.py", "line": 42, "content": "..."}
  ],
  "total_matches": 15,
  "truncated": false
}
```

#### 3.2.6 Agent Tool

**Purpose**: Spawn subagents for hierarchical task decomposition.

**Schema**:
```json
{
  "name": "agent",
  "parameters": {
    "agent_type": {"type": "string", "description": "Type of subagent to spawn"},
    "prompt": {"type": "string", "description": "Initial prompt for subagent"}
  }
}
```

**Key Design Decisions**:
- **Tool availability**: Defined in agent's Markdown definition (frontmatter), not passed at spawn time
- **No depth awareness**: Agents don't know their recursion depth; they handle errors when max depth is exceeded
- **Clean context**: Subagents start with a fresh context file, receiving only the initial prompt
- **Minimal enforcement**: Workflow and interaction patterns defined in-context, not hard-coded

**Guardrails**:
| Guardrail | Description | Default |
|-----------|-------------|---------|
| `max_recursion_depth` | Maximum agent nesting level | `3` |
| `timeout_seconds` | Maximum subagent execution time | `300` |

**Error Handling**:
When max recursion depth is exceeded, the Agent tool returns an error. The parent agent's system prompt should instruct it how to handle this situation.

**Result Format**:
```json
{
  "success": true,
  "agent_id": "uuid",
  "result": "...",
  "tool_calls_made": 5,
  "execution_time_seconds": 12.5
}
```

**Error Result**:
```json
{
  "success": false,
  "error": "max_recursion_depth_exceeded",
  "message": "Maximum recursion depth (3) reached. Cannot spawn more subagents."
}
```

### 3.3 Tool Availability Model

```
Global Config (harness.toml)
     │
     ├── Tools Section (defines all tools + their guardrails)
     │
     └── Agents Directory (Markdown files with frontmatter)
              │
              └── tools: ["list", "read", "search"] in frontmatter
```

**Key Principle**: Guardrails are global (same rules for all agents), but tool availability can be reduced per agent.

**Example**:
- Global config allows reading from `/workspace` and `/docs`
- Agent A has tools: `["read", "search"]` — can read from both paths
- Agent B has tools: `["read"]` — can read, but cannot search
- Neither agent can access paths outside `/workspace` and `/docs`

### 3.4 Tool Definitions

**Note**: Final tool parameter schemas should reference existing implementations:
- Claude Code's tool definitions (for compatibility)
- Ollama's tool calling API
- OpenAI's function calling format

The current tool definitions in this document are preliminary and will be refined during implementation by examining proven standards.

---

## 4. Agent Lifecycle and Communication

### 4.1 Agent States

```
┌─────────────┐
│   Created   │  ← Agent instantiated with config
└──────┬──────┘
       │ start()
       ▼
┌─────────────┐
│   Running   │  ← Processing messages, making tool calls
└──────┬──────┘
       │ stop() | error | complete
       ▼
┌─────────────┐
│   Stopped   │  ← Execution halted
└─────────────┘
```

### 4.2 Hierarchical Agent Spawning

```
Main Agent (depth: 0)
     │
     ├── spawns Researcher (depth: 1)
     │        │
     │        └── spawns Analyst (depth: 2)
     │
     └── spawns Writer (depth: 1)
              │
              └── spawns Reviewer (depth: 2)
                       │
                       └── max_depth=3 reached, Agent tool returns error
```

**Design Principles**:
- **No depth awareness**: Agents don't know their depth. They only receive an error if they try to spawn when max depth is reached.
- **Error handling in-context**: System prompts instruct agents how to handle the `max_recursion_depth_exceeded` error.
- **Minimal hard-coded workflow**: Interaction patterns defined through system prompts, not enforced in code.

**Spawning Process**:
1. Parent agent calls Agent tool with `agent_type` and `prompt`
2. Agent tool checks if `current_depth < max_recursion_depth`
3. If exceeded: return error to parent
4. If allowed: create subagent with:
   - Fresh, empty context
   - Initial prompt from parent
   - Tool set from agent definition (frontmatter)
   - Incremented depth (internal tracking, not exposed to agent)

### 4.3 Subagent Communication

#### 4.3.1 Parent-to-Child Communication

When spawning a subagent, the parent provides:
1. **Agent type**: Which agent definition to use
2. **Initial prompt**: Task description for the subagent

```json
{
  "agent_type": "researcher",
  "prompt": "Search for all Python files with TODO comments in /workspace/project"
}
```

The subagent's behavior and available tools are defined in its Markdown definition file (frontmatter), not passed at spawn time.

#### 4.3.2 Child-to-Parent Reporting

**MVP Approach**: Direct Return

- Subagent runs to completion and returns final result
- Parent receives result synchronously
- No intermediate progress updates in MVP

```python
# Subagent execution
result = await subagent.run(prompt)
# Result returned directly to parent
```

**Phase 2 Considerations**:
- Optional status callbacks for long-running tasks
- Progress streaming to parent
- Cancellation signals

#### 4.3.3 Context Isolation

Each subagent has its own isolated context:
- **Fresh context**: Empty conversation history at start
- **Initial prompt**: Only what the parent provides
- **Separate file**: Writes to its own JSONL file
- **Result only**: Only final result returned to parent

```
Parent Context                    Child Context
├── conversation (ongoing)        ├── conversation (empty, then grows)
├── state                         ├── state (minimal, from prompt)
└── children[]                    └── (isolated from parent)
    └── {child_id, result}
```

This clean isolation simplifies debugging and prevents context contamination.

### 4.4 Error Propagation

```
Subagent Error
     │
     ├── Recoverable → Return error to parent, parent decides action
     │
     └── Fatal → Propagate up, halt execution
```

---

## 5. Configuration Approach

### 5.1 TOML Configuration (harness.toml)

```toml
# yoker.toml - Main harness configuration

[harness]
name = "my-yoke"
version = "1.0"

[ollama]
base_url = "http://localhost:11434"
model = "llama3.2"
timeout_seconds = 60

# All Ollama API parameters exposed
[ollama.parameters]
temperature = 0.7
top_p = 0.9
top_k = 40
num_ctx = 4096
num_predict = -1  # -1 = infinite
stop = ["</answer>", "HUMAN:"]
seed = 42

[context]
storage_path = "./context"
session_id = "auto"  # or specific UUID
persist_after_turn = true

[logging]
level = "INFO"
file = "./logs/yoke.log"
include_tool_calls = true
include_guardrail_checks = true

# Global tool definitions with guardrails
[tools.list]
enabled = true
allowed_paths = ["/workspace", "/docs"]
max_depth = 5
max_entries = 2000

[tools.read]
enabled = true
allowed_paths = ["/workspace", "/docs", "/config"]
allowed_extensions = [".txt", ".md", ".json", ".yaml", ".toml", ".py", ".js"]
max_size_kb = 500
blocked_patterns = ["\\.env", "credentials", "secret"]

[tools.write]
enabled = true
allowed_paths = ["/workspace/output"]
allow_overwrite = false
max_size_kb = 1000
blocked_extensions = [".exe", ".sh", ".bat"]

[tools.update]
enabled = true
allowed_paths = ["/workspace"]
require_exact_match = true
max_diff_size_kb = 100

[tools.search]
enabled = true
allowed_paths = ["/workspace", "/docs"]
max_regex_complexity = "medium"  # low, medium, high
max_results = 500
timeout_ms = 10000

[tools.agent]
enabled = true
max_recursion_depth = 3
timeout_seconds = 300

# Default agent settings
[agents]
directory = "./agents"  # Where to find agent definitions (Markdown files)
default_type = "main"
```

### 5.2 Agent Definitions (Markdown with Frontmatter)

Agent definitions are stored as Markdown files with YAML frontmatter, following Claude Code's format. This enables:
- Reusing existing Claude Code agents without changes
- Human-readable agent definitions
- Rich documentation in the Markdown body

**Example: `agents/researcher.md`**

```markdown
---
name: researcher
description: Research assistant that searches and reads files
tools: List, Read, Search
color: blue
---

# Researcher Agent

You are a research assistant specialized in finding and analyzing information.

## Workflow

1. Use Search to find relevant files
2. Use Read to examine file contents
3. Compile findings into a structured report

## Constraints

- Only read files within allowed paths
- Report findings concisely
- Note any files that couldn't be accessed
```

**Frontmatter Fields**:

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Agent identifier (used in Agent tool calls) |
| `description` | Yes | Short description for LLM tool definition |
| `tools` | Yes | Comma-separated list of available tools |
| `color` | No | Display color (for UI integrations) |

**Tool Mapping**:
The `tools` field lists tools available to this agent. The harness validates that:
- All listed tools are enabled in the TOML config
- Agent cannot use tools not in this list
- Guardrails from TOML apply to all tools globally

### 5.3 Configuration Validation Rules

| Field | Validation | Error Level |
|-------|------------|-------------|
| `ollama.base_url` | Valid URL format | Error |
| `ollama.model` | Non-empty string | Error |
| `tools.*.allowed_paths` | Paths must exist | Warning |
| `tools.*.max_*` | Positive integers | Error |
| `agents.directory` | Directory must exist | Error |
| Agent frontmatter `tools` | Must be subset of enabled tools | Error |
| Agent frontmatter `name` | Non-empty, unique | Error |

### 5.4 Configuration Hot-Reload (Phase 2)

Not included in MVP. Future consideration for development workflow.

---

## 6. MVP Scope

### 6.1 In Scope

- [x] Single TOML configuration file for harness settings
- [x] Agent definitions as Markdown files with frontmatter
- [x] 6 specific tools (List, Read, Write, Update, Search, Agent)
- [x] Guardrails for all tools
- [x] Per-agent tool subsets (defined in frontmatter)
- [x] Context persistence (JSONL format)
- [x] Ollama integration with configurable parameters
- [x] Hierarchical agent spawning
- [x] Recursion depth limits (error on exceed)
- [x] Logging and basic reporting
- [x] Sphinx/ReadTheDocs documentation
- [x] PyPI-ready package structure

### 6.2 Out of Scope (Phase 2)

- [ ] Token optimization / context window management
- [ ] Configuration hot-reload
- [ ] Web UI
- [ ] Multi-user support
- [ ] Agent persistence across sessions
- [ ] Advanced subagent communication (message queues)
- [ ] Tool result caching
- [ ] Parallel tool execution

### 6.3 Technical Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Package name | `yoke` | Available on PyPI, pairs with "clitic" |
| Language | Python 3.10+ | Rich ecosystem, async support, matches clitic |
| Config format | TOML | Human-readable, Python stdlib support |
| Agent definitions | Markdown + frontmatter | Compatible with Claude Code agents |
| Context storage | JSONL | Append-friendly, streamable, resilient |
| HTTP client | httpx | Async, streaming support |
| Logging | structlog | Structured, contextual logging |
| Documentation | Sphinx + ReadTheDocs | Standard Python documentation |

### 6.4 Project Structure (following clitic best practices)

```
yoker/
├── src/
│   └── yoker/
│       ├── __init__.py
│       ├── py.typed                    # PEP 561 marker
│       ├── config/
│       │   ├── __init__.py
│       │   ├── loader.py               # TOML loading
│       │   └── validator.py            # Schema validation
│       ├── context/
│       │   ├── __init__.py
│       │   └── manager.py              # Context persistence (JSONL)
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── base.py                 # Tool interface
│       │   ├── list.py
│       │   ├── read.py
│       │   ├── write.py
│       │   ├── update.py
│       │   ├── search.py
│       │   └── agent.py
│       ├── guardrails/
│       │   ├── __init__.py
│       │   └── enforcer.py
│       ├── agents/
│       │   ├── __init__.py
│       │   ├── definition.py           # Markdown + frontmatter parser
│       │   └── runner.py                # Agent execution
│       ├── backend/
│       │   ├── __init__.py
│       │   └── ollama.py
│       └── main.py                     # CLI entry point
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_config/
│   ├── test_tools/
│   └── test_agents/
├── docs/
│   ├── conf.py
│   ├── index.md
│   ├── installation.md
│   ├── quickstart.md
│   ├── api/
│   └── development/
├── examples/
│   ├── basic/
│   │   ├── yoker.toml
│   │   └── agents/
│   │       └── main.md
│   └── research-workflow/
│       ├── yoker.toml
│       └── agents/
│           ├── main.md
│           ├── researcher.md
│           └── analyst.md
├── pyproject.toml
├── README.md
├── LICENSE
├── .readthedocs.yaml
└── .gitignore
```

### 6.5 pyproject.toml (Template)

Following clitic's structure:

```toml
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "yoker"
version = "0.1.0"
description = "A Python agent harness with configurable tools and guardrails - one who yokes agents together"
readme = "README.md"
license = {text = "MIT"}
requires-python = ">=3.10"
authors = [
  {name = "Christophe VG", email = "contact@christophe.vg"}
]
classifiers = [
  "Development Status :: 3 - Alpha",
  "Intended Audience :: Developers",
  "License :: OSI Approved :: MIT License",
  "Programming Language :: Python :: 3",
  "Programming Language :: Python :: 3.10",
  "Programming Language :: Python :: 3.11",
  "Programming Language :: Python :: 3.12",
  "Topic :: Scientific/Engineering :: Artificial Intelligence",
  "Typing :: Typed",
]
keywords = ["agent", "llm", "ollama", "ai", "harness"]

dependencies = [
  "httpx>=0.25.0",
  "structlog>=23.0.0",
  "pyyaml>=6.0",           # Frontmatter parsing
  "tomli>=2.0;python_version<'3.11'",
]

[project.optional-dependencies]
dev = [
  "pytest>=7.0.0",
  "pytest-cov>=4.0.0",
  "pytest-asyncio>=0.21.0",
  "mypy>=1.0.0",
  "ruff>=0.1.0",
  "build>=1.0.0",
  "twine>=5.0.0",
  "sphinx>=7.0.0",
  "sphinx-rtd-theme>=2.0.0",
  "myst-parser>=2.0.0",
  "tox>=4.0.0",
]

[project.urls]
Homepage = "https://github.com/christophevg/yoker"
Documentation = "https://yoker.readthedocs.io/"
Repository = "https://github.com/christophevg/yoker"
Issues = "https://github.com/christophevg/yoker/issues"

[project.scripts]
yoker = "yoker.main:cli"

[tool.setuptools.packages.find]
where = ["src"]
```

---

## 7. Future Considerations

### 7.1 Phase 2 Features

#### 7.1.1 Token Management

**Research needed**: Context window optimization strategies
- Automatic summarization of old conversation
- Tool result compression
- Priority-based context retention
- Cost tracking and limits

#### 7.1.2 Advanced Communication

- Message queues between agents
- Event broadcasting
- Progress streaming to parent
- Cancellation signals

#### 7.1.3 Tool Extensions

- Bash tool (with strict guardrails)
- HTTP client tool
- Database tool
- Code execution tool (sandboxed)

### 7.2 Scalability Considerations

- Multiple concurrent agents
- Agent pools for parallel work
- Distributed context storage
- Plugin system for custom tools

### 7.3 Security Enhancements

- Sandboxed file operations
- Rate limiting per tool
- Audit trail with tamper-proof logging
- RBAC for multi-user scenarios

---

## 8. Open Questions

### 8.1 Subagent Reporting Mechanism

**Question**: How should subagents report progress and results back to parents?

**Options**:
1. Direct return (synchronous)
2. Message queue (async)
3. Callback-based updates

**Recommendation**: Start with direct return, add callbacks for Phase 2.

### 8.2 Context Pruning Strategy

**Question**: When context exceeds limits, what should be pruned?

**Options**:
1. Oldest-first removal
2. Summarization of old turns
3. Priority-based retention

**Recommendation**: Research in Phase 2, start with simple limits.

### 8.3 Tool Timeout Behavior

**Question**: How should tool timeouts be handled?

**Options**:
1. Return error to agent
2. Retry with backoff
3. Graceful degradation

**Recommendation**: Return error, let agent decide retry strategy.

---

## Appendix A: Error Codes

| Code | Category | Description |
|------|----------|-------------|
| E001 | Config | Invalid TOML syntax |
| E002 | Config | Missing required field |
| E003 | Config | Invalid path in allowed_paths |
| E004 | Config | Agent definition not found |
| E005 | Config | Invalid agent frontmatter |
| E101 | Guardrail | Path not in allowed_paths |
| E102 | Guardrail | File extension not allowed |
| E103 | Guardrail | File size exceeds limit |
| E104 | Guardrail | Max recursion depth exceeded |
| E201 | Tool | Tool not available to agent |
| E202 | Tool | Invalid tool parameters |
| E203 | Tool | Tool execution timeout |
| E301 | Ollama | Connection refused |
| E302 | Ollama | Model not found |
| E303 | Ollama | Context length exceeded |

---

## Appendix B: Example Configurations

### B.1 Minimal Configuration

**yoker.toml**:
```toml
[ollama]
base_url = "http://localhost:11434"
model = "llama3.2"

[tools.list]
allowed_paths = ["."]

[tools.read]
allowed_paths = ["."]

[agents]
directory = "./agents"
```

**agents/main.md**:
```markdown
---
name: main
description: Default assistant
tools: List, Read
---

You are a helpful assistant.
```

### B.2 Full Configuration

See Section 5.1 for complete TOML example and Section 5.2 for agent definition format.

---

## Appendix C: Naming Rationale

**"yoker"** was chosen as the package name because:

1. **Meaning**: One who yokes - the agent noun from "yoke" - a person or device that joins or attaches things together
2. **Etymology**: From PIE *\yeug-* meaning "to join" - same root as yoga (union), conjugate, junction
3. **Pairs with "clitic"**: Both are joining tools (clitic joins words, yoker joins agents)
4. **PyPI Available**: The name is not taken
5. **Agent Noun**: Emphasizes the active role - "the one who yokes" - fitting for an agent harness
6. **Five Letters**: Short, memorable, easy to type

Research details: `research/2026-04-14-agent-harness-naming/`