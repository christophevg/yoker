# API Design: Write/Update Tool Content Display

**Date**: 2026-05-05
**Task**: 1.5.5 - Show Write/Update Tool Content in CLI
**Purpose**: Design backend architecture for displaying file content during write and update operations

## Summary

This document designs the event system and configuration changes needed to display file content during WriteTool and UpdateTool operations. The design extends the existing event system with content metadata, adds configuration options for verbosity, and handles large files with truncation.

## Current State Analysis

### Existing Event Types

The current event system (`src/yoker/events/types.py`) has:

- `ToolCallEvent` - emitted when a tool is called, contains `tool_name` and `arguments`
- `ToolResultEvent` - emitted when a tool returns, contains `tool_name`, `result`, and `success`

### Current Tool Output

**WriteTool** (`src/yoker/tools/write.py`):
- Returns `ToolResult(success=True, result="File written successfully")` on success
- Returns `ToolResult(success=False, result="", error="...")` on failure
- No content information in result

**UpdateTool** (`src/yoker/tools/update.py`):
- Returns `ToolResult(success=True, result="File updated successfully")` on success
- Returns `ToolResult(success=False, result="", error="...")` on failure
- No content or diff information in result

### Current Event Handler

`ConsoleEventHandler._handle_tool_result()`:
- Shows `✓ Success` or `✗ <error message>` for tool results
- No content display, just success/failure indicator

### Current Configuration

`WriteToolConfig`:
```python
allow_overwrite: bool = False
max_size_kb: int = 1000
blocked_extensions: tuple[str, ...] = (".exe", ".sh", ".bat")
```

`UpdateToolConfig`:
```python
require_exact_match: bool = True
max_diff_size_kb: int = 100
```

## Design Recommendations

### 1. Event System Changes

#### Option A: New Event Type (Recommended)

Create a new `ToolContentEvent` for content display:

```python
@dataclass(frozen=True)
class ToolContentEvent(Event):
  """Emitted when a tool has content to display (write/update operations).

  This event is optional - tools can emit it when they have meaningful
  content to show. The event handler can choose to display or ignore it.
  """

  tool_name: str
  operation: str  # "write", "replace", "insert_before", "insert_after", "delete"
  path: str  # Resolved file path
  content_type: str  # "full", "diff", "summary"
  content: str | None = None  # Content to display (truncated if too large)
  metadata: dict[str, Any] = field(default_factory=dict)
  # For diff operations:
  # - old_content: original content (before)
  # - new_content: modified content (after)
  # - line_count: number of lines affected
```

**Rationale**:
- Separate event type allows granular control
- Optional event - doesn't affect tools that don't need it
- Supports both full content and diff views
- Metadata field allows extensibility

#### Option B: Extend ToolResultEvent

Add content fields to `ToolResultEvent`:

```python
@dataclass(frozen=True)
class ToolResultEvent(Event):
  tool_name: str
  result: str
  success: bool = True
  # New fields:
  content: str | None = None
  content_type: str = "summary"  # "full", "diff", "summary"
  metadata: dict[str, Any] = field(default_factory=dict)
```

**Drawbacks**:
- Couples content display to result event
- Less flexible for future extensions
- Breaks existing event handlers

#### Recommendation: Option A

Create a new `ToolContentEvent` that is emitted after `ToolResultEvent`. This:
- Keeps content display optional
- Allows handlers to ignore content if not needed
- Doesn't break existing event handlers
- Provides clear separation between result and content

### 2. Configuration Schema

Add a new configuration section for content display:

```python
@dataclass(frozen=True)
class ContentDisplayConfig:
  """Configuration for displaying file content in tool operations.

  Attributes:
    show_content: Whether to show content for write/update operations.
    max_content_lines: Maximum lines to show before truncation.
    max_content_bytes: Maximum bytes to show before truncation.
    show_diff_for_updates: Whether to show before/after for updates.
    max_diff_lines: Maximum lines in diff display.
    syntax_highlight: Whether to apply syntax highlighting.
  """

  show_content: bool = True
  max_content_lines: int = 50
  max_content_bytes: int = 4096  # 4KB default
  show_diff_for_updates: bool = True
  max_diff_lines: int = 30
  syntax_highlight: bool = True
```

Add to `ToolsConfig`:

```python
@dataclass(frozen=True)
class ToolsConfig:
  # ... existing fields ...
  content_display: ContentDisplayConfig = field(default_factory=ContentDisplayConfig)
```

### 3. Content Handling Strategy

#### Truncation Strategy

For large files:

1. **Line-based truncation** (preferred):
   - Show first N lines (configurable: `max_content_lines`)
   - Show last M lines if showing only first loses context
   - Append "... N more lines" message

2. **Byte-based truncation**:
   - Fallback for very long lines
   - Truncate at `max_content_bytes`
   - Append "... (truncated)" message

3. **Smart truncation**:
   - For updates, show affected lines + context (±3 lines)
   - For full content, show beginning and end

#### Format for Content Display

**Write Operations**:
```
Write tool: example.py
────────────────────────────────────────
def hello():
    print("Hello, World!")
────────────────────────────────────────
```

**Update Operations (Diff)**:
```
Update tool: example.py (replace)
────────────────────────────────────────
- def hello():
-     print("Hello, World!")
+ def hello(name):
+     print(f"Hello, {name}!")
────────────────────────────────────────
```

**Update Operations (Full)**:
For small changes or when diff is not available:
```
Update tool: example.py (insert_after line 5)
────────────────────────────────────────
def hello():
    print("Hello, World!")
    return True  # <- inserted
────────────────────────────────────────
```

#### Diff Generation for Updates

For `UpdateTool`, track old and new content:

1. **Replace operation**:
   - Store original content before replacement
   - Store new content after replacement
   - Generate unified diff for display

2. **Insert operations**:
   - Show the line being inserted
   - Show context (±2 lines around insertion point)

3. **Delete operation**:
   - Show the deleted content
   - Show context around deletion point

### 4. Integration Points

#### WriteTool Changes

```python
def execute(self, **kwargs: Any) -> ToolResult:
  # ... existing validation and write logic ...

  # Emit content event if content display is enabled
  if self._config.tools.content_display.show_content:
    content_to_show = self._truncate_content(content, self._config)
    # Emit event via callback or return metadata
    # (see Event Emission Strategy below)

  return ToolResult(
    success=True,
    result="File written successfully",
    # Content is emitted separately via event
  )
```

#### UpdateTool Changes

```python
def execute(self, **kwargs: Any) -> ToolResult:
  # ... existing validation ...

  # Read original content
  original_content = resolved.read_text(encoding="utf-8")

  # ... perform operation ...

  # For replace operations, generate diff
  if operation == "replace" and self._config.tools.content_display.show_diff_for_updates:
    diff = self._generate_diff(original_content, result_content)
    # Emit event via callback or return metadata

  return ToolResult(success=True, result="File updated successfully")
```

#### Event Emission Strategy

Tools don't have direct access to event emission. Two approaches:

**Option A: Content Metadata in ToolResult (Recommended)**

Extend `ToolResult` to include optional content metadata:

```python
@dataclass
class ToolResult:
  success: bool
  result: str
  error: str = ""
  # New fields:
  content_metadata: dict[str, Any] | None = None
```

The `Agent` class checks for `content_metadata` and emits `ToolContentEvent`:

```python
# In Agent.process()
if tool_result.content_metadata:
  self._emit(
    ToolContentEvent(
      type=EventType.TOOL_CONTENT,
      tool_name=tool_name,
      **tool_result.content_metadata
    )
  )
```

**Option B: Tool Content Callback**

Add optional callback to Tool base class:

```python
class Tool(ABC):
  def __init__(
    self,
    guardrail: Guardrail | None = None,
    content_callback: Callable[[dict[str, Any]], None] | None = None,
  ) -> None:
    self._guardrail = guardrail
    self._content_callback = content_callback
```

**Recommendation**: Option A is simpler and keeps tools stateless.

#### ConsoleEventHandler Changes

Add handler for `ToolContentEvent`:

```python
def _handle_tool_content(self, event: ToolContentEvent) -> None:
  """Handle tool content event."""
  if not self.show_tool_calls:
    return

  # Format header
  tool_name = self._capitalize(event.tool_name)
  operation = event.operation
  path = Path(event.path).name

  header = f"{tool_name} tool: {path} ({operation})"
  self.console.print(f"\n{header}", style=TOOL_STYLE)

  # Show content based on type
  if event.content_type == "diff":
    self._show_diff_content(event)
  elif event.content_type == "full":
    self._show_full_content(event)
  else:
    self._show_summary(event)

def _show_full_content(self, event: ToolContentEvent) -> None:
  """Show full file content with truncation."""
  if event.content is None:
    return

  # Apply syntax highlighting if enabled
  if self.syntax_highlight:
    # Use Rich syntax highlighting
    from rich.syntax import Syntax
    syntax = Syntax(
      event.content,
      lexer="python",  # Auto-detect from extension
      theme="monokai",
      line_numbers=True,
    )
    self.console.print(syntax)
  else:
    self.console.print("─" * 50)
    self.console.print(event.content)
    self.console.print("─" * 50)

def _show_diff_content(self, event: ToolContentEvent) -> None:
  """Show before/after diff for updates."""
  old_content = event.metadata.get("old_content", "")
  new_content = event.metadata.get("new_content", "")

  # Use difflib for unified diff
  import difflib
  diff = difflib.unified_diff(
    old_content.splitlines(keepends=True),
    new_content.splitlines(keepends=True),
    fromfile="before",
    tofile="after",
  )

  # Print diff with colors
  self.console.print("─" * 50)
  for line in diff:
    if line.startswith("+"):
      self.console.print(line.rstrip(), style=Style(color="green"))
    elif line.startswith("-"):
      self.console.print(line.rstrip(), style=Style(color="red"))
    elif line.startswith("@"):
      self.console.print(line.rstrip(), style=Style(color="cyan"))
    else:
      self.console.print(line.rstrip())
  self.console.print("─" * 50)
```

### 5. Backwards Compatibility

The design maintains backwards compatibility:

1. **New event type is optional** - handlers that don't know about `ToolContentEvent` simply ignore it
2. **Existing events unchanged** - `ToolCallEvent` and `ToolResultEvent` work as before
3. **Configuration defaults to current behavior** - `show_content=False` by default maintains silence
4. **ToolResult extension is optional** - tools that don't set `content_metadata` work as before

To enable content display:

```toml
[tools.content_display]
show_content = true
show_diff_for_updates = true
max_content_lines = 50
```

## Implementation Checklist

### Phase 1: Core Infrastructure

- [ ] Add `ToolContentEvent` to `src/yoker/events/types.py`
- [ ] Add `ContentDisplayConfig` to `src/yoker/config/schema.py`
- [ ] Add `content_metadata` field to `ToolResult` in `src/yoker/tools/base.py`
- [ ] Update `EventType` enum to include `TOOL_CONTENT`

### Phase 2: Tool Changes

- [ ] Update `WriteTool.execute()` to include content metadata
- [ ] Update `UpdateTool.execute()` to track old/new content and generate diff
- [ ] Add `_truncate_content()` helper method to both tools
- [ ] Add `_generate_diff()` helper to `UpdateTool`

### Phase 3: Agent Integration

- [ ] Update `Agent.process()` to check for `content_metadata` in tool results
- [ ] Emit `ToolContentEvent` after `ToolResultEvent` when metadata present

### Phase 4: Console Handler

- [ ] Add `_handle_tool_content()` to `ConsoleEventHandler`
- [ ] Add `_show_full_content()` and `_show_diff_content()` methods
- [ ] Add syntax highlighting support (Rich Syntax)
- [ ] Add truncation indicators ("... N more lines")

### Phase 5: Testing

- [ ] Unit tests for `ToolContentEvent` creation
- [ ] Unit tests for content truncation logic
- [ ] Unit tests for diff generation
- [ ] Integration tests for event emission
- [ ] Visual tests for console output

### Phase 6: Documentation

- [ ] Update README.md with content display examples
- [ ] Add demo script for write tool content display
- [ ] Add demo script for update tool diff display
- [ ] Generate screenshots for documentation

## File Changes Summary

| File | Changes |
|------|---------|
| `src/yoker/events/types.py` | Add `ToolContentEvent`, `EventType.TOOL_CONTENT` |
| `src/yoker/config/schema.py` | Add `ContentDisplayConfig`, update `ToolsConfig` |
| `src/yoker/tools/base.py` | Add `content_metadata` to `ToolResult` |
| `src/yoker/tools/write.py` | Add content metadata emission |
| `src/yoker/tools/update.py` | Add diff tracking and content metadata |
| `src/yoker/events/handlers.py` | Add `_handle_tool_content()` and display methods |
| `src/yoker/agent.py` | Check for content metadata and emit events |

## Alternative Approaches Considered

### Alternative 1: Content in ToolResult

Instead of a separate event, include full content in `ToolResult.result`.

**Rejected because**:
- Couples content display to tool result
- Large content could overwhelm result parsing
- Less flexible for future enhancements

### Alternative 2: Always Show Content

Display content unconditionally for write/update operations.

**Rejected because**:
- Not all use cases need content display
- Large files would flood console output
- Configuration allows user control

### Alternative 3: Streaming Content

Stream content as it's being written/updated.

**Rejected because**:
- Write/update operations are atomic
- No intermediate states to stream
- Adds complexity without clear benefit

## Questions for Implementation

1. **Syntax Highlighting**: Should we use Rich's `Syntax` class for code highlighting? It requires knowing the file extension. We could auto-detect from path.

2. **Diff Algorithm**: Should we use Python's `difflib.unified_diff` or a more sophisticated diff library for better diff visualization?

3. **Large File Handling**: For very large files, should we show:
   - First N lines only?
   - First N and last M lines?
   - Structured summary (file size, line count, first few lines)?

4. **Binary Files**: Should we skip content display for binary files? How to detect binary files?

5. **Update Operation Display**: For update operations, should we show:
   - Full diff with context?
   - Just the changed lines?
   - Both (configurable)?