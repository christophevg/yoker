# Dual Backend Architecture — Architecture Decision

**Date**: 2026-06-29
**Status**: Architecture Decision — Phase 1 Complete, Phase 2 Redesigned
**Related**: `analysis/litellm-integration-analysis.md`, `analysis/multi-provider-backend-design.md`

## Executive Summary

After extensive research into litellm integration (`analysis/litellm-integration-analysis.md`), we've made a critical architecture decision for MBI-006: **dual backend architecture**.

**Phase 1 (DONE):** OllamaBackend using native Ollama SDK — preserves full features
**Phase 2 (NEW):** LitellmBackend wrapping litellm library — unified interface for 100+ providers

This decision replaces the original Phase 2 (OpenAI backend) and Phase 3 (Anthropic backend) with a single unified approach.

---

## Architecture Decision

### The Problem

The original MBI-006 design planned three sequential backend implementations:
- Phase 1: Protocol + Ollama Refactor ✓
- Phase 2: OpenAI Backend (using openai SDK)
- Phase 3: Anthropic Backend (using anthropic SDK)

Research revealed litellm as a potential unified solution, but with critical limitations for Ollama.

### Research Findings

**litellm Advantages:**
- Unified interface for OpenAI, Anthropic, and 100+ other providers
- Automatic tool schema translation across providers
- Automatic message format conversion
- Well-maintained, actively developed
- Handles provider-specific quirks

**litellm Limitations with Ollama:**
- **No web tools support**: litellm does NOT support Ollama's `web_search`/`web_fetch` endpoints
- **Streaming tool call bugs**: Known issues with Ollama streaming tool calls in litellm
- **Lost native stats**: litellm doesn't preserve Ollama's `total_duration`, `prompt_eval_count`, `eval_count`
- **Thinking not documented**: Ollama's thinking mode is not officially supported in litellm

### The Solution: Dual Backend Architecture

**OllamaBackend (Phase 1 - DONE)**
- Native Ollama SDK (`ollama.AsyncClient`)
- Full features: web tools, native stats, thinking mode
- No litellm bugs or limitations
- Direct API access

**LitellmBackend (Phase 2 - NEW)**
- Unified interface for OpenAI, Anthropic, and 100+ providers
- Wraps `litellm.acompletion()` with stream translation to `ChatChunk`
- Handles provider-specific quirks automatically
- Provides standardized `input_tokens`/`output_tokens` stats

### Implementation

```python
# Backend factory dispatch
BACKENDS: dict[str, Callable[[Config], ModelBackend]] = {
  "ollama": lambda cfg: OllamaBackend(cfg),      # Native SDK (Phase 1)
  "openai": lambda cfg: LitellmBackend(cfg),     # Via litellm (Phase 2)
  "anthropic": lambda cfg: LitellmBackend(cfg),  # Via litellm (Phase 2)
  # ... 100+ other providers via litellm
}
```

---

## Web Tools Strategy

**Problem**: Web tools (`websearch`/`webfetch`) use Ollama's native API and have no litellm equivalent.

**Solution**: Web tools remain Ollama-specific:

```python
class Agent:
  def _create_tool_backends(self) -> dict[str, Any]:
    backends = {}
    if self.config.backend.provider == "ollama":
      if self.config.tools.websearch.enabled:
        backends["websearch"] = OllamaWebSearchBackend(self._ollama_client)
      if self.config.tools.webfetch.enabled:
        backends["webfetch"] = OllamaWebFetchBackend(self._ollama_client)
    return backends
```

**Behavior**:
- Ollama provider: Web tools work with native SDK
- Other providers: Web tools fail gracefully with clear error message

---

## Why This Is Better

### Compared to Original Phase 2/3 Design

**Original Plan:**
- Implement OpenAI backend manually (M-sized)
- Implement Anthropic backend manually (L-sized)
- Maintain 3 separate SDK dependencies
- Handle provider quirks manually

**New Plan:**
- Implement LitellmBackend once (M-sized)
- Support 100+ providers automatically
- Reduce SDK dependencies (litellm + ollama only)
- Let litellm handle provider quirks

### Compared to litellm-Only Architecture

**litellm-only approach** would lose:
- Ollama web tools (critical feature for some users)
- Ollama native stats (performance monitoring)
- Ollama thinking mode (experimental but valuable)
- Bug-free Ollama streaming (litellm has known issues)

**Dual backend architecture** preserves:
- All Ollama features (via native SDK)
- All litellm benefits (via unified backend)

---

## Code Impact

### Files Changed

**Phase 1 (DONE):**
- `src/yoker/backends/protocol.py` — ModelBackend Protocol + ChatChunk types
- `src/yoker/backends/ollama.py` — OllamaBackend implementation
- `src/yoker/backends/factory.py` — create_backend() factory
- `src/yoker/config/__init__.py` — Tagged union config schema
- `src/yoker/agent/` — Agent wiring to use backend

**Phase 2 (NEW):**
- `src/yoker/backends/litellm.py` — NEW LitellmBackend implementation
- `src/yoker/backends/factory.py` — Add OpenAI/Anthropic to BACKENDS registry
- `src/yoker/bootstrap/modellist.py` — Add OpenAI/Anthropic curated models
- `pyproject.toml` — Add litellm dependency

### Lines of Code

**Original Plan:**
- Phase 2 (OpenAI backend): ~400 lines
- Phase 3 (Anthropic backend): ~500 lines
- **Total: ~900 lines**

**New Plan:**
- Phase 2 (LitellmBackend): ~500 lines
- **Total: ~500 lines**
- **Savings: ~400 lines**

Plus automatic support for 100+ additional providers.

---

## Dependencies

**Added:**
- `litellm >= 1.90.0` — Multi-provider abstraction

**Kept:**
- `ollama >= 0.4.0` — Native Ollama SDK (for web tools and full features)

**Removed from original plan:**
- `openai` SDK — No longer needed (litellm handles)
- `anthropic` SDK — No longer needed (litellm handles)

---

## Migration Path

### Phase 1 (DONE)
- ModelBackend Protocol introduced
- OllamaBackend implements Protocol
- Agent uses backend abstraction
- Config schema widened to tagged union

### Phase 2 (NEW)
- Add litellm dependency
- Implement LitellmBackend
- Register for OpenAI and Anthropic
- Verify multi-provider support

### User Experience
- Existing Ollama users: No changes, everything works as before
- New OpenAI/Anthropic users: Add API key to config, everything works
- Web tools: Work with Ollama, fail gracefully with others

---

## Acceptance Criteria

**Phase 1 (DONE):**
- [x] ModelBackend Protocol and ChatChunk types
- [x] OllamaBackend works with full features
- [x] Config schema is tagged union
- [x] Subagent spawn is provider-agnostic
- [x] make check green

**Phase 2 (NEW):**
- [ ] LitellmBackend implements ModelBackend Protocol
- [ ] OpenAI backend works end-to-end
- [ ] Anthropic backend works end-to-end
- [ ] Web tools work with Ollama, fail gracefully with others
- [ ] make check green

---

## References

- `analysis/litellm-integration-analysis.md` — Comprehensive litellm research
- `analysis/multi-provider-backend-design.md` — Original design (Phase 1 implemented, Phase 2/3 replaced)
- `analysis/security-multi-provider-backend.md` — Security analysis
- TODO.md — Task breakdown (tasks 8.1-8.9 for Phase 2)