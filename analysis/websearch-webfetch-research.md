# WebSearch and WebFetch Tool Research Summary

**Research Date:** 2026-05-04
**Full Report:** `research/2026-05-04-websearch-webfetch-tools/README.md`

---

## Executive Summary

**Architecture Decision: Pluggable Backend System**

WebSearch and WebFetch tools will use a pluggable backend architecture:
- **Primary implementation**: Ollama native tools (web_search, web_fetch) for fast deployment
- **Future implementation**: Local backends (DDGS + Trafilatura) for offline-first operation
- **Configuration-driven**: Backend selection via config file

This hybrid approach enables quick implementation while preserving extensibility.

---

## Approach Comparison

| Aspect | Ollama Native | Custom (DDGS + Trafilatura) |
|--------|---------------|----------------------------|
| **Offline Operation** | No (requires cloud) | Yes (local processing) |
| ** **Summarization** | Built-in (server-side) | Requires separate LLM call** |
| **API Key Required** | Yes (OLLAMA_API_KEY) | No |
| **Guardrail Control** | None | Full |
| **Search Backend** | Unknown | Selectable (bing, google, ddg, etc.) |
| **Content Extraction** | Unknown | Configurable (precision/recall) |
| **Max Results** | 10 | Unlimited |
| **Cost** | Free with account | Free |

**Key Insight**: Ollama's native tools handle summarization server-side, reducing token usage and round-trips. Local implementation would require fetching raw content and then sending to LLM for processing.

---

## Recommended Architecture

### Pluggable Backend Pattern

```python
# Abstract interface
class WebSearchBackend(Protocol):
    async def search(self, query: str, max_results: int) -> list[SearchResult]: ...

class WebFetchBackend(Protocol):
    async def fetch(self, url: str) -> FetchedContent: ...

# Implementations
class OllamaWebSearchBackend(WebSearchBackend):
    """Uses Ollama's native web_search tool"""

class OllamaWebFetchBackend(WebFetchBackend):
    """Uses Ollama's native web_fetch tool with built-in summarization"""

class LocalWebSearchBackend(WebSearchBackend):
    """Uses DDGS library for local search"""

class LocalWebFetchBackend(WebFetchBackend):
    """Uses httpx + Trafilatura for local content extraction"""

# Configuration
[tools.websearch]
backend = "ollama"  # or "local" when implemented

[tools.webfetch]
backend = "ollama"  # or "local" when implemented
```

### Implementation Order

| Phase | Task | Backend | Priority |
|-------|------|---------|----------|
| 1 | 2.12 WebSearchTool | OllamaWebSearchBackend | High |
| 1 | 2.13 WebFetchTool | OllamaWebFetchBackend | High |
| 2 | 2.13.1 Local WebSearch | LocalWebSearchBackend (DDGS) | Medium |
| 2 | 2.13.2 Local WebFetch | LocalWebFetchBackend (httpx + Trafilatura) | Medium |

---

## Recommended Implementation

### WebSearch Tool

- **Library**: DDGS (duckduckgo-search)
- **Backends**: bing, brave, duckduckgo, google, mojeek, yandex, yahoo, wikipedia
- **Features**: Multi-backend, proxy support, DHT network caching

```python
from ddgs import DDGS
results = DDGS().text("query", max_results=10, backend="duckduckgo")
# Returns: [{"title": "...", "href": "...", "body": "..."}]
```

### WebFetch Tool

- **HTTP Client**: httpx (already in dependencies)
- **Content Extraction**: Trafilatura (0.958 F1 score)
- **Output Formats**: markdown, JSON, HTML, TXT, XML

```python
import httpx
from trafilatura import extract

async with httpx.AsyncClient(timeout=30) as client:
    response = await client.get(url)
    content = extract(response.text, output_format="markdown", favor_precision=True)
```

---

## Security Guardrails

| Security Measure | Recommended Value | Implementation |
|-----------------|-------------------|----------------|
| Domain Whitelist | Configurable | Pattern matching (exact + wildcard subdomains) |
| SSRF Protection | Required | Block private IPs (10.x, 192.168.x, 169.254.x, 127.x, 0.0.0.0/8) |
| DNS Rebinding | Required | Resolve at validation AND connection time |
| Redirect Limits | 5 max | Revalidate each target against allowlist |
| Content Size | 2MB max | Track response size during streaming |
| Timeout | 30 seconds | Built into httpx AsyncClient |
| Scheme | HTTPS only | Reject http:// in production |

### WebGuardrail Configuration

```toml
[tools.websearch]
enabled = true
backend = "duckduckgo"
max_results = 10
timeout_seconds = 30

[tools.webfetch]
enabled = true
timeout_seconds = 30
max_size_kb = 2048
output_format = "markdown"
max_redirects = 5

[permissions.web_domains]
allow = ["*.github.com", "docs.python.org", "pypi.org"]
block = ["*.internal", "*.local"]
```

---

## Files to Create

### Phase 1: Ollama Backend

| File | Purpose |
|------|---------|
| `src/yoker/tools/websearch.py` | WebSearchTool with pluggable backend |
| `src/yoker/tools/webfetch.py` | WebFetchTool with pluggable backend |
| `src/yoker/tools/web_backend.py` | Backend protocol and Ollama implementations |
| `src/yoker/tools/web_guardrail.py` | WebGuardrail implementation |
| `src/yoker/config/schema.py` | Add WebSearchToolConfig, WebFetchToolConfig |
| `tests/test_tools/test_websearch.py` | Unit tests (mocked backend) |
| `tests/test_tools/test_webfetch.py` | Unit tests (mocked backend) |
| `demos/websearch.md` | Demo script |
| `demos/webfetch.md` | Demo script |

### Phase 2: Local Backend (Future)

| File | Purpose |
|------|---------|
| `src/yoker/tools/web_backends/local_search.py` | LocalWebSearchBackend (DDGS) |
| `src/yoker/tools/web_backends/local_fetch.py` | LocalWebFetchBackend (httpx + Trafilatura) |
| `tests/test_tools/test_web_backends/` | Backend-specific tests |

---

## Dependencies

### Phase 1: Ollama Backend

No new dependencies required - uses existing Ollama integration.

### Phase 2: Local Backend (Future)

Add to `pyproject.toml`:

```toml
dependencies = [
  # ... existing ...
  "ddgs>=8.0.0",        # Web search (local backend)
  "trafilatura>=2.0.0", # Content extraction (local backend)
]
```

---

## Key Takeaways

1. **Pluggable architecture** - Backend selection via configuration
2. **Start with Ollama** - Fast implementation with built-in summarization
3. **Plan for local backends** - DDGS + Trafilatura for offline-first future
4. **Comprehensive SSRF guardrails essential** - domain whitelisting, private IP blocking, redirect validation
5. **No immediate dependencies needed** - Phase 1 uses existing Ollama integration