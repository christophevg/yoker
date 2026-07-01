# Development Summary: Multi-Provider Bootstrap Wizard (MBI-006 Phase 1)

## What was implemented

Implemented the multi-provider bootstrap wizard based on the design in `analysis/bootstrap-multi-provider-design.md`. The wizard now supports:

- **Ollama** (default) - Local inference server with optional cloud tier
- **OpenAI** - GPT models via OpenAI API
- **Anthropic** - Claude models via Anthropic API
- **Gemini** - Gemini models via Google AI API

### Key Changes

#### 1. Created `src/yoker/bootstrap/providers.py`

- `CuratedModel` dataclass for model entries
- `ProviderInfo` dataclass for provider metadata
- `PROVIDERS` registry with all supported providers
- `PROVIDER_ORDER` list for display order (Ollama first for backward compatibility)
- Helper functions: `get_provider_info()`, `get_default_provider()`, `get_curated_models()`, `get_default_model()`

#### 2. Updated `src/yoker/bootstrap/modellist.py`

- Added `curated_models_for_provider()` - provider-specific model lists
- Added `default_model_for_provider()` - provider-specific default model
- Maintains backward compatibility with legacy `curated_models()` and `default_model_id()`

#### 3. Updated `src/yoker/bootstrap/steps.py`

- New multi-provider steps:
  - `step_provider_selection()` - Step 2: Select provider from list
  - `step_account_check_provider()` - Step 3: Provider-specific account check
  - `step_authentication()` - Step 4: Provider-specific auth (API key vs app)
  - `step_model_selection_provider()` - Step 5: Provider-specific model selection
  - `step_confirm_provider()` - Step 6: Confirmation with provider info
- Legacy steps preserved for backward compatibility

#### 4. Updated `src/yoker/bootstrap/wizard.py`

- `build_bootstrap_overrides()` now takes provider parameter
- Generates provider-aware config:
  ```python
  overrides = {
    "backend.provider": provider,
    f"backend.{provider}.model": model,
  }
  if api_key:
    overrides[f"backend.{provider}.api_key"] = api_key
  ```
- `BootstrapWizard.run()` uses new multi-provider flow

#### 5. Updated `src/yoker/bootstrap/__init__.py`

- Exports new functions and classes

#### 6. Bug Fix: Default Model

Fixed a pre-existing issue where the default model in `config/providers.py` was `llama3.2:latest` instead of `gemini-3-flash-preview:cloud` (per MBI-002 task 2.0). This was causing test failures.

Also added `help` metadata to `OllamaConfig` fields to support annotation-driven config comments.

## Files Modified

### New Files
- `src/yoker/bootstrap/providers.py` - Provider metadata and registry
- `tests/test_bootstrap/test_providers.py` - Unit tests for provider metadata

### Modified Files
- `src/yoker/bootstrap/__init__.py` - Added new exports
- `src/yoker/bootstrap/modellist.py` - Added provider-specific functions
- `src/yoker/bootstrap/steps.py` - Added multi-provider step functions
- `src/yoker/bootstrap/wizard.py` - Updated for multi-provider support
- `src/yoker/config/providers.py` - Fixed default model and added help metadata
- `tests/test_bootstrap/test_modellist.py` - Added provider model tests
- `tests/test_bootstrap/test_overrides.py` - Added multi-provider override tests

## Tests

All 1444 tests pass.

### New Tests
- 32 new tests in `test_providers.py` covering:
  - Provider registry structure
  - Provider metadata validation
  - Curated model lists
  - Default model retrieval

- 19 new tests in `test_modellist.py` covering:
  - Provider-specific model lists
  - Default model matching

- 16 new tests in `test_overrides.py` covering:
  - Ollama provider overrides (app vs API key)
  - OpenAI provider overrides
  - Anthropic provider overrides
  - Gemini provider overrides
  - None connection handling

## Design Principles Followed

1. **Data-driven**: All provider-specific logic comes from `ProviderInfo`, not conditionals
2. **Backward compatible**: Default to Ollama, existing configs work
3. **Simple flow**: 6 steps regardless of provider
4. **Security**: API keys via masked input, chmod 600 on config file

## Verification

```bash
make test     # 1444 passed
make lint     # All checks passed
make typecheck # Success: no issues found in 99 source files
```