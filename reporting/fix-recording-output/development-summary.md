# Fix Recording Output - Development Summary

## What was implemented

Fixed the difference between interactive and non-interactive console output in the demo script by preventing Rich's `Live` display from capturing intermediate states during SVG generation.

## Problem Analysis

**Symptom:**
- When piped to `less`: Output was clean (no repeated content)
- When run in interactive terminal: Output had repeated content in the SVG

**Root Cause:**
Rich's `Live` display updates the console multiple times per second during streaming. When `console.record=True` is enabled for SVG generation, each `Live.update()` call gets recorded, resulting in all intermediate states being captured in the SVG.

This happened because:
1. `ConsoleEventHandler` used `LiveDisplay` (which wraps Rich's `Live`)
2. `LiveDisplay` created a `Live` context regardless of whether the console was recording
3. When recording, every intermediate update was captured in the SVG

## Solution

Moved the recording detection from `ConsoleEventHandler` to `LiveDisplay`:

1. **Added `_is_recording` flag to `LiveDisplay`** (`src/yoker/events/spinner.py`):
   - Checks `console.record` on initialization
   - Stores the flag for later use

2. **Modified `LiveDisplay.__enter__`**:
   - Only creates `Live` context when NOT recording
   - When recording, skips `Live` and just accumulates text

3. **Modified `LiveDisplay.__exit__`**:
   - When recording, prints accumulated text directly to console
   - When not recording, exits the `Live` context normally

4. **Updated `LiveDisplay._update`**:
   - Added docstring clarifying it's a no-op when recording

5. **Removed `_is_recording` from `ConsoleEventHandler`** (`src/yoker/events/handlers.py`):
   - No longer needed since `LiveDisplay` handles it internally
   - Removed all `if not self._is_recording:` checks for spinner calls

## Files Modified

1. `src/yoker/events/spinner.py` - LiveDisplay class
   - Added `_is_recording` attribute
   - Modified `__enter__` to skip `Live` when recording
   - Modified `__exit__` to print accumulated content when recording
   - Updated `_update` docstring

2. `src/yoker/events/handlers.py` - ConsoleEventHandler class
   - Removed `_is_recording` attribute
   - Removed all conditional spinner checks (now handled by LiveDisplay)

3. `tests/test_svg_generation.py` - Test suite
   - Updated tests to check `LiveDisplay._is_recording` instead of `ConsoleEventHandler._is_recording`
   - Tests now verify that `LiveDisplay` correctly detects recording mode

## Tests

All tests pass:
- Unit tests: `make test` - 1222 passed
- Linting: `make lint` - No errors
- Type checking: `make typecheck` - Success

## Verification

Verified the fix works correctly:
- SVG generation now shows clean output without repeated content
- Interactive terminal still shows spinner and real-time updates
- Both modes work correctly

Example output from demo script:
```
> List files matching "CLAUDE*" in the current directory. Reply in 2 lines or less.
The user wants me to list files matching "CLAUDE*" in the current directory and reply in 2 lines or less. I should use
the list function with a pattern to find files matching that glob pattern.

⏺ List tool:
  ✓ Success

The result shows there's 1 file matching the pattern "CLAUDE*" in the current directory: CLAUDE.md. I need to reply in 2
lines or less.

Found 1 file: CLAUDE.md
⏱ 1.2s | 1807+47=1854 tokens | 1578 tok/s
```

The tool call and success message appear only once in the SVG.