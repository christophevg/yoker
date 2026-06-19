"""Message processing logic for the async Agent."""

import inspect
import json
from collections.abc import Awaitable
from typing import Any, cast

import httpx
from structlog import get_logger

from yoker.events import (
  ContentChunkEvent,
  ContentEndEvent,
  ContentStartEvent,
  Event,
  EventCallback,
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
from yoker.logging import log_timing
from yoker.tools.base import ValidationResult
from yoker.tools.guardrails import Guardrail
from yoker.tools.schema import ToolSpec

log = get_logger(__name__)


def _is_async_handler(handler: EventCallback) -> bool:
  """Return True if calling the handler must be awaited."""
  if inspect.iscoroutinefunction(handler):
    return True
  return callable(handler) and inspect.iscoroutinefunction(type(handler).__call__)


async def emit(event: Event, handlers: list[EventCallback]) -> None:
  """Emit an event to all registered handlers."""
  for handler in handlers:
    try:
      if _is_async_handler(handler):
        await cast("Awaitable[None]", handler(event))
      else:
        handler(event)
    except Exception as e:
      log.error(
        "event_handler_error",
        handler=getattr(handler, "__name__", str(handler)),
        event_type=event.type,
        error=str(e),
      )


async def process_message(agent: Any, message: str) -> str:
  """Process a single message and return the response."""
  log.info("async_turn_started", message_preview=message[:50])
  await emit(TurnStartEvent(type=EventType.TURN_START, message=message), agent._event_handlers)
  agent.context.start_turn(message)

  while True:
    stream = await _chat_stream(agent)
    content, thinking, tool_calls, stats = await _consume_stream(agent, stream)

    if not tool_calls:
      agent.context.end_turn(content, thinking=thinking or None)
      await emit(_turn_end_event(content, tool_calls, stats), agent._event_handlers)
      log.info("async_turn_completed", response_length=len(content), tool_calls_count=0)
      return content

    await _execute_tool_calls(agent, tool_calls, thinking)


async def _chat_stream(agent: Any) -> Any:
  """Start a streaming chat request."""
  try:
    return await agent._client.chat(
      model=agent.model,
      messages=agent.context.get_context(),
      tools=agent.tool_registry.get_schemas(),
      think=agent.thinking_mode.is_enabled,
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
    raise NetworkError(f"Network error: {e}", original_error=e, recoverable=True) from e


async def _consume_stream(agent: Any, stream: Any) -> tuple[str, str, list[Any], dict[str, int]]:
  """Consume the chat stream and return content, thinking, tool calls, stats."""
  content = ""
  thinking = ""
  tool_calls: list[Any] = []
  in_thinking = False
  in_content = False
  stats = {"prompt_eval_count": 0, "eval_count": 0, "total_duration_ms": 0}

  async for chunk in stream:
    if chunk.done:
      stats["prompt_eval_count"] = chunk.prompt_eval_count or 0
      stats["eval_count"] = chunk.eval_count or 0
      stats["total_duration_ms"] = (chunk.total_duration or 0) // 1_000_000

    if chunk.message.thinking:
      in_thinking, thinking = await _handle_thinking_chunk(
        agent, chunk.message.thinking, in_thinking, thinking
      )

    if chunk.message.content:
      in_content, content = await _handle_content_chunk(
        agent, chunk.message.content, in_thinking, in_content, content, thinking
      )
      in_thinking = False

    if chunk.message.tool_calls:
      tool_calls.extend(chunk.message.tool_calls)

  await _close_streams(agent, in_content, in_thinking, content, thinking)
  return content, thinking, tool_calls, stats


async def _handle_thinking_chunk(
  agent: Any, text: str, in_thinking: bool, thinking: str
) -> tuple[bool, str]:
  """Handle a thinking chunk and return updated state."""
  if not in_thinking and agent.thinking_mode.is_visible:
    in_thinking = True
    await emit(ThinkingStartEvent(type=EventType.THINKING_START), agent._event_handlers)
  thinking += text
  if agent.thinking_mode.is_visible:
    await emit(ThinkingChunkEvent(type=EventType.THINKING_CHUNK, text=text), agent._event_handlers)
  return in_thinking, thinking


async def _handle_content_chunk(
  agent: Any,
  text: str,
  in_thinking: bool,
  in_content: bool,
  content: str,
  thinking: str,
) -> tuple[bool, str]:
  """Handle a content chunk and return updated state."""
  if in_thinking and agent.thinking_mode.is_visible:
    await emit(
      ThinkingEndEvent(type=EventType.THINKING_END, total_length=len(thinking)),
      agent._event_handlers,
    )
  if not in_content:
    in_content = True
    await emit(ContentStartEvent(type=EventType.CONTENT_START), agent._event_handlers)
  content += text
  await emit(
    ContentChunkEvent(type=EventType.CONTENT_CHUNK, text=text, content_type="text/plain"),
    agent._event_handlers,
  )
  return in_content, content


async def _close_streams(
  agent: Any, in_content: bool, in_thinking: bool, content: str, thinking: str
) -> None:
  """Emit end events for open content or thinking streams."""
  if in_content:
    await emit(
      ContentEndEvent(type=EventType.CONTENT_END, total_length=len(content)),
      agent._event_handlers,
    )
  elif in_thinking and agent.thinking_mode.is_visible:
    await emit(
      ThinkingEndEvent(type=EventType.THINKING_END, total_length=len(thinking)),
      agent._event_handlers,
    )


def _turn_end_event(response: str, tool_calls: list[Any], stats: dict[str, int]) -> TurnEndEvent:
  """Build a TurnEndEvent from consumed stream stats."""
  return TurnEndEvent(
    type=EventType.TURN_END,
    response=response,
    tool_calls_count=len(tool_calls),
    prompt_eval_count=stats["prompt_eval_count"],
    eval_count=stats["eval_count"],
    total_duration_ms=stats["total_duration_ms"],
  )


async def _execute_tool_calls(agent: Any, tool_calls: list[Any], thinking: str) -> None:
  """Deduplicate and execute tool calls, emitting events."""
  unique_calls = _deduplicate_tool_calls(tool_calls)
  if unique_calls:
    formatted = [
      {
        "id": getattr(call, "id", f"call_{i}"),
        "function": {
          "name": call.function.name,
          "arguments": call.function.arguments,
        },
      }
      for i, call in enumerate(unique_calls)
    ]
    agent.context.add_tool_calls(formatted, thinking=thinking or None)

  for call in unique_calls:
    await _execute_single_tool_call(agent, call)


def _deduplicate_tool_calls(tool_calls: list[Any]) -> list[Any]:
  """Return tool calls without duplicates."""
  seen: set[str] = set()
  unique: list[Any] = []
  for call in tool_calls:
    call_id = getattr(call, "id", None)
    key = (
      call_id
      if call_id
      else f"{call.function.name}:{json.dumps(call.function.arguments, sort_keys=True)}"
    )
    if key not in seen:
      seen.add(key)
      unique.append(call)
    else:
      log.info("tool_call_duplicate_detected", tool=call.function.name, call_key=key)
  return unique


async def _execute_single_tool_call(agent: Any, call: Any) -> None:
  """Execute a single tool call and emit result events."""
  tool_name = call.function.name
  tool_args = call.function.arguments

  await emit(
    ToolCallEvent(type=EventType.TOOL_CALL, tool_name=tool_name, arguments=tool_args),
    agent._event_handlers,
  )
  log.debug("async_tool_call", tool=tool_name, args=tool_args)

  result, success, tool_result = await _run_tool(agent, tool_name, tool_args)

  log.debug("async_tool_result", tool=tool_name, success=success)
  await emit(
    ToolResultEvent(
      type=EventType.TOOL_RESULT,
      tool_name=tool_name,
      result=str(result),
      success=success,
    ),
    agent._event_handlers,
  )

  if success and tool_result.content_metadata is not None:
    await emit(
      ToolContentEvent(
        type=EventType.TOOL_CONTENT,
        tool_name=tool_name,
        operation=tool_result.content_metadata.get("operation", ""),
        path=tool_result.content_metadata.get("path", ""),
        content_type=tool_result.content_metadata.get("content_type", "application/x-summary"),
        content=tool_result.content_metadata.get("content"),
        metadata=tool_result.content_metadata.get("metadata", {}),
      ),
      agent._event_handlers,
    )

  agent.context.add_tool_result(
    tool_name=tool_name,
    tool_id=getattr(call, "id", tool_name),
    result=str(result),
    success=success,
  )


async def _run_tool(agent: Any, tool_name: str, tool_args: dict[str, Any]) -> tuple[str, bool, Any]:
  """Run a tool and return (result, success, raw_tool_result)."""
  spec = agent.tool_registry.get(tool_name)
  if spec is None:
    log.warning("tool_not_found", tool=tool_name)
    return f"Error: Unknown tool '{tool_name}'", False, None

  validation = _validate_tool_args(agent, spec, tool_args)
  if not validation.valid:
    log.info("guardrail_blocked", tool=tool_name, reason=validation.reason)
    return f"Error: {validation.reason}", False, None

  if agent.config.logging.include_permission_checks:
    log.info("guardrail_allowed", tool=tool_name, path=tool_args.get("path"))

  try:
    with log_timing("tool_execution", tool=tool_name):
      tool_result = await spec.execute(**tool_args)
    success = tool_result.success
    result = str(tool_result.result) if success else f"Error: {tool_result.error}"
    return result, success, tool_result
  except Exception as e:
    log.error("tool_error", tool=tool_name, error=str(e))
    return f"Error executing tool: {e}", False, None


def _validate_tool_args(agent: Any, spec: ToolSpec, tool_args: dict[str, Any]) -> Any:
  """Validate tool arguments using schema-driven guardrails.

  Reads each parameter's guard type from the tool spec and dispatches
  the corresponding argument to the appropriate agent guardrail. Returns
  the first validation failure, or a valid result when no guardrail applies.
  """
  for param_name, guard_type in spec.guards.items():
    value = tool_args.get(param_name)
    if value is None:
      continue

    guardrail: Guardrail | None = agent._guardrails[guard_type.value]
    if not guardrail:
      continue

    validation = guardrail.validate(spec.name, value)
    if not validation.valid:
      return validation

  return ValidationResult(valid=True)
