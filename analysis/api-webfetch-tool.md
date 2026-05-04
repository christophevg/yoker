# API Design: WebFetch Tool (Task 2.12)

**Date**: 2026-05-04
**Task**: Task 2.12 - WebFetch Tool Implementation
**Status**: Design Complete
**Related**: `analysis/websearch-webfetch-research.md`, `src/yoker/tools/websearch.py`

---

## Summary

This document defines the API design for the WebFetch tool, following the pluggable backend architecture established by WebSearchTool. The tool fetches web content and optionally summarizes it using configurable backends (Ollama native or local httpx+Trafilatura).

---

## Architecture Overview

### Pluggable Backend Pattern

WebFetch follows the same backend pattern as WebSearch:

```
WebFetchTool (Tool)
    ├── WebFetchBackend (Protocol) - Interface
    │       ├── OllamaWebFetchBackend - Ollama native web_fetch
    │       └── LocalWebFetchBackend - Future: httpx + Trafilatura
    └── WebGuardrail - Shared security guardrail
```

### Key Components

| Component | File | Purpose |
|-----------|------|---------|
| `WebFetchTool` | `tools/webfetch.py` | Tool implementation |
| `WebFetchBackend` | `tools/web_backend.py` | Protocol interface |
| `OllamaWebFetchBackend` | `tools/web_backend.py` | Ollama native implementation |
| `FetchedContent` | `tools/web_types.py` | Result dataclass |
| `WebFetchError` | `tools/web_types.py` | Exception class |
| `WebFetchToolConfig` | `config/schema.py` | Configuration dataclass |
| `WebGuardrail` | `tools/web_guardrail.py` | Shared guardrail (extended) |

---

## Data Types

### FetchedContent

```python
@dataclass(frozen=True)
class FetchedContent:
  """Content fetched from a web URL.

  Attributes:
    url: The URL that was fetched.
    title: Page title (extracted or derived).
    content: Fetched content (markdown, text, or original).
    content_type: Content format ("markdown", "text", "html").
    source: Backend that fetched this content ("ollama", "local").
    metadata: Additional metadata (e.g., links, images, word_count).
  """

  url: str
  title: str
  content: str
  content_type: str = "markdown"
  source: str = "unknown"
  metadata: dict[str, Any] = field(default_factory=dict)

  def to_dict(self) -> dict[str, Any]:
    """Convert to dictionary for ToolResult."""
    return {
      "url": self.url,
      "title": self.title,
      "content": self.content,
      "content_type": self.content_type,
      "source": self.source,
      "metadata": self.metadata,
    }

  @classmethod
  def from_dict(cls, data: dict[str, Any]) -> "FetchedContent":
    """Create from dictionary."""
    return cls(
      url=str(data.get("url", "")),
      title=str(data.get("title", "")),
      content=str(data.get("content", "")),
      content_type=str(data.get("content_type", "markdown")),
      source=str(data.get("source", "unknown")),
      metadata=dict(data.get("metadata", {})),
    )
```

### WebFetchError

```python
class WebFetchError(Exception):
  """Exception for web fetch errors.

  Attributes:
    message: Human-readable error message.
    url: URL that failed (if applicable).
    backend: Backend that raised the error.
    cause: Original exception if wrapped.
    error_type: Type of error (ssrf, timeout, size, invalid_url, etc.).
  """

  def __init__(
    self,
    message: str,
    url: str = "",
    backend: str = "unknown",
    cause: Exception | None = None,
    error_type: str = "unknown",
  ) -> None:
    self.message = message
    self.url = url
    self.backend = backend
    self.cause = cause
    self.error_type = error_type
    super().__init__(message)

  def __str__(self) -> str:
    if self.backend != "unknown":
      return f"[{self.backend}] {self.message}"
    return self.message
```

---

## Backend Protocol

### WebFetchBackend Protocol

```python
class WebFetchBackend(Protocol):
  """Protocol for web fetch backend implementations.

  Defines the interface that all fetch backends must implement.
  Supports both synchronous Ollama native tools and async local backends.

  Implementations:
    - OllamaWebFetchBackend: Uses Ollama's native web_fetch function
    - LocalWebFetchBackend: Uses httpx + Trafilatura (future)
  """

  def fetch(
    self,
    url: str,
    *,
    content_type: str = "markdown",
    max_size_kb: int = 2048,
    timeout_seconds: int = 30,
  ) -> FetchedContent:
    """Fetch content from a URL.

    Args:
      url: URL to fetch.
      content_type: Output format ("markdown", "text", "html").
      max_size_kb: Maximum content size in KB.
      timeout_seconds: Fetch timeout in seconds.

    Returns:
      FetchedContent with extracted content.

    Raises:
      WebFetchError: If fetch fails.
    """
    ...
```

### OllamaWebFetchBackend Implementation

```python
class OllamaWebFetchBackend:
  """Web fetch backend using Ollama's native web_fetch function.

  Uses the Ollama Python SDK's built-in web_fetch capability.
  Requires an authenticated Client for cloud-based fetch.

  Features:
    - Native Ollama SDK integration
    - Built-in content extraction and summarization
    - Configurable output format

  Limitations:
    - Requires OLLAMA_API_KEY for cloud-based fetch
    - Limited control over fetch process
    - Cannot enforce all client-side guardrails
  """

  def __init__(
    self,
    client: "Client",
    timeout_seconds: int = 30,
    max_size_kb: int = 2048,
  ) -> None:
    """Initialize backend.

    Args:
      client: Authenticated Ollama Client instance.
      timeout_seconds: Default fetch timeout in seconds.
      max_size_kb: Default maximum content size in KB.
    """
    self._client = client
    self._timeout_seconds = timeout_seconds
    self._max_size_kb = max_size_kb
    self._backend_name = "ollama"

  def fetch(
    self,
    url: str,
    *,
    content_type: str = "markdown",
    max_size_kb: int | None = None,
    timeout_seconds: int | None = None,
  ) -> FetchedContent:
    """Fetch content via Ollama web_fetch function.

    Uses client.web_fetch() which returns structured content.

    Args:
      url: URL to fetch.
      content_type: Output format (default "markdown").
      max_size_kb: Max content size (uses default if None).
      timeout_seconds: Timeout (uses default if None).

    Returns:
      FetchedContent with extracted content.

    Raises:
      WebFetchError: If Ollama request fails or content exceeds limits.
    """
    max_size = max_size_kb or self._max_size_kb
    timeout = timeout_seconds or self._timeout_seconds

    try:
      # Use client's web_fetch method
      # Returns WebFetchResponse with .content, .title attributes
      response = self._client.web_fetch(url)

      # Extract content
      content = str(response.content or "")
      title = str(response.title or "")

      # Check size limit
      content_size_kb = len(content.encode("utf-8")) / 1024
      if content_size_kb > max_size:
        raise WebFetchError(
          f"Content size ({content_size_kb:.1f}KB) exceeds limit ({max_size}KB)",
          url=url,
          backend=self._backend_name,
          error_type="size_limit",
        )

      return FetchedContent(
        url=url,
        title=title,
        content=content,
        content_type=content_type,
        source=self._backend_name,
        metadata={"size_kb": content_size_kb},
      )

    except ConnectionError as e:
      raise WebFetchError(
        f"Failed to connect to Ollama server: {e}",
        url=url,
        backend=self._backend_name,
        cause=e,
        error_type="connection",
      ) from e
    except Exception as e:
      error_name = type(e).__name__
      if "Timeout" in error_name:
        raise WebFetchError(
          f"Fetch timeout after {timeout}s",
          url=url,
          backend=self._backend_name,
          cause=e,
          error_type="timeout",
        ) from e
      raise WebFetchError(
        f"Fetch failed: {e}",
        url=url,
        backend=self._backend_name,
        cause=e,
        error_type="unknown",
      ) from e
```

---

## Tool Implementation

### WebFetchTool Class

```python
class WebFetchTool(Tool):
  """Tool for fetching web content using pluggable backends.

  Fetches content from URLs and returns structured results.
  Uses a configurable backend (Ollama native or local httpx).
  Validates URLs through WebGuardrail before execution.

  Example:
    tool = WebFetchTool(backend=OllamaWebFetchBackend(client))
    result = tool.execute(url="https://example.com", content_type="markdown")
  """

  def __init__(
    self,
    backend: WebFetchBackend | None = None,
    guardrail: WebGuardrail | None = None,
  ) -> None:
    """Initialize WebFetchTool with optional backend and guardrail.

    Args:
      backend: Optional backend for web fetch (defaults to None).
      guardrail: Optional guardrail for URL validation.
    """
    super().__init__(guardrail=guardrail)
    self._backend = backend

  @property
  def name(self) -> str:
    """Tool name used for registration."""
    return "web_fetch"

  @property
  def description(self) -> str:
    """Tool description shown to the LLM."""
    return "Fetch content from a web URL"

  def get_schema(self) -> dict[str, Any]:
    """Return Ollama-compatible schema.

    Returns:
      Schema with url, content_type, and max_size_kb parameters.
    """
    return {
      "type": "function",
      "function": {
        "name": self.name,
        "description": self.description,
        "parameters": {
          "type": "object",
          "properties": {
            "url": {
              "type": "string",
              "description": "URL to fetch",
            },
            "content_type": {
              "type": "string",
              "description": "Output format (markdown, text, html)",
              "enum": ["markdown", "text", "html"],
              "default": "markdown",
            },
            "max_size_kb": {
              "type": "integer",
              "description": "Maximum content size in KB",
              "default": 2048,
              "minimum": 1,
              "maximum": 10240,
            },
          },
          "required": ["url"],
        },
      },
    }

  def execute(self, **kwargs: Any) -> ToolResult:
    """Execute web fetch with the given parameters.

    Steps:
      1. Validate parameters via guardrail if provided.
      2. Extract and validate URL parameter.
      3. Delegate to backend for fetch execution.
      4. Return structured results or error.

    Args:
      **kwargs: Must contain 'url', optionally 'content_type', 'max_size_kb'.

    Returns:
      ToolResult with FetchedContent dict or error.
    """
    # Step 1: Extract URL parameter
    url = kwargs.get("url", "")
    if not url:
      return ToolResult(
        success=False,
        result={},
        error="URL is required",
      )

    # Strip whitespace and validate
    url = url.strip()
    if not url:
      return ToolResult(
        success=False,
        result={},
        error="URL cannot be empty or whitespace",
      )

    # Step 2: Extract optional parameters
    content_type = kwargs.get("content_type", "markdown")
    if content_type not in ("markdown", "text", "html"):
      content_type = "markdown"

    max_size_kb = kwargs.get("max_size_kb", 2048)
    if not isinstance(max_size_kb, int):
      try:
        max_size_kb = int(max_size_kb)
      except (ValueError, TypeError):
        max_size_kb = 2048
    max_size_kb = max(1, min(10240, max_size_kb))

    # Step 3: Validate via guardrail
    if self._guardrail:
      validation = self._guardrail.validate_url(url)
      if not validation.valid:
        return ToolResult(
          success=False,
          result={},
          error=validation.reason,
        )

    # Step 4: Check backend
    if self._backend is None:
      return ToolResult(
        success=False,
        result={},
        error="No backend configured for web fetch",
      )

    # Step 5: Execute fetch
    try:
      content = self._backend.fetch(
        url=url,
        content_type=content_type,
        max_size_kb=max_size_kb,
      )

      return ToolResult(
        success=True,
        result=content.to_dict(),
      )

    except WebFetchError as e:
      logger.error(f"Web fetch error: {e}")
      return ToolResult(
        success=False,
        result={},
        error=str(e),
      )
    except Exception as e:
      logger.error(f"Unexpected error in web fetch: {e}")
      return ToolResult(
        success=False,
        result={},
        error=f"Fetch failed: {e}",
      )
```

---

## Configuration Schema

### WebFetchToolConfig

```python
@dataclass(frozen=True)
class WebFetchToolConfig(ToolConfig):
  """Web fetch tool configuration.

  Attributes:
    backend: Backend to use ("ollama" or "local").
    timeout_seconds: Fetch timeout in seconds.
    max_size_kb: Maximum content size in KB.
    max_redirects: Maximum redirect hops to follow.
    content_type: Default output format ("markdown", "text", "html").
    domain_allowlist: Domains to allow (empty = all allowed).
    domain_blocklist: Domains to block (empty = none blocked).
    block_private_cidrs: Whether to block private IP ranges.
    block_metadata_endpoints: Whether to block cloud metadata IPs.
    require_https: Whether to require HTTPS (block HTTP).
    follow_redirects: Whether to follow redirects.
    validate_redirects: Whether to revalidate each redirect URL.
  """

  backend: str = "ollama"
  timeout_seconds: int = 30
  max_size_kb: int = 2048
  max_redirects: int = 5
  content_type: str = "markdown"
  domain_allowlist: tuple[str, ...] = ()
  domain_blocklist: tuple[str, ...] = ()
  block_private_cidrs: bool = True
  block_metadata_endpoints: bool = True
  require_https: bool = True
  follow_redirects: bool = True
  validate_redirects: bool = True
```

### Updated ToolsConfig

```python
@dataclass(frozen=True)
class ToolsConfig:
  """All tool configurations.

  Attributes:
    list: List tool config.
    read: Read tool config.
    write: Write tool config.
    update: Update tool config.
    search: Search tool config.
    agent: Agent tool config.
    git: Git tool config.
    mkdir: Mkdir tool config.
    websearch: Web search tool config.
    webfetch: Web fetch tool config.
  """

  list: ListToolConfig = field(default_factory=ListToolConfig)
  read: ReadToolConfig = field(default_factory=ReadToolConfig)
  write: WriteToolConfig = field(default_factory=WriteToolConfig)
  update: UpdateToolConfig = field(default_factory=UpdateToolConfig)
  search: SearchToolConfig = field(default_factory=SearchToolConfig)
  agent: AgentToolConfig = field(default_factory=AgentToolConfig)
  git: GitToolConfig = field(default_factory=GitToolConfig)
  mkdir: MkdirToolConfig = field(default_factory=MkdirToolConfig)
  websearch: WebSearchToolConfig = field(default_factory=WebSearchToolConfig)
  webfetch: WebFetchToolConfig = field(default_factory=WebFetchToolConfig)
```

---

## Guardrail Integration

### WebGuardrail Extension for WebFetch

The existing `WebGuardrail` needs a new method for URL-specific validation:

```python
def validate_url(self, url: str) -> ValidationResult:
  """Validate a URL for web fetch.

  Steps:
    1. Validate URL format (scheme, host, etc.).
    2. Check for SSRF attempts (private IPs, metadata endpoints).
    3. Check domain allowlist if configured.
    4. Check domain blocklist if configured.
    5. Check HTTPS requirement if configured.

  Args:
    url: URL string to validate.

  Returns:
    ValidationResult with success/failure and reason.
  """
  # Parse URL
  try:
    from urllib.parse import urlparse
    parsed = urlparse(url)
  except Exception:
    return ValidationResult(valid=False, reason="Invalid URL format")

  # Check scheme
  if self._config.require_https and parsed.scheme != "https":
    return ValidationResult(valid=False, reason="Only HTTPS URLs are allowed")

  # Extract host
  host = parsed.hostname
  if not host:
    return ValidationResult(valid=False, reason="URL must have a host")

  # Check SSRF (private IPs, metadata endpoints)
  if self._config.block_private_cidrs:
    ssrf_error = self._check_ssrf_for_host(host)
    if ssrf_error:
      return ValidationResult(valid=False, reason=ssrf_error)

  # Check domain allowlist
  if self._config.domain_allowlist:
    if not self._domain_matches_list(host, self._config.domain_allowlist):
      return ValidationResult(valid=False, reason=f"Domain not in allowlist: {host}")

  # Check domain blocklist
  if self._config.domain_blocklist:
    if self._domain_matches_list(host, self._config.domain_blocklist):
      return ValidationResult(valid=False, reason=f"Domain is blocked: {host}")

  return ValidationResult(valid=True)

def _check_ssrf_for_host(self, host: str) -> str | None:
  """Check if a host resolves to a private IP.

  Resolves the hostname and checks against private CIDRs.
  Also checks for metadata IP addresses.

  Args:
    host: Hostname or IP address.

  Returns:
    Error message if SSRF detected, None if safe.
  """
  # Check for localhost
  if host.lower() in ("localhost", "localhost.localdomain"):
    return "SSRF blocked: localhost detected"

  # Check for IP address patterns
  import ipaddress
  try:
    ip = ipaddress.ip_address(host)
    # Check against private CIDRs
    for cidr in PRIVATE_CIDRS:
      if ip in cidr:
        return f"SSRF blocked: private IP address detected ({host})"
    # Check metadata IP
    if str(ip) in METADATA_IPS:
      return "SSRF blocked: cloud metadata endpoint detected"
  except ValueError:
    # Not an IP, resolve hostname
    if not self._is_safe_domain(host):
      return f"SSRF blocked: domain may resolve to private IP ({host})"

  return None
```

---

## SSRF Protection Details

### Private CIDR Ranges (from WebGuardrail)

| CIDR | Description |
|------|-------------|
| `10.0.0.0/8` | RFC 1918 Private (Class A) |
| `172.16.0.0/12` | RFC 1918 Private (Class B) |
| `192.168.0.0/16` | RFC 1918 Private (Class C) |
| `127.0.0.0/8` | Loopback |
| `169.254.0.0/16` | Link-local (cloud metadata) |
| `::1/128` | IPv6 loopback |
| `fe80::/10` | IPv6 link-local |
| `fc00::/7` | IPv6 ULA |

### Cloud Metadata Endpoints

| IP | Cloud Provider |
|----|----------------|
| `169.254.169.254` | AWS/GCP/Azure |

### URL Validation Attacks Blocked

| Attack Vector | Protection |
|---------------|------------|
| Direct private IP | IP validation against CIDRs |
| DNS rebinding | DNS resolution at validation time |
| URL-encoded IPs | Decode before validation |
| Hex-encoded IPs | Parse 0x notation |
| Decimal-encoded IPs | Parse decimal notation |
| IPv6 private | IPv6 CIDR validation |
| IPv4-mapped IPv6 | Strip ::ffff: prefix |
| Redirect chains | Validate each redirect URL |
| Localhost | Hostname blacklist |

---

## Error Types

### WebFetchError Categories

| error_type | Description | Example |
|------------|-------------|---------|
| `invalid_url` | Malformed URL | Missing scheme, invalid characters |
| `ssrf` | SSRF attempt blocked | Private IP, metadata endpoint |
| `domain_blocked` | Domain in blocklist | Internal domains |
| `domain_not_allowed` | Domain not in allowlist | Non-whitelisted domain |
| `connection` | Connection failed | DNS failure, network error |
| `timeout` | Request timed out | Exceeded timeout_seconds |
| `size_limit` | Content too large | Exceeded max_size_kb |
| `redirect_limit` | Too many redirects | Exceeded max_redirects |
| `https_required` | HTTP not allowed | require_https=True |
| `unknown` | Other errors | Backend-specific errors |

---

## File Structure

### New Files

| File | Purpose |
|------|---------|
| `src/yoker/tools/webfetch.py` | WebFetchTool implementation |
| `tests/test_tools/test_webfetch.py` | Unit tests |

### Modified Files

| File | Changes |
|------|---------|
| `src/yoker/tools/web_backend.py` | Add `WebFetchBackend`, `OllamaWebFetchBackend` |
| `src/yoker/tools/web_types.py` | Add `FetchedContent`, `WebFetchError` |
| `src/yoker/tools/web_guardrail.py` | Add `validate_url()` method |
| `src/yoker/tools/__init__.py` | Register `WebFetchTool` |
| `src/yoker/config/schema.py` | Add `WebFetchToolConfig` |
| `src/yoker/agent.py` | Add `WebFetchTool` to registry |
| `demos/webfetch.md` | Demo script |

---

## Configuration Example

### TOML Configuration

```toml
[tools.webfetch]
enabled = true
backend = "ollama"
timeout_seconds = 30
max_size_kb = 2048
max_redirects = 5
content_type = "markdown"
domain_allowlist = []
domain_blocklist = ["*.internal", "*.local", "*.localhost"]
block_private_cidrs = true
block_metadata_endpoints = true
require_https = true
follow_redirects = true
validate_redirects = true
```

---

## Integration with Agent

### Tool Registration

```python
# In src/yoker/tools/__init__.py

from .webfetch import WebFetchTool

def create_default_registry(config: Config | None = None) -> ToolRegistry:
  """Create default tool registry with optional config."""
  registry = ToolRegistry()

  # ... other tools ...

  # WebFetchTool
  if config and config.tools.webfetch.enabled:
    from .web_backend import OllamaWebFetchBackend
    from .web_guardrail import WebGuardrail, WebGuardrailConfig

    guardrail_config = WebGuardrailConfig(
      domain_allowlist=config.tools.webfetch.domain_allowlist,
      domain_blocklist=config.tools.webfetch.domain_blocklist,
      block_private_cidrs=config.tools.webfetch.block_private_cidrs,
      timeout_seconds=config.tools.webfetch.timeout_seconds,
    )
    guardrail = WebGuardrail(config=guardrail_config)

    # Backend selection
    if config.tools.webfetch.backend == "ollama":
      backend = OllamaWebFetchBackend(client=ollama_client)
    else:
      # Future: LocalWebFetchBackend
      backend = None

    registry.register(WebFetchTool(backend=backend, guardrail=guardrail))

  return registry
```

---

## Testing Strategy

### Unit Tests

| Test Category | Tests |
|---------------|-------|
| URL Validation | Empty, whitespace, invalid scheme, missing host |
| SSRF Protection | Private IPs, metadata IPs, DNS rebinding, encoded IPs |
| Domain Filtering | Allowlist, blocklist, wildcard matching |
| Backend Selection | Ollama backend, future local backend |
| Error Handling | Connection errors, timeouts, size limits |
| Configuration | Default values, custom values |

### Mocked Backend Tests

```python
# tests/test_tools/test_webfetch.py

import pytest
from unittest.mock import Mock, patch
from yoker.tools.webfetch import WebFetchTool
from yoker.tools.web_backend import OllamaWebFetchBackend
from yoker.tools.web_types import FetchedContent, WebFetchError

class TestWebFetchTool:
  """Tests for WebFetchTool."""

  def test_execute_valid_url(self, mock_backend):
    """Test fetch with valid URL."""
    tool = WebFetchTool(backend=mock_backend)
    result = tool.execute(url="https://example.com")
    assert result.success
    assert "content" in result.result

  def test_execute_empty_url(self):
    """Test fetch with empty URL."""
    tool = WebFetchTool(backend=None)
    result = tool.execute(url="")
    assert not result.success
    assert "required" in result.error.lower()

  def test_execute_private_ip_blocked(self, mock_guardrail):
    """Test SSRF protection blocks private IPs."""
    tool = WebFetchTool(backend=None, guardrail=mock_guardrail)
    result = tool.execute(url="http://192.168.1.1/secret")
    assert not result.success
    assert "ssrf" in result.error.lower()

  def test_execute_domain_blocked(self, mock_guardrail):
    """Test domain blocklist."""
    tool = WebFetchTool(backend=None, guardrail=mock_guardrail)
    result = tool.execute(url="https://internal.local/data")
    assert not result.success
    assert "blocked" in result.error.lower()

  def test_size_limit_exceeded(self, mock_backend):
    """Test content size limit."""
    mock_backend.fetch.side_effect = WebFetchError(
      "Content size exceeds limit",
      error_type="size_limit",
    )
    tool = WebFetchTool(backend=mock_backend)
    result = tool.execute(url="https://example.com/large")
    assert not result.success
    assert "size" in result.error.lower()
```

---

## Action Items

### Phase 1: Core Implementation

1. **Create `web_types.py` additions**
   - Add `FetchedContent` dataclass
   - Add `WebFetchError` exception class
   - Add exports to `__all__`

2. **Create `web_backend.py` additions**
   - Add `WebFetchBackend` protocol
   - Add `OllamaWebFetchBackend` implementation
   - Add exports to `__all__`

3. **Extend `web_guardrail.py`**
   - Add `validate_url()` method
   - Add `_check_ssrf_for_host()` helper
   - Add configuration for fetch-specific options

4. **Create `webfetch.py`**
   - Implement `WebFetchTool` class
   - Wire up backend and guardrail
   - Add schema and execute method

5. **Update `config/schema.py`**
   - Add `WebFetchToolConfig` dataclass
   - Update `ToolsConfig` to include `webfetch`

6. **Update `__init__.py`**
   - Register `WebFetchTool` in registry
   - Export new classes

7. **Update `agent.py`**
   - Add `WebFetchTool` to `_build_tool_registry()`

8. **Create tests**
   - `tests/test_tools/test_webfetch.py`
   - Test all validation, SSRF, domain filtering

9. **Create demo script**
   - `demos/webfetch.md`
   - Show fetch of public URL

### Phase 2: Local Backend (Future)

1. Create `LocalWebFetchBackend` using httpx + Trafilatura
2. Implement content extraction with configurable precision/recall
3. Add SSRF protection at connection level
4. Implement redirect validation

---

## Checklist

- [ ] FetchedContent dataclass defined
- [ ] WebFetchError exception defined
- [ ] WebFetchBackend protocol defined
- [ ] OllamaWebFetchBackend implemented
- [ ] WebGuardrail.validate_url() implemented
- [ ] WebFetchTool implemented
- [ ] WebFetchToolConfig defined
- [ ] ToolsConfig updated
- [ ] Tool registered in `__init__.py`
- [ ] Tool added to `agent.py`
- [ ] Unit tests written
- [ ] Demo script created
- [ ] Documentation updated