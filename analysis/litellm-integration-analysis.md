# litellm Integration Analysis

**Status**: Analysis Complete
**Date**: 2026-06-29
**Decision Impact**: One-way street (full adoption)

## Executive Summary

This document analyzes the integration of litellm as Yoker's backend abstraction layer. The goal is **complete adoption** - leveraging litellm's capabilities to their fullest extent rather than creating additional abstraction layers.

**Key Recommendation**: Proceed with integration. litellm provides comprehensive coverage for Yoker's current providers (Ollama, OpenAI, Anthropic) with normalized APIs, streaming support, and tool calling. However, web tools will require a special migration strategy.

---

## 1. Configuration Integration

### 1.1 Integration Approach

litellm uses a model-prefix pattern (`provider/model`) instead of Yoker's tagged union approach. The mapping is:

**Current Yoker Config:**
```python
@dataclass(frozen=True)
class BackendConfig:
  provider: str = "ollama"
  ollama: OllamaConfig = field(default_factory=OllamaConfig)
  openai: OpenAIConfig | None = None
  anthropic: AnthropicConfig | None = None
```

**litellm Pattern:**
```python
# litellm determines provider from model string prefix
response = completion(
  model="ollama/llama3.2:latest",
  model="openai/gpt-4o",
  model="anthropic/claude-3-5-sonnet-20241022"
)
```

**Migration Strategy:**
1. Keep Yoker's `Config` dataclass structure (Clevis-based CLI args)
2. Add a `LitellmBackendConfig` that maps Yoker config to litellm parameters
3. Use `api_base` parameter for custom base URLs (e.g., Ollama local server)
4. Pass provider-specific parameters via kwargs

### 1.2 Configuration Mapping

#### API Keys
**Yoker**: Stored in config with `metadata={'cli': False}` for security
**litellm**: Supports both environment variables AND explicit parameter passing

```python
# Yoker config
config = BackendConfig(
  provider="ollama",
  ollama=OllamaConfig(api_key="secret", base_url="http://localhost:11434")
)

# litellm integration
def create_litellm_client(config: Config) -> None:
  # Option 1: Set environment variable
  os.environ["OLLAMA_API_KEY"] = config.backend.ollama.api_key

  # Option 2: Pass explicitly (recommended for Yoker)
  litellm.completion(
    model=f"ollama/{config.backend.ollama.model}",
    api_key=config.backend.ollama.api_key,
    api_base=config.backend.ollama.base_url,
    ...
  )
```

**Recommendation**: Keep Yoker's config structure, inject into litellm calls explicitly. This maintains Yoker's security model and Clevis CLI generation.

#### Provider-Specific Parameters

**Ollama (`num_ctx`):**
```python
# Yoker
OllamaParameters(num_ctx=4096, temperature=0.7, top_p=0.9, top_k=40)

# litellm
litellm.completion(
  model="ollama/llama3.2:latest",
  num_ctx=4096,  # litellm passes through to Ollama
  temperature=0.7,
  top_p=0.9,
  top_k=40,
)
```

**Anthropic (`budget_tokens`):**
```python
# Yoker
AnthropicParameters(budget_tokens=1024)

# litellm
litellm.completion(
  model="anthropic/claude-3-5-sonnet-20241022",
  budget_tokens=1024,  # passed through
)
```

**litellm Advantage**: Provider-specific parameters are passed through automatically. The `OllamaChatConfig` class in litellm already handles `num_ctx`, `mirostat`, and other Ollama-specific params.

#### Base URL / Trust Boundary

**Yoker**: Interactive warning/confirmation for custom `base_url`
**litellm**: Supports `api_base` parameter

```python
# Yoker's current trust boundary check
validate_base_url_trust(config.backend, interactive=True)

# litellm integration
litellm.completion(
  model="ollama/llama3.2:latest",
  api_base=config.backend.ollama.base_url,  # custom URL
)
```

**Migration**: Keep Yoker's trust boundary validation. Apply it before creating litellm calls.

### 1.3 Environment Variables

litellm reads from environment variables:
- `OLLAMA_API_KEY` → `api_key` parameter
- `OPENAI_API_KEY` → OpenAI authentication
- `ANTHROPIC_API_KEY` → Anthropic authentication

**Yoker's TOML config can map to env vars:**
```toml
[backend.ollama]
api_key = "${OLLAMA_API_KEY}"  # Clevis interpolation
```

**Integration Strategy**: Yoker's config system (Clevis) already supports environment variable interpolation. Keep this pattern, let litellm read from environment OR inject explicitly from config.

### 1.4 Code Changes

**Files Affected:**
- `/src/yoker/config/__init__.py` - Add litellm parameter mapping utilities
- `/src/yoker/backends/factory.py` - Replace backend factory with litellm client creation

**New Files:**
- `/src/yoker/backends/litellm_config.py` - Map Yoker config to litellm parameters

**Migration Steps:**
1. Create `LitellmConfigMapper` class to convert Yoker config to litellm kwargs
2. Update `create_backend()` factory to return `LitellmBackend` instance
3. Keep Yoker's `BackendConfig` dataclass for CLI args and validation
4. Add parameter pass-through logic for provider-specific options

---

## 2. Agent Integration

### 2.1 Streaming Interface Mapping

**Yoker's Current Interface:**
```python
class ModelBackend(Protocol):
  def chat_stream(
    self,
    *,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    think: bool = False,
    **kwargs: Any,
  ) -> AsyncIterator[ChatChunk]:
```

**litellm's Interface:**
```python
async def acompletion(
  model: str,
  messages: List = [],
  tools: Optional[List] = None,
  stream: bool = False,
  **kwargs
) -> AsyncIterator[ModelResponseStream]:
```

**Key Difference**: litellm returns `ModelResponseStream` objects, not `ChatChunk`.

### 2.2 Chunk Translation Strategy

**litellm Stream Format:**
```python
async for chunk in litellm.acompletion(model="ollama/llama3.2", messages=[...], stream=True):
  # chunk is ModelResponseStream with:
  # - chunk.choices[0].delta.content (text delta)
  # - chunk.choices[0].delta.tool_calls (tool call deltas)
  # - chunk.usage (usage stats)
```

**Yoker's ChatChunk Format:**
```python
@dataclass(frozen=True)
class ChatChunk:
  event: ChatChunkEvent  # CONTENT_START, CONTENT_DELTA, etc.
  index: int | None
  text: str | None
  tool_call: ToolCallDelta | None
  usage: UsageStats | None
```

**Translation Layer:**
```python
class LitellmBackend(ModelBackend):
  async def chat_stream(self, model: str, messages: list, tools: list | None, think: bool, **kwargs) -> AsyncIterator[ChatChunk]:
    # Convert Yoker model to litellm format
    litellm_model = self._to_litellm_model(model)

    # Map Yoker params to litellm params
    litellm_kwargs = self._map_params(think=think, **kwargs)

    async for chunk in litellm.acompletion(
      model=litellm_model,
      messages=messages,
      tools=tools,
      stream=True,
      **litellm_kwargs
    ):
      # Translate litellm ModelResponseStream to Yoker ChatChunk
      for yoker_chunk in self._translate_chunk(chunk):
        yield yoker_chunk
```

### 2.3 Event Synthesis

**Challenge**: litellm doesn't emit explicit `START`/`STOP` events. Yoker requires:
- `CONTENT_START` before first delta
- `CONTENT_DELTA` for each text chunk
- `CONTENT_STOP` when content ends
- `THINKING_START/DELTA/STOP` for reasoning blocks
- `TOOL_CALL_START/DELTA/STOP` for tool calls

**Solution**: Maintain state in `LitellmBackend` to synthesize events:

```python
def _translate_chunk(self, chunk: ModelResponseStream) -> Iterator[ChatChunk]:
  """Translate litellm stream chunk to Yoker ChatChunk events."""

  # State tracking (per-stream instance)
  in_content = False
  in_thinking = False
  in_tool_call = {}

  delta = chunk.choices[0].delta

  # Handle thinking/reasoning (for Anthropic/o-series)
  if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
    if not in_thinking:
      yield ChatChunk(event=ChatChunkEvent.THINKING_START, index=0)
      in_thinking = True
    yield ChatChunk(event=ChatChunkEvent.THINKING_DELTA, text=delta.reasoning_content)

  # Handle content
  if delta.content:
    if in_thinking:
      yield ChatChunk(event=ChatChunkEvent.THINKING_STOP, index=0)
      in_thinking = False
    if not in_content:
      yield ChatChunk(event=ChatChunkEvent.CONTENT_START, index=0)
      in_content = True
    yield ChatChunk(event=ChatChunkEvent.CONTENT_DELTA, text=delta.content)

  # Handle tool calls
  if delta.tool_calls:
    for tc in delta.tool_calls:
      if tc.index not in in_tool_call:
        yield ChatChunk(
          event=ChatChunkEvent.TOOL_CALL_START,
          index=tc.index,
          tool_call=ToolCallDelta(index=tc.index, id=tc.id, name=tc.function.name if tc.function else None)
        )
        in_tool_call[tc.index] = True

      if tc.function and tc.function.arguments:
        yield ChatChunk(
          event=ChatChunkEvent.TOOL_CALL_DELTA,
          index=tc.index,
          tool_call=ToolCallDelta(index=tc.index, arguments_delta=tc.function.arguments)
        )

  # Handle usage (final chunk)
  if hasattr(chunk, 'usage') and chunk.usage:
    if in_content:
      yield ChatChunk(event=ChatChunkEvent.CONTENT_STOP, index=0)
    if in_thinking:
      yield ChatChunk(event=ChatChunkEvent.THINKING_STOP, index=0)
    yield ChatChunk(
      event=ChatChunkEvent.USAGE,
      usage=UsageStats(
        input_tokens=chunk.usage.prompt_tokens,
        output_tokens=chunk.usage.completion_tokens
      )
    )
    yield ChatChunk(event=ChatChunkEvent.DONE)
```

### 2.4 Subagent Spawning

**Yoker's Current Approach:**
```python
def with_model(backend: BackendConfig, model: str) -> BackendConfig:
  """Create a copy of backend config with overridden model."""
  if backend.provider == "ollama" and backend.ollama:
    new_ollama = replace(backend.ollama, model=model)
    return replace(backend, ollama=new_ollama)
  # ... similar for other providers
```

**litellm Integration:**
```python
# Much simpler - just change the model string
def with_model(backend: BackendConfig, model: str) -> str:
  """Return litellm model string with new model."""
  return f"{backend.provider}/{model}"
```

**Benefit**: litellm eliminates the need for provider-specific config manipulation for model changes.

### 2.5 Code Changes

**Files Affected:**
- `/src/yoker/backends/litellm_backend.py` - New backend implementation
- `/src/yoker/backends/protocol.py` - Keep Protocol, update implementations
- `/src/yoker/agent/_processing.py` - No changes (already uses ChatChunk)

**Migration Steps:**
1. Create `LitellmBackend` class implementing `ModelBackend` Protocol
2. Implement `_translate_chunk()` for stream translation
3. Handle provider-specific thinking modes (Anthropic/o-series)
4. Replace `OllamaBackend`, `OpenAIBackend`, `AnthropicBackend` with single `LitellmBackend`
5. Delete provider-specific backend files (ollama.py, openai.py)

---

## 3. Tool Calling Integration

### 3.1 Tool Schema Normalization

**litellm's Approach:**
litellm accepts OpenAI-format tool schemas and translates to provider-specific formats automatically:

```python
# Yoker's current format (OpenAI-compatible)
tools = [
  {
    "type": "function",
    "function": {
      "name": "read_file",
      "description": "Read a file",
      "parameters": {
        "type": "object",
        "properties": {
          "path": {"type": "string"}
        }
      }
    }
  }
]

# litellm accepts this directly
response = litellm.completion(
  model="ollama/llama3.2",
  messages=[...],
  tools=tools  # Same format
)
```

**No Changes Needed**: Yoker's tool schema is already OpenAI-compatible. litellm handles translation to:
- Anthropic's tool format
- Ollama's tool format
- Other providers

### 3.2 Tool Execution Flow

**Current Yoker Flow:**
```
Backend returns tool call → Agent receives ChatChunk TOOL_CALL_* →
Agent executes tool → Agent adds tool result to context →
Agent calls backend again
```

**litellm Flow:**
```
litellm returns tool call in stream → Agent receives translated ChatChunk TOOL_CALL_* →
Agent executes tool → Agent adds tool result to context →
Agent calls litellm again
```

**Key Point**: litellm does NOT automatically execute tools. It normalizes tool calling across providers but expects the caller to handle tool execution. This matches Yoker's current approach perfectly.

### 3.3 Guardrails Integration

**Yoker's Guardrails:**
```python
class Guardrail(Protocol):
  def validate(self, tool_name: str, value: Any) -> ValidationResult:
    """Validate tool argument against security policy."""
```

**Integration Point:**
Guardrails execute AFTER tool call is received but BEFORE tool execution. This happens in `_processing.py`:

```python
async def _execute_single_tool_call(agent: Any, call: Any) -> None:
  # Validate tool args with guardrails
  validation = _validate_tool_args(agent, spec, tool_args)
  if not validation.valid:
    return ToolResult(success=False, error=validation.reason)

  # Execute tool
  result = await spec.execute(*bound.args, **bound.kwargs)
```

**No Changes Needed**: litellm doesn't interfere with tool execution. Guardrails continue to work as-is.

### 3.4 Parallel Tool Calls

**litellm Support:**
litellm handles parallel tool calls in streaming mode - each tool call gets a unique `index`:

```python
# litellm stream chunk
delta.tool_calls = [
  {"index": 0, "id": "call_1", "function": {"name": "read", "arguments": '{"path": "a.txt"}'}},
  {"index": 1, "id": "call_2", "function": {"name": "read", "arguments": '{"path": "b.txt"}'}}
]
```

**Yoker's Handling:**
Already supports parallel tool calls via `_deduplicate_tool_calls()` and sequential execution.

**Integration**: Translate litellm's tool call deltas to Yoker's `ToolCallDelta` format. No changes needed to execution logic.

### 3.5 Code Changes

**Files Affected:**
- `/src/yoker/tools/schema.py` - No changes (already OpenAI-compatible)
- `/src/yoker/agent/_processing.py` - No changes to tool execution logic
- `/src/yoker/backends/litellm_backend.py` - Translate tool call chunks

**Migration Steps:**
1. Ensure tool schema format matches litellm expectations (already compatible)
2. Test tool calling across providers (Ollama, OpenAI, Anthropic)
3. Verify guardrails execute at correct point in flow

---

## 4. Skills Integration

### 4.1 Dynamic Skill Loading

**Yoker's Current Approach:**
Skills are loaded dynamically from configured directories and registered in `SkillRegistry`. When a skill is invoked, its context (system prompt + invocation block) is injected into the conversation.

```python
def inject_skill_context(self, skill_name: str, args: str | None = None) -> None:
  skill = self.skills.get(skill_name)
  self.context.add_message("user", format_invocation_block(skill, args or ""))
```

**litellm Integration:**
Skills are orthogonal to litellm. Skill context injection happens BEFORE calling litellm:

```python
# Agent receives user message
# Agent injects skill context
# Agent calls litellm with enhanced messages
response = litellm.completion(
  model=f"{provider}/{model}",
  messages=agent.context.get_context(),  # Includes skill context
  tools=agent.tools.get_schemas(),
)
```

**No Changes Needed**: Skills operate at the context/message level, independent of backend.

### 4.2 Prompt Templates

**Potential Conflict**: litellm applies its own prompt templates for some providers.

**Yoker's Approach**: Agent definitions include system prompts. Context manager handles message assembly.

**Resolution**: litellm's prompt templates are applied at the API level (converting messages to provider-specific formats). Yoker's system prompts and skill context remain intact.

```python
# Yoker's message format
messages = [
  {"role": "system", "content": "You are running inside Yoker..."},
  {"role": "system", "content": skill.system_prompt},  # Skill context
  {"role": "user", "content": "..."},
]

# litellm preserves messages and translates to provider format
```

### 4.3 Code Changes

**Files Affected:**
- `/src/yoker/skills/` - No changes
- `/src/yoker/agent/agent.py` - No changes to skill injection logic
- `/src/yoker/context/` - No changes

**Migration Steps:**
1. Test skill invocation with litellm backend
2. Verify skill context appears in messages sent to litellm
3. No code changes expected

---

## 5. Web Tools Integration

**Critical Challenge**: litellm does NOT provide web search/fetch capabilities. Yoker's web tools currently use the native Ollama SDK.

### 5.1 Current Web Tools Architecture

```python
# Yoker's web tools use native Ollama SDK
class OllamaWebSearchBackend:
  def __init__(self, async_client: AsyncClient, ...):
    self._client = async_client  # ollama.AsyncClient

  async def search(self, query: str) -> list[SearchResult]:
    # Uses ollama client's built-in web search
    results = await self._client.web_search(query=query)
    return [SearchResult(...) for r in results]
```

### 5.2 Integration Options

**Option A: External Provider (Tavily/Perplexity) via litellm**
```python
# Use Tavily via litellm
response = litellm.completion(
  model="tavily/tavily-search",
  messages=[{"role": "user", "content": query}],
)

# Requires:
# - Tavily API key
# - Network access to Tavily API
# - Migration from local Ollama web search
```

**Pros:**
- Unified through litellm
- Works across all providers (not just Ollama)

**Cons:**
- Requires external API key
- Requires network access (privacy concern)
- Different search quality/results

**Option B: Keep Native Ollama SDK for Web Tools Only**
```python
# Agent continues using Ollama SDK for web tools
class Agent:
  def _create_tool_backends(self) -> dict[str, Any]:
    backends = {}
    if self.config.backend.provider == "ollama":
      if self.config.tools.websearch.enabled:
        # Keep Ollama SDK for web search
        from yoker.tools.web import OllamaWebSearchBackend
        backends["websearch"] = OllamaWebSearchBackend(
          async_client=self._ollama_client  # Native Ollama client
        )
    return backends
```

**Pros:**
- Preserves current behavior
- Local, privacy-preserving web search
- No external dependencies

**Cons:**
- Web tools tied to Ollama backend
- Requires maintaining Ollama SDK dependency
- Mixed architecture (litellm + native SDK)

**Option C: Remove Web Tools**
Deprecate web search/fetch tools, let users invoke external search via other means.

**Recommendation**: **Option B (Keep Native Ollama SDK for Web Tools)**

**Rationale:**
1. Preserves current behavior and privacy
2. No breaking changes for users
3. Minimal code impact
4. Only web tools remain Ollama-specific; everything else uses litellm

### 5.3 Implementation Details

**Hybrid Approach:**
```python
class Agent:
  def __init__(self, ...):
    # Create litellm backend for chat
    self._litellm_backend = create_litellm_backend(config)

    # Keep Ollama client for web tools (Ollama-only)
    if config.backend.provider == "ollama" and config.backend.ollama.api_key:
      self._ollama_client = AsyncClient(host=config.backend.ollama.base_url)
      self._tool_backends["websearch"] = OllamaWebSearchBackend(self._ollama_client)
      self._tool_backends["webfetch"] = OllamaWebFetchBackend(self._ollama_client)
```

**Code Changes:**
- `/src/yoker/agent/agent.py` - Keep `_create_tool_backends()` for Ollama web tools
- `/src/yoker/backends/litellm_backend.py` - Chat backend only
- `/src/yoker/tools/web/` - Keep Ollama web tool backends

---

## 6. Security Integration

### 6.1 API Key Handling

**Current Yoker:**
```python
@dataclass(frozen=True)
class OllamaConfig:
  api_key: str | None = field(default=None, metadata={"cli": False})
```

**litellm Patterns:**
1. Environment variables: `os.environ["OLLAMA_API_KEY"]`
2. Explicit parameter: `litellm.completion(api_key="...", ...)`
3. Client-level: `litellm.client(api_key="...")`

**Integration Strategy:**
Keep Yoker's config structure (Clevis CLI, TOML files). Inject API keys explicitly:

```python
class LitellmBackend:
  def __init__(self, config: Config):
    self.config = config
    self.api_key = self._get_api_key(config)

  def _get_api_key(self, config: Config) -> str | None:
    """Extract API key from Yoker config."""
    provider = config.backend.provider
    if provider == "ollama":
      return config.backend.ollama.api_key
    elif provider == "openai":
      return config.backend.openai.api_key
    elif provider == "anthropic":
      return config.backend.anthropic.api_key
    return None

  async def chat_stream(self, ...):
    async for chunk in litellm.acompletion(
      model=f"{provider}/{model}",
      api_key=self.api_key,  # Explicit injection
      ...
    ):
      yield self._translate_chunk(chunk)
```

### 6.2 Base URL Trust Boundary

**Yoker's Current Validation:**
```python
def validate_base_url_trust(config: BackendConfig, interactive: bool) -> None:
  """Warn/confirm when custom base_url is configured."""
  # Check if base_url differs from default
  # Show interactive warning in CLI mode
```

**Integration:**
Keep this validation in Agent initialization, before creating litellm backend:

```python
class Agent:
  def __init__(self, ...):
    # Trust boundary check (Yoker-specific security)
    validate_base_url_trust(self.config.backend, interactive=console_logging)

    # Then create litellm backend
    self._backend = create_backend(self.config)
```

### 6.3 Provider Credentials Management

**litellm's Approach:**
litellm can read credentials from environment variables automatically.

**Yoker's Approach:**
Yoker explicitly manages credentials in config files.

**Integration:**
Don't rely on litellm's environment variable reading. Keep Yoker's explicit credential management:

```python
# Yoker's approach (explicit)
config = get_yoker_config()  # Reads from TOML
backend = LitellmBackend(config)  # Injects credentials

# NOT this (litellm's implicit)
os.environ["OPENAI_API_KEY"] = "..."  # Don't do this
litellm.completion(model="openai/gpt-4o", ...)  # litellm reads from env
```

### 6.4 Code Changes

**Files Affected:**
- `/src/yoker/backends/trust.py` - Keep as-is
- `/src/yoker/config/__init__.py` - Keep `metadata={"cli": False}` for API keys
- `/src/yoker/backends/litellm_backend.py` - Inject API keys explicitly

**Migration Steps:**
1. Ensure API keys flow from config to litellm calls
2. Verify base_url trust validation still executes
3. Test with custom base URLs (Ollama local server, Azure OpenAI, etc.)

---

## 7. Streaming/Events Integration

### 7.1 Thinking/Reasoning Content

**litellm Support:**
- Anthropic: Returns `thinking` blocks in streaming
- OpenAI o-series: Returns `reasoning_content` in delta
- Ollama: Returns `thinking` field in response

**Yoker's Event System:**
```python
class ChatChunkEvent(Enum):
  THINKING_START = auto()
  THINKING_DELTA = auto()
  THINKING_STOP = auto()
  CONTENT_START = auto()
  CONTENT_DELTA = auto()
  CONTENT_STOP = auto()
```

**Integration:**
litellm preserves provider-specific thinking blocks. Translation in `LitellmBackend`:

```python
def _translate_chunk(self, chunk: ModelResponseStream) -> Iterator[ChatChunk]:
  delta = chunk.choices[0].delta

  # OpenAI o-series reasoning
  if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
    if not self._in_thinking:
      yield ChatChunk(event=ChatChunkEvent.THINKING_START, index=0)
      self._in_thinking = True
    yield ChatChunk(event=ChatChunkEvent.THINKING_DELTA, text=delta.reasoning_content)

  # Anthropic thinking blocks (handled in content_block_start/delta events)
  # Ollama thinking (in chunk.message.thinking)
```

### 7.2 Usage Statistics

**litellm Usage:**
```python
chunk.usage.prompt_tokens
chunk.usage.completion_tokens
```

**Yoker's UsageStats:**
```python
@dataclass(frozen=True)
class UsageStats:
  input_tokens: int | None = None
  output_tokens: int | None = None
  prompt_eval_count: int | None = None  # Ollama native
  eval_count: int | None = None  # Ollama native
  total_duration_ms: int | None = None  # Ollama native
```

**Integration:**
```python
def _translate_usage(self, litellm_usage) -> UsageStats:
  # Standard fields (all providers)
  usage = UsageStats(
    input_tokens=litellm_usage.prompt_tokens,
    output_tokens=litellm_usage.completion_tokens
  )

  # Provider-specific fields (if available)
  if hasattr(litellm_usage, 'prompt_eval_count'):
    usage.prompt_eval_count = litellm_usage.prompt_eval_count
  if hasattr(litellm_usage, 'eval_count'):
    usage.eval_count = litellm_usage.eval_count
  if hasattr(litellm_usage, 'total_duration'):
    usage.total_duration_ms = litellm_usage.total_duration // 1_000_000

  return usage
```

### 7.3 Event Timing

**Yoker's Event Flow:**
```
TurnStart → ThinkingStart → ThinkingDelta* → ThinkingStop →
ContentStart → ContentDelta* → ContentStop →
ToolCallStart → ToolCallDelta* → ToolCallStop →
Usage → Done → TurnEnd
```

**litellm's Stream Flow:**
```
ModelResponseStream chunks with:
  - delta.content
  - delta.reasoning_content (o-series)
  - delta.tool_calls
  - usage (final chunk)
```

**State Management:**
The `LitellmBackend` must track state to emit proper START/STOP events:

```python
class LitellmBackend(ModelBackend):
  def __init__(self, config: Config):
    self._in_content = False
    self._in_thinking = False
    self._in_tool_call: dict[int, bool] = {}

  async def chat_stream(self, ...) -> AsyncIterator[ChatChunk]:
    # Reset state for each stream
    self._in_content = False
    self._in_thinking = False
    self._in_tool_call = {}

    async for chunk in litellm.acompletion(...):
      for event in self._translate_chunk(chunk):
        yield event
```

### 7.4 Code Changes

**Files Affected:**
- `/src/yoker/backends/litellm_backend.py` - Event translation logic
- `/src/yoker/events/types.py` - No changes
- `/src/yoker/agent/_processing.py` - No changes (consumes ChatChunk)

**Migration Steps:**
1. Implement stateful stream translation
2. Test event timing matches Yoker's expectations
3. Verify thinking blocks work for Anthropic/o-series
4. Test usage stats across providers

---

## 8. Testing Implications

### 8.1 Mocking litellm

**Challenge**: litellm is a complex library with many provider integrations. Mocking it directly is difficult.

**Approach**: Mock at the `ModelBackend` Protocol level, not litellm itself.

```python
# tests/conftest.py
@pytest.fixture
def mock_backend():
  """Mock backend that yields test ChatChunks."""
  class MockBackend(ModelBackend):
    async def chat_stream(self, ...):
      yield ChatChunk(event=ChatChunkEvent.CONTENT_START, index=0)
      yield ChatChunk(event=ChatChunkEvent.CONTENT_DELTA, text="Hello")
      yield ChatChunk(event=ChatChunkEvent.CONTENT_STOP, index=0)
      yield ChatChunk(event=ChatChunkEvent.DONE)
  return MockBackend()

# Agent tests use mock_backend
agent = Agent(backend=mock_backend, ...)
```

### 8.2 Integration Tests

For real litellm integration tests, use:
1. **Provider-specific fixtures** (Ollama local, OpenAI API key, etc.)
2. **VCR/cassette recording** for reproducibility
3. **Docker Compose** for local provider testing

```python
# tests/integration/test_litellm_backend.py
@pytest.mark.integration
async def test_ollama_streaming():
  """Test real Ollama streaming via litellm."""
  backend = LitellmBackend(config)
  chunks = []
  async for chunk in backend.chat_stream(model="llama3.2", messages=[...]):
    chunks.append(chunk)

  assert chunks[0].event == ChatChunkEvent.CONTENT_START
  assert chunks[-1].event == ChatChunkEvent.DONE
```

### 8.3 Testing Strategy

| Test Type | Scope | Approach |
|-----------|-------|----------|
| Unit Tests | Backend translation | Mock `litellm.acompletion` |
| Integration Tests | Provider communication | Real provider (local Ollama) |
| End-to-End Tests | Agent with backend | Real provider + event handlers |

### 8.4 Code Changes

**Files Added:**
- `/tests/unit/backends/test_litellm_backend.py` - Unit tests with mocks
- `/tests/integration/backends/test_litellm_integration.py` - Provider tests

**Migration Steps:**
1. Create mock backend fixtures
2. Port existing backend tests to use mocks
3. Add integration tests for each provider
4. Set up CI pipeline with local Ollama container

---

## 9. Migration Path

### 9.1 Migration Phases

**Phase 1: Parallel Implementation (2-3 weeks)**
1. Implement `LitellmBackend` alongside existing backends
2. Add `provider: "litellm"` config option
3. Test with single provider (Ollama)
4. Validate event translation matches existing behavior

**Phase 2: Multi-Provider Testing (1-2 weeks)**
1. Test OpenAI backend via litellm
2. Test Anthropic backend via litellm
3. Compare streaming behavior across providers
4. Validate thinking/reasoning blocks

**Phase 3: Feature Parity (1-2 weeks)**
1. Verify web tools work with Ollama backend
2. Test subagent spawning
3. Validate tool calling across providers
4. Test guardrails and security

**Phase 4: Deprecation (1 week)**
1. Remove `OllamaBackend`, `OpenAIBackend` classes
2. Update `create_backend()` factory
3. Remove native SDK dependencies (except Ollama for web tools)
4. Update documentation

### 9.2 Minimal Viable Integration

**What's Required:**
1. `LitellmBackend` class implementing `ModelBackend` Protocol
2. Stream translation from `ModelResponseStream` to `ChatChunk`
3. Config mapping from Yoker to litellm parameters
4. Web tools keep native Ollama SDK

**What Can Wait:**
1. Advanced provider-specific features (if not used)
2. Token caching (if litellm doesn't support)
3. Performance optimizations

### 9.3 Rollback Strategy

**If litellm doesn't work:**
1. Keep `ModelBackend` Protocol
2. Revert to `OllamaBackend`, `OpenAIBackend`
3. No changes to Agent layer (Protocol isolates implementation)

**Rollback Safety:**
The `ModelBackend` Protocol provides a clean abstraction boundary. If litellm proves problematic, we can revert to provider-specific backends without touching Agent code.

### 9.4 Code Changes Timeline

| Week | Files Changed | Lines Changed (Est.) |
|------|---------------|---------------------|
| 1-2 | `/src/yoker/backends/litellm_backend.py` (new) | +500 |
| 2-3 | `/src/yoker/backends/factory.py`, `/src/yoker/config/` | +100 |
| 3-4 | Tests, integration tests | +300 |
| 4-5 | Deprecation, cleanup | -400 (remove old backends) |
| **Total** | | **+500 net new, delete 400** |

---

## 10. Architectural Simplification

### 10.1 Code Deletion Opportunities

**Backend Implementations (DELETE):**
```
/src/yoker/backends/ollama.py          # -189 lines
/src/yoker/backends/openai.py          # -223 lines
/src/yoker/backends/anthropic.py       # (not yet implemented, ~200 lines saved)
```

**Factory Logic (SIMPLIFY):**
```python
# Current: provider-specific branches
def create_backend(config: Config) -> ModelBackend:
  if config.backend.provider == "ollama":
    return OllamaBackend(...)
  elif config.backend.provider == "openai":
    return OpenAIBackend(...)
  elif config.backend.provider == "anthropic":
    return AnthropicBackend(...)

# Simplified: single litellm backend
def create_backend(config: Config) -> ModelBackend:
  return LitellmBackend(config)
```

**Provider-Specific Config (KEEP):**
Keep `OllamaConfig`, `OpenAIConfig`, `AnthropicConfig` for:
1. Clevis CLI arg generation
2. Provider-specific parameters (`num_ctx`, `budget_tokens`)
3. Validation and type safety

### 10.2 New Code Additions

**New Files:**
```
/src/yoker/backends/litellm_backend.py    # +500 lines (stream translation, config mapping)
/src/yoker/backends/litellm_config.py     # +150 lines (parameter mapping utilities)
```

**Modified Files:**
```
/src/yoker/backends/factory.py           # Simplified factory
/src/yoker/agent/agent.py                # Web tools backend creation
/pyproject.toml                          # Add litellm dependency
```

### 10.3 Dependency Changes

**Add:**
```toml
[project.dependencies]
litellm = ">=1.90.0"
```

**Remove:**
```toml
[project.dependencies]
# Keep ollama for web tools only
ollama = ">=0.4.0"

# Remove (litellm handles these)
# openai = ">=1.0.0"  # REMOVE
# anthropic = ">=0.40.0"  # REMOVE
```

**Result:**
- Reduced dependency count
- Simplified dependency management
- litellm handles provider SDKs internally

### 10.4 Yoker-Specific Features to Keep

**Keep These (Core Yoker Features):**

1. **Guardrails** - Security layer, provider-agnostic
2. **Event System** - Yoker's ChatChunk/Event abstraction
3. **Context Management** - Message history management
4. **Tool Registry** - Tool registration and execution
5. **Skills** - Dynamic skill loading and context injection
6. **Bootstrap** - First-time setup wizard
7. **UI Layer** - Event-driven UI handlers
8. **Web Tools** - Keep Ollama SDK for web search/fetch

**Replace with litellm:**

1. **Provider-specific backends** - Ollama, OpenAI, Anthropic
2. **Stream translation** - Let litellm handle provider differences
3. **API normalization** - litellm's core value proposition
4. **Credential handling** - Inject from config to litellm

### 10.5 Migration Summary

| Component | Before | After | Change |
|-----------|--------|-------|--------|
| Backend Classes | 3 (Ollama, OpenAI, Anthropic) | 1 (Litellm) | Simplify |
| Stream Translation | Per-provider | Per-litellm | Consolidate |
| Provider Config | Tagged union | Keep | No change |
| API Keys | Per-provider | Inject to litellm | Simplify |
| Tool Calling | Manual translation | litellm handles | Simplify |
| Web Tools | Native Ollama SDK | Keep Ollama SDK | No change |
| Events | Yoker's ChatChunk | Translate from litellm | Keep |
| Guardrails | Yoker's system | Keep | No change |
| Dependencies | 3 SDKs | 1 (litellm) + ollama | Reduce |

**Net Impact:**
- **Lines of Code**: -400 (backend), +650 (litellm integration) = **+250 net**
- **Complexity**: Reduced (one backend, not three)
- **Maintenance**: Lower (litellm handles provider updates)
- **Features**: Same + multi-provider support via litellm

---

## Summary of Recommendations

### Must Do

1. **Adopt litellm for chat streaming** - Single backend implementation
2. **Keep Yoker's config system** - Clevis CLI, TOML config, provider-specific params
3. **Keep ModelBackend Protocol** - Isolates Yoker from litellm
4. **Keep native Ollama SDK for web tools** - No litellm equivalent
5. **Translate streams to ChatChunk events** - Preserve Yoker's event system

### Keep

1. **Guardrails** - Security layer
2. **Event System** - Yoker's abstraction
3. **Context Management** - Message handling
4. **Tool Registry** - Execution layer
5. **Skills System** - Context injection
6. **Web Tools** - With Ollama SDK

### Delete

1. **OllamaBackend** - Replace with LitellmBackend
2. **OpenAIBackend** - Replace with LitellmBackend
3. **Provider-specific stream translation** - Unified in LitellmBackend
4. **Direct OpenAI/Anthropic SDK dependencies** - litellm handles

### Testing Strategy

1. **Unit Tests**: Mock ModelBackend Protocol
2. **Integration Tests**: Real providers (local Ollama, API keys for others)
3. **Rollback Strategy**: Protocol abstraction allows revert

### Timeline

**4-5 weeks total:**
- Week 1-2: Implement LitellmBackend
- Week 2-3: Test multi-provider support
- Week 3-4: Feature parity testing
- Week 4-5: Deprecation and cleanup

---

## Appendix: Key litellm Findings

### Provider Prefix Pattern
```python
model="ollama/llama3.2:latest"  # Ollama
model="openai/gpt-4o"           # OpenAI
model="anthropic/claude-3-5-sonnet-20241022"  # Anthropic
```

### Stream API
```python
async for chunk in litellm.acompletion(model=model, messages=messages, stream=True):
  # chunk.choices[0].delta.content
  # chunk.choices[0].delta.tool_calls
  # chunk.usage
```

### Tool Calling
```python
tools = [{"type": "function", "function": {...}}]  # OpenAI format
response = litellm.completion(model=model, messages=messages, tools=tools)
```

### Provider-Specific Parameters
```python
# Ollama
litellm.completion(model="ollama/llama3.2", num_ctx=4096, ...)

# Anthropic
litellm.completion(model="anthropic/claude-3-5-sonnet", budget_tokens=1024, ...)

# OpenAI o-series
litellm.completion(model="openai/o1", reasoning_effort="high", ...)
```

### Thinking/Reasoning
```python
# Automatically preserved in stream
delta.reasoning_content  # OpenAI o-series
# Anthropic returns thinking blocks
```

### Authentication
```python
# Explicit (recommended for Yoker)
litellm.completion(model="openai/gpt-4o", api_key="...")

# Environment variable
os.environ["OPENAI_API_KEY"] = "..."
litellm.completion(model="openai/gpt-4o")
```

### Base URL / Custom Endpoint
```python
litellm.completion(
  model="ollama/llama3.2",
  api_base="http://localhost:11434",
  ...
)
```