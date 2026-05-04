# WebSearch and WebFetch Tool Implementation Research

**Research Date:** 2026-05-04
**Purpose:** Investigate implementation approaches for WebSearch and WebFetch tools in yoker, comparing Ollama native support vs. custom HTTP client implementations.
**Previous Research:** none

---

## Executive Summary

Ollama provides native WebSearch and WebFetch capabilities as of version 0.18.1 (March 2026), offering immediate integration with minimal setup. However, custom implementations using libraries like DDGS (for search) and Trafilatura (for content extraction) provide greater control, offline capability, and avoid external API dependencies. For yoker's Ollama-first, library-first architecture, a hybrid approach is recommended: use DDGS for WebSearch and httpx+Trafilatura for WebFetch, both wrapped with comprehensive SSRF guardrails.

---

## 1. Ollama Native Support

### Key Findings

- Ollama 0.18.1 (March 2026) introduced native `web_search` and `web_fetch` tools [1]
- Both tools require an Ollama API key from ollama.com/settings/keys [1]
- WebSearch endpoint: `POST https://ollama.com/api/web_search` with `query` and `max_results` (default 5, max 10) [1]
- WebFetch endpoint: `POST https://ollama.com/api/web_fetch` with `url` parameter [1]
- Returns structured JSON with title, URL, content snippets (search) or title, content, links (fetch) [1]
- Works with Python SDK: `ollama.web_search()` and `ollama.web_fetch()` [1]

### Limitations

- **Requires external API key** - conflicts with yoker's offline-first design goal
- **External dependency** - all web requests route through Ollama's cloud service
- **No control over guardrails** - cannot implement domain whitelists, rate limits, or content filtering
- **Limited configuration** - max 10 results per search, no backend selection

### Details

The native implementation is convenient for users already using Ollama's cloud services. Authentication uses the `OLLAMA_API_KEY` environment variable or Authorization header. MCP server integration is provided for tools like Cline and Codex [1].

**Sources:**
- [Web search - Ollama](https://docs.ollama.com/capabilities/web-search)

---

## 2. Custom HTTP Client Approach

### WebSearch: DDGS Library

#### Key Findings

- DDGS (formerly duckduckgo_search) is a metasearch library aggregating results from multiple backends [2]
- Supports multiple search engines: bing, brave, duckduckgo, google, mojeek, yandex, yahoo, wikipedia [2]
- Free and open source (MIT license), ~4.4 million monthly downloads [2]
- `text()` method returns list of dicts with title, href, body [2]
- Supports proxy configuration for rate limit mitigation [2]
- DHT network (beta) provides 90% faster repeated queries via P2P caching [2]

#### Limitations

- No official API - works by scraping, subject to rate limits (HTTP 202) [2]
- Rate limit handling requires retry logic or proxy rotation [2]
- DHT network not available on Windows [2]
- Python >= 3.10 required [2]

### WebFetch: httpx + Trafilatura

#### Key Findings

- Trafilatura achieves 0.958 F1 score on content extraction benchmarks [3]
- Multiple output formats: markdown, JSON, HTML, TXT, XML [3]
- Metadata extraction: title, author, date, site name [3]
- `extract()` function with precision/recall tuning options [3]
- `fast=True` option provides ~2x performance by skipping fallback algorithms [3]
- Can work with pre-fetched HTML from httpx [3]

#### httpx Integration

- yoker already has httpx>=0.25.0 as a dependency
- Async and streaming support built-in
- Can pass HTML content to Trafilatura's `extract()` function
- Full control over timeouts, redirects, and size limits

### Details

```python
# WebSearch with DDGS
from ddgs import DDGS
results = DDGS().text("python programming", max_results=5)
# Returns: [{"title": "...", "href": "...", "body": "..."}]

# WebFetch with httpx + Trafilatura
import httpx
from trafilatura import extract

async def fetch_url(url: str) -> str:
  async with httpx.AsyncClient(timeout=30.0) as client:
    response = await client.get(url)
    return extract(response.text, output_format="markdown")
```

**Sources:**
- [DDGS GitHub](https://github.com/deedy5/ddgs)
- [Trafilatura Python Usage](https://trafilatura.readthedocs.io/en/latest/usage-python.html)

---

## 3. Paid Search API Alternatives

### Comparison Table

| Service | Free Tier | Cost (per 1K queries) | Rate Limits | Notes |
|---------|-----------|----------------------|-------------|-------|
| DDGS | Unlimited | Free | Scraping-based | Requires retry/proxy handling |
| Ollama Native | Requires API key | Free with account | Unknown | Cloud-dependent |
| SerpAPI | 250/month | $75 for 5K ($0.015/search) | 1K/hour (dev tier) | Full SERP data |
| DataForSEO | None | $0.0006/search | Custom | Cheapest for bulk |
| Scrape.do | None | $1.16/1K | Custom | 21.6x cheaper than SerpAPI |
| Google Custom Search | 100/day | $5/1K | 100/day free | Site-specific only, not full web |

### Analysis

For yoker's use case:
- **DDGS is optimal** - free, multiple backends, no API key required
- **Google Custom Search API is NOT suitable** - limited to site-specific search, not general web search
- **SerpAPI alternatives** are expensive for hobbyist/personal use

**Sources:**
- [SerpApi Pricing](https://serpapi.com/pricing)
- [Cheapest SERP API in 2026](https://proxies.sx/blog/cheapest-serp-api-comparison-2026)

---

## 4. Security Guardrails

### Key Findings

Industry-standard security patterns for web fetch tools [4][5]:

| Security Measure | Implementation |
|-----------------|----------------|
| **Domain Whitelist** | Pattern matching (exact + wildcard subdomains) |
| **SSRF Protection** | Block private IPs (10.x, 192.168.x, 169.254.x, 127.x, 0.0.0.0/8) |
| **DNS Rebinding** | Resolve host at validation AND connection time |
| **Redirect Limits** | 3-5 max redirects, revalidate each target against allowlist |
| **Content Size** | 10KB-2MB limits (default: 2MB) |
| **Timeout** | 10-30 seconds (default: 10s) |
| **Scheme Restriction** | HTTPS-only in production |

### Domain Whitelist Pattern

```python
def is_domain_allowed(host: str, allowlist: list[str]) -> bool:
  for entry in allowlist:
    if host == entry or host.endswith("." + entry):
      return True
  return False
```

### SSRF IP Blocking

```python
PRIVATE_IP_RANGES = [
  ipaddress.ip_network("10.0.0.0/8"),
  ipaddress.ip_network("172.16.0.0/12"),
  ipaddress.ip_network("192.168.0.0/16"),
  ipaddress.ip_network("169.254.0.0/16"),  # link-local
  ipaddress.ip_network("127.0.0.0/8"),
  ipaddress.ip_network("0.0.0.0/8"),
]
```

### Redirect Validation

```python
MAX_REDIRECTS = 5

async def validate_redirect(url: str, allowlist: list[str]) -> bool:
  parsed = urllib.parse.urlparse(url)
  if parsed.scheme not in ("http", "https"):
    return False
  return is_domain_allowed(parsed.hostname, allowlist)
```

**Sources:**
- [AI Agent Policy URL Security: SSRF Defenses](https://cordum.io/blog/ai-agent-policy-url-security-ssrf)
- [Security: add URL allowlist · PR #19042](https://github.com/openclaw/openclaw/pull/19042)

---

## 5. Trade-off Analysis

### Control vs. Dependency

| Aspect | Ollama Native | Custom (DDGS + Trafilatura) |
|--------|---------------|----------------------------|
| **Offline Operation** | No (requires cloud) | Yes (local processing) |
| **API Key Required** | Yes | No |
| **Guardrail Control** | None | Full |
| **Search Backend** | Unknown | Selectable (bing, google, ddg, etc.) |
| **Content Extraction** | Unknown | Configurable (precision/recall) |
| **Maintenance Burden** | None (managed service) | Library updates, rate limit handling |

### Feature Parity

| Feature | Ollama Native | Custom Implementation |
|---------|---------------|----------------------|
| Domain whitelisting | No | Yes |
| Blacklisting | No | Yes |
| Content size limits | Unknown | Yes |
| Timeout enforcement | Unknown | Yes |
| Rate limiting | Unknown | Yes |
| Redirect control | Unknown | Yes |
| Output format control | Fixed | Configurable |

### Guardrail Implementation

Custom implementation makes guardrails significantly easier:
- **Domain checks**: Before any HTTP request
- **Size limits**: httpx response streaming with size tracking
- **Timeouts**: Built into httpx AsyncClient
- **Rate limiting**: Application-level throttling
- **SSRF protection**: Pre-flight IP validation

---

## 6. Recommendation

### Recommended Approach: Custom Implementation

**WebSearch Tool:**
- Use DDGS library for multi-backend search
- Wrap with `WebGuardrail` for domain filtering
- Support configurable backend selection

**WebFetch Tool:**
- Use httpx (already a dependency) for HTTP fetching
- Use Trafilatura for content extraction
- Support multiple output formats (markdown, JSON, text)

**Justification:**
1. **Aligns with yoker's Ollama-first design** - no external cloud dependencies for web access
2. **Library-first architecture** - tools are self-contained, testable without network
3. **Static permissions** - guardrails defined upfront in configuration
4. **Full guardrail control** - SSRF protection, domain whitelists, content limits
5. **No additional API keys** - DDGS is free, no rate limits with proper handling

### Near-Miss Tier

**Ollama Native Integration** (Alternative)
- **Why it nearly made the cut**: Zero implementation effort, immediate availability
- **Why ranked below**: Conflicts with offline-first design, external dependency, no guardrail control
- **Best for**: Users who already use Ollama cloud services and don't need custom security policies

---

## 7. Implementation Outline

### Configuration Schema

```toml
[tools.websearch]
enabled = true
backend = "duckduckgo"  # or "bing", "brave", "google"
max_results = 10
timeout_seconds = 30

[tools.webfetch]
enabled = true
timeout_seconds = 30
max_size_kb = 2048
output_format = "markdown"  # or "json", "text", "html"
max_redirects = 5

[permissions.web_domains]
allow = ["*.github.com", "docs.python.org", "pypi.org"]
block = ["*.internal", "*.local"]
```

### WebGuardrail Class

```python
@dataclass(frozen=True)
class WebGuardrailConfig:
  allowed_domains: tuple[str, ...] = ()
  blocked_domains: tuple[str, ...] = ()
  max_size_kb: int = 2048
  timeout_seconds: int = 30
  max_redirects: int = 5
  allow_private_ips: bool = False

class WebGuardrail(Guardrail):
  def validate(self, tool_name: str, params: dict[str, Any]) -> ValidationResult:
    if tool_name == "webfetch":
      return self._validate_url(params.get("url"))
    if tool_name == "websearch":
      return self._validate_search(params)
    return ValidationResult(valid=True)

  def _validate_url(self, url: str | None) -> ValidationResult:
    # 1. Parse URL
    # 2. Check scheme (https only in production)
    # 3. Check domain against allowlist/blocklist
    # 4. Resolve DNS and check for private IPs
    # 5. Return validation result
    ...
```

### WebSearchTool Implementation

```python
class WebSearchTool(Tool):
  def __init__(self, guardrail: WebGuardrail | None = None, backend: str = "duckduckgo"):
    self._guardrail = guardrail
    self._backend = backend

  @property
  def name(self) -> str:
    return "websearch"

  def get_schema(self) -> dict[str, Any]:
    return {
      "type": "function",
      "function": {
        "name": "websearch",
        "description": "Search the web for information",
        "parameters": {
          "type": "object",
          "properties": {
            "query": {"type": "string", "description": "Search query"},
            "max_results": {"type": "integer", "default": 5, "maximum": 10}
          },
          "required": ["query"]
        }
      }
    }

  def execute(self, query: str, max_results: int = 5) -> ToolResult:
    # Validate with guardrail
    if self._guardrail:
      result = self._guardrail.validate("websearch", {"query": query})
      if not result.valid:
        return ToolResult(success=False, result="", error=result.reason)

    # Execute search
    with DDGS() as ddgs:
      results = ddgs.text(query, max_results=max_results, backend=self._backend)

    return ToolResult(success=True, result={"results": results})
```

### WebFetchTool Implementation

```python
class WebFetchTool(Tool):
  def __init__(self, guardrail: WebGuardrail | None = None, output_format: str = "markdown"):
    self._guardrail = guardrail
    self._output_format = output_format

  @property
  def name(self) -> str:
    return "webfetch"

  def get_schema(self) -> dict[str, Any]:
    return {
      "type": "function",
      "function": {
        "name": "webfetch",
        "description": "Fetch and extract content from a web page",
        "parameters": {
          "type": "object",
          "properties": {
            "url": {"type": "string", "description": "URL to fetch"},
            "output_format": {"type": "string", "enum": ["markdown", "json", "text"]}
          },
          "required": ["url"]
        }
      }
    }

  async def execute(self, url: str, output_format: str | None = None) -> ToolResult:
    # Validate URL with guardrail
    if self._guardrail:
      result = self._guardrail.validate("webfetch", {"url": url})
      if not result.valid:
        return ToolResult(success=False, result="", error=result.reason)

    # Fetch with httpx
    async with httpx.AsyncClient(timeout=self._guardrail.timeout_seconds) as client:
      response = await client.get(url, follow_redirects=True, max_redirects=self._guardrail.max_redirects)
      response.raise_for_status()

      # Check size limit
      content_size = len(response.content) / 1024
      if content_size > self._guardrail.max_size_kb:
        return ToolResult(success=False, result="", error=f"Content exceeds size limit")

      # Extract with Trafilatura
      extracted = extract(
        response.text,
        output_format=output_format or self._output_format,
        favor_precision=True,
        with_metadata=True
      )

    return ToolResult(success=True, result=extracted)
```

### Files to Create/Modify

| File | Purpose |
|------|---------|
| `src/yoker/tools/websearch.py` | WebSearchTool implementation |
| `src/yoker/tools/webfetch.py` | WebFetchTool implementation |
| `src/yoker/tools/web_guardrail.py` | WebGuardrail implementation |
| `src/yoker/config/schema.py` | Add WebSearchToolConfig, WebFetchToolConfig |
| `src/yoker/tools/__init__.py` | Export and register new tools |
| `src/yoker/tools/path_guardrail.py` | Add to `_FILESYSTEM_TOOLS` (not needed for web) |
| `tests/test_tools/test_websearch.py` | Unit tests |
| `tests/test_tools/test_webfetch.py` | Unit tests |
| `demos/websearch.md` | Demo script |
| `demos/webfetch.md` | Demo script |

---

## Key Takeaways

1. **Custom implementation is recommended** for yoker's offline-first, library-first architecture
2. **DDGS provides free multi-backend search** without API keys or rate limits (with proper handling)
3. **Trafilatura provides high-quality content extraction** with configurable output formats
4. **Comprehensive SSRF guardrails are essential** - domain whitelisting, private IP blocking, redirect validation
5. **httpx already in dependencies** - no additional HTTP client needed
6. **Static permissions align with yoker design** - all guardrails defined in configuration upfront

---

## Sources

[1] Web search - Ollama - https://docs.ollama.com/capabilities/web-search - Accessed 2026-05-04
[2] DDGS - DuckDuckGo Search Library - https://github.com/deedy5/ddgs - Accessed 2026-05-04
[3] Trafilatura Python Usage - https://trafilatura.readthedocs.io/en/latest/usage-python.html - Accessed 2026-05-04
[4] AI Agent Policy URL Security: SSRF Defenses - https://cordum.io/blog/ai-agent-policy-url-security-ssrf - Accessed 2026-05-04
[5] SerpApi: Plans and Pricing - https://serpapi.com/pricing - Accessed 2026-05-04
[6] Cheapest SERP API in 2026 - https://proxies.sx/blog/cheapest-serp-api-comparison-2026 - Accessed 2026-05-04