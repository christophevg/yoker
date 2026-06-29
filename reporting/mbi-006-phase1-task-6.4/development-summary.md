# MBI-006 Phase 1 Task 6.4: render_config_toml Union-Aware

**Date**: 2026-06-29
**Task**: Make `render_config_toml` union-aware for BackendConfig tagged-union shape
**Status**: Complete

## Implementation Summary

### What was implemented

Created `src/yoker/config/writer.py` with `render_config_toml` function that:

1. **Renders Config dataclasses to TOML format** - Converts the entire Config hierarchy to a TOML string representation
2. **Handles tagged unions** - Specifically handles BackendConfig's discriminated union structure with `provider`, `ollama`, `openai`, and `anthropic` fields
3. **Omits None sub-configs** - When `openai=None` or `anthropic=None`, those sections are completely omitted from the TOML output
4. **Preserves round-trip equality** - Writing and reading back produces an equivalent Config

### Files Created

- `src/yoker/config/writer.py` - New module with `render_config_toml` function
- `tests/test_config/test_writer.py` - Comprehensive test suite for the writer

### Key Design Decisions

1. **Recursive dataclass rendering** - The function walks the dataclass hierarchy recursively, handling nested structures properly
2. **Section-based output** - Each nested dataclass gets its own `[section.subsection]` header
3. **Value formatting** - Properly formats booleans, strings, numbers, lists/tuples, and dictionaries
4. **Two-space indentation** - Follows project conventions (though TOML doesn't require indentation)

### Implementation Details

```python
def render_config_toml(config: Any, overrides: dict[str, Any] | None = None) -> str:
    """Render a Config dataclass to TOML format.

    Handles the tagged-union structure of BackendConfig by omitting
    None sub-configs.
    """
```

Key helper functions:

- `_render_dataclass_section()` - Recursively renders dataclass sections with proper TOML headers
- `_format_value()` - Formats Python values as TOML literals (strings, booleans, numbers, arrays)

### Test Coverage

8 tests created covering:

1. **test_render_ollama_only_config** - Ollama-only config produces correct TOML with no openai/anthropic sections
2. **test_render_config_omits_none_sub_configs** - None sub-configs are completely omitted from output
3. **test_render_config_with_openai** - OpenAI config produces correct TOML with openai section
4. **test_roundtrip_ollama_config** - Write and read back produces equivalent config
5. **test_render_full_config** - Full Config with all sections renders correctly
6. **test_render_config_with_tuple_fields** - Tuple/list fields render as TOML arrays
7. **test_render_config_with_dict_fields** - Dict fields render as TOML sections
8. **test_render_config_with_empty_collections** - Empty collections are omitted

All tests pass successfully.

### Example Output

For an Ollama-only config:

```toml
[backend]
provider = "ollama"

[backend.ollama]
base_url = "http://localhost:11434"
model = "llama3.2:latest"
timeout_seconds = 60

[backend.ollama.parameters]
temperature = 0.7
top_p = 0.9
top_k = 40
num_ctx = 4096
```

Note: No `[backend.openai]` or `[backend.anthropic]` sections are present.

## Acceptance Criteria Status

✅ **Omits None per-provider sub-configs** - Implemented and tested
✅ **Round-trip equality for Ollama-only config** - Verified with `test_roundtrip_ollama_config`
✅ **Depends on 6.3** - BackendConfig tagged-union is in place (task 6.3 already complete)

## Test Results

```
make check
- Format: ✅ All files formatted
- Lint: ✅ All checks passed
- Typecheck: ✅ No issues found in 88 source files
- Tests: ✅ 1336 passed, 6 warnings
```

## Notes

- The `overrides` parameter is reserved for future use (deferred with wizard work)
- The function does NOT modify `build_bootstrap_overrides` (that's deferred)
- The implementation is generic and will work with any dataclass structure, not just Config
- Security: Test uses `os.chmod(config_path, 0o600)` to satisfy Clevis security checks

## Future Enhancements

- The `overrides` parameter could be used for wizard-generated config overrides
- Could add validation to ensure BackendConfig has exactly one non-None sub-config matching the provider
- Could add a helper function to write config directly to a file path