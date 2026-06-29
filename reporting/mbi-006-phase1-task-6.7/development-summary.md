# MBI-006 Phase 1 Task 6.7: Subagent Spawn Provider-Agnostic

## Implementation Summary

**Date:** 2026-06-29
**Branch:** `feature/mbi-006-phase1-backend-protocol`
**Task:** Make subagent spawn provider-agnostic (Task 6.7 from MBI-006 Phase 1)

### What was implemented

This task makes the subagent spawn mechanism provider-agnostic by removing hardcoded `OllamaConfig` rebuilds and using the `with_model()` helper function introduced in Task 6.6.

### Changes Made

#### 1. Verified `with_model()` Helper (Task 6.6)

**File:** `src/yoker/backends/__init__.py`

The `with_model()` helper was already implemented in Task 6.6 and supports all three providers:
- Ollama (Phase 1)
- OpenAI (Phase 2/3)
- Anthropic (Phase 2/3)

The helper correctly copies the backend config and overrides only the model field on the active provider's sub-config.

#### 2. Updated Subagent Spawn Logic

**File:** `src/yoker/builtin/agent.py`

**Before (lines 146-160):**
```python
config: Config | None = None
if model is not None:
  if parent_config is not None:
    # Use with_model to create provider-agnostic config copy with model override
    backend = with_model(parent_config.backend, model)
    config = replace(
      parent_config,
      backend=backend,
    )
  else:
    # No parent config, create default with model
    from yoker.config import BackendConfig, OllamaConfig

    config = Config(backend=BackendConfig(ollama=OllamaConfig(model=model)))
else:
  config = parent_config
```

**After:**
```python
config: Config | None = None
if model is not None:
  if parent_config is not None:
    # Use with_model to create provider-agnostic config copy with model override
    backend = with_model(parent_config.backend, model)
    config = replace(
      parent_config,
      backend=backend,
    )
  else:
    # No parent config (should not happen in practice - parent_agent is validated).
    # Use default BackendConfig (defaults to Ollama) and set model via with_model.
    from yoker.backends import with_model as _with_model
    from yoker.config import BackendConfig

    default_backend = BackendConfig()  # Defaults to Ollama per Q9
    backend = _with_model(default_backend, model)
    config = Config(backend=backend)
else:
  config = parent_config
```

**Key improvements:**
- Removed hardcoded `OllamaConfig` rebuild
- Uses `BackendConfig()` default (which defaults to Ollama per design decision Q9)
- Uses `with_model()` to set the model (provider-agnostic)
- Added comment explaining this case should not happen in practice

#### 3. Added Comprehensive Tests

**File:** `tests/test_backends/test_with_model.py` (new file)

Created comprehensive tests for the `with_model()` helper:

**Unit tests for `with_model`:**
- `test_with_model_ollama`: Verifies Ollama provider config is copied correctly
- `test_with_model_openai`: Verifies OpenAI provider config is copied correctly
- `test_with_model_anthropic`: Verifies Anthropic provider config is copied correctly
- `test_with_model_preserves_none_fields`: Verifies None fields are preserved
- `test_with_model_ollama_is_primary_path`: Verifies primary Ollama path works correctly

**Integration tests for subagent spawn:**
- `test_subagent_inherits_parent_provider_ollama`: Verifies subagent inherits parent's Ollama provider
- `test_subagent_no_model_uses_parent_config`: Verifies subagent with no model uses parent config unchanged

**Note:** OpenAI and Anthropic provider tests will be added in Phase 2/3 when those backends are implemented.

### Acceptance Criteria Verification

✅ **Subagent `Config.backend` equals parent's `backend` with only `model` overridden**
- Implemented via `with_model()` helper which copies the parent's backend config and overrides only the model field
- Preserves all other provider settings (base_url, timeout_seconds, api_key, etc.)

✅ **No hardcoded `OllamaConfig` rebuild in `_create_subagent`**
- Removed `from yoker.config import BackendConfig, OllamaConfig`
- Removed `BackendConfig(ollama=OllamaConfig(model=model))`
- Now uses `BackendConfig()` (default) + `with_model()` (provider-agnostic)

✅ **`make check` green**
- All 1353 tests pass
- No linting errors
- No type checking errors

### Dependencies

- **Task 6.3** (BackendConfig tagged-union): ✅ Complete - BackendConfig supports ollama/openai/anthropic
- **Task 6.6** (Agent wiring with ModelBackend): ✅ Complete - `with_model()` helper exists and works

### Design Decisions

1. **Fallback to Default BackendConfig**: When there's no parent config (shouldn't happen in practice), the code now uses `BackendConfig()` which defaults to Ollama (per design decision Q9) and then uses `with_model()` to set the model. This is provider-agnostic because:
   - Uses the default provider (Ollama, but configured as default)
   - Uses `with_model()` to set the model (provider-agnostic operation)

2. **Test Coverage**: Tests verify that:
   - The `with_model()` helper works for all three providers
   - Subagent inherits parent's provider choice
   - Subagent's model is overridden correctly
   - All other provider settings are preserved

### Files Modified

1. `src/yoker/builtin/agent.py` - Updated `_create_subagent()` to use provider-agnostic approach
2. `tests/test_backends/test_with_model.py` - New test file for `with_model()` helper

### Files Unchanged

- `src/yoker/backends/__init__.py` - `with_model()` helper already implemented in Task 6.6
- All other files - No changes needed

### Next Steps

Task 6.7 is complete. The next task in Phase 1 is **Task 6.8: Phase 1 verification** which will verify all Phase 1 tasks work together correctly.

### Testing Results

```
make check
```

**Result:** ✅ All checks pass
- Tests: 1353 passed, 6 warnings
- Coverage: 84%
- Lint: No errors
- Type checking: No errors