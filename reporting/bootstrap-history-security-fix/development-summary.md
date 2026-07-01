# Bootstrap History Security Fix - Development Summary

## Problem

The bootstrap wizard was recording all user inputs (including API keys) to the command history file (`~/.yoker_history`). This was:

1. **Not needed** - Bootstrap is for one-time configuration, not conversation
2. **A security issue** - API keys and other sensitive data should never be logged/stored in history files

## Root Cause

The `InteractiveUIHandler` class always used `prompt_toolkit`'s `FileHistory` which persists all inputs to disk. The bootstrap wizard used the same UI handler instance, causing all configuration questions and responses (including API keys) to be stored in `~/.yoker_history`.

### Code Analysis

**Before the fix:**

1. `InteractiveUIHandler.__init__()` accepted a `history_file` parameter defaulting to `None`
2. When `None`, it would default to `Path.home() / ".yoker_history"`
3. It always created a `FileHistory` object, persisting all inputs to disk
4. The bootstrap wizard in `__main__.py` created a UI handler without any special handling for history

**Files involved:**

- `src/yoker/ui/interactive.py` - InteractiveUIHandler implementation
- `src/yoker/__main__.py` - Bootstrap wizard invocation
- `src/yoker/bootstrap/wizard.py` - Bootstrap wizard orchestration
- `src/yoker/bootstrap/steps.py` - Individual wizard step functions

## Solution

Modified `InteractiveUIHandler` to support disabling persistent history, and updated the bootstrap wizard to use in-memory history only.

### Changes Made

#### 1. Enhanced `InteractiveUIHandler` (`src/yoker/ui/interactive.py`)

**Added history control:**

- Added `History` base class import from `prompt_toolkit.history`
- Modified `history_file` parameter to accept `Path | None | str`
- Added logic to handle three cases:
  - `history_file=None` → Use default path (`~/.yoker_history`)
  - `history_file="none"` → Use `InMemoryHistory` (no persistence)
  - `history_file=<Path>` → Use `FileHistory` with custom path
- Updated type annotations to support `Path | None` for `self.history_file`

**Code changes:**

```python
from prompt_toolkit.history import FileHistory, History, InMemoryHistory

def __init__(
  self,
  history_file: Path | None | str = None,
  ...
) -> None:
  self.history_file: Path | None
  if history_file is None:
    self.history_file = Path.home() / ".yoker_history"
  elif history_file == "none":
    self.history_file = None
  elif isinstance(history_file, Path):
    self.history_file = history_file
  else:
    self.history_file = Path(history_file)

def _create_session(self) -> PromptSession[str]:
  history: History
  if self.history_file is None:
    history = InMemoryHistory()
  else:
    self.history_file.parent.mkdir(parents=True, exist_ok=True)
    history = FileHistory(str(self.history_file))
  return PromptSession(history=history, ...)
```

#### 2. Updated Bootstrap Wizard (`src/yoker/__main__.py`)

**Modified bootstrap UI creation:**

Changed from:
```python
bootstrap_ui = _create_ui(Config())
```

To:
```python
# IMPORTANT: Use history_file="none" to prevent bootstrap prompts (including
# API keys) from being persisted to ~/.yoker_history. Bootstrap is for
# one-time configuration, not conversation, and should never log secrets.
bootstrap_ui = InteractiveUIHandler(history_file="none")
```

#### 3. Added Security Tests (`tests/test_bootstrap/test_history_security.py`)

Created comprehensive tests to verify:

- Default behavior uses `FileHistory` (persists to disk)
- `history_file=None` uses default path
- `history_file="none"` explicitly disables history (uses `InMemoryHistory`)
- Custom paths work correctly

**Test coverage:**

```python
class TestBootstrapHistorySecurity:
  def test_interactive_handler_default_uses_file_history(self, tmp_path):
    """Default InteractiveUIHandler uses FileHistory (persists to disk)."""
    
  def test_interactive_handler_none_uses_default_path(self):
    """Passing None to history_file uses the default ~/.yoker_history path."""
    
  def test_interactive_handler_explicit_none_disables_history(self):
    """Passing 'none' string explicitly disables history (uses InMemoryHistory)."""
    
  def test_interactive_handler_custom_path_uses_file_history(self, tmp_path):
    """Custom history file path is used correctly."""
```

## Verification

All verification checks passed:

### Tests

- ✅ All new security tests pass
- ✅ All existing tests pass (except pre-existing failures unrelated to this change)
- ✅ No regression in functionality

```bash
$ uv run pytest tests/test_bootstrap/test_history_security.py -v
============================= test session starts ==============================
tests/test_bootstrap/test_history_security.py::TestBootstrapHistorySecurity::test_interactive_handler_default_uses_file_history PASSED
tests/test_bootstrap/test_history_security.py::TestBootstrapHistorySecurity::test_interactive_handler_none_uses_default_path PASSED
tests/test_bootstrap/test_history_security.py::TestBootstrapHistorySecurity::test_interactive_handler_explicit_none_disables_history PASSED
tests/test_bootstrap/test_history_security.py::TestBootstrapHistorySecurity::test_interactive_handler_custom_path_uses_file_history PASSED
```

### Linting

- ✅ No linting errors

```bash
$ make lint
uv run ruff check src tests examples
All checks passed!
```

### Type Checking

- ✅ No type errors

```bash
$ make typecheck
uv run mypy src examples
Success: no issues found in 99 source files
```

## Security Impact

**Before:** Bootstrap wizard inputs (including API keys) were persisted to `~/.yoker_history` in plain text.

**After:** Bootstrap wizard uses `InMemoryHistory` which exists only in memory during the session and is never written to disk. API keys and other configuration inputs are now secure.

## Files Modified

- `src/yoker/ui/interactive.py` - Enhanced to support disabling history
- `src/yoker/__main__.py` - Use history-disabled UI for bootstrap
- `tests/test_bootstrap/test_history_security.py` - New test file for security verification

## Implementation Notes

1. **Backward compatibility**: The default behavior (passing `history_file=None`) still uses `FileHistory` and persists to `~/.yoker_history`, so existing code is unaffected.

2. **Explicit disable**: The string `"none"` was chosen as a sentinel value to explicitly disable history. This is clearer than using `None` for two different purposes (default vs. disabled).

3. **Type safety**: Added proper type annotations (`Path | None | str` for parameter, `Path | None` for attribute) to ensure mypy validation.

4. **Documentation**: Added comprehensive docstrings explaining the security implications and proper usage.

## Acceptance Criteria

All acceptance criteria met:

- ✅ Bootstrap wizard does NOT add inputs to history file
- ✅ API keys entered during bootstrap are not persisted
- ✅ Regular conversation mode still works with history
- ✅ Tests verify both security and functionality
- ✅ No linting errors
- ✅ No type checking errors
- ✅ All existing tests pass (except pre-existing failures)