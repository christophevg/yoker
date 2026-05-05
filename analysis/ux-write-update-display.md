# UX Analysis: Write/Update Tool Content Display

**Task**: 1.5.5 - Show Write/Update Tool Content in CLI
**Date**: 2026-05-05
**Status**: Analysis Complete

## Executive Summary

This document analyzes the user experience requirements for displaying file content during write and update operations in the yoker CLI. The goal is to provide visual consistency with the Read tool while offering users appropriate information about what is being written or modified.

## Current State Analysis

### ReadTool Display Pattern

**Location**: `src/yoker/events/handlers.py` (lines 228-283)

**Current Implementation**:
```
Read tool: <filename>
  ✓ Success
```

**Key Design Elements**:
- Tool name in cyan color (matches `TOOL_STYLE`)
- Simple filename display (basename only, not full path)
- Success/failure indicator with checkmark/cross
- No content preview for Read (content returned to LLM, not displayed)

### Write/Update Current State

**WriteTool** (`src/yoker/tools/write.py`):
- Returns: `ToolResult(success=True, result="File written successfully")`
- No content in result
- Arguments: `path`, `content`, `create_parents`

**UpdateTool** (`src/yoker/tools/update.py`):
- Returns: `ToolResult(success=True, result="File updated successfully")`
- No content in result
- Arguments: `path`, `operation`, `old_string`, `new_string`, `line_number`
- Operation types: `replace`, `insert_before`, `insert_after`, `delete`

**Current Display** (from handlers.py):
```
Write tool: <filename>
  ✓ Success
```

**Problem**: User cannot see what content was written or what changes were made.

## User Experience Requirements

### 1. Visual Consistency

**Read Tool Pattern** (reference):
- Cyan color for tool name
- Simple filename display
- Success/failure indicator

**Write Tool Needs**:
- Show operation type: Write (new file) or Write (overwrite)
- Show filename
- For new files: show content preview
- For overwrites: show content preview with overwrite warning

**Update Tool Needs**:
- Show operation type: Replace, Insert, Delete
- Show filename and location
- For small changes: show diff-style before/after
- For large changes: show summary only

### 2. Content Display Format

#### Write Tool Display

```
Write tool: <filename>
  Creating new file (create_parents: true)
  --- Content (N lines) ---
  <first few lines>
  ...
  <last line if truncated>
  --- End ---
  ✓ Success
```

**Alternative (compact)**:
```
Write tool: <filename>
  [New file] 15 lines written
  ✓ Success
```

#### Update Tool Display

For **replace** operations:
```
Update tool: <filename>
  Replace operation:
  - "old text"
  + "new text"
  ✓ Success
```

For **insert** operations:
```
Update tool: <filename>
  Insert after line 42:
  + "new line content"
  ✓ Success
```

For **delete** operations:
```
Update tool: <filename>
  Delete line 15:
  - "deleted line content"
  ✓ Success
```

### 3. Verbosity Control

**Configuration Options** (proposed addition to `Config`):

```python
@dataclass(frozen=True)
class DisplayConfig:
  """Display configuration for tool output."""
  
  # Verbosity level: 'silent', 'summary', 'content'
  # - silent: Show only tool name and success/failure
  # - summary: Show tool name, operation, and line count
  # - content: Show full content preview
  tool_output_verbosity: str = "summary"
  
  # Maximum lines to show before truncation
  max_content_lines: int = 10
  
  # Show diffs for update operations (before/after)
  show_diffs: bool = True
  
  # Maximum diff size to display (in lines)
  max_diff_lines: int = 5
```

**Recommended Defaults**:
- `tool_output_verbosity: "summary"` - Balance between information and noise
- `max_content_lines: 10` - Show first 5 and last 5 for long files
- `show_diffs: True` - Useful for verifying changes
- `max_diff_lines: 5` - Keep diffs manageable

### 4. Implementation Approaches

#### Option A: Extend ToolResult (Simplest)

**Pros**:
- Minimal changes to existing code
- Content captured in result string
- No new event types needed

**Cons**:
- Mixes display logic with tool logic
- Result string becomes display string (not ideal)
- Less flexible for future enhancements

**Implementation**:
```python
# In WriteTool.execute()
if success:
  if config.display.tool_output_verbosity == "content":
    preview = self._format_content_preview(content, config.display.max_content_lines)
    result = f"File written successfully\n{preview}"
  elif config.display.tool_output_verbosity == "summary":
    lines = len(content.splitlines())
    result = f"File written successfully ({lines} lines)"
  else:  # silent
    result = "File written successfully"
```

#### Option B: Add Content to Events (Recommended)

**Pros**:
- Clean separation between tool logic and display logic
- Display logic stays in ConsoleEventHandler
- Flexible for future enhancements (color, formatting)
- Consistent with event-driven architecture

**Cons**:
- Requires extending event types
- Slightly more complex

**Implementation**:

1. **Extend ToolCallEvent**:
```python
@dataclass(frozen=True)
class ToolCallEvent(Event):
  """Emitted when a tool is called."""
  
  tool_name: str
  arguments: dict[str, Any]
  # New fields for content display
  content_preview: str | None = None  # For write operations
  operation_type: str | None = None    # For update operations
  diff_preview: str | None = None      # For update operations
```

2. **Extend ToolResultEvent**:
```python
@dataclass(frozen=True)
class ToolResultEvent(Event):
  """Emitted when a tool returns a result."""
  
  tool_name: str
  result: str
  success: bool = True
  # New fields for result details
  lines_written: int | None = None     # For write operations
  lines_modified: int | None = None    # For update operations
```

3. **Update Agent.emit_tool_call**:
```python
# In Agent._process_tool_call()
# Capture content for write/update tools and include in event
content_preview = None
if tool_name == "write" and config.display.tool_output_verbosity == "content":
  content_preview = self._format_content_preview(arguments.get("content", ""))
```

4. **Update ConsoleEventHandler**:
```python
def _handle_tool_call(self, event: ToolCallEvent) -> None:
  if self.show_tool_calls:
    tool_name = self._capitalize(event.tool_name)
    
    # Format based on content availability
    if event.content_preview:
      self.console.print(f"\n{tool_name} tool: {self._extract_filename(event.arguments)}")
      self.console.print(event.content_preview, style="dim")
    else:
      details = self._format_tool_details(event.tool_name, event.arguments)
      self.console.print(f"\n{tool_name} tool: {details}", style=TOOL_STYLE)
```

#### Option C: Separate Display Formatter Class (Cleanest)

**Pros**:
- Complete separation of concerns
- Display logic isolated in one place
- Easy to extend for new tools
- Testable independently

**Cons**:
- More files to maintain
- Additional abstraction layer

**Implementation**:
```python
# src/yoker/display/formatter.py

class ToolOutputFormatter:
  """Formats tool output for display."""
  
  def __init__(self, config: DisplayConfig):
    self.config = config
  
  def format_write_preview(
    self,
    path: str,
    content: str,
    is_overwrite: bool,
  ) -> str | None:
    """Format write operation preview."""
    if self.config.tool_output_verbosity == "silent":
      return None
    
    lines = content.splitlines()
    filename = Path(path).name
    
    if self.config.tool_output_verbosity == "summary":
      operation = "Overwriting" if is_overwrite else "Creating"
      return f"{operation} {filename} ({len(lines)} lines)"
    
    # content verbosity
    return self._format_full_preview(filename, content, is_overwrite)
  
  def format_update_preview(
    self,
    path: str,
    operation: str,
    old_string: str | None,
    new_string: str | None,
    line_number: int | None,
  ) -> str | None:
    """Format update operation preview."""
    if self.config.tool_output_verbosity == "silent":
      return None
    
    filename = Path(path).name
    
    if self.config.tool_output_verbosity == "summary":
      return self._format_summary(filename, operation, old_string, new_string)
    
    # content verbosity with diffs
    return self._format_diff_preview(filename, operation, old_string, new_string, line_number)
```

## Recommended Approach

**Use Option B (Add Content to Events)** with elements of Option C (Display Formatter).

### Rationale

1. **Event-driven consistency**: The system already uses events for all display logic. Adding content fields maintains this pattern.

2. **Separation of concerns**: Display logic stays in `ConsoleEventHandler` where it belongs, not in tools.

3. **Configurability**: Adding `DisplayConfig` allows users to control verbosity without changing code.

4. **Future-proof**: Easy to add more display features (syntax highlighting, colors, etc.) without touching tool implementations.

### Implementation Plan

#### Phase 1: Configuration

1. Add `DisplayConfig` dataclass to `config/schema.py`
2. Add `display` field to `Config` dataclass
3. Update config loader to parse display settings
4. Default: `tool_output_verbosity: "summary"`

#### Phase 2: Event Types

1. Extend `ToolCallEvent` with:
   - `content_preview: str | None = None`
   - `operation_type: str | None = None`

2. Extend `ToolResultEvent` with:
   - `lines_written: int | None = None`
   - `lines_modified: int | None = None`

#### Phase 3: Display Logic

1. Create helper methods in `ConsoleEventHandler`:
   - `_format_write_preview(arguments, config)`
   - `_format_update_preview(arguments, config)`
   - `_format_diff(old_string, new_string)`

2. Update `_handle_tool_call` to use preview formatting

3. Update `_handle_tool_result` to show summary info

#### Phase 4: Tool Updates

1. Modify `Agent._process_tool_call()` to extract content for preview
2. Pass `DisplayConfig` to agent through config
3. Emit content in `ToolCallEvent`

### Configuration File Example

```toml
[display]
# Verbosity: 'silent', 'summary', 'content'
tool_output_verbosity = "summary"

# Maximum lines to show before truncation
max_content_lines = 10

# Show diffs for update operations
show_diffs = true

# Maximum diff lines to display
max_diff_lines = 5
```

### Display Examples by Verbosity Level

#### Silent Mode
```
Write tool: example.py
  ✓ Success
```

#### Summary Mode (Recommended Default)
```
Write tool: example.py
  Creating new file (24 lines)
  ✓ Success
```

```
Update tool: example.py
  Replace at line 15: "old text" → "new text"
  ✓ Success
```

#### Content Mode
```
Write tool: example.py
  Creating new file:
  1: """Module docstring."""
  2: 
  3: def hello():
  4:     print("Hello, world!")
  ... (20 more lines)
  ✓ Success
```

```
Update tool: example.py
  Replace operation:
  - "print('hello')"
  + "print('Hello, World!')"
  ✓ Success
```

## Edge Cases

### Large Files

**Problem**: Showing 1000+ lines of content is unreadable.

**Solution**: Always truncate with configurable `max_content_lines`.

```
Write tool: large_file.py
  Creating new file (1500 lines):
  1-10: <first 10 lines>
  ... (1480 lines truncated)
  1491-1500: <last 10 lines>
  ✓ Success
```

### Binary Files

**Problem**: Binary content is not displayable.

**Solution**: Detect binary files and show size only.

```
Write tool: image.png
  Creating new file (245 KB binary)
  ✓ Success
```

### Unicode/Encoding Issues

**Problem**: Invalid UTF-8 sequences cause display errors.

**Solution**: Replace invalid bytes with placeholder character (already handled by tools with `errors="replace"`).

### Empty Files

**Problem**: Empty content is valid but looks odd.

**Solution**: Show explicit empty indicator.

```
Write tool: empty.txt
  Creating new file (0 lines, empty)
  ✓ Success
```

## Testing Requirements

1. **Unit Tests** (in `tests/test_events/test_handlers.py`):
   - Test `_format_write_preview` with various content sizes
   - Test `_format_update_preview` for each operation type
   - Test `_format_diff` with multi-line changes
   - Test truncation logic

2. **Integration Tests**:
   - Test full write flow with display
   - Test full update flow with display
   - Test verbosity configuration changes

3. **Visual Tests**:
   - Demo script showing all verbosity levels
   - Demo script showing update operations

## Acceptance Criteria

1. **Visual Consistency**: Write/Update display matches Read tool styling (cyan color, filename-only display)

2. **Verbosity Control**: Three levels (silent, summary, content) configurable via TOML

3. **Content Display**:
   - Write: Shows operation type, filename, and line count/preview
   - Update: Shows operation type, location, and diff preview

4. **Large Content**: Truncation with "... N more lines" indicator

5. **Diff Display**: For updates, shows before/after for small changes (≤5 lines)

6. **No Breaking Changes**: Existing configuration works with sensible defaults

7. **Tests**: All unit and integration tests pass

8. **Documentation**: README and CLAUDE.md updated with display configuration

## Files to Modify

| File | Changes |
|------|---------|
| `src/yoker/config/schema.py` | Add `DisplayConfig` dataclass |
| `src/yoker/events/types.py` | Extend `ToolCallEvent` and `ToolResultEvent` |
| `src/yoker/events/handlers.py` | Add `_format_write_preview`, `_format_update_preview`, `_format_diff` methods |
| `src/yoker/agent.py` | Pass display config to events, extract content for preview |
| `tests/test_events/test_handlers.py` | Add tests for new formatting methods |
| `README.md` | Document display configuration options |
| `CLAUDE.md` | Update current state and add display config to checklist |

## Dependencies

- **Task 1.5.4** (Event Logging System): Must be complete (provides event infrastructure)
- **Task 1.5.3** (Demo Session Script): Provides visual testing capability

## Timeline Estimate

- **Configuration**: 1 hour
- **Event Types**: 30 minutes
- **Display Logic**: 2-3 hours
- **Tool Updates**: 1 hour
- **Tests**: 2 hours
- **Documentation**: 1 hour

**Total**: 7.5-8.5 hours

## Related Documentation

- `analysis/ux-demo-session.md` - Demo session UX analysis
- `analysis/ux-mouse-selection.md` - Mouse selection UX analysis
- `reporting/1.5.4-event-logging/summary.md` - Event logging implementation