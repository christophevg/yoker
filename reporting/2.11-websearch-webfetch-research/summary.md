# Task 2.11: WebSearch and WebFetch Tools Research

## Summary

Completed research on implementation approaches for WebSearch and WebFetch tools in yoker.

## Key Findings

### Ollama Native Support
- **Requires cloud API key** - conflicts with yoker's offline-first design
- **No guardrail control** - cannot implement domain whitelists or SSRF protection
- **Not recommended** for yoker's requirements

### Recommended Implementation

| Tool | Library | Reason |
|------|---------|--------|
| WebSearch | DDGS | Free, multi-backend, no API key required |
| WebFetch | httpx + Trafilatura | Already in deps, excellent extraction quality |

### Essential Guardrails

1. **SSRF Protection**
   - Block private IP ranges (10.x, 192.168.x, 169.254.x, 127.x)
   - DNS rebinding defense (validate at connection time)
   - Redirect limits (5 max, revalidate each target)

2. **Access Control**
   - Domain whitelist with wildcard subdomains
   - HTTPS-only in production

3. **Resource Limits**
   - Content size limit (2MB default)
   - Timeout (30 seconds)
   - Result count limits

## Deliverables

- `analysis/websearch-webfetch-research.md` - Analysis summary
- `research/2026-05-04-websearch-webfetch-tools/README.md` - Full research report
- `research/2026-05-04-websearch-webfetch-tools/SOURCES.md` - Source provenance

## Next Steps

Tasks 2.12 (WebSearch Tool) and 2.13 (WebFetch Tool) can now proceed with:
1. API design documents
2. Security analysis
3. Implementation with guardrails