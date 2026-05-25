"""Asynchronous Agent implementation for Yoker.

This module provides Agent, an async-first agent that chats with Ollama
and uses tools. All I/O operations are async.
"""

import inspect
import json
import os
from collections.abc import Awaitable
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import httpx
from ollama import AsyncClient

from yoker.base import AgentCore, EventCallback
from yoker.events import (
  ContentChunkEvent,
  ContentEndEvent,
  ContentStartEvent,
  Event,
  EventType,
  SessionEndEvent,
  SessionStartEvent,
  ThinkingChunkEvent,
  ThinkingEndEvent,
  ThinkingStartEvent,
  ToolCallEvent,
  ToolContentEvent,
  ToolResultEvent,
  TurnEndEvent,
  TurnStartEvent,
)
from yoker.exceptions import NetworkError
from yoker.logging import get_logger, log_timing
from yoker.thinking import ThinkingMode
from yoker.tools import ToolRegistry
from yoker.tools.agent import AgentTool

if TYPE_CHECKING:
  from yoker.agents import AgentDefinition
  from yoker.commands import CommandRegistry
  from yoker.config import Config
  from yoker.context import ContextManager
  from yoker.tools.path_guardrail import PathGuardrail

log = get_logger(__name__)


class Agent:
  """Asynchronous agent that chats with Ollama and uses tools.

  This implementation uses composition with AgentCore for shared state.
  All I/O operations are async.

  Attributes:
    client: AsyncClient for Ollama API communication.
    model: Model to use for chat.
    config: Configuration object.
    context: ContextManager for conversation history.
    thinking_mode: Current thinking mode (on/off/silent).
    agent_definition: Loaded agent definition (if provided).
    _recursion_depth: Current recursion depth (internal, for subagent tracking).
    _max_recursion_depth: Maximum allowed recursion depth (internal).
  """

  def __init__(
    self,
    model: str | None = None,
    config: "Config | None" = None,
    config_path: Path | str | None = None,
    thinking_mode: ThinkingMode = ThinkingMode.ON,
    command_registry: "CommandRegistry | None" = None,
    agent_definition: "AgentDefinition | None" = None,
    agent_path: Path | str | None = None,
    context_manager: "ContextManager | None" = None,
    _recursion_depth: int = 0,
  ) -> None:
    """Initialize the async agent.

    Args:
      model: Model to use (overrides config if provided).
      config: Configuration object (takes precedence over config_path).
      config_path: Path to configuration file (loaded if config not provided).
      thinking_mode: Thinking mode (on/off/silent, default: ON).
      command_registry: Optional command registry for slash-commands.
      agent_definition: Pre-loaded AgentDefinition to use for system prompt.
      agent_path: Path to agent definition file (Markdown with frontmatter).
      context_manager: Optional ContextManager for conversation persistence.
      _recursion_depth: Internal parameter for subagent recursion tracking.
    """
    # Load configuration once (following same precedence as AgentCore)
    from yoker.config import Config

    if config is not None:
      loaded_config = config
    elif config_path is not None:
      from yoker.config import load_config

      loaded_config = load_config(config_path)
    else:
      loaded_config = Config()

    # Initialize async-specific client
    api_key = os.environ.get("OLLAMA_API_KEY")
    if api_key:
      self._client = AsyncClient(
        host="https://ollama.com", headers={"Authorization": f"Bearer {api_key}"}
      )
      log.info("async_ollama_client_initialized", host="ollama.com", auth="api_key")
    else:
      base_url = loaded_config.backend.ollama.base_url
      self._client = AsyncClient(host=base_url)
      log.info("async_ollama_client_initialized", host=base_url, auth="none")

    # Delegate initialization to AgentCore for shared state
    # Pass AsyncClient for async web tools (WebSearch/WebFetch)
    self._core = AgentCore(
      model=model,
      config=loaded_config,
      thinking_mode=thinking_mode,
      command_registry=command_registry,
      agent_definition=agent_definition,
      agent_path=agent_path,
      context_manager=context_manager,
      client=self._client,  # Pass AsyncClient for async web tools
      _recursion_depth=_recursion_depth,
    )

    # Register AgentTool (needs reference to parent agent for subagent spawning)
    # This must happen after AgentCore is initialized but before agent is used
    if self._core.agent_definition is not None:
      allowed_tools = {t.lower() for t in self._core.agent_definition.tools}
      if "agent" in allowed_tools:
        self._core.tool_registry.register(
          AgentTool(guardrail=self._core.guardrail, parent_agent=self)
        )
    else:
      self._core.tool_registry.register(
        AgentTool(guardrail=self._core.guardrail, parent_agent=self)
      )

    log.info(
      "async_agent_initialized",
      model=self.model,
      thinking_mode=self.thinking_mode.value,
      has_agent_definition=self.agent_definition is not None,
      available_tools=self.tool_registry.names,
    )

  # Property delegations to AgentCore
  @property
  def config(self) -> "Config":
    """Configuration object."""
    return self._core.config

  @property
  def model(self) -> str:
    """Model name to use for chat."""
    return self._core.model

  @property
  def thinking_mode(self) -> ThinkingMode:
    """Current thinking mode state."""
    return self._core.thinking_mode

  @thinking_mode.setter
  def thinking_mode(self, value: ThinkingMode) -> None:
    """Set thinking mode state."""
    self._core.thinking_mode = value

  @property
  def agent_definition(self) -> "AgentDefinition | None":
    """Loaded agent definition, if any."""
    return self._core.agent_definition

  @property
  def tool_registry(self) -> ToolRegistry:
    """Registry of available tools."""
    return self._core.tool_registry

  @property
  def context(self) -> "ContextManager":
    """Context manager for conversation history."""
    return self._core.context

  @property
  def command_registry(self) -> "CommandRegistry | None":
    """Command registry for slash-commands."""
    return self._core.command_registry

  @property
  def _recursion_depth(self) -> int:
    """Current recursion depth (internal)."""
    return self._core.recursion_depth

  @property
  def _max_recursion_depth(self) -> int:
    """Maximum allowed recursion depth."""
    return self._core.max_recursion_depth

  @property
  def _event_handlers(self) -> list[EventCallback]:
    """Event handlers storage (internal, for backward compatibility)."""
    return self._core._event_handlers

  @property
  def client(self) -> AsyncClient:
    """AsyncClient for Ollama API communication."""
    return self._client

  # Access to guardrail for tool validation
  @property
  def _guardrail(self) -> "PathGuardrail":
    """Path guardrail for filesystem tool validation."""
    return self._core.guardrail

  # Event handler methods delegate to core
  def add_event_handler(self, handler: EventCallback) -> None:
    """Register an event handler.

    Event handlers receive all events emitted during agent processing.
    Handlers can access potentially sensitive data (tool results, file contents).
    Only register handlers from trusted sources.

    Supports both sync and async handlers:
      - Sync handlers: def handler(event: Event) -> None
      - Async handlers: async def handler(event: Event) -> None

    Args:
      handler: Callable that receives Event objects.

    Example:
      def my_handler(event: Event):
          if isinstance(event, ContentChunkEvent):
              print(event.text, end='', flush=True)

      agent.add_event_handler(my_handler)

    Security Note (SEC-ASYNC-1):
      Handler registration is logged for audit purposes.
    """
    handler_name = getattr(handler, "__name__", str(handler))
    # Get the __call__ method if handler is an instance, otherwise use handler
    # This is needed because inspect.iscoroutinefunction(instance) returns False
    # for instances with async __call__, but inspect.iscoroutinefunction(instance.__call__)
    # returns True.
    call_fn = getattr(handler, "__call__", handler)  # noqa: B004
    log.info(
      "handler_registered",
      handler=handler_name,
      is_async=inspect.iscoroutinefunction(call_fn),
    )
    self._core.add_event_handler(handler)

  def remove_event_handler(self, handler: EventCallback) -> None:
    """Remove a registered event handler.

    Args:
      handler: The handler to remove.

    Raises:
      ValueError: If the handler is not registered.
    """
    self._core.remove_event_handler(handler)

  async def _emit(self, event: Event) -> None:
    """Emit an event to all registered handlers asynchronously.

    Supports both sync and async handlers for backward compatibility.
    Sync handlers are called directly, async handlers are awaited.

    Security Note (SEC-ASYNC-5):
      Event emission does not guard against slow sync handlers.
      Handlers should complete quickly to avoid blocking the event loop.

    Args:
      event: The event to emit.
    """
    for handler in self._core.get_event_handlers():
      try:
        # Check if handler is async: either a coroutine function or an instance
        # with an async __call__ method.
        # inspect.iscoroutinefunction(instance) returns False for instances with
        # async __call__, but inspect.iscoroutinefunction(instance.__call__) returns True.
        call_fn = getattr(handler, "__call__", handler)  # noqa: B004
        if inspect.iscoroutinefunction(call_fn):
          # Async handler - await it
          # mypy doesn't narrow the type, so we cast to help it
          await cast("Awaitable[None]", handler(event))
        else:
          # Sync handler - call directly
          # Note: This runs in the async context and could block
          handler(event)
      except Exception as e:
        log.error(
          "event_handler_error",
          handler=handler.__name__,
          event_type=event.type,
          error=str(e),
        )

  async def process(self, message: str) -> str:
    """Process a single message and return the response asynchronously.

    Handles tool calls internally until a final response is ready.
    Uses streaming when thinking is enabled.

    Emits events during processing:
    - TURN_START
    - THINKING_START/CHUNK/END (if enabled)
    - CONTENT_START/CHUNK/END
    - TOOL_CALL/RESULT (if tools called)
    - TURN_END

    Args:
      message: User message to process.

    Returns:
      Assistant's response text.

    Raises:
      NetworkError: If communication with Ollama fails.
    """
    log.info("async_turn_started", message_preview=message[:50])
    await self._emit(TurnStartEvent(type=EventType.TURN_START, message=message))
    self.context.start_turn(message)

    # Process with model, handling tool calls in a loop
    while True:
      # Use streaming for better UX
      try:
        stream = await self._client.chat(
          model=self.model,
          messages=self.context.get_context(),
          tools=self.tool_registry.get_schemas(),
          think=self.thinking_mode.is_enabled,
          stream=True,
        )
      except (
        httpx.RemoteProtocolError,
        httpx.ConnectError,
        httpx.ReadError,
        httpx.WriteError,
        httpx.ConnectTimeout,
        httpx.ReadTimeout,
      ) as e:
        # Wrap network errors with recovery information
        log.error("network_error", error_type=type(e).__name__, message=str(e))
        raise NetworkError(
          f"Network error: {e}",
          original_error=e,
          recoverable=True,
        ) from e

      # Accumulate partial fields
      content = ""
      thinking = ""
      tool_calls: list[Any] = []
      in_thinking = False
      in_content = False

      # Track stats from last chunk
      prompt_eval_count = 0
      eval_count = 0
      total_duration_ms = 0

      async for chunk in stream:
        # Capture stats from done chunk
        if chunk.done:
          prompt_eval_count = chunk.prompt_eval_count or 0
          eval_count = chunk.eval_count or 0
          total_duration_ms = (chunk.total_duration or 0) // 1_000_000  # ns to ms

        # Handle thinking output
        if chunk.message.thinking:
          if not in_thinking and self.thinking_mode.is_visible:
            in_thinking = True
            await self._emit(ThinkingStartEvent(type=EventType.THINKING_START))
          thinking += chunk.message.thinking
          if self.thinking_mode.is_visible:
            await self._emit(
              ThinkingChunkEvent(
                type=EventType.THINKING_CHUNK,
                text=chunk.message.thinking,
              )
            )

        # Handle content output
        if chunk.message.content:
          if in_thinking and self.thinking_mode.is_visible:
            in_thinking = False
            await self._emit(
              ThinkingEndEvent(
                type=EventType.THINKING_END,
                total_length=len(thinking),
              )
            )
          if not in_content:
            in_content = True
            await self._emit(ContentStartEvent(type=EventType.CONTENT_START))
          content += chunk.message.content
          await self._emit(
            ContentChunkEvent(
              type=EventType.CONTENT_CHUNK,
              text=chunk.message.content,
            )
          )

        # Handle tool calls
        if chunk.message.tool_calls:
          tool_calls.extend(chunk.message.tool_calls)

      # End content if we were streaming
      if in_content:
        await self._emit(
          ContentEndEvent(
            type=EventType.CONTENT_END,
            total_length=len(content),
          )
        )
      elif in_thinking and self.thinking_mode.is_visible:
        # No content, but thinking ended
        await self._emit(
          ThinkingEndEvent(
            type=EventType.THINKING_END,
            total_length=len(thinking),
          )
        )

      # If no tool calls, we're done with this turn
      if not tool_calls:
        # Include thinking in context if present
        self.context.end_turn(content, thinking=thinking if thinking else None)
        await self._emit(
          TurnEndEvent(
            type=EventType.TURN_END,
            response=content,
            tool_calls_count=len(tool_calls),
            prompt_eval_count=prompt_eval_count,
            eval_count=eval_count,
            total_duration_ms=total_duration_ms,
          )
        )

        log.info(
          "async_turn_completed",
          response_length=len(content),
          tool_calls_count=len(tool_calls),
        )

        # Persist context if configured
        if self.config.context.persist_after_turn:
          self.context.save()

        return content

      # Deduplicate tool calls (LLM may send duplicates in streaming)
      # Use tool call ID if available, otherwise use name+args
      seen_calls: set[str] = set()
      unique_calls: list[Any] = []
      for call in tool_calls:
        # Prefer tool call ID for deduplication
        call_id = getattr(call, "id", None)
        if call_id:
          call_key = call_id
        else:
          # Fallback to tool name + arguments
          args_str = json.dumps(call.function.arguments, sort_keys=True)
          call_key = f"{call.function.name}:{args_str}"
        if call_key not in seen_calls:
          seen_calls.add(call_key)
          unique_calls.append(call)
        else:
          # Log when a duplicate is detected
          log.info(
            "tool_call_duplicate_detected",
            tool=call.function.name,
            call_key=call_key,
          )

      # Log summary if duplicates were found
      if len(tool_calls) != len(unique_calls):
        log.info(
          "tool_calls_deduplicated",
          original_count=len(tool_calls),
          unique_count=len(unique_calls),
        )

      # Add assistant message with tool_calls to context BEFORE executing
      # This is required for the LLM to understand what tools were called
      if unique_calls:
        # Format tool_calls for Ollama API
        formatted_calls = [
          {
            "id": getattr(call, "id", f"call_{i}"),
            "function": {
              "name": call.function.name,
              "arguments": call.function.arguments,
            },
          }
          for i, call in enumerate(unique_calls)
        ]
        # Include thinking content if present
        self.context.add_tool_calls(
          formatted_calls,
          thinking=thinking if thinking else None,
        )

      # Process tool calls
      for call in unique_calls:
        tool_name = call.function.name
        tool_args = call.function.arguments

        await self._emit(
          ToolCallEvent(
            type=EventType.TOOL_CALL,
            tool_name=tool_name,
            arguments=tool_args,
          )
        )

        log.debug("async_tool_call", tool=tool_name, args=tool_args)

        tool = self.tool_registry.get(tool_name)
        if tool is None:
          result = f"Error: Unknown tool '{tool_name}'"
          success = False
          log.warning("tool_not_found", tool=tool_name)
        else:
          # Validate tool parameters through guardrail (SEC-ASYNC-5)
          # Guardrails remain synchronous to prevent timing attacks
          validation = self._guardrail.validate(tool_name, tool_args)
          if not validation.valid:
            log.info("guardrail_blocked", tool=tool_name, reason=validation.reason)
            result = f"Error: {validation.reason}"
            success = False
          else:
            if self.config.logging.include_permission_checks:
              log.info(
                "guardrail_allowed",
                tool=tool_name,
                path=tool_args.get("path"),
              )
            try:
              with log_timing("tool_execution", tool=tool_name):
                tool_result = await tool.execute(**tool_args)
              success = tool_result.success
              if success:
                result = str(tool_result.result)
              else:
                result = f"Error: {tool_result.error}"
            except Exception as e:
              result = f"Error executing tool: {e}"
              success = False
              log.error("tool_error", tool=tool_name, error=str(e))

        log.debug("async_tool_result", tool=tool_name, success=success)

        await self._emit(
          ToolResultEvent(
            type=EventType.TOOL_RESULT,
            tool_name=tool_name,
            result=str(result),
            success=success,
          )
        )

        # Emit ToolContentEvent if content_metadata is present
        if success and tool_result.content_metadata is not None:
          await self._emit(
            ToolContentEvent(
              type=EventType.TOOL_CONTENT,
              tool_name=tool_name,
              operation=tool_result.content_metadata.get("operation", ""),
              path=tool_result.content_metadata.get("path", ""),
              content_type=tool_result.content_metadata.get("content_type", "summary"),
              content=tool_result.content_metadata.get("content"),
              metadata=tool_result.content_metadata.get("metadata", {}),
            )
          )

        # Add tool result to context
        self.context.add_tool_result(
          tool_name=tool_name,
          tool_id=getattr(call, "id", tool_name),
          result=str(result),
          success=success,
        )

  async def begin_session(self) -> None:
    """Begin an agent session asynchronously.

    Emits SESSION_START event with session metadata.
    Saves context to persist session state.
    Call this before processing messages.
    """
    # Save context to ensure session_start record is written
    self.context.save()

    log.info(
      "async_session_started",
      model=self.model,
      session_id=self.context.get_session_id(),
      thinking_mode=self.thinking_mode.value,
    )

    await self._emit(
      SessionStartEvent(
        type=EventType.SESSION_START,
        model=self.model,
        thinking_enabled=self.thinking_mode.is_enabled,
      )
    )

  async def end_session(self, reason: str = "quit") -> None:
    """End an agent session asynchronously.

    Emits SESSION_END event.
    Closes context to ensure all data is persisted.
    Call this when done processing messages.

    Args:
      reason: Reason for ending the session (e.g., "quit", "error", "interrupt").
    """
    # Close context to write session_end record
    # Note: context.close() is synchronous but safe to call in async context
    # (it writes to a file, which is a non-blocking operation for small writes)
    self.context.close()

    log.info("async_session_ended", reason=reason)

    await self._emit(
      SessionEndEvent(
        type=EventType.SESSION_END,
        reason=reason,
      )
    )


__all__ = ["Agent"]
