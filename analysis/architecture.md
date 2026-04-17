# Yoker Architecture Definition

**Document Version**: 1.0
**Date**: 2026-04-17
**Status**: Architecture Definition

## Executive Summary

Yoker is a Python library for building AI agent harnesses with configurable tools, guardrails, and pluggable components. Unlike monolithic coding assistants, Yoker is designed as a **focused library** that can be embedded in applications, extended with plugins, and used recursively to spawn isolated sub-agents.

**Core Design Philosophy**:
- **Pluggable Architecture**: Every major component is an interface with swappable implementations
- **Configuration-Driven**: Single TOML file defines all permissions and behavior upfront
- **Non-Interrupted Workflow**: No runtime prompts for permissions—everything configured ahead
- **Recursive Composition**: Sub-agents are instances of the same library with isolated contexts
- **Library-First**: Core is a library, CLI/TUI is a thin wrapper

---

## 1. High-Level Architecture

### 1.1 Architecture Overview Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Yoker Library                                   │
│                                                                              │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                           CLI/TUI Layer                                 │  │
│  │                    (prompt-toolkit → Clitic)                           │  │
│  │   ┌─────────────┐  ┌──────────────┐  ┌────────────────────────────┐   │  │
│  │   │   Session   │  │   History    │  │   Completion & Hints        │   │  │
│  │   │   Manager   │  │   Manager    │  │                            │   │  │
│  │   └─────────────┘  └──────────────┘  └────────────────────────────┘   │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                      │                                       │
│                                      ▼                                       │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                          Core Engine                                    │  │
│  │  ┌─────────────┐  ┌──────────────┐  ┌────────────────────────────┐    │  │
│  │  │   Agent     │  │   Tool       │  │   Context Manager          │    │  │
│  │  │   Runner    │◄─┤   Dispatcher │◄─┤   (Pluggable)              │    │  │
│  │  │             │  │              │  │                            │    │  │
│  │  └──────┬──────┘  └──────┬───────┘  └────────────────────────────┘    │  │
│  │         │                │                                            │  │
│  │         │                ▼                                            │  │
│  │         │         ┌─────────────────┐                                │  │
│  │         │         │   Permission    │                                │  │
│  │         │         │   Enforcer      │                                │  │
│  │         │         │   (Pluggable)   │                                │  │
│  │         │         └─────────────────┘                                │  │
│  │         │                                                              │  │
│  │         ▼                ▼                                            │  │
│  │  ┌─────────────┐  ┌──────────────────────────────────────────────┐   │  │
│  │  │  Backend    │  │              Tool Implementations              │   │  │
│  │  │  Provider   │  │  (Plugin System)                               │   │  │
│  │  │ (Pluggable) │  │  ┌──────┐ ┌─────┐ ┌──────┐ ┌───────┐ ┌─────┐  │   │  │
│  │  │             │  │  │ List │ │Read │ │Write │ │Update │ │Search│  │   │  │
│  │  │ ┌─────────┐ │  │  └──────┘ └─────┘ └──────┘ └───────┘ └─────┘  │   │  │
│  │  │ │ Ollama  │ │  │  ┌──────┐ ┌─────┐                              │   │  │
│  │  │ │Provider │ │  │  │Agent │ │ Git │  ... (custom plugins)        │   │  │
│  │  │ └─────────┘ │  │  └──────┘ └─────┘                              │   │  │
│  │  └─────────────┘  └──────────────────────────────────────────────┘   │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                      │                                       │
│                                      ▼                                       │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                      Support Services                                  │  │
│  │  ┌─────────────┐  ┌──────────────┐  ┌────────────────────────────┐   │  │
│  │  │ Structured  │  │ Observation  │  │   Statistics Collector      │   │  │
│  │  │ Logging     │  │ Layer        │  │   (Tokens, Time)            │   │  │
│  │  │ (structlog) │  │ (Pluggable)  │  │                            │   │  │
│  │  └─────────────┘  └──────────────┘  └────────────────────────────┘   │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                      Configuration Layer                               │  │
│  │  ┌─────────────────────────────────────────────────────────────────┐  │  │
│  │  │                    TOML Configuration                            │  │  │
│  │  │  [harness] [backend] [context] [permissions] [tools.*] [agents] │  │  │
│  │  └─────────────────────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Core Architecture Pattern

Yoker uses a **Single-Agent Loop with Hierarchical Spawning** pattern:

```
┌─────────────────────────────────────────────────────────────────┐
│                    Parent Agent (depth: 0)                       │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │ Agent Instance                                               │ │
│  │ ┌───────────┐  ┌───────────────┐  ┌───────────────────────┐ │ │
│  │ │ Context   │  │ Tools         │  │ Backend Provider       │ │ │
│  │ │ Manager   │  │ (subset)      │  │ (model-specific)       │ │ │
│  │ └───────────┘  └───────────────┘  └───────────────────────┘ │ │
│  │                                                               │ │
│  │ Agent Tool Call: spawn sub-agent                              │ │
│  │         │                                                     │ │
│  │         ▼                                                     │ │
│  │ ┌─────────────────────────────────────────────────────────────┐│ │
│  │ │            Child Agent (depth: 1)                           ││ │
│  │ │ ┌───────────┐  ┌───────────────┐  ┌─────────────────────┐  ││ │
│  │ │ │ Fresh     │  │ Tools         │  │ Backend Provider     │  ││ │
│  │ │ │ Context   │  │ (subset)      │  │ (can differ)         │  ││ │
│  │ │ └───────────┘  └───────────────┘  └─────────────────────┘  ││ │
│  │ │                                                              ││ │
│  │ │ Agent Tool Call: spawn sub-agent                             ││ │
│  │ │         │                                                    ││ │
│  │ │         ▼                                                    ││ │
│  │ │ ┌──────────────────────────────────────────────────────────┐ ││ │
│  │ │ │       Grandchild Agent (depth: 2)                        │ ││ │
│  │ │ │       (isolated context, may use different model)         │ ││ │
│  │ │ └──────────────────────────────────────────────────────────┘ ││ │
│  │ └─────────────────────────────────────────────────────────────┘│ │
│  └─────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
```

**Key Principles**:
- Each agent is an isolated instance of the library
- Sub-agents get fresh, empty context (no pollution from parent)
- Each agent can use a different model (configurable in agent definition)
- Recursion depth is tracked internally and enforced via errors
- Agent definitions specify available tools (subset of global tool set)

---

## 2. Component Architecture

### 2.1 Pluggable Component System

Every major component follows a plugin pattern:

```python
from abc import ABC, abstractmethod
from typing import TypeVar, Generic

T = TypeVar('T')

class PluginInterface(ABC, Generic[T]):
    """Base interface for all pluggable components."""
    
    @classmethod
    @abstractmethod
    def name(cls) -> str:
        """Unique identifier for this plugin type."""
        pass
    
    @classmethod
    @abstractmethod
    def create(cls, config: dict) -> T:
        """Factory method to create instance from configuration."""
        pass
```

### 2.2 Context Manager (Pluggable)

**Purpose**: Persist and manage conversation context across LLM turns.

**Interface**:
```python
class ContextManager(PluginInterface['ContextManager']):
    """Interface for context management strategies."""
    
    @abstractmethod
    def add_message(self, role: str, content: str, 
                    tool_calls: list | None = None) -> None:
        """Add a message to the context."""
        pass
    
    @abstractmethod
    def add_tool_result(self, tool_call_id: str, result: str) -> None:
        """Add a tool result to the context."""
        pass
    
    @abstractmethod
    def get_context(self) -> list[dict]:
        """Get current context for LLM API call."""
        pass
    
    @abstractmethod
    def save(self) -> None:
        """Persist context to storage."""
        pass
    
    @abstractmethod
    def load(self, session_id: str) -> None:
        """Load context from storage."""
        pass
    
    @abstractmethod
    def get_statistics(self) -> ContextStatistics:
        """Get token count, message count, etc."""
        pass
```

**MVP Implementation**: `BasicPersistenceContextManager`
- Append-only JSONL storage
- No compaction
- Simple statistics (token counting)

**Phase 1 Implementation**: `CompactionContextManager`
- Summarization of old turns
- Priority-based retention
- Tool result compression

**Phase 2 Implementation**: `MultiTierContextManager`
- In-context + Redis + Vector store
- Long-term memory integration

**Decision Rationale**:
| Strategy | Why Include? | Implementation |
|----------|--------------|----------------|
| Basic Persistence | Simple, fast for MVP | JSONL append-only |
| Compaction | Handles long conversations | Summarization, priority retention |
| Multi-Tier | Production-grade memory | External storage integration |

---

### 2.3 Backend Provider (Pluggable)

**Purpose**: Abstract LLM backend communication.

**Interface**:
```python
class BackendProvider(PluginInterface['BackendProvider']):
    """Interface for LLM backend providers."""
    
    @abstractmethod
    async def complete(
        self, 
        messages: list[dict],
        tools: list[dict] | None = None,
        **kwargs
    ) -> AsyncGenerator[StreamEvent, None]:
        """Stream completion from the LLM."""
        pass
    
    @abstractmethod
    def get_model_info(self) -> ModelInfo:
        """Get model capabilities and metadata."""
        pass
    
    @abstractmethod
    def count_tokens(self, text: str) -> int:
        """Count tokens for the given text."""
        pass
```

**MVP Implementation**: `OllamaProvider`
- HTTP API communication
- Streaming support
- Configurable parameters (temperature, top_p, etc.)

**Phase 2 Implementations**:
- `OpenAIProvider` - OpenAI API
- `AnthropicProvider` - Claude API
- `LiteLLMProvider` - Unified interface via LiteLLM

**Per-Agent Model Configuration**:
Each agent can specify its model in the definition frontmatter:

```yaml
---
name: researcher
model: llama3.2:latest  # Agent-specific model
tools: List, Read, Search
---
```

**Decision Rationale**:
| Provider | Why Include? | Priority |
|----------|--------------|----------|
| Ollama | Primary use case, local models | MVP |
| OpenAI | Widely used, good tool calling | Phase 4 |
| Anthropic | Claude models, excellent reasoning | Phase 4 |

---

### 2.4 Permission System

**Purpose**: Enforce boundaries for all tool operations upfront.

**Architecture**:
```
┌─────────────────────────────────────────────────────────────────────────┐
│                          Permission System                                │
│                                                                           │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                    Global Permissions (TOML)                       │  │
│  │  [permissions]                                                       │  │
│  │  filesystem = ["/workspace", "/docs"]                              │  │
│  │  network = "none"                    # blocked by default           │  │
│  │  max_file_size_kb = 500                                            │  │
│  │  recursion_depth = 3                                               │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                      │                                    │
│                                      ▼                                    │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                    Tool-Specific Permissions                       │  │
│  │  [tools.read]                                                       │  │
│  │  blocked_patterns = ["\\.env", "credentials"]                      │  │
│  │  allowed_extensions = [".txt", ".md", ".py", ...]                  │  │
│  │                                                                     │  │
│  │  [tools.git]                                                        │  │
│  │  allowed_commands = ["status", "log", "diff"]                      │  │
│  │  # "commit" requires ask_user permission                            │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                      │                                    │
│                                      ▼                                    │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                 Permission Enforcement Layer                        │  │
│  │  - Single enforcement point for all tools                          │  │
│  │  - Validates before tool execution                                 │  │
│  │  - Logs all permission decisions                                   │  │
│  │  - Raises PermissionViolationError if blocked                      │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                      │                                    │
│                        ┌─────────────┴─────────────┐                    │
│                        ▼                           ▼                    │
│  ┌─────────────────────────────┐  ┌─────────────────────────────────┐   │
│  │    BlockHandler (default)   │  │   Plugin: AskUserHandler        │   │
│  │    - Raise exception        │  │   - Prompt user for confirmation│   │
│  │    - Log violation          │  │   - Requires interactive TUI    │   │
│  │    - No runtime prompt      │  │   - User can allow/block        │   │
│  └─────────────────────────────┘  └─────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

**Permission Modes**:
| Mode | Behavior | Use Case |
|------|----------|----------|
| `block` (default) | Raise exception, log violation | Automated workflows |
| `allow` | Permit operation without prompt | Trusted operations |
| `ask_user` | Prompt user for confirmation | Dangerous operations (git commit) |

**Configuration Example**:
```toml
[permissions]
# Global boundaries
filesystem_paths = ["/workspace", "/docs"]
network_access = "none"

[permissions.handlers.default]
mode = "block"  # Default: raise exception

[permissions.handlers.git_commit]
mode = "ask_user"  # Requires user confirmation
message = "Commit changes to repository?"

[tools.git]
allowed_commands = ["status", "log", "diff", "commit"]
requires_permission = ["commit"]  # These need explicit permission
```

**Decision Rationale**:
| Feature | Why Include? | Priority |
|---------|--------------|----------|
| Static Rules | Non-interrupted workflow, configurable upfront | MVP |
| Block/Allow Modes | Basic permission handling | MVP |
| Ask User Plugin | Safe handling of dangerous operations | Phase 1 |
| Permission Plugins | Extensibility for custom handlers | Phase 1 |

---

### 2.5 Tool System (Plugin Architecture)

**Purpose**: Define and execute guarded operations.

**Tool Interface**:
```python
class Tool(PluginInterface['Tool']):
    """Interface for all tools."""
    
    @abstractmethod
    def get_schema(self) -> dict:
        """Return JSON Schema for LLM tool definition."""
        pass
    
    @abstractmethod
    def get_permissions(self) -> list[str]:
        """Return required permissions."""
        pass
    
    @abstractmethod
    async def execute(
        self, 
        params: dict, 
        context: ExecutionContext
    ) -> ToolResult:
        """Execute the tool with validated parameters."""
        pass
    
    def validate_permissions(
        self, 
        params: dict, 
        permissions: PermissionSet
    ) -> ValidationResult:
        """Check if operation is permitted."""
        # Default: check against global permissions
        pass
```

**MVP Core Tools**:

| Tool | Purpose | Key Permissions |
|------|---------|------------------|
| List | List directory contents | `filesystem_paths`, `max_depth`, `max_entries` |
| Read | Read file contents | `filesystem_paths`, `allowed_extensions`, `max_size_kb` |
| Write | Create new files | `filesystem_paths`, `allow_overwrite`, `max_size_kb` |
| Update | Edit existing files | `filesystem_paths`, `require_exact_match` |
| Search | Search for patterns | `filesystem_paths`, `max_results`, `timeout_ms` |
| Agent | Spawn sub-agents | `recursion_depth`, `timeout_seconds` |

**Phase 1 Tools**:

| Tool | Purpose | Key Permissions |
|------|---------|------------------|
| Git | Version control operations | `allowed_commands`, `ask_user_for` |

**Phase 2 Tools**:

| Tool | Purpose | Key Permissions |
|------|---------|------------------|
| HTTP | Make HTTP requests | `allowed_domains`, `timeout_seconds` |

**Plugin Loading**:
```python
# Configuration
[tools.custom_analyzer]
module = "my_package.tools"
class = "CodeAnalyzer"
enabled = true

# The tool is loaded and registered automatically
```

**Decision Rationale**:
| Tool | Why Include? | Priority |
|------|--------------|----------|
| Core 6 (List, Read, Write, Update, Search, Agent) | Essential file operations + sub-agent spawning | MVP |
| Git | Version control integration, commit workflow | Phase 1 |
| HTTP | External API access, web resources | Phase 2 |
| Plugin System | Extensibility for custom tools | MVP |

---

### 2.6 Observation Layer (Pluggable)

**Purpose**: Process tool outputs before returning to the LLM.

**Interface**:
```python
class ObservationLayer(PluginInterface['ObservationLayer']):
    """Interface for processing tool outputs."""
    
    @abstractmethod
    def process_result(
        self, 
        tool_name: str,
        result: ToolResult,
        context: ExecutionContext
    ) -> ProcessedResult:
        """Process and potentially enhance tool result."""
        pass
    
    @abstractmethod
    def aggregate_results(
        self, 
        results: list[ProcessedResult]
    ) -> AggregatedResult:
        """Combine multiple tool results intelligently."""
        pass
```

**MVP Implementation**: `PassThroughObservationLayer`
- Returns results directly without processing
- Simple, predictable behavior

**Phase 1 Implementations**:
- `ErrorParsingLayer` - Parse and structure error messages

**Phase 2 Implementations**:
- `DiffSummaryLayer` - Summarize git diffs
- `TestResultLayer` - Parse test output and classify results

**Decision Rationale**:
| Strategy | Why Include? | Priority |
|----------|--------------|----------|
| PassThrough | Simple, no transformation | MVP |
| Error Parsing | Better error feedback to LLM | Phase 1 |
| Diff Summary | Concise code change representation | Phase 2 |

---

### 2.7 Agent Runner

**Purpose**: Orchestrate the agent loop (observe → plan → act → reflect).

**Implementation**:
```python
class AgentRunner:
    """Orchestrates agent execution loop."""
    
    def __init__(
        self,
        agent_definition: AgentDefinition,
        backend: BackendProvider,
        context_manager: ContextManager,
        tool_dispatcher: ToolDispatcher,
        permission_enforcer: PermissionEnforcer,
        observation_layer: ObservationLayer,
    ):
        self.agent = agent_definition
        self.backend = backend
        self.context = context_manager
        self.tools = tool_dispatcher
        self.permissions = permission_enforcer
        self.observer = observation_layer
    
    async def run(self, prompt: str) -> AgentResult:
        """Execute agent loop until completion."""
        self.context.add_message("user", prompt)
        
        while not self._is_complete():
            # Build context for LLM
            messages = self.context.get_context()
            
            # Call LLM
            async for event in self.backend.complete(messages, self.tools.get_schemas()):
                if event.type == "text":
                    yield TextEvent(event.content)
                elif event.type == "tool_call":
                    # Execute tool
                    result = await self._execute_tool(event.tool_call)
                    self.context.add_tool_result(event.tool_call.id, result)
                    yield ToolEvent(event.tool_call.name, result)
            
            # Check for completion
            if self._should_stop():
                break
        
        return self._build_result()
    
    async def _execute_tool(self, tool_call: ToolCall) -> str:
        """Execute a tool call with permission checking."""
        # Check permissions
        self.permissions.validate(tool_call.name, tool_call.parameters)
        
        # Execute tool
        result = await self.tools.execute(tool_call.name, tool_call.parameters)
        
        # Process through observation layer
        processed = self.observer.process_result(tool_call.name, result, self.context)
        
        return processed.content
```

---

### 2.8 Statistics Collector

**Purpose**: Track token usage and timing for each session.

**Implementation**:
```python
@dataclass
class SessionStatistics:
    """Statistics for an agent session."""
    
    # Token tracking
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    tokens_per_turn: list[TurnTokens] = field(default_factory=list)
    
    # Time tracking
    start_time: datetime = field(default_factory=datetime.now)
    llm_time_ms: int = 0
    tool_time_ms: int = 0
    
    # Tool tracking
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    
    def record_turn(self, turn: TurnRecord) -> None:
        """Record statistics for a turn."""
        self.total_input_tokens += turn.input_tokens
        self.total_output_tokens += turn.output_tokens
        self.tokens_per_turn.append(TurnTokens(
            input=turn.input_tokens,
            output=turn.output_tokens
        ))
        self.llm_time_ms += turn.llm_time_ms
        self.tool_time_ms += turn.tool_time_ms
```

**Decision Rationale**:
| Feature | Why Include? | Priority |
|---------|--------------|----------|
| Token Counting | Statistics, debugging, optimization | MVP |
| Time Tracking | Performance analysis, debugging | MVP |
| Cost Calculation | Not needed (local models via Ollama) | N/A |

---

## 3. Configuration Architecture

### 3.1 TOML Configuration Schema

```toml
# yoker.toml - Main harness configuration

[harness]
name = "my-yoke"
version = "1.0"
log_level = "INFO"

# Backend configuration
[backend]
provider = "ollama"  # MVP: only "ollama"

[backend.ollama]
base_url = "http://localhost:11434"
model = "llama3.2:latest"
timeout_seconds = 60

[backend.ollama.parameters]
temperature = 0.7
top_p = 0.9
top_k = 40
num_ctx = 4096

# Context management
[context]
manager = "basic_persistence"  # basic_persistence | compaction | multi_tier
storage_path = "./context"
session_id = "auto"  # or specific UUID
persist_after_turn = true

# Global permissions
[permissions]
filesystem_paths = ["/workspace", "/docs"]
network_access = "none"
max_file_size_kb = 500
max_recursion_depth = 3

[permissions.handlers.default]
mode = "block"

[permissions.handlers.git_commit]
mode = "ask_user"
message = "Commit changes to repository?"

# Tool definitions
[tools.list]
enabled = true
max_depth = 5
max_entries = 2000

[tools.read]
enabled = true
allowed_extensions = [".txt", ".md", ".json", ".yaml", ".toml", ".py", ".js"]
blocked_patterns = ["\\.env", "credentials", "secret"]

[tools.write]
enabled = true
allow_overwrite = false
max_size_kb = 1000
blocked_extensions = [".exe", ".sh", ".bat"]

[tools.update]
enabled = true
require_exact_match = true
max_diff_size_kb = 100

[tools.search]
enabled = true
max_regex_complexity = "medium"
max_results = 500
timeout_ms = 10000

[tools.agent]
enabled = true
max_recursion_depth = 3
timeout_seconds = 300

[tools.git]
enabled = true
allowed_commands = ["status", "log", "diff", "commit"]
requires_permission = ["commit"]

# Agent definitions
[agents]
directory = "./agents"
default_type = "main"

# Logging configuration
[logging]
format = "json"  # json | text
include_tool_calls = true
include_permission_checks = true
```

### 3.2 Agent Definition Format

```yaml
---
# Required fields
name: researcher
description: Research assistant that searches and reads files

# Model configuration (agent-specific)
model: llama3.2:latest  # Can differ from default

# Tool subset
tools:
  - List
  - Read
  - Search

# Agent-specific permissions (subset of global)
permissions:
  filesystem_paths: ["/workspace"]  # More restrictive than global

# Metadata
color: blue
---

# System Prompt (Markdown body)

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

---

## 4. Roadmap

### 4.1 Phase 0: Foundation (MVP)

**Goal**: Minimal viable harness with core functionality.

**Scope**:
- ✅ Single-agent loop with sequential tool execution
- ✅ Pluggable architecture for all major components
- ✅ Basic context persistence (JSONL)
- ✅ Ollama backend provider
- ✅ Static permission rules (block/allow modes)
- ✅ Core 6 tools (List, Read, Write, Update, Search, Agent)
- ✅ Pass-through observation layer
- ✅ Token and time statistics
- ✅ Structured logging (structlog)
- ✅ Simple TUI (prompt-toolkit)
- ✅ Standard testing (pytest)

**Key Files**:
```
src/yoker/
├── __init__.py
├── config/
│   ├── loader.py          # TOML loading
│   └── validator.py       # Schema validation
├── context/
│   ├── interface.py       # ContextManager ABC
│   └── basic.py           # BasicPersistence implementation
├── backend/
│   ├── interface.py       # BackendProvider ABC
│   └── ollama.py          # Ollama implementation
├── permissions/
│   ├── enforcer.py        # Permission enforcement
│   └── handlers.py        # Block/Allow handlers
├── tools/
│   ├── interface.py       # Tool ABC
│   ├── registry.py        # Tool registry
│   ├── list.py
│   ├── read.py
│   ├── write.py
│   ├── update.py
│   ├── search.py
│   └── agent.py
├── observation/
│   ├── interface.py       # ObservationLayer ABC
│   └── passthrough.py     # PassThrough implementation
├── agents/
│   ├── definition.py      # Markdown + frontmatter parser
│   └── runner.py          # Agent execution loop
├── statistics.py          # Token and time tracking
├── logging.py             # Structured logging setup
└── main.py                # CLI entry point
```

**Success Criteria**:
- Can start agent with TUI
- Agent can list/read/write/update/search files
- Agent can spawn sub-agents (with recursion limit)
- All operations respect permission boundaries
- Context persists across sessions
- Statistics are tracked and reported

---

### 4.2 Phase 1: Essential Enhancements

**Goal**: Improve usability and add git integration.

**Scope**:
- ✅ Git tool (status, log, diff, commit)
- ✅ Project + Agent guides (CLAUDE.md style)
- ✅ Compaction context manager
- ✅ Parallel read-only tool execution
- ✅ Ask-user permission handler
- ✅ Error parsing observation layer

**New Components**:
```
src/yoker/
├── tools/
│   └── git.py             # Git operations
├── context/
│   └── compaction.py      # Summarization context manager
├── permissions/
│   └── ask_user.py        # Interactive permission handler
├── observation/
│   └── error_parsing.py   # Error message parsing
└── guides/
    ├── project.py         # CLAUDE.md loading
    └── agent.py           # Guide injection
```

---

### 4.3 Phase 2: Advanced Features

**Goal**: Production-ready with advanced capabilities.

**Scope**:
- ✅ Multi-tier context manager (Redis + vector store)
- ✅ Diff summary observation layer
- ✅ Test result observation layer
- ✅ Agent test harness (mock LLM responses)
- ✅ Full observability (metrics, traces)

**New Components**:
```
src/yoker/
├── context/
│   └── multi_tier.py      # Redis + vector store
├── observation/
│   ├── diff_summary.py
│   └── test_result.py
├── testing/
│   ├── mock_backend.py
│   └── fixtures.py
└── observability/
    ├── metrics.py
    └── traces.py
```

---

### 4.4 Phase 3: Clitic Integration

**Goal**: Rich TUI experience with Clitic framework.

**Scope**:
- ✅ Clitic TUI framework integration
- ✅ Multi-pane interface
- ✅ Progress indicators
- ✅ Session management UI
- ✅ Real-time log viewer

---

### 4.5 Phase 4: Extended Backend Support

**Goal**: Support multiple LLM backends.

**Scope**:
- ✅ OpenAI backend provider
- ✅ Anthropic backend provider
- ✅ Backend provider plugin system
- ✅ Model capabilities detection
- ✅ Provider-specific tool calling formats

**New Components**:
```
src/yoker/
├── backend/
│   ├── openai.py          # OpenAI implementation
│   ├── anthropic.py       # Claude implementation
│   └── capabilities.py    # Model capability detection
```

---

## 5. Component Decision Summary

### 5.1 What We Include and Why

| Component | Decision | Rationale |
|-----------|----------|-----------|
| **Execution Environment** | Host execution (no sandbox) | Path-based restrictions sufficient for library use case, sandboxing out of scope |
| **Context Management** | Pluggable, Basic first | Essential for all sessions, pluggable for future optimization |
| **Backend Provider** | Pluggable, Ollama first | Must support different models per agent, Ollama for local development |
| **Permission System** | Static rules, pluggable handlers | Non-interrupted workflow, extensible for user prompts |
| **Tool Execution** | Sequential (MVP) | Simpler, no race conditions, parallel reads in Phase 1 |
| **Observation Layer** | Pass-through (MVP) | Direct results, pluggable for intelligent processing later |
| **Git Integration** | Git tool with permissions | Important for coding workflows, commit needs permission |
| **Guides System** | Agent-only (MVP), Project+Agent (Phase 1) | Essential for context, project-level guides add project awareness |
| **Cost Tracking** | Token + time statistics | Statistics without cost calculation (local models) |
| **Plugin System** | Python-level tool plugins | Extensibility, custom tools |
| **CLI/TUI** | Simple TUI → Clitic | Start simple, upgrade to full framework |

### 5.2 What We Exclude and Why

| Component | Decision | Rationale |
|-----------|----------|-----------|
| **OS Sandbox** | Out of scope | Complexity, platform-specific, path-based permissions sufficient for library use case |
| **Container Isolation** | Out of scope | Heavy setup, overkill for library use case |
| **Cost Calculation** | N/A | Local models (Ollama) have no API cost |
| **Model Routing** | Future | Requires multi-backend support, model intelligence detection |
| **Interactive Prompts for Permissions** | Phase 1 | MVP focuses on non-interrupted workflow |
| **Lifecycle Hooks** | Future | Overkill for library, plugins provide extensibility |
| **Agent Test Harness** | Phase 2 | Standard testing sufficient for MVP |

---

## 6. Key Design Decisions

### 6.1 Pluggable Architecture

**Decision**: Every major component is an interface with swappable implementations.

**Rationale**:
- Future-proof: can add new backends, context managers, observation layers
- Testable: can mock components easily
- Configurable: users can choose implementations via config

**Trade-off**:
- + Flexibility and extensibility
- + Future-proof
- - More initial complexity
- - Need to design good interfaces

### 6.2 Per-Agent Model Configuration

**Decision**: Each agent can specify its model, different from the default.

**Rationale**:
- Sub-agents may need different capabilities (e.g., fast model for simple tasks)
- Recursive spawning requires isolated configuration
- Aligns with "library composition" philosophy

**Implementation**:
- Agent definition frontmatter includes `model` field
- AgentRunner receives backend provider instance configured for that model
- Sub-agent spawning creates new backend instance if model differs

### 6.3 Static Permission System

**Decision**: All permissions defined upfront in configuration, no runtime prompts by default.

**Rationale**:
- Non-interrupted workflow: agent can run autonomously
- Predictable: behavior determined by config
- Secure: boundaries defined before execution

**Trade-off**:
- + Autonomous operation
- + Predictable behavior
- + Simpler implementation
- - Less flexible than interactive prompts
- - Requires careful upfront configuration

### 6.4 Sequential Tool Execution

**Decision**: Tools execute one at a time, in order.

**Rationale**:
- Simpler implementation
- No race conditions
- Easier to debug
- Predictable state

**Trade-off**:
- + Simplicity
- + No race conditions
- + Predictable
- - Slower than parallel execution

### 6.5 Library-First Design

**Decision**: Core is a library, CLI/TUI is a thin wrapper.

**Rationale**:
- Embeddable in other applications
- Testable independently
- Clear separation of concerns
- Can be used as daemon/automation engine

**Trade-off**:
- + Reusable
- + Testable
- + Embeddable
- - More complex than monolithic tool

---

## 7. Open Questions

### 7.1 Sub-Agent Result Streaming

**Question**: Should sub-agents stream partial results to parent, or only final result?

**Options**:
1. **Final result only** (MVP) - Simpler, matches current design
2. **Progress callbacks** - Sub-agent calls callback with progress
3. **Streaming** - Sub-agent streams events to parent

**Recommendation**: Start with final result only (MVP), add callbacks in Phase 1.

### 7.2 Context Isolation Granularity

**Question**: How much context should sub-agents receive from parent?

**Options**:
1. **Clean context** (current design) - Only initial prompt
2. **Inherited context** - Copy parent context, can filter
3. **Shared context** - Reference parent context, read-only

**Recommendation**: Keep clean context (MVP). If needed, parent can pass relevant info in prompt.

### 7.3 Tool Result Size Limits

**Question**: How to handle large tool results (big files, long searches)?

**Options**:
1. **Truncate** - Cut off at limit, inform agent
2. **Paginate** - Return chunks, agent requests more
3. **Compress** - Summarize or compress results

**Recommendation**: Truncate with clear message (MVP). Add pagination in Phase 1 for specific tools.

---

## 8. Success Metrics

### 8.1 MVP Success Criteria

| Metric | Target |
|--------|--------|
| Test coverage | >80% |
| Core tool tests | 100% pass |
| Context persistence | JSONL survives restart |
| Agent spawning | Recursion limit enforced |
| Permission enforcement | All violations blocked |
| Documentation | Sphinx build passes |

### 8.2 Phase 1 Success Criteria

| Metric | Target |
|--------|--------|
| Git tool tests | 100% pass |
| Compaction | Context fits in 128KB window |
| Parallel reads | 2x speedup for 5+ concurrent reads |
| Ask-user handler | Interactive permission prompts work |

### 8.3 Phase 2 Success Criteria

| Metric | Target |
|--------|--------|
| Multi-tier context | Redis integration works |
| Test harness | Mock LLM responses work |
| Observability | Metrics and traces collected |

### 8.4 Phase 4 Success Criteria

| Metric | Target |
|--------|--------|
| OpenAI backend | Tests pass, tool calling works |
| Anthropic backend | Tests pass, tool calling works |
| Model detection | Capabilities correctly identified |

---

## Appendix A: Comparison with Existing Harnesses

| Feature | Yoker | Claude Code | Aider | Cursor | Windsurf |
|---------|-------|-------------|-------|--------|----------|
| **Architecture** | Library | CLI App | CLI App | IDE | IDE |
| **Backend** | Pluggable | Anthropic | Model-agnostic | Frontier models | Codeium |
| **Context** | Pluggable | 5-layer compaction | History summarization | 4-tier memory | Session-scoped |
| **Permissions** | Static + plugins | 4-layer cascading | Git-native | IDE-integrated | IDE-integrated |
| **Tools** | Plugin system | 50+ built-in | Git + file ops | IDE-integrated | IDE-integrated |
| **Sub-agents** | Hierarchical spawning | Subagent tool | No | Up to 8 parallel | Cascade agent |
| **Sandbox** | None (out of scope) | Seatbelt/bwrap | None | Custom VM | IDE sandbox |
| **Git Integration** | Phase 1 | Yes | Native | Worktrees | IDE integration |
| **TUI** | Clitic (Phase 3) | Ink/React | Terminal | IDE | IDE |

**Key Differentiators**:
- Yoker is a **library**, not a CLI or IDE
- Yoker has **pluggable everything** (context, backend, permissions, observation)
- Yoker uses **static permissions** for non-interrupted workflow
- Yoker supports **per-agent model configuration**
- Yoker is designed for **recursive composition** (sub-agents are instances of same library)

---

## Appendix B: File Structure

```
yoker/
├── src/
│   └── yoker/
│       ├── __init__.py              # Public API exports
│       ├── py.typed                 # PEP 561 marker
│       ├── config/
│       │   ├── __init__.py
│       │   ├── loader.py            # TOML loading
│       │   └── validator.py         # Schema validation
│       ├── context/
│       │   ├── __init__.py
│       │   ├── interface.py         # ContextManager ABC
│       │   ├── basic.py             # BasicPersistence implementation
│       │   └── compaction.py        # Compaction implementation (Phase 1)
│       ├── backend/
│       │   ├── __init__.py
│       │   ├── interface.py         # BackendProvider ABC
│       │   ├── ollama.py            # Ollama implementation
│       │   ├── openai.py            # OpenAI implementation (Phase 4)
│       │   └── anthropic.py         # Anthropic implementation (Phase 4)
│       ├── permissions/
│       │   ├── __init__.py
│       │   ├── enforcer.py          # Permission enforcement
│       │   ├── handlers.py          # Block/Allow handlers
│       │   └── ask_user.py          # AskUser handler (Phase 1)
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── interface.py         # Tool ABC
│       │   ├── registry.py          # Tool registry
│       │   ├── list.py
│       │   ├── read.py
│       │   ├── write.py
│       │   ├── update.py
│       │   ├── search.py
│       │   ├── agent.py
│       │   └── git.py               # Git tool (Phase 1)
│       ├── observation/
│       │   ├── __init__.py
│       │   ├── interface.py         # ObservationLayer ABC
│       │   ├── passthrough.py       # PassThrough implementation
│       │   ├── error_parsing.py     # Error parsing (Phase 1)
│       │   └── diff_summary.py      # Diff summary (Phase 2)
│       ├── agents/
│       │   ├── __init__.py
│       │   ├── definition.py        # Markdown + frontmatter parser
│       │   └── runner.py            # Agent execution loop
│       ├── guides/
│       │   ├── __init__.py
│       │   ├── project.py           # CLAUDE.md loading (Phase 1)
│       │   └── agent.py             # Guide injection (Phase 1)
│       ├── statistics.py            # Token and time tracking
│       ├── logging.py               # Structured logging setup
│       └── main.py                  # CLI entry point
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_config/
│   ├── test_context/
│   ├── test_backend/
│   ├── test_permissions/
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

---

## Appendix C: Configuration Examples

### C.1 Minimal Configuration

```toml
# yoker.toml - Minimal configuration

[backend]
provider = "ollama"

[backend.ollama]
base_url = "http://localhost:11434"
model = "llama3.2:latest"

[context]
manager = "basic_persistence"
storage_path = "./context"

[permissions]
filesystem_paths = ["."]

[tools.list]
enabled = true

[tools.read]
enabled = true

[agents]
directory = "./agents"
```

### C.2 Full Configuration

See Section 3.1 for complete TOML schema.

---

## Appendix D: Agent Definition Examples

### D.1 Researcher Agent

```yaml
---
name: researcher
description: Research assistant that searches and reads files
model: llama3.2:latest
tools:
  - List
  - Read
  - Search
permissions:
  filesystem_paths: ["/workspace"]
color: blue
---

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

### D.2 Writer Agent

```yaml
---
name: writer
description: Agent that writes and updates files
model: llama3.2:latest
tools:
  - List
  - Read
  - Write
  - Update
permissions:
  filesystem_paths: ["/workspace/output"]
color: green
---

You are a writing assistant that creates and modifies files.

## Workflow

1. Use Read to understand existing content
2. Use Write to create new files
3. Use Update to modify existing files

## Constraints

- Only write to output directory
- Check for existing files before writing
- Follow project conventions
```