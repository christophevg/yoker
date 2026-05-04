# Sources: WebSearch and WebFetch Tool Implementation

**Date**: 2026-05-04T00:00:00Z
**Previous Research**: none

---

## Searches

### search-1

- **Query**: Ollama native web search web fetch tool support 2026
- **Timestamp**: 2026-05-04T00:00:00Z
- **Results**:
  - [launch: fix web search, add web fetch, and enable both for local (#14886)](https://github.com/ollama/ollama/commit/bcf6d55b54b9792083e785b5cfaf6ad8eb9f8dca) - GitHub commit showing native web search/fetch implementation
  - [Web search - Ollama](https://docs.ollama.com/capabilities/web-search) - Official Ollama documentation
  - [x/cmd: enable web search and web fetch with flag · PR #13690](https://github.com/ollama/ollama/pull/13690) - PR adding --experimental-websearch flag
  - [Ollama Web Search: Real-Time Internet Access Without RAG](https://craftrigs.com/articles/ollama-0-18-1-web-browsing-local-llm-no-rag/) - CraftRigs analysis of Ollama 0.18.1 capabilities
  - [Ollama web search - OpenClaw](https://docs.openclaw.ai/tools/ollama-search) - OpenClaw framework integration docs

### search-2

- **Query**: DuckDuckGo search API Python free rate limits 2026
- **Timestamp**: 2026-05-04T00:00:00Z
- **Results**:
  - [duckduckgo-search v8.1.1](https://pypi.org/project/duckduckgo-search/) - Main Python library (now called ddgs)
  - [duckpy v3.2.0](https://pypi.org/project/duckpy/) - Simpler alternative library
  - [deedy5/ddgs](https://github.com/deedy5/ddgs) - GitHub repository for ddgs library
  - [DuckDuckGo API Documentation](https://searchapi.io/docs/duckduckgo-api) - Paid API via SearchAPI.io
  - [202 ratelimit on DDGS · Issue #290](https://github.com/deedy5/duckduckgo_search/issues/290) - Rate limit discussion

### search-3

- **Query**: SerpAPI Google Custom Search API comparison pricing rate limits 2026
- **Timestamp**: 2026-05-04T00:00:00Z
- **Results**:
  - [SerpApi: Plans and Pricing](https://serpapi.com/pricing) - Official SerpAPI pricing tiers
  - [Google Custom Search API Vs. SerpApi: Which Is Better?](https://postecards.poste.it/bold-stats/google-custom-search-api-vs-serpapi-which-is-better-1764802066) - Comparison article
  - [Cheapest SERP API in 2026: Google Search API Pricing Compared](https://proxies.sx/blog/cheapest-serp-api-comparison-2026) - Pricing comparison
  - [SERP API Pricing Comparison 2026: Best Value Provider](https://apiserpent.com/blog/serp-api-pricing-comparison.html) - Serpent API comparison
  - [Best SerpApi Alternatives in 2026: 6 Cheaper SERP APIs Compared](https://scrape.do/blog/serpapi-alternatives) - Alternatives analysis

### search-4

- **Query**: Python web content extraction trafilatura readability httpx 2026
- **Timestamp**: 2026-05-04T00:00:00Z
- **Results**:
  - [Trafilatura Python Usage](https://trafilatura.readthedocs.io/en/latest/usage-python.html) - Python API documentation
  - [Trafilatura Overview](https://trafilatura.readthedocs.io/) - Main documentation
  - [Trafilatura Quickstart](https://trafilatura.readthedocs.io/en/latest/quickstart.html) - Quick start guide
  - [Trafilatura: Web Content Extraction with Python](https://www.contextractor.com/trafilatura/) - Feature overview
  - [GitHub - trafilatura](https://github.com/brendanlong/trafilatura) - GitHub repository

### search-5

- **Query**: web fetch tool guardrails security domain whitelist content size limits timeout
- **Timestamp**: 2026-05-04T00:00:00Z
- **Results**:
  - [agent-fetch v0.1.10](https://crates.io/crates/agent-fetch) - Sandboxed HTTP client for AI agents
  - [Security: add URL allowlist for web_search and web_fetch · PR #19042](https://github.com/openclaw/openclaw/pull/19042) - OpenClaw URL allowlist security feature
  - [AI Agent Policy URL Security: SSRF Defenses](https://cordum.io/blog/ai-agent-policy-url-security-ssrf) - Best practices for securing remote policy fetch
  - [SECURITY.md at main · AlexClaw](https://github.com/thatsme/AlexClaw/blob/main/SECURITY.md) - Content sanitization policy
  - [Tools - Fabro](https://docs.fabro.sh/agents/tools) - Web fetch tool configuration

## Fetches

### fetch-1

- **URL**: https://docs.ollama.com/capabilities/web-search
- **Timestamp**: 2026-05-04T00:00:00Z
- **Source**: search-1
- **Title**: Web search - Ollama
- **Content**: [fetched/fetch-1.md](fetched/fetch-1.md)
- **Summary**: Official Ollama documentation for web search and web fetch APIs. Covers authentication via OLLAMA_API_KEY, API endpoints (POST https://ollama.com/api/web_search and /api/web_fetch), parameters, response formats, Python/JavaScript SDK usage, and MCP server integration.
- **Key Excerpts**:
  - "Requires API key from https://ollama.com/settings/keys (free Ollama account needed)"
  - "Endpoint: POST https://ollama.com/api/web_search" with query and max_results parameters
  - "Endpoint: POST https://ollama.com/api/web_fetch" with url parameter
  - "Use with tools=[web_search, web_fetch] parameter in chat"

### fetch-2

- **URL**: https://github.com/deedy5/ddgs
- **Timestamp**: 2026-05-04T00:00:00Z
- **Source**: search-2
- **Title**: DDGS - DuckDuckGo Search Library
- **Content**: [fetched/fetch-2.md](fetched/fetch-2.md)
- **Summary**: Comprehensive Python library for web search using multiple backends (bing, brave, duckduckgo, google, etc.). Includes text, images, videos, news, books search and URL content extraction. Supports CLI, API server, MCP server, and DHT network modes.
- **Key Excerpts**:
  - "Metasearch library aggregating results from multiple web search services"
  - "text() supports: bing, brave, duckduckgo, google, grokipedia, mojeek, yandex, yahoo, wikipedia"
  - "extract(url, fmt='text_markdown') - Content extraction from URLs"
  - "DHT Network: 90% faster repeated queries (50ms instead of 1-2s)"
  - "Python >= 3.10 required"

### fetch-3

- **URL**: https://trafilatura.readthedocs.io/en/latest/usage-python.html
- **Timestamp**: 2026-05-04T00:00:00Z
- **Source**: search-4
- **Title**: Trafilatura Python Usage
- **Content**: [fetched/fetch-3.md](fetched/fetch-3.md)
- **Summary**: Python API for web content extraction. Covers extract(), bare_extraction(), baseline(), html2txt() functions, output formats (csv, json, html, markdown, txt, xml), precision/recall tuning, metadata extraction, and integration with HTTP responses.
- **Key Excerpts**:
  - "extract() - Wrapper function, easiest way to perform text extraction and conversion"
  - "output_format: csv, json, html, markdown, txt, xml, xmltei"
  - "favor_precision=True - focus on central/relevant elements"
  - "fast=True (or no_fallback=True) - bypasses fallback algorithms, ~2x faster"
  - "with_metadata=True - include metadata in output"

### fetch-4

- **URL**: https://cordum.io/blog/ai-agent-policy-url-security-ssrf
- **Timestamp**: 2026-05-04T00:00:00Z
- **Source**: search-5
- **Title**: AI Agent Policy URL Security: SSRF Defenses
- **Content**: [fetched/fetch-4.md](fetched/fetch-4.md)
- **Summary**: Comprehensive SSRF defense patterns for AI agents. Covers host allowlist enforcement, DNS rebinding protection, redirect limits (5 hops), size limits (2MB default), timeouts (10 seconds), scheme enforcement (HTTPS-only in production), and environment variable configuration.
- **Key Excerpts**:
  - "Host allowlist enforced via SAFETY_POLICY_URL_ALLOWLIST (comma-separated hosts)"
  - "Redirect chain capped at 5 hops, each redirect URL revalidated against allowlist"
  - "HTTP client timeout: 10 seconds"
  - "Default max response size: 2,097,152 bytes"
  - "DNS resolution runs in URL validation and again in DialContext"

## Citations

- [1] Web search - Ollama - https://docs.ollama.com/capabilities/web-search - fetch-1
- [2] DDGS - DuckDuckGo Search Library - https://github.com/deedy5/ddgs - fetch-2
- [3] Trafilatura Python Usage - https://trafilatura.readthedocs.io/en/latest/usage-python.html - fetch-3
- [4] AI Agent Policy URL Security: SSRF Defenses - https://cordum.io/blog/ai-agent-policy-url-security-ssrf - fetch-4
- [5] Security: add URL allowlist for web_search and web_fetch - https://github.com/openclaw/openclaw/pull/19042 - search-5
- [6] SerpApi: Plans and Pricing - https://serpapi.com/pricing - search-3
- [7] Cheapest SERP API in 2026 - https://proxies.sx/blog/cheapest-serp-api-comparison-2026 - search-3

## Excluded Findings

### Excluded: Google Custom Search API

- **URL**: https://postecards.poste.it/bold-stats/google-custom-search-api-vs-serpapi-which-is-better-1764802066
- **Found**: 2026-05-04T00:00:00Z
- **Reason**: Not suitable for general web search - limited to site-specific search only
- **Context**: Google Custom Search API only searches within defined sites, cannot be used for broad web scraping or competitive analysis

### Excluded: OpenClaw/Ollama web search integration

- **URL**: https://docs.openclaw.ai/tools/ollama-search
- **Found**: 2026-05-04T00:00:00Z
- **Reason**: Redundant with official Ollama documentation
- **Context**: OpenClaw wraps Ollama's native web search, but the official docs provide more complete technical details