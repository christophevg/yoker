# Development Summary: Provider Configuration Refactoring

**Date**: 2026-06-30
**Task**: Refactor provider configurations and LitellmBackend implementation based on analysis

## Changes Implemented

### 1. Provider Parameters Default to None

All provider parameters now default to `None` to allow providers to use their own defaults, rather than overriding them with Yoker defaults.

**Modified Files:**
- `src/yoker/config/providers.py`

**Changes:**

#### OllamaParameters
- Changed all parameter defaults to `None`
- Added new parameters: `num_predict`, `repeat_penalty`, `seed`
- Updated docstring to document Ollama defaults

#### OpenAIParameters
- Changed all parameter defaults to `None`
- Added new parameters: `max_completion_tokens`, `presence_penalty`, `frequency_penalty`, `seed`
- Moved `reasoning_effort` from `OpenAIConfig` to `OpenAIParameters` (where it belongs)
- Updated docstring to document OpenAI defaults

#### AnthropicParameters
- Changed parameter defaults to `None` except `max_tokens` (which is required)
- Moved `max_tokens` from `AnthropicConfig` to `AnthropicParameters` (where it belongs)
- Added new parameter: `stop_sequences`
- Changed `budget_tokens` default to `None`
- Updated docstring to clarify that `max_tokens` is required

#### GeminiParameters
- Changed all parameter defaults to `None`
- Added new parameters: `max_tokens` (alias for max_output_tokens), `safety_settings`

### 2. Fixed LitellmBackend Parameter Flattening

**Modified Files:**
- `src/yoker/backends/litellm.py`

**Changes:**
- Implemented proper flattening of nested `parameters` dict into top-level kwargs
- The `params` property now correctly handles:
  - Flattening nested `parameters` dict
  - Renaming `base_url` to `api_base` (litellm-specific transform)
  - Renaming `timeout_seconds` to `timeout` (litellm-specific transform)
  - Removing `model` key (passed separately)

### 3. Moved Misplaced Parameters

**OpenAI**: `reasoning_effort` moved from `OpenAIConfig` to `OpenAIParameters`
- This is a model-level parameter, not a client-level configuration

**Anthropic**: `max_tokens` moved from `AnthropicConfig` to `AnthropicParameters`
- This is required by the Anthropic API, so it must have a default value (4096)

### 4. Added Missing Parameters

Based on the analysis in `analysis/litellm-provider-parameters.md`:

**OllamaParameters:**
- `num_predict: int | None = None` (mapped from max_tokens)
- `repeat_penalty: float | None = None`
- `seed: int | None = None`

**OpenAIParameters:**
- `max_completion_tokens: int | None = None` (for o-series)
- `presence_penalty: float | None = None`
- `frequency_penalty: float | None = None`
- `seed: int | None = None`

**AnthropicParameters:**
- `stop_sequences: list[str] | None = None`

**GeminiParameters:**
- `max_tokens: int | None = None` (alias for max_output_tokens)
- `safety_settings: list[dict[str, str]] | None = None`

## Test Updates

**Modified Files:**
- `tests/test_config/test_multi_provider.py`
- `tests/test_config.py`

**Changes:**
- Updated test expectations to reflect `None` defaults instead of concrete values
- Updated test for `AnthropicConfig` to use `parameters.max_tokens` instead of `config.max_tokens`
- Added validation tests for new parameters

## Verification

All checks pass:
- **Tests**: `make test` - 1383 passed
- **Lint**: `make lint` - All checks passed
- **Typecheck**: `make typecheck` - Success: no issues found in 93 source files

## Design Decisions

### Why None Defaults?

The analysis revealed that LiteLLM passes parameters directly to providers, and each provider has its own defaults. When Yoker sets explicit defaults like `temperature=0.7`, it overrides the provider defaults, which may not be desirable.

By changing all parameters to default to `None`, we:
1. Allow providers to use their own optimal defaults
2. Give users explicit control when they want to override
3. Reduce unnecessary parameter passing

### Why Keep `max_tokens` Default for Anthropic?

Anthropic's API **requires** `max_tokens` to be set. Without a default, users would be forced to set it explicitly. The default of 4096 provides a reasonable value while still allowing users to override it.

### Why Flatten Parameters in LitellmBackend?

The config system creates a nested structure:
```python
{'model': 'gpt-4o', 'parameters': {'temperature': 0.7, ...}}
```

But LiteLLM expects flat kwargs:
```python
{'model': 'openai/gpt-4o', 'temperature': 0.7, ...}
```

The flattening logic in `LitellmBackend.chat_stream()` handles this transformation, along with provider-specific renaming (e.g., `base_url` → `api_base`).

## Files Modified

1. `src/yoker/config/providers.py` - Refactored all parameter classes
2. `src/yoker/backends/litellm.py` - Fixed parameter flattening
3. `tests/test_config/test_multi_provider.py` - Updated tests for new defaults
4. `tests/test_config.py` - Updated OllamaParameters defaults test

## Backward Compatibility

This is a **breaking change** for users who:
1. Create `OllamaParameters`, `OpenAIParameters`, `AnthropicParameters`, or `GeminiParameters` instances directly
2. Expect specific default values

However, for users who:
1. Use TOML configuration files
2. Use CLI arguments
3. Use the default instances created by the config system

The impact is minimal because `None` values are filtered out when passed to LiteLLM, allowing provider defaults to take effect.

## Future Work

Based on the analysis document, additional parameters could be added:

**OpenAI:**
- `verbosity` (for GPT-5)
- `web_search_options`
- `context_management`

**Anthropic:**
- `thinking` (for adaptive thinking models)
- `metadata` (for user identification)

**Gemini:**
- `reasoning_effort` (for Gemini 3+)
- `thinking`
- `response_schema`
- `video_metadata`, `detail` (for media handling)

**Ollama:**
- `mirostat`, `mirostat_eta`, `mirostat_tau`
- `tfs_z`
- `num_gqa`, `num_gpu`, `num_thread`
- `keep_alive` (in Config)
- `format` (JSON mode)

These can be added incrementally as needed.

