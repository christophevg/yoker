"""Message processing logic for the async Agent.

This module provides the streaming, tool call handling, and event emission
logic used by the Agent class.
"""

import inspect
import json
from collections.abc import Awaitable
from typing import Any, cast

import httpx

from yoker.events import (
  ContentChunkEvent,
  ContentEndEvent,
  ContentStartEvent,
  Event,
  EventType,
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

log = get_logger(__name__)


class ProcessingMixin:
  """Mixin providing message processing logic for Agent.

  This mixin expects the host class to expose the same attributes as Agent:
    - _client: async chat client
    - model: str
    - thinking_mode: ThinkingMode
    - tool_registry: ToolRegistry
    - context: ContextManager
    - _guardrail: PathGuardrail
    - config: Config
    - _emit: async method to emit events
    - _core: AgentCore (optional, for recursion depth)

  Note:
    Methods use ``self: Any`` so the mixin can be combined with Agent
    without mypy requiring the mixin itself to define every attribute.
  """

  async def _emit(self: Any, event: Event) -> None:
    """Emit an event to all registered handlers asynchronously.

    Supports both sync and async handlers for backward compatibility.
    Sync handlers are called directly, async handlers are awaited.

    Security Note (SEC-ASYNC-5):
      Event emission does not guard against slow sync handlers.
      Handlers should complete quickly to avoid blocking the event loop.

    Args:
      event: The event to emit.
    """
    core: Any = self._core
    for handler in core.get_event_handlers():
      try:
        call_fn = getattr(handler, "__call__", handler)  # noqa: B004
        if inspect.iscoroutinefunction(call_fn):
          await cast("Awaitable[None]", handler(event))
        else:
          handler(event)
      except Exception as e:
        log.error(
          "event_handler_error",
          handler=handler.__name__,
          event_type=event.type,
          error=str(e),
        )

  async def process(self: Any, message: str) -> str:
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

    while True:
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
        log.error("network_error", error_type=type(e).__name__, message=str(e))
        raise NetworkError(
          f"Network error: {e}",
          original_error=e,
          recoverable=True,
        ) from e

      content = ""
      thinking = ""
      tool_calls: list[Any] = []
      in_thinking = False
      in_content = False

      prompt_eval_count = 0
      eval_count = 0
      total_duration_ms = 0

      async for chunk in stream:
        if chunk.done:
          prompt_eval_count = chunk.prompt_eval_count or 0
          eval_count = chunk.eval_count or 0
          total_duration_ms = (chunk.total_duration or 0) // 1_000_000

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
              content_type="text/plain",
            )
          )

        if chunk.message.tool_calls:
          tool_calls.extend(chunk.message.tool_calls)

      if in_content:
        await self._emit(
          ContentEndEvent(
            type=EventType.CONTENT_END,
            total_length=len(content),
          )
        )
      elif in_thinking and self.thinking_mode.is_visible:
        await self._emit(
          ThinkingEndEvent(
            type=EventType.THINKING_END,
            total_length=len(thinking),
          )
        )

      if not tool_calls:
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

        return content

      seen_calls: set[str] = set()
      unique_calls: list[Any] = []
      for call in tool_calls:
        call_id = getattr(call, "id", None)
        if call_id:
          call_key = call_id
        else:
          args_str = json.dumps(call.function.arguments, sort_keys=True)
          call_key = f"{call.function.name}:{args_str}"
        if call_key not in seen_calls:
          seen_calls.add(call_key)
          unique_calls.append(call)
        else:
          log.info(
            "tool_call_duplicate_detected",
            tool=call.function.name,
            call_key=call_key,
          )

      if len(tool_calls) != len(unique_calls):
        log.info(
          "tool_calls_deduplicated",
          original_count=len(tool_calls),
          unique_count=len(unique_calls),
        )

      if unique_calls:
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
        self.context.add_tool_calls(
          formatted_calls,
          thinking=thinking if thinking else None,
        )

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

        if success and tool_result.content_metadata is not None:
          await self._emit(
            ToolContentEvent(
              type=EventType.TOOL_CONTENT,
              tool_name=tool_name,
              operation=tool_result.content_metadata.get("operation", ""),
              path=tool_result.content_metadata.get("path", ""),
              content_type=tool_result.content_metadata.get(
                "content_type", "application/x-summary"
              ),
              content=tool_result.content_metadata.get("content"),
              metadata=tool_result.content_metadata.get("metadata", {}),
            )
          )

        self.context.add_tool_result(
          tool_name=tool_name,
          tool_id=getattr(call, "id", tool_name),
          result=str(result),
          success=success,
        )
