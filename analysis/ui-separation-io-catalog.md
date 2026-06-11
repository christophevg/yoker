# UI Separation - IO Operations Catalog

**Document Status:** Draft
**Created:** 2026-06-11
**Last Updated:** 2026-06-11

## Overview

This document catalogs all input/output operations in the current codebase, identifying where they are and how they should be handled in the new architecture.

---

## 1. Input Operations

### 1.1 User Message Input

| Location | Operation | Current Implementation | UI Handler Method |
|----------|-----------|----------------------|-------------------|
| `__main__.py:103` | User message input | `prompt_input_async()` via prompt_toolkit | `get_input(prompt)` |
| `__main__.py:243` | Interactive prompt loop | `while True:` with `prompt_input_async()` | Session loop in UI |

**Batch alternatives:**
- **stdin**: Read from standard input (one message per line)
- **--script FILE**: Read from file (multiple messages)
- **--prompt TEXT**: Single CLI argument

---

## 2. Output Operations

### 2.1 Session Lifecycle (Removed from Agent)

**Note:** Session lifecycle events are removed from Agent. The UI calls `start()` and `shutdown()` directly, without events.

| Current Location | Current Event | Migration |
|-----------------|---------------|-----------|
| `handlers.py:146-150` | Session start banner | **Removed** - UI calls `start()` directly |
| `handlers.py:154` | Session end message | **Removed** - UI calls `shutdown()` directly |

**Rationale:**
- Agent does NOT have session lifecycle (`begin_session()`, `end_session()` removed)
- UI calls `start()` and `shutdown()` on UI handler directly
- Future: Session concept (multi-agent) may reintroduce these at a higher level

### 2.2 Turn Lifecycle

| Location | Operation | Content | Current Event | UI Handler Method |
|----------|-----------|---------|---------------|-------------------|
| `handlers.py:159-165` | Turn start | Reset flags, prepare for new turn | `TurnStartEvent` | Internal state |
| `handlers.py:167-191` | Turn end | Stats (timing, tokens), cleanup | `TurnEndEvent` | `output_stats(...)` |

### 2.3 Thinking Stream

| Location | Operation | Content | Current Event | UI Handler Method |
|----------|-----------|---------|---------------|-------------------|
| `handlers.py:193-213` | Thinking start | Separator, start LiveDisplay | `ThinkingStartEvent` | `start_thinking_stream()` |
| `handlers.py:214-220` | Thinking chunk | Stream thinking text | `ThinkingChunkEvent` | `stream_thinking(chunk)` |
| `handlers.py:222-227` | Thinking end | Newlines after thinking | `ThinkingEndEvent` | `end_thinking_stream(length)` |

### 2.4 Content Stream

| Location | Operation | Content | Current Event | UI Handler Method |
|----------|-----------|---------|---------------|-------------------|
| `handlers.py:229-251` | Content start | Separator, start LiveDisplay | `ContentStartEvent` | `start_content_stream()` |
| `handlers.py:253-258` | Content chunk | Stream response text | `ContentChunkEvent` | `stream_content(chunk, content_type)` |
| `handlers.py:260-264` | Content end | Final newline | `ContentEndEvent` | `end_content_stream(length)` |

### 2.5 Tool Execution

| Location | Operation | Content | Current Event | UI Handler Method |
|----------|-----------|---------|---------------|-------------------|
| `handlers.py:306-321` | Tool call | Tool name, arguments | `ToolCallEvent` | `output_tool_call(tool, args)` |
| `handlers.py:362-380` | Tool result | Success/failure status | `ToolResultEvent` | `output_tool_result(tool, success, result)` |
| `handlers.py:381-418` | Tool content | File content, diff display | `ToolContentEvent` | `output_tool_content(tool, op, path, content, type, meta)` |

### 2.6 Errors

| Location | Operation | Content | Current Type | UI Handler Method |
|----------|-----------|---------|--------------|-------------------|
| `handlers.py:539-544` | Error event | Error type, message | `ErrorEvent` | `output_error(exception)` |
| `handlers.py:546-549` | Command result | Command output | `CommandEvent` | `output_command_result(result)` |
| `__main__.py:287-291` | Network error | Network error message | Exception | `output_error(exception)` |
| `__main__.py:318-322` | Recoverable error | Retry message | Exception | `output_error(exception)` |
| `__main__.py:328-336` | Ollama error | API error message | Exception | `output_error(exception)` |

### 2.7 Agent Info

| Location | Operation | Content | Current Type | UI Handler Method |
|----------|-----------|---------|--------------|-------------------|
| `__main__.py:396-399` | Agent loaded | Agent name, description, tools | Direct print | `start(model, version, config)` |

---

## 3. Content Types

### 3.1 Events with Variable Content Types

These events need `content_type` field because content type varies:

| Event | Possible Content Types | Notes |
|-------|------------------------|-------|
| `ContentChunkEvent` | `text/plain`, `text/markdown`, `text/html` | LLM output, type from LLM or detection |
| `ToolContentEvent` | `text/plain`, `text/x-diff`, `application/json` | Tool output, type from tool |

### 3.2 Events with Fixed Content Types

These events have implicit content type (no `content_type` field needed):

| Event | Content Type | Notes |
|-------|-------------|-------|
| `ThinkingChunkEvent` | `text/plain` | LLM thinking trace |
| `ToolCallEvent` | Structured data | Tool name + arguments |
| `ToolResultEvent` | Structured data | Success + result string |
| ~~`SessionStartEvent`~~ | ~~Structured data~~ | ~~Removed from Agent~~ |
| ~~`SessionEndEvent`~~ | ~~Structured data~~ | ~~Removed from Agent~~ |
| `TurnEndEvent` | Structured data | Stats |

### 3.3 Content Type Detection

**Strategy:**
1. Use library to detect from content (e.g., `python-magic`, `chardet`)
2. Fallback: Detect from file extension
3. Fallback: Default to `text/plain`

**Implementation:**
```python
# In ReadTool or similar
def detect_content_type(content: bytes, path: Path) -> str:
    # Try content detection
    try:
        import magic
        mime = magic.from_buffer(content, mime=True)
        if mime.startswith('text/'):
            return mime
    except ImportError:
        pass
    
    # Fallback: extension
    ext = path.suffix.lower()
    mime_map = {
        '.md': 'text/markdown',
        '.html': 'text/html',
        '.json': 'application/json',
        '.py': 'text/plain',  # with syntax highlighting
        '.diff': 'text/x-diff',
    }
    if ext in mime_map:
        return mime_map[ext]
    
    # Fallback: plain text
    return 'text/plain'
```

---

## 4. ANSI Handling

### 4.1 Sources

| Source | Can Produce ANSI? | Handling |
|--------|------------------|----------|
| Tool output (git, etc.) | Yes | Use `--no-color` flags, strip if needed |
| LLM content | Yes (if instructed) | Preserve, bubble to UI |
| LLM thinking | Yes (if instructed) | Preserve, bubble to UI |
| Agent events | No | Agent doesn't add ANSI |

### 4.2 Tool Implementation

Tools that could produce ANSI should:

```python
class GitTool:
    def execute(self, operation: str, ...):
        # Force plain text output
        args = [operation, "--no-color", ...]
        result = self._run_git(args)
        return ToolResult(result=result, ...)

class ReadTool:
    def execute(self, file_path: str, ...):
        content = self._read_file(file_path)
        # Content may contain ANSI from file itself
        # Preserve as-is
        return ToolResult(result=content, ...)
```

### 4.3 UI Handling

```python
class InteractiveUIHandler:
    def stream_content(self, chunk: str, content_type: str):
        # Rich console can handle ANSI
        self.console.print(chunk)

class BatchUIHandler:
    def stream_content(self, chunk: str, content_type: str):
        # Preserve ANSI for piping
        sys.stdout.write(chunk)
```

---

## 5. Streaming Considerations

### 5.1 Default: Streaming

- Agent always streams (backend default)
- UI receives chunks via events
- UI decides how to display

### 5.2 UI Buffering (Optional)

UI implementations that want buffered output can:

```python
class BufferedUIHandler(BaseUIHandler):
    def __init__(self):
        self._content_buffer = []
        self._thinking_buffer = []
    
    def stream_content(self, chunk: str, content_type: str):
        self._content_buffer.append(chunk)
    
    def end_content_stream(self, total_length: int):
        content = "".join(self._content_buffer)
        self._display_buffered(content, content_type)
        self._content_buffer = []
```

This allows API/UI implementations to receive complete content instead of streaming.

---

## 6. Event to UI Method Mapping

| Event | UI Handler Method(s) | Notes |
|-------|---------------------|-------|
| ~~`SessionStartEvent`~~ | ~~UI calls `start()` directly~~ | ~~Removed from Agent~~ |
| ~~`SessionEndEvent`~~ | ~~UI calls `shutdown()` directly~~ | ~~Removed from Agent~~ |
| `TurnStartEvent` | Internal state | Start of turn |
| `TurnEndEvent` | `output_stats(...)` | Stats display |
| `ThinkingStartEvent` | `start_thinking_stream()` | Start thinking |
| `ThinkingChunkEvent` | `stream_thinking(chunk)` | Thinking chunk |
| `ThinkingEndEvent` | `end_thinking_stream(length)` | End thinking |
| `ContentStartEvent` | `start_content_stream()` | Start content |
| `ContentChunkEvent` | `stream_content(chunk, content_type)` | Content chunk |
| `ContentEndEvent` | `end_content_stream(length)` | End content |
| `ToolCallEvent` | `output_tool_call(tool, args)` | Tool execution start |
| `ToolResultEvent` | `output_tool_result(tool, success, result)` | Tool result |
| `ToolContentEvent` | `output_tool_content(...)` | Tool content display |
| `ErrorEvent` | `output_error(exception)` | Error display |
| `CommandEvent` | `output_command_result(result)` | Command result |

---

## 7. Migration Notes

### 7.1 Current State

- `ConsoleEventHandler` receives events and renders via Rich console
- `__main__.py` catches exceptions and prints directly
- Formatting logic embedded in handler

### 7.2 Target State

- `UIHandler` protocol defines all methods
- `InteractiveUIHandler` implements with Rich
- `BatchUIHandler` implements with stdout/stderr
- All exceptions caught by UI, displayed via `output_error()`

---

**End of Document**

