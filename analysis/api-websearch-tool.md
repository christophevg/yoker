# WebSearchTool API Design

**Date**: 2026-05-04
**Task**: Design pluggable backend architecture for WebSearchTool
**Related Documents**: `analysis/websearch-webfetch-research.md`

---

## Summary

This document defines the API for WebSearchTool, a tool that enables agents to search the web using a pluggable backend architecture. The design follows existing yoker tool patterns (ReadTool, ListTool) while supporting multiple backend implementations (Ollama native first, local DDGS later).

---

## Architecture Overview

```
WebSearchTool (Tool)
    |
    +-- WebGuardrail (validation)
    |
    +-- WebSearchBackend (Protocol)
           |
           +-- OllamaWebSearchBackend (Phase 1)
           |
           +-- LocalWebSearchBackend (Phase 2 - future)
```

**Key Design Decisions**:
1. **Pluggable backend** - Backend selection via configuration
2. **Protocol-based** - `WebSearchBackend` is a Protocol, not an ABC
3. **Guardrail separation** - WebGuardrail handles web-specific validation
4. **Structured results** - `SearchResult` frozen dataclass for type safety
5. **Async-first** - Backends are async for future HTTP client support

---

## Tool Interface

### WebSearchTool

```python
class WebSearchTool(Tool):
  """Tool for searching the web using pluggable backends.
  
  Searches the web for information and returns structured results.
  Uses a configurable backend (Ollama native or local DDGS).
  Validates queries through WebGuardrail before execution.
  
  Example:
    tool = WebSearchTool(backend=OllamaWebSearchBackend())
    result = tool.execute(query="Python async best practices", max_results=5)
  """

  def __init__(
    self,
    backend: "WebSearchBackend | None" = None,
    guardrail: "WebGuardrail | None" = None,
  ) -> None:
    """Initialize WebSearchTool with optional backend and guardrail.
    
    Args:
      backend: Optional backend for web search (defaults to Ollama).
      guardrail: Optional guardrail for query validation.
    """
    
  @property
  def name(self) -> str:
    return "web_search"

  @property
  def description(self) -> str:
    return "Search the web for information"

  def get_schema(self) -> dict[str, Any]:
    """Return Ollama-compatible schema.
    
    Returns:
      {
        "type": "function",
        "function": {
          "name": "web_search",
          "description": "Search the web for information",
          "parameters": {
            "type": "object",
            "properties": {
              "query": {
                "type": "string",
                "description": "Search query"
              },
              "max_results": {
                "type": "integer",
                "description": "Maximum number of results to return",
                "default": 10,
                "minimum": 1,
                "maximum": 50
              }
            },
            "required": ["query"]
          }
        }
      }
    """

  def execute(self, **kwargs: Any) -> ToolResult:
    """Execute web search with the given parameters.
    
    Steps:
      1. Validate parameters via guardrail if provided.
      2. Extract and validate query parameter.
      3. Delegate to backend for search execution.
      4. Return structured results or error.
    
    Args:
      **kwargs: Must contain 'query', optionally 'max_results'.
    
    Returns:
      ToolResult with list of SearchResult dicts or error.
    """
```

---

## Backend Protocol

### WebSearchBackend (Protocol)

```python
from typing import Protocol

class WebSearchBackend(Protocol):
  """Protocol for web search backend implementations.
  
  Defines the interface that all search backends must implement.
  Supports both synchronous Ollama native tools and async local backends.
  
  Implementations:
    - OllamaWebSearchBackend: Uses Ollama's native web_search tool
    - LocalWebSearchBackend: Uses DDGS library (future)
  """

  def search(self, query: str, max_results: int = 10) -> list["SearchResult"]:
    """Execute a web search and return results.
    
    Args:
      query: Search query string.
      max_results: Maximum number of results to return (1-50).
    
    Returns:
      List of SearchResult objects.
    
    Raises:
      WebSearchError: If search fails.
    """
```

### SearchResult (Dataclass)

```python
@dataclass(frozen=True)
class SearchResult:
  """A single web search result.
  
  Attributes:
    title: Page title.
    url: Result URL.
    snippet: Short text snippet/summary.
    source: Backend that produced this result (e.g., "ollama", "duckduckgo").
  """
  
  title: str
  url: str
  snippet: str
  source: str = "unknown"
```

---

## Backend Implementations

### OllamaWebSearchBackend

```python
class OllamaWebSearchBackend:
  """Web search backend using Ollama's native web_search tool.
  
  Uses the Ollama server's built-in web search capability.
  Requires OLLAMA_API_KEY environment variable.
  
  Features:
    - Server-side search (backend configurable on Ollama side)
    - Built-in summarization
    - No additional dependencies
  
  Limitations:
    - Requires network access
    - Requires API key
    - Limited to 10 results
    - No domain filtering on client side
  """

  def __init__(self, client: "OllamaClient | None" = None) -> None:
    """Initialize backend with optional Ollama client.
    
    Args:
      client: Optional Ollama client (creates default if None).
    """

  def search(self, query: str, max_results: int = 10) -> list[SearchResult]:
    """Execute search via Ollama web_search tool.
    
    Note:
      Ollama web_search has a hard limit of 10 results.
      If max_results > 10, only 10 results are returned.
    
    Args:
      query: Search query string.
      max_results: Maximum results (capped at 10 for Ollama).
    
    Returns:
      List of SearchResult objects.
    
    Raises:
      WebSearchError: If Ollama request fails.
    """
```

### LocalWebSearchBackend (Future)

```python
class LocalWebSearchBackend:
  """Local web search backend using DDGS library.
  
  Performs searches directly from the client using DuckDuckGo.
  No API key required.
  
  Features:
    - No API key required
    - Multiple backends (duckduckgo, google, bing, brave)
    - Unlimited results
    - Full control over guardrails
  
  Limitations:
    - Requires DDGS dependency
    - Rate limiting possible
    - No server-side summarization
  """

  def __init__(
    self,
    backend: str = "duckduckgo",
    timeout_seconds: int = 30,
  ) -> None:
    """Initialize local search backend.
    
    Args:
      backend: Search backend to use (duckduckgo, google, bing, brave).
      timeout_seconds: Request timeout in seconds.
    """

  def search(self, query: str, max_results: int = 10) -> list[SearchResult]:
    """Execute search via DDGS library.
    
    Args:
      query: Search query string.
      max_results: Maximum results (no hard limit).
    
    Returns:
      List of SearchResult objects.
    
    Raises:
      WebSearchError: If search fails.
    """
```

---

## Guardrails

### WebGuardrail

```python
class WebGuardrail(Guardrail):
  """Guardrail for web tool validation.
  
  Validates:
    - Query length (prevents excessive queries)
    - Domain allowlist (optional, for restricted searches)
    - Domain blocklist (optional, for blocked domains)
    - Timeout enforcement
    - Result count limits
  
  Note:
    Domain filtering is client-side validation only.
    Ollama backend may still access blocked domains.
    For full control, use LocalWebSearchBackend.
  """

  def __init__(self, config: "WebSearchToolConfig") -> None:
    """Initialize guardrail with configuration.
    
    Args:
      config: WebSearchToolConfig with validation settings.
    """

  def validate(self, tool_name: str, params: dict[str, Any]) -> ValidationResult:
    """Validate web search parameters.
    
    Steps:
      1. Validate query is present and non-empty.
      2. Validate query length <= max_query_length.
      3. Validate max_results is within bounds (1-50).
      4. Check domain allowlist if configured.
      5. Check domain blocklist if configured.
    
    Args:
      tool_name: Name of tool being validated.
      params: Tool parameters from LLM.
    
    Returns:
      ValidationResult with success/failure and reason.
    """
```

### Domain Validation

```python
def _check_domain_allowlist(self, query: str) -> str | None:
  """Check if query violates domain allowlist.
  
  Note:
    This is a heuristic check. It looks for domain patterns
    in the query string. For full control, use LocalWebSearchBackend
    which can filter results by domain.
  
  Args:
    query: Search query string.
  
  Returns:
    Error message if blocked, None if allowed.
  """

def _check_domain_blocklist(self, query: str) -> str | None:
  """Check if query matches blocked domains.
  
  Args:
    query: Search query string.
  
  Returns:
    Error message if blocked, None if allowed.
  """
```

---

## Configuration Schema

### WebSearchToolConfig

```python
@dataclass(frozen=True)
class WebSearchToolConfig(ToolConfig):
  """Web search tool configuration.
  
  Attributes:
    enabled: Whether the tool is enabled.
    backend: Backend to use ("ollama" or "local").
    max_results: Maximum results per search (default 10).
    max_query_length: Maximum query string length (default 500).
    timeout_seconds: Search timeout in seconds (default 30).
    domain_allowlist: Domains to allow (empty = all allowed).
    domain_blocklist: Domains to block (empty = none blocked).
  """
  
  enabled: bool = True
  backend: Literal["ollama", "local"] = "ollama"
  max_results: int = 10
  max_query_length: int = 500
  timeout_seconds: int = 30
  domain_allowlist: tuple[str, ...] = ()
  domain_blocklist: tuple[str, ...] = ()
```

### Configuration File Example

```toml
[tools.websearch]
enabled = true
backend = "ollama"
max_results = 10
max_query_length = 500
timeout_seconds = 30
domain_allowlist = []
domain_blocklist = ["*.internal", "*.local"]

# Future: Local backend configuration
# [tools.websearch.local]
# backend = "duckduckgo"
# proxy = "http://localhost:8080"
```

### Integration with ToolsConfig

```python
@dataclass(frozen=True)
class ToolsConfig:
  """All tool configurations."""
  
  list: ListToolConfig = field(default_factory=ListToolConfig)
  read: ReadToolConfig = field(default_factory=ReadToolConfig)
  write: WriteToolConfig = field(default_factory=WriteToolConfig)
  update: UpdateToolConfig = field(default_factory=UpdateToolConfig)
  search: SearchToolConfig = field(default_factory=SearchToolConfig)
  agent: AgentToolConfig = field(default_factory=AgentToolConfig)
  git: GitToolConfig = field(default_factory=GitToolConfig)
  mkdir: MkdirToolConfig = field(default_factory=MkdirToolConfig)
  websearch: WebSearchToolConfig = field(default_factory=WebSearchToolConfig)  # NEW
```

---

## Error Handling

### WebSearchError

```python
class WebSearchError(Exception):
  """Base exception for web search errors.
  
  Attributes:
    message: Human-readable error message.
    backend: Backend that raised the error.
    cause: Original exception if wrapped.
  """
  
  def __init__(
    self,
    message: str,
    backend: str = "unknown",
    cause: Exception | None = None,
  ) -> None:
    """Initialize error with context."""
    self.message = message
    self.backend = backend
    self.cause = cause
    super().__init__(message)
```

### Error Scenarios

| Scenario | HTTP Status | Error Type | Message |
|----------|-------------|------------|---------|
| Query too long | N/A | WebGuardrailError | "Query exceeds maximum length: {len} > {max}" |
| Backend timeout | N/A | WebSearchError | "Search timeout after {seconds}s" |
| Backend unavailable | N/A | WebSearchError | "Backend unavailable: {details}" |
| Invalid response | N/A | WebSearchError | "Invalid response from backend" |
| API key missing | N/A | WebSearchError | "OLLAMA_API_KEY not configured" |
| Rate limited | N/A | WebSearchError | "Rate limit exceeded, try again later" |
| Domain blocked | N/A | WebGuardrailError | "Query contains blocked domain: {domain}" |

---

## Tool Registration

### Integration with ToolRegistry

```python
# src/yoker/tools/__init__.py

from .websearch import WebSearchTool

def create_default_registry(parent_agent: "Agent | None" = None) -> ToolRegistry:
  """Create registry with all built-in tools."""
  registry = ToolRegistry()
  registry.register(ReadTool())
  registry.register(ListTool())
  registry.register(WriteTool())
  registry.register(UpdateTool())
  registry.register(SearchTool())
  registry.register(ExistenceTool())
  registry.register(MkdirTool())
  registry.register(AgentTool(parent_agent=parent_agent))
  # WebSearchTool requires config - added when backend is configured
  return registry
```

### Agent Integration

```python
# src/yoker/agent.py

def _build_tool_registry(self, config: Config) -> ToolRegistry:
  """Build tool registry from configuration.
  
  Creates backend instances based on configuration and
  injects them into tools that need them.
  """
  registry = create_default_registry(parent_agent=self)
  
  # Add WebSearchTool if enabled
  if config.tools.websearch.enabled:
    backend = self._create_websearch_backend(config)
    guardrail = WebGuardrail(config.tools.websearch)
    registry.register(WebSearchTool(backend=backend, guardrail=guardrail))
  
  return registry

def _create_websearch_backend(self, config: Config) -> WebSearchBackend:
  """Create web search backend based on configuration.
  
  Args:
    config: Yoker configuration.
  
  Returns:
    WebSearchBackend implementation.
  """
  backend_type = config.tools.websearch.backend
  
  if backend_type == "ollama":
    return OllamaWebSearchBackend(client=self._client)
  elif backend_type == "local":
    # Future: LocalWebSearchBackend
    raise NotImplementedError("Local backend not yet implemented")
  else:
    raise ValueError(f"Unknown web search backend: {backend_type}")
```

---

## File Structure

### Files to Create

| File | Purpose |
|------|---------|
| `src/yoker/tools/websearch.py` | WebSearchTool implementation |
| `src/yoker/tools/web_backend.py` | Backend protocol and implementations |
| `src/yoker/tools/web_guardrail.py` | WebGuardrail implementation |
| `src/yoker/tools/web_types.py` | SearchResult, WebSearchError dataclasses |
| `tests/test_tools/test_websearch.py` | Unit tests with mocked backend |
| `demos/websearch.md` | Demo script |

### Files to Modify

| File | Change |
|------|--------|
| `src/yoker/tools/__init__.py` | Export WebSearchTool, create_websearch_backend |
| `src/yoker/config/schema.py` | Add WebSearchToolConfig, update ToolsConfig |
| `src/yoker/agent.py` | Add _create_websearch_backend, update _build_tool_registry |
| `README.md` | Add WebSearchTool to features table |

---

## Testing Strategy

### Unit Tests

```python
# tests/test_tools/test_websearch.py

class TestWebSearchTool:
  """Unit tests for WebSearchTool."""
  
  def test_schema_matches_spec(self):
    """Verify schema has required fields."""
    
  def test_execute_returns_results(self, mock_backend):
    """Test successful search returns results."""
    
  def test_query_required(self, mock_backend):
    """Test that query is required."""
    
  def test_max_results_bounds(self, mock_backend):
    """Test max_results is clamped to valid range."""
    
  def test_guardrail_blocks_long_query(self, mock_guardrail):
    """Test guardrail blocks excessively long queries."""
    
  def test_guardrail_blocks_domain(self, mock_guardrail):
    """Test guardrail blocks queries for blocked domains."""
    
  def test_backend_timeout(self, mock_backend_timeout):
    """Test timeout handling."""
    
  def test_backend_error(self, mock_backend_error):
    """Test backend error handling."""


class TestOllamaWebSearchBackend:
  """Unit tests for Ollama backend."""
  
  def test_search_returns_results(self, mock_ollama_client):
    """Test search returns structured results."""
    
  def test_max_results_capped_at_10(self, mock_ollama_client):
    """Test Ollama backend caps results at 10."""
    
  def test_api_key_required(self):
    """Test that OLLAMA_API_KEY is checked."""
```

### Integration Tests

```python
# tests/integration/test_websearch_live.py

@pytest.mark.integration
class TestWebSearchIntegration:
  """Integration tests with real Ollama backend."""
  
  @pytest.mark.skipif(not os.environ.get("OLLAMA_API_KEY"))
  def test_real_search_returns_results(self):
    """Test real search returns results."""
```

---

## Demo Script

```markdown
# demos/websearch.md

Search the web for recent Python async best practices and show me the top 3 results.

Query: "Python async best practices 2024"
Max results: 3
```

Expected output (concise):
```
Found 3 results for "Python async best practices 2024":

1. [Real Python] Asynchronous Python: A Guide
   https://realpython.com/async-python/
   Learn when to use async/await and how to structure async code.

2. [Python Docs] asyncio Documentation
   https://docs.python.org/3/library/asyncio.html
   Official documentation for Python's asyncio library.

3. [Blog] Python Async Best Practices
   https://example.com/python-async
   Common patterns and anti-patterns for async Python.
```

---

## Dependencies

### Phase 1: Ollama Backend

No new dependencies. Uses existing `ollama` client.

### Phase 2: Local Backend (Future)

Add to `pyproject.toml`:
```toml
dependencies = [
  # ... existing ...
  "ddgs>=8.0.0",  # Web search (local backend)
]
```

---

## Security Considerations

### Guardrail Enforcement

| Threat | Mitigation |
|--------|------------|
| Excessive query length | `max_query_length` configuration |
| Forbidden domains | `domain_blocklist` validation |
| SSRF (Server-Side Request Forgery) | Ollama backend handles URL fetching |
| Rate limiting | Backend implementation handles retries |
| Timeout attacks | `timeout_seconds` enforcement |

### Client-Side vs Server-Side

**Important**: Domain filtering in `WebGuardrail` is client-side validation only. The Ollama backend may still access any domain. For full control:

1. Use `LocalWebSearchBackend` (Phase 2)
2. Configure Ollama server restrictions
3. Use network-level filtering (firewall, proxy)

---

## Action Items

### Implementation Checklist

- [ ] Create `src/yoker/tools/web_types.py` with `SearchResult` and `WebSearchError`
- [ ] Create `src/yoker/tools/web_backend.py` with `WebSearchBackend` protocol
- [ ] Implement `OllamaWebSearchBackend` in `web_backend.py`
- [ ] Create `src/yoker/tools/web_guardrail.py` with `WebGuardrail`
- [ ] Create `src/yoker/tools/websearch.py` with `WebSearchTool`
- [ ] Update `src/yoker/config/schema.py` with `WebSearchToolConfig`
- [ ] Update `src/yoker/tools/__init__.py` to export new components
- [ ] Update `src/yoker/agent.py` to create backend and register tool
- [ ] Create `tests/test_tools/test_websearch.py` with unit tests
- [ ] Create `demos/websearch.md` demo script
- [ ] Update `README.md` with WebSearchTool feature
- [ ] Update `src/yoker/tools/path_guardrail.py` to add "websearch" to `_FILESYSTEM_TOOLS` exclusion (it's not a filesystem tool)

### Future Work

- [ ] Implement `LocalWebSearchBackend` with DDGS (Phase 2)
- [ ] Add WebFetchTool with similar architecture
- [ ] Add result caching for repeated queries
- [ ] Add search history logging

---

## Conclusion

This API design provides a clean, extensible foundation for web search in yoker:

1. **Pluggable backends** - Easy to add new backends
2. **Type-safe results** - Frozen dataclasses for SearchResult
3. **Guardrail integration** - Consistent with existing tool patterns
4. **Configuration-driven** - Backend selection via TOML
5. **Testable** - Mock backends for unit testing
6. **Documented** - Comprehensive docstrings and examples