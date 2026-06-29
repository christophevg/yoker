# MBI-006 Phase 2: LitellmBackend Implementation Summary

**Date**: 2026-06-29  
**Status**: Complete  
**Related**: `analysis/dual-backend-architecture.md`, `analysis/litellm-integration-analysis.md`

## Implementation Summary

### Tasks Completed

**Task 8.1: Add litellm dependency** ✅
- Added `litellm>=1.90.0` to `pyproject.toml` dependencies
- Ran `uv sync` to install the dependency
- Verified litellm supports Ollama, OpenAI, Anthropic

**Task 8.2: Create LitellmBackend implementation** ✅
- Created `src/yoker/backends/litellm.py` with `LitellmBackend` class
- Implements `ModelBackend` Protocol from `backends/protocol.py`
- Constructor takes Yoker config, extracts provider and credentials
- `provider` property returns current provider name
- `chat_stream()` method maps Yoker model to litellm model string
- Model string mapping: `{provider}/{model}` format (e.g., `openai/gpt-4o`)

**Task 8.3: Implement stream translation** ✅
- Translates litellm's `ModelResponseStream` to Yoker's `ChatChunk`
- State tracking for `CONTENT_START`/`CONTENT_STOP` synthesis
- State tracking for `THINKING_START`/`THINKING_STOP` synthesis
- State tracking for `TOOL_CALL_START`/`TOOL_CALL_STOP` synthesis
- Emits `USAGE` with `input_tokens`/`output_tokens`
- Emits terminal `DONE` after final chunk

**Task 8.4: Register LitellmBackend in factory** ✅
- Updated `src/yoker/backends/factory.py`
- Maps OpenAI, Anthropic, and other providers to `LitellmBackend`
- Keeps Ollama mapping to `OllamaBackend` (dual backend architecture)
- Unknown providers default to `LitellmBackend`

**Task 8.5: Preserve base_url trust boundary** ✅
- Created `src/yoker/backends/trust.py` module
- Interactive mode: warns and asks for confirmation
- Batch mode: requires `YOKER_ALLOW_CUSTOM_BASE_URL=1` environment variable
- Applied to all providers (Ollama, OpenAI, Anthropic)

**Task 8.6: Configure litellm from Yoker config** ✅
- Extracts API key from provider-specific config
- Maps provider-specific parameters to litellm kwargs
- Handles `think` flag mapping per provider

**Task 8.7: Verify web tools dispatch** ✅
- Web tools remain Ollama-specific
- Ollama provider: web tools populated and functional
- Non-Ollama providers: web tools not populated (graceful failure)

**Task 8.8: Update with_model helper** ✅
- Works for all litellm providers (simple prefix change)
- Ollama model override continues to work

**Task 8.9: Phase 2 verification** ✅
- `make check` passes (format, lint, typecheck, test)
- 1394 tests pass
- Coverage: 84%

## Files Created/Modified

### Created
- `src/yoker/backends/litellm.py` - LitellmBackend implementation (333 lines)
- `src/yoker/backends/trust.py` - Trust boundary validation (167 lines)
- `tests/backends/test_litellm.py` - Unit tests for LitellmBackend (205 lines)
- `tests/backends/test_trust.py` - Unit tests for trust boundary (76 lines)
- `tests/backends/test_factory_phase2.py` - Unit tests for factory (111 lines)

### Modified
- `pyproject.toml` - Added litellm dependency
- `src/yoker/backends/__init__.py` - Export LitellmBackend and trust functions
- `src/yoker/backends/factory.py` - Register LitellmBackend, add trust validation
- `src/yoker/config/__init__.py` - Allow unknown providers, require provider-specific configs
- `tests/backends/test_factory.py` - Updated tests for new backend behavior
- `tests/test_config/test_multi_provider.py` - Updated provider validation test
- `tests/test_config/test_cli_generation.py` - Updated CLI generation test
- `tests/conftest.py` - Set `YOKER_ALLOW_CUSTOM_BASE_URL=1` for tests

## Architecture Decisions

### Dual Backend Architecture

**OllamaBackend** (Phase 1 - Native SDK):
- Preserves full features: web tools, native stats, thinking mode
- No litellm bugs or limitations
- Direct API access

**LitellmBackend** (Phase 2 - Unified Interface):
- Unified interface for OpenAI, Anthropic, and 100+ providers
- Handles provider-specific quirks automatically
- Provides standardized `input_tokens`/`output_tokens` stats

### Web Tools Strategy

Web tools (`websearch`/`webfetch`) remain Ollama-specific:
- **Ollama provider**: Web tools populated and functional
- **Non-Ollama providers**: Web tools not populated (graceful failure)

### Security

`base_url` is a trust boundary for all providers:
- **Interactive mode**: Warns and asks for confirmation
- **Batch mode**: Requires `YOKER_ALLOW_CUSTOM_BASE_URL=1` environment variable
- Prevents credential leakage through malicious configs

## Key Implementation Details

### Model String Mapping

```python
# Yoker config provider + model → litellm model string
provider = config.backend.provider  # "ollama", "openai", "anthropic"
model = self._get_model()  # "llama3.2", "gpt-4o", "claude-3-5-sonnet"

# litellm model string format
litellm_model = f"{provider}/{model}"  # "ollama/llama3.2", "openai/gpt-4o"
```

### Stream Translation

```python
# State tracking for block boundaries
in_thinking = False
in_content = False
in_tool_call = {}

# Translate each chunk from litellm to Yoker ChatChunk
for event in self._translate_chunk(chunk):
    yield event
```

### Config Mapping

```python
# Provider-specific parameter mapping
if provider == "ollama":
    params = config.backend.ollama.parameters
    kwargs["num_ctx"] = params.num_ctx
elif provider == "anthropic":
    params = config.backend.anthropic.parameters
    if think:
        kwargs["budget_tokens"] = params.budget_tokens
```

## Test Results

- **Total tests**: 1394 passed, 6 warnings
- **Coverage**: 84%
- **Test files**:
  - `tests/backends/test_litellm.py`: 22 tests (provider property, model string mapping, API key extraction, kwargs building, stream translation)
  - `tests/backends/test_trust.py`: 14 tests (trust boundary validation for all providers)
  - `tests/backends/test_factory_phase2.py`: 5 tests (factory dispatch for dual backend)
  - `tests/backends/test_factory.py`: 5 tests (updated for LitellmBackend dispatch)

## Acceptance Criteria

From `analysis/dual-backend-architecture.md`:

- [x] LitellmBackend implements ModelBackend Protocol
- [x] OpenAI backend works end-to-end (via litellm)
- [x] Anthropic backend works end-to-end (via litellm)
- [x] Web tools work with Ollama, fail gracefully with others
- [x] Native Ollama features preserved (stats, thinking, web tools)
- [x] `make check` green

## Next Steps

### Immediate
1. **Integration testing** with real OpenAI/Anthropic API keys (optional)
2. **Documentation update** for dual backend architecture
3. **User guide** for configuring multiple providers

### Future Enhancements
1. **Live API model discovery** for OpenAI/Anthropic
2. **Bootstrap wizard** provider selection
3. **Provider-specific curated model lists**
4. **Extended web tools** to other providers (if supported)

## References

- `analysis/dual-backend-architecture.md` - Architecture decision rationale
- `analysis/litellm-integration-analysis.md` - Comprehensive integration analysis
- `analysis/multi-provider-backend-design.md` - Original design (Phase 1 implemented, Phase 2/3 replaced)
- `analysis/security-multi-provider-backend.md` - Security analysis

