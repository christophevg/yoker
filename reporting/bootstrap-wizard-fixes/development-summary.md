# Bootstrap Wizard Fixes - Development Summary

**Date**: 2026-06-30
**Task**: Fix issues in the bootstrap wizard

## Issues Fixed

### Issue 1: Gemini Description
**Problem**: Gemini description didn't mention free tier and Google account availability.

**Solution**: Updated Gemini description to include note about free tier.

**File**: `src/yoker/bootstrap/providers.py`

**Change**:
```python
# Before
description="Gemini models via Google AI API",

# After
description="Gemini models via Google AI API (free tier available, works with your Google account)",
```

### Issue 2: Incorrect Gemini Models
**Problem**: Gemini models list was outdated. User confirmed `gemini-2.5-flash` works but wasn't listed.

**Solution**: Updated Gemini models to reflect currently available models.

**Files**:
- `src/yoker/bootstrap/providers.py`
- `src/yoker/config/providers.py`

**Changes**:
- Updated default model from `gemini-1.5-flash` to `gemini-2.5-flash`
- Updated curated models list:
  - `gemini-2.5-flash` (latest fast model, recommended)
  - `gemini-2.0-flash` (fast and efficient)
  - `gemini-1.5-flash` (previous generation fast model)
  - `gemini-1.5-pro` (balanced performance)

### Issue 3: Crash When Entering Model Manually
**Problem**: ValidationError when switching providers: "backend.gemini: required when provider='gemini' (got: None)"

**Root Cause**: When creating config overrides for a new provider, the code was setting `backend.provider` and `backend.<provider>.model`, but not initializing the provider-specific config section. The validation in `BackendConfig.__post_init__` requires that when `provider` is set to a known provider, the corresponding config must not be `None`.

**Solution**: Updated `build_bootstrap_overrides()` to initialize provider configs when switching providers.

**File**: `src/yoker/bootstrap/wizard.py`

**Changes**:
```python
# Added imports
from yoker.config.providers import (
  AnthropicConfig,
  GeminiConfig,
  OpenAIConfig,
)

# Updated build_bootstrap_overrides to initialize provider configs
overrides: dict[str, Any] = {
  "backend.provider": provider,
}

# Initialize provider config for non-Ollama providers (Ollama has default factory)
if provider == "openai":
  overrides["backend.openai"] = OpenAIConfig()
elif provider == "anthropic":
  overrides["backend.anthropic"] = AnthropicConfig()
elif provider == "gemini":
  overrides["backend.gemini"] = GeminiConfig()
# Ollama has default_factory in BackendConfig, so no need to initialize
```

### Issue 4: gpt-oss:20b Model Not Found
**Problem**: `gpt-oss:20b` model doesn't exist in Ollama.

**Solution**: Replaced with popular, actually available local models.

**Files**:
- `src/yoker/bootstrap/providers.py`
- `src/yoker/config/providers.py`
- `src/yoker/bootstrap/modellist.py`

**Changes**:
- Updated default Ollama model from `gemini-3-flash-preview:cloud` to `llama3.2:3b`
- Updated curated models list:
  - `llama3.2:3b` (fast local model, good for most tasks) - default
  - `llama3.1:8b` (larger local model, better quality)
  - `qwen2.5:7b` (local model, strong coding abilities)
  - `gemma2:9b` (local model, efficient and capable)

### Issue 5: Tool Call Error with Gemini
**Status**: Not a bootstrap wizard issue - this is a model compatibility issue with Ollama's implementation of Gemini models. No fix required in this task.

## Test Updates

Updated all tests to reflect new default models:

**Files**:
- `tests/test_bootstrap/test_modellist.py`
  - Updated note derivation tests (removed cloud model references)
  - Updated Gemini default model assertion
- `tests/test_bootstrap/test_providers.py`
  - Updated Gemini default model assertion
- `tests/test_config.py`
  - Updated default model assertions from `gemini-3-flash-preview:cloud` to `llama3.2:3b`
- `tests/test_config/test_writer.py`
  - Updated default model assertions in TOML rendering tests

## Verification

All checks pass:
- ✅ Tests: `make test` - 1443 passed, 6 warnings
- ✅ Linting: `make lint` - All checks passed
- ✅ Type checking: `make typecheck` - Success: no issues found in 99 source files
- ✅ Formatting: `make format` - 204 files left unchanged

## Summary

All four bootstrap wizard issues have been successfully fixed:

1. ✅ Gemini description now mentions free tier and Google account
2. ✅ Gemini models list updated to current available models
3. ✅ Provider config initialization bug fixed (critical bug)
4. ✅ Ollama models list updated to valid local models

The most critical fix was Issue 3, which prevented users from switching providers in the bootstrap wizard. This was a validation bug that occurred because the `BackendConfig` validation requires provider-specific configs to be initialized, but the wizard was only setting the provider name and model without creating the config instance.

## Files Modified

1. `src/yoker/bootstrap/providers.py` - Gemini description and models, Ollama models
2. `src/yoker/bootstrap/wizard.py` - Provider config initialization fix
3. `src/yoker/bootstrap/modellist.py` - Ollama models list
4. `src/yoker/config/providers.py` - Default model for Gemini and Ollama
5. `tests/test_bootstrap/test_modellist.py` - Test assertions
6. `tests/test_bootstrap/test_providers.py` - Test assertions
7. `tests/test_config.py` - Test assertions
8. `tests/test_config/test_writer.py` - Test assertions