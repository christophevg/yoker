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
from yoker.tools.schema import ToolResult, ValidationResult
from yoker.tools.context import ToolContext
from yoker.tools.guardrails import Guardrail
from yoker.tools.schema import ToolSpec

logger = get_logger(__name__)


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
      logger.error(
        "event_handler_error",
        handler=getattr(handler, "__name__", str(handler)),
        event_type=event.type,
        error=str(e),
      )


async def process_message(agent: Any, message: str) -> str:
  """Process a single message and return the response."""
  logger.info("turn_started", message_preview=message[:50])
  await emit(TurnStartEvent(type=EventType.TURN_START, message=message), agent._event_handlers)
  agent.context.start_turn(message)

  while True:
    stream = await _chat_stream(agent)
    content, thinking, tool_calls, stats = await _consume_stream(agent, stream)

    if not tool_calls:
      agent.context.end_turn(content, thinking=thinking or None)
      await emit(_turn_end_event(content, tool_calls, stats), agent._event_handlers)
      logger.info("turn_completed", response_length=len(content), tool_calls_count=0)
      return content

    await _execute_tool_calls(agent, tool_calls, thinking)


async def _chat_stream(agent: Any) -> Any:
  """Start a streaming chat request."""
  try:
    return await agent._client.chat(
      model=agent.model,
      messages=agent.context.get_context(),
      tools=agent.tools.get_schemas(),
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
    logger.error("network_error", error_type=type(e).__name__, message=str(e))
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
      logger.debug("tool_call_duplicate", tool=call.function.name, call_key=key)
  return unique


async def _execute_single_tool_call(agent: Any, call: Any) -> None:
  """Execute a single tool call and emit result events."""
  tool_name = call.function.name
  tool_args = call.function.arguments

  await emit(
    ToolCallEvent(type=EventType.TOOL_CALL, tool_name=tool_name, arguments=tool_args),
    agent._event_handlers,
  )
  logger.debug("tool_call", tool=tool_name, args=tool_args)

  result, success, tool_result = await _run_tool(agent, tool_name, tool_args)

  logger.debug("tool_result", tool=tool_name, success=success)
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
  spec = agent.tools.get(tool_name)
  if spec is None:
    logger.warning("tool_not_found", tool=tool_name)
    return f"Error: Unknown tool '{tool_name}'", False, None

  validation = _validate_tool_args(agent, spec, tool_args)
  if not validation.valid:
    logger.warning("guardrail_blocked", tool=tool_name, reason=validation.reason)
    return f"Error: {validation.reason}", False, None

  if agent.config.logging.include_permission_checks:
    logger.info("guardrail_allowed", tool=tool_name, path=tool_args.get("path"))

  try:
    with log_timing("tool_execution", tool=tool_name):
      tool_result = await _execute_tool(spec, agent, tool_args)
    success = tool_result.success
    result = str(tool_result.result) if success else f"Error: {tool_result.error}"
    return result, success, tool_result
  except Exception as e:
    logger.error("tool_error", tool=tool_name, error=str(e))
    return f"Error executing tool: {e}", False, None


async def _execute_tool(spec: ToolSpec, agent: Any, tool_args: dict[str, Any]) -> ToolResult:
  """Execute a tool with proper argument binding and context injection.

  Handles:
  - Binding kwargs to the tool's signature
  - Injecting ToolContext if the tool expects it
  - Calling sync or async tools
  - Normalizing the result to ToolResult
  """
  # Get the original tool signature
  sig = inspect.signature(spec.execute)

  # Build kwargs, injecting context if needed
  kwargs = tool_args.copy()
  if _tool_needs_context(spec):
    kwargs["ctx"] = _build_tool_context(agent, spec.name)

  # Bind arguments
  try:
    bound = sig.bind(**kwargs)
    bound.apply_defaults()
  except TypeError as e:
    return ToolResult(success=False, error=f"Invalid tool arguments: {e}")

  # Call the tool
  result = spec.execute(*bound.args, **bound.kwargs)

  # Handle async
  if inspect.isawaitable(result):
    result = await result

  # Normalize to ToolResult
  if isinstance(result, ToolResult):
    return result
  return ToolResult(success=True, result=result)


def _validate_tool_args(agent: Any, spec: ToolSpec, tool_args: dict[str, Any]) -> ValidationResult:
  """Validate tool arguments using schema-driven guardrails."""
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


def _tool_needs_context(spec: ToolSpec) -> bool:
  """Check if a tool expects a ToolContext parameter.

  Inspects the original tool function signature (not a wrapper).
  """
  try:
    sig = inspect.signature(spec.execute)
    for param in sig.parameters.values():
      if param.annotation is ToolContext:
        return True
      # Handle string annotation or ForwardRef
      if isinstance(param.annotation, str) and param.annotation == "ToolContext":
        return True
      if isinstance(param.annotation, inspect.Parameter.empty):
        continue
      # Check for ForwardRef
      if hasattr(param.annotation, "__forward_arg__"):
        return param.annotation.__forward_arg__ == "ToolContext"
    return False
  except (ValueError, TypeError):
    return False


def _build_tool_context(agent: Any, tool_name: str) -> ToolContext:
  """Build a ToolContext for the given tool.

  Args:
    agent: The agent instance.
    tool_name: The tool name (may include namespace prefix like "yoker:write").

  Returns:
    ToolContext with tool-specific config, shared config, and backends.
  """
  # Extract base tool name (remove namespace prefix)
  base_name = tool_name.split(":")[-1] if ":" in tool_name else tool_name

  # Get tool-specific config from config.tools
  tool_config = agent.config.tools[base_name]

  # Get shared config
  shared_config = agent.config.tools_shared

  # Get backends dict (may be empty dict if backends not yet set up)
  backends = getattr(agent, "_tool_backends", {})

  return ToolContext(config=tool_config, shared=shared_config, backends=backends)
