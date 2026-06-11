# UI Separation - UI Handler Design

**Document Status:** Draft
**Created:** 2026-06-11
**Last Updated:** 2026-06-11

## Overview

This document defines the UIHandler protocol and implementations for the new architecture.

---

## 1. UIHandler Protocol

### 1.1 Design Principles

1. **All methods receive raw data** - No formatting in events
2. **UI handles formatting** - Each implementation formats appropriately
3. **Streaming by default** - Agent streams, UI can buffer if needed
4. **Minimal base class** - No forced formatting in base class

### 1.2 Protocol Definition

```python
# yoker/ui/handler.py

from typing import Protocol


class UIHandler(Protocol):
    """Abstract interface for all UI operations.
    
    All methods receive raw, unformatted data.
    Implementations are responsible for formatting and output.
    
    Input methods return None for no input (end of session).
    Output methods should handle ANSI codes appropriately for their context.
    
    Streaming:
        Agent always streams by default.
        UI implementations can buffer if needed.
    """
    
    # === Lifecycle ===
    
    async def start(self, model: str, version: str, config: dict) -> None:
        """Start UI session. Called once at beginning.
        
        Args:
            model: Model name being used.
            version: Yoker version.
            config: Configuration summary (thinking_enabled, etc.).
        """
        ...
    
    async def shutdown(self, reason: str) -> None:
        """End UI session. Called once at end.
        
        Args:
            reason: Reason for ending ("quit", "error", "interrupt").
        """
        ...
    
    # === Input ===
    
    async def get_input(self, prompt: str = "> ") -> str | None:
        """Get user input.
        
        Args:
            prompt: Prompt string to display.
            
        Returns:
            User input string, or None if end of input (EOF).
        """
        ...
    
    # === Content Output (stdout in batch) ===
    
    def output_content(self, content: str, content_type: str = "text/plain") -> None:
        """Output content text.
        
        Args:
            content: Content text (may contain ANSI from LLM).
            content_type: MIME type of content.
        """
        ...
    
    def output_command_result(self, result: str) -> None:
        """Output command result.
        
        Args:
            result: Command output text.
        """
        ...
    
    # === Diagnostic Output (stderr in batch) ===
    
    def output_thinking(self, text: str) -> None:
        """Output thinking/trace text.
        
        Args:
            text: Thinking text (may contain ANSI from LLM).
        """
        ...
    
    def output_tool_call(self, tool_name: str, args: dict) -> None:
        """Output tool call information.
        
        Args:
            tool_name: Name of tool being called.
            args: Tool arguments (may be truncated for display).
        """
        ...
    
    def output_tool_result(self, tool_name: str, success: bool, result: str) -> None:
        """Output tool result status.
        
        Args:
            tool_name: Name of tool.
            success: Whether tool succeeded.
            result: Result text or error message.
        """
        ...
    
    def output_tool_content(
        self,
        tool_name: str,
        operation: str,
        path: str,
        content: str | None,
        content_type: str,
        metadata: dict
    ) -> None:
        """Output tool content (file contents, diff, etc.).
        
        Args:
            tool_name: Name of tool.
            operation: Operation type (read, write, update, etc.).
            path: File path.
            content: Content text (may be None for summary).
            content_type: MIME type of content.
            metadata: Additional metadata (lines, bytes, etc.).
        """
        ...
    
    def output_stats(
        self,
        duration_ms: int,
        prompt_tokens: int,
        eval_tokens: int
    ) -> None:
        """Output turn statistics.
        
        Args:
            duration_ms: Duration in milliseconds.
            prompt_tokens: Number of prompt tokens.
            eval_tokens: Number of evaluation tokens.
        """
        ...
    
    def output_error(self, error: Exception) -> None:
        """Output error message.
        
        Args:
            error: Exception that occurred.
        """
        ...
    
    # === Streaming ===
    
    def start_content_stream(self) -> None:
        """Start streaming content."""
        ...
    
    def stream_content(self, chunk: str, content_type: str = "text/plain") -> None:
        """Stream content chunk.
        
        Args:
            chunk: Content chunk (may contain ANSI from LLM).
            content_type: MIME type of content.
        """
        ...
    
    def end_content_stream(self, total_length: int) -> None:
        """End streaming content.
        
        Args:
            total_length: Total content length.
        """
        ...
    
    def start_thinking_stream(self) -> None:
        """Start streaming thinking."""
        ...
    
    def stream_thinking(self, chunk: str) -> None:
        """Stream thinking chunk.
        
        Args:
            chunk: Thinking chunk (may contain ANSI from LLM).
        """
        ...
    
    def end_thinking_stream(self, total_length: int) -> None:
        """End streaming thinking.
        
        Args:
            total_length: Total thinking length.
        """
        ...
```

---

## 2. Event Bridge

The event bridge connects the EventHandler protocol to the UIHandler protocol.

```python
# yoker/ui/bridge.py

from yoker.events import Event, EventType
from yoker.ui.handler import UIHandler


class UIBridge:
    """Bridge between EventHandler protocol and UIHandler.
    
    Receives events from Agent and calls appropriate UIHandler methods.
    """
    
    def __init__(self, ui_handler: UIHandler):
        self.ui = ui_handler
    
    async def __call__(self, event: Event) -> None:
        """Handle event by dispatching to UI handler.
        
        Note: SESSION_START and SESSION_END events are removed from Agent.
        UI calls start() and shutdown() directly, not via events.
        """
        match event.type:
            case EventType.TURN_START:
                pass  # Internal state
            case EventType.TURN_END:
                self._handle_turn_end(event)
            case EventType.THINKING_START:
                self.ui.start_thinking_stream()
            case EventType.THINKING_CHUNK:
                self.ui.stream_thinking(event.text)
            case EventType.THINKING_END:
                self.ui.end_thinking_stream(event.total_length)
            case EventType.CONTENT_START:
                self.ui.start_content_stream()
            case EventType.CONTENT_CHUNK:
                self.ui.stream_content(event.text, getattr(event, 'content_type', 'text/plain'))
            case EventType.CONTENT_END:
                self.ui.end_content_stream(event.total_length)
            case EventType.TOOL_CALL:
                self.ui.output_tool_call(event.tool_name, event.arguments)
            case EventType.TOOL_RESULT:
                self.ui.output_tool_result(event.tool_name, event.success, event.result)
            case EventType.TOOL_CONTENT:
                self.ui.output_tool_content(
                    event.tool_name,
                    event.operation,
                    event.path,
                    event.content,
                    event.content_type,
                    event.metadata
                )
            case EventType.ERROR:
                # Convert to exception for UI
                self.ui.output_error(Exception(f"{event.error_type}: {event.message}"))
    
    def _handle_turn_end(self, event) -> None:
        self.ui.output_stats(
            duration_ms=event.total_duration_ms,
            prompt_tokens=event.prompt_eval_count,
            eval_tokens=event.eval_count
        )
```

---

## 3. Base UI Handler

### 3.1 Design

The base class is minimal - it only manages state, not formatting. Each implementation handles formatting itself.

```python
# yoker/ui/base.py

from abc import ABC, abstractmethod


class BaseUIHandler(ABC):
    """Base implementation with state management.
    
    Provides:
    - State tracking (turn count, streaming state)
    - Default implementations for convenience
    
    Does NOT provide:
    - Formatting (implementation-specific)
    - Buffering (implementation choice)
    
    Subclasses implement:
    - Platform-specific output methods
    - Input handling
    - Error formatting
    """
    
    def __init__(self) -> None:
        self._turn_count = 0
        self._streaming_content = False
        self._streaming_thinking = False
    
    # === State Management ===
    
    def _start_turn(self) -> None:
        """Start a new turn."""
        self._turn_count += 1
        self._streaming_content = False
        self._streaming_thinking = False
    
    def _end_turn(self) -> None:
        """End current turn."""
        self._streaming_content = False
        self._streaming_thinking = False
    
    # === Default Implementations ===
    
    def output_content(self, content: str, content_type: str = "text/plain") -> None:
        """Default: output via streaming."""
        self.start_content_stream()
        self.stream_content(content, content_type)
        self.end_content_stream(len(content))
    
    def output_thinking(self, text: str) -> None:
        """Default: output via streaming."""
        self.start_thinking_stream()
        self.stream_thinking(text)
        self.end_thinking_stream(len(text))
    
    # === Abstract Methods ===
    
    @abstractmethod
    async def start(self, model: str, version: str, config: dict) -> None: ...
    
    @abstractmethod
    async def shutdown(self, reason: str) -> None: ...
    
    @abstractmethod
    async def get_input(self, prompt: str = "> ") -> str | None: ...
    
    @abstractmethod
    def start_content_stream(self) -> None: ...
    
    @abstractmethod
    def stream_content(self, chunk: str, content_type: str = "text/plain") -> None: ...
    
    @abstractmethod
    def end_content_stream(self, total_length: int) -> None: ...
    
    @abstractmethod
    def start_thinking_stream(self) -> None: ...
    
    @abstractmethod
    def stream_thinking(self, chunk: str) -> None: ...
    
    @abstractmethod
    def end_thinking_stream(self, total_length: int) -> None: ...
    
    # ... other abstract methods
```

---

## 4. Interactive UI Handler

### 4.1 Design

Uses prompt_toolkit for input and Rich for output. Supports streaming via Live display.

```python
# yoker/ui/interactive.py

from pathlib import Path
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings, KeyPressEvent
from prompt_toolkit.shortcuts import PromptSession
from rich.console import Console
from rich.style import Style

from yoker.ui.base import BaseUIHandler
from yoker.ui.spinner import LiveDisplay


class InteractiveUIHandler(BaseUIHandler):
    """Interactive UI with prompt_toolkit input and Rich output.
    
    Features:
    - Multiline input (Esc+Enter for newline)
    - Command history
    - Rich console formatting
    - Live streaming display
    """
    
    def __init__(
        self,
        history_file: Path | None = None,
        show_thinking: bool = True,
        show_tool_calls: bool = True,
    ) -> None:
        super().__init__()
        self.console = Console()
        self.history_file = history_file or Path.home() / ".yoker_history"
        self.show_thinking = show_thinking
        self.show_tool_calls = show_tool_calls
        self._live: LiveDisplay | None = None
        
        # Create prompt session
        self._session = self._create_session()
    
    def _create_session(self) -> PromptSession[str]:
        """Create prompt session with multiline support."""
        kb = KeyBindings()
        
        @kb.add("enter")
        def _handle_enter(event: KeyPressEvent) -> None:
            event.current_buffer.validate_and_handle()
        
        @kb.add("escape", "enter")
        def _handle_meta_enter(event: KeyPressEvent) -> None:
            event.current_buffer.insert_text("\n")
        
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        
        return PromptSession(
            history=FileHistory(str(self.history_file)),
            multiline=True,
            mouse_support=False,
            key_bindings=kb,
        )
    
    # === Lifecycle ===
    
    async def start(self, model: str, version: str, config: dict) -> None:
        self.console.print(f"Yoker v{version} - Using model: {model}")
        thinking_status = "enabled" if config.get("thinking_enabled", True) else "disabled"
        self.console.print(f"Thinking mode: {thinking_status} (use /think on|off to toggle)")
        self.console.print("Type /help for available commands.")
        self.console.print("Press Ctrl+D (or Ctrl+Z on Windows) to quit.\n")
    
    async def shutdown(self, reason: str) -> None:
        self.console.print("\nGoodbye!")
    
    # === Input ===
    
    async def get_input(self, prompt: str = "> ") -> str | None:
        try:
            result: str = await self._session.prompt_async(prompt)
            return result
        except EOFError:
            return None
        except KeyboardInterrupt:
            self.console.print()  # Newline after ^C
            return None
    
    # === Content Output ===
    
    def start_content_stream(self) -> None:
        self._live = LiveDisplay(console=self.console)
        self._live.__enter__()
        self._live.start_spinner()
    
    def stream_content(self, chunk: str, content_type: str = "text/plain") -> None:
        if self._live:
            self._live.append_response(chunk)
    
    def end_content_stream(self, total_length: int) -> None:
        if self._live:
            self._live.stop_spinner()
            self._live.__exit__(None, None, None)
            self._live = None
    
    # === Thinking Output ===
    
    def start_thinking_stream(self) -> None:
        if self.show_thinking:
            # Similar to content stream
            pass
    
    def stream_thinking(self, chunk: str) -> None:
        if self.show_thinking:
            if self._live:
                self._live.append_thinking(chunk)
            else:
                self.console.print(chunk, style=Style(color="bright_black", dim=True))
    
    def end_thinking_stream(self, total_length: int) -> None:
        if self.show_thinking:
            # End thinking stream
            pass
    
    # === Tool Output ===
    
    def output_tool_call(self, tool_name: str, args: dict) -> None:
        if self.show_tool_calls:
            args_str = " ".join(f"{k}={v}" for k, v in list(args.items())[:3])
            self.console.print(f"\n⏺ {tool_name}: {args_str}")
    
    def output_tool_result(self, tool_name: str, success: bool, result: str) -> None:
        if self.show_tool_calls:
            if success:
                self.console.print("  ✓ Success")
            else:
                error_msg = result[:50] if result else "Failed"
                self.console.print(f"  ✗ {error_msg}")
    
    # === Error Output ===
    
    def output_error(self, error: Exception) -> None:
        # Format based on error type
        if isinstance(error, NetworkError):
            if error.recoverable:
                msg = f"Network Error: {error}\nYour message was preserved. Try again or type a new message."
            else:
                msg = f"Fatal Network Error: {error}\nUnable to recover. Please restart the session."
        else:
            msg = f"Error: {error}"
        
        self.console.print(msg, style=Style(color="red", bold=True))
```

---

## 5. Batch UI Handler

### 5.1 Design

Uses stdin/stdout/stderr. No formatting, preserves ANSI. No streaming buffering needed (can output directly).

```python
# yoker/ui/batch.py

import sys
from yoker.ui.base import BaseUIHandler


class BatchUIHandler(BaseUIHandler):
    """Batch UI for non-interactive execution.
    
    Output channels:
    - Content → stdout
    - Thinking, errors, stats → stderr
    
    Input:
    - From file (predefined messages)
    - From stdin (one message per line)
    - From CLI argument (--prompt)
    
    No formatting - preserves ANSI from LLM.
    """
    
    def __init__(
        self,
        show_thinking: bool = False,
        show_tool_calls: bool = False,
        show_stats: bool = False,
    ) -> None:
        super().__init__()
        self.show_thinking = show_thinking
        self.show_tool_calls = show_tool_calls
        self.show_stats = show_stats
        
        # Predefined input source
        self._input_source: list[str] | None = None
        self._input_index = 0
    
    def set_input_messages(self, messages: list[str]) -> None:
        """Set predefined input messages."""
        self._input_source = messages
        self._input_index = 0
    
    # === Lifecycle ===
    
    async def start(self, model: str, version: str, config: dict) -> None:
        # Minimal output for batch mode
        if self.show_thinking:
            print(f"# Model: {model}", file=sys.stderr)
    
    async def shutdown(self, reason: str) -> None:
        # No output for batch mode
        pass
    
    # === Input ===
    
    async def get_input(self, prompt: str = "> ") -> str | None:
        if self._input_source is not None:
            # Predefined messages
            if self._input_index >= len(self._input_source):
                return None
            message = self._input_source[self._input_index]
            self._input_index += 1
            return message
        else:
            # Read from stdin
            try:
                return input()
            except EOFError:
                return None
    
    # === Content Output (stdout) ===
    
    def start_content_stream(self) -> None:
        pass  # No setup needed
    
    def stream_content(self, chunk: str, content_type: str = "text/plain") -> None:
        print(chunk, file=sys.stdout, end="", flush=True)
    
    def end_content_stream(self, total_length: int) -> None:
        print(file=sys.stdout)  # Final newline
    
    # === Thinking Output (stderr) ===
    
    def start_thinking_stream(self) -> None:
        pass
    
    def stream_thinking(self, chunk: str) -> None:
        if self.show_thinking:
            print(chunk, file=sys.stderr, end="", flush=True)
    
    def end_thinking_stream(self, total_length: int) -> None:
        if self.show_thinking:
            print(file=sys.stderr)
    
    # === Tool Output (stderr) ===
    
    def output_tool_call(self, tool_name: str, args: dict) -> None:
        if self.show_tool_calls:
            args_str = " ".join(f"{k}={v}" for k, v in list(args.items())[:3])
            print(f"# Tool: {tool_name}({args_str})", file=sys.stderr)
    
    def output_tool_result(self, tool_name: str, success: bool, result: str) -> None:
        if self.show_tool_calls:
            status = "✓" if success else "✗"
            print(f"# {status} {tool_name}: {result[:50]}", file=sys.stderr)
    
    # === Stats Output (stderr) ===
    
    def output_stats(self, duration_ms: int, prompt_tokens: int, eval_tokens: int) -> None:
        if self.show_stats:
            total = prompt_tokens + eval_tokens
            duration_s = duration_ms / 1000.0
            print(f"# Stats: {duration_s:.1f}s, {total} tokens", file=sys.stderr)
    
    # === Error Output (stderr) ===
    
    def output_error(self, error: Exception) -> None:
        error_type = type(error).__name__
        print(f"Error [{error_type}]: {error}", file=sys.stderr)
```

---

## 6. Usage Example

### 6.1 Interactive Mode

```python
# In __main__.py

from yoker.agent import Agent
from yoker.ui.interactive import InteractiveUIHandler
from yoker.ui.bridge import UIBridge

async def main():
    # Create agent
    agent = Agent(config=config)
    
    # Create UI handler
    ui = InteractiveUIHandler(
        show_thinking=True,
        show_tool_calls=True,
    )
    
    # Bridge events to UI
    bridge = UIBridge(ui)
    agent.add_event_handler(bridge)
    
    # Start UI (not via event)
    await ui.start(agent.model, VERSION, {"thinking_enabled": True})
    
    try:
        while True:
            user_input = await ui.get_input()
            if user_input is None:
                break
            
            if user_input.startswith("/"):
                # Handle command
                result = handle_command(user_input, agent, ui)
                ui.output_command_result(result)
            else:
                # Process with agent
                await agent.process(user_input)
    except NetworkError as e:
        ui.output_error(e)
    finally:
        await ui.shutdown("quit")
```

### 6.2 Batch Mode

```python
# In __main__.py --batch mode

from yoker.agent import Agent
from yoker.ui.batch import BatchUIHandler
from yoker.ui.bridge import UIBridge

async def main():
    # Create agent
    agent = Agent(config=config)
    
    # Create UI handler
    ui = BatchUIHandler(
        show_thinking=False,
        show_tool_calls=False,
        show_stats=False,
    )
    
    # Bridge events to UI
    bridge = UIBridge(ui)
    agent.add_event_handler(bridge)
    
    # Start UI (not via event)
    await ui.start(agent.model, VERSION, {})
    
    try:
        while True:
            user_input = await ui.get_input()
            if user_input is None:
                break
            
            await agent.process(user_input)
    except YokerError as e:
        ui.output_error(e)
        sys.exit(1)
    finally:
        await ui.shutdown("complete")
```

---

**End of Document**

