"""Message processing logic for the async Agent."""

import inspect
import json
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, TypedDict, cast

import httpx
import litellm
from structlog import get_logger

from yoker.backends import ChatChunk, ChatChunkEvent
from yoker.events import (
  ContentChunkEvent,
  ContentEndEvent,
  ContentStartEvent,
  ContextOverflowEvent,
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
from yoker.tools.context import ToolContext
from yoker.tools.guardrails import Guardrail
from yoker.tools.schema import ToolResult, ToolSpec, ValidationResult

logger = get_logger(__name__)


class OverflowContext(TypedDict):
  """Payload passed to the ``on_context_overflow`` hook.

  Attributes:
    message_count: Number of messages currently in the context.
    estimated_tokens: The estimated token count that triggered overflow.
    max_tokens: The configured soft cap (``context.max_tokens``).
    messages: The current message list (OpenAI-style dicts). The hook may
      return a validated replacement list.
  """

  message_count: int
  estimated_tokens: int
  max_tokens: int
  messages: list[dict[str, Any]]


# Anthropic context_management directive for thinking-block clearing.
# Forwarded to LitellmBackend only when supports_context_management is True.
_ANTHROPIC_CLEAR_THINKING: dict[str, Any] = {
  "edits": [{"type": "clear_thinking_20251015", "keep": "all"}],
}


def _strip_thinking_blocks(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
  """Drop the ``thinking`` key from each message dict.

  This is the fallback for backends that do not support a provider-side
  ``context_management`` directive (e.g. Ollama, OpenAI). Always-on when
  the backend lacks support — no config flag gates it.

  Args:
    messages: The message list to strip. The caller's list is not
      mutated; a new list of shallow-copied dicts is returned so the
      context's own dicts stay intact.

  Returns:
    A new list of message dicts with ``thinking`` keys removed.
  """
  stripped: list[dict[str, Any]] = []
  for msg in messages:
    if "thinking" in msg:
      new_msg = dict(msg)
      new_msg.pop("thinking", None)
      stripped.append(new_msg)
    else:
      stripped.append(msg)
  return stripped


def _estimate_tokens(
  messages: list[dict[str, Any]],
  last_input_tokens: int | None,
) -> int:
  """Hybrid token estimation.

  Uses the last turn's ``UsageStats.input_tokens`` (captured from the
  backend's USAGE chunk) when available — it is the most accurate signal
  and adds no new dependency. Falls back to a char/4 heuristic over the
  serialized messages when no usage has been observed yet (e.g. the first
  turn, or backends that do not report usage).

  Args:
    messages: The message list to estimate for.
    last_input_tokens: Last captured ``UsageStats.input_tokens``, or None.

  Returns:
    Estimated token count for the message list.
  """
  if last_input_tokens is not None and last_input_tokens > 0:
    return last_input_tokens
  # char/4 heuristic fallback. Sum content + tool_calls + thinking lengths
  # as a rough proxy; matches the order of magnitude for tokenised text.
  total_chars = 0
  for msg in messages:
    content = msg.get("content") or ""
    if isinstance(content, str):
      total_chars += len(content)
    thinking = msg.get("thinking") or ""
    if isinstance(thinking, str):
      total_chars += len(thinking)
    tool_calls = msg.get("tool_calls")
    if isinstance(tool_calls, list):
      total_chars += len(json.dumps(tool_calls))
  return total_chars // 4


def _validate_hook_output(
  original: list[dict[str, Any]],
  replacement: list[dict[str, Any]],
) -> bool:
  """Validate the shape and invariants of a hook-returned message list.

  The hook may return a replacement message list. This function validates:

  - Every item is a dict with a ``role`` key.
  - No ``role=system`` message was dropped (the protected set must survive).
  - Tool-call/tool-result pairing is intact: every ``role=tool`` message
    has a preceding assistant message with ``tool_calls`` referencing its
    ``tool_id`` (no orphaned tool results).
  - Every assistant ``tool_calls`` message that references tool ids has
    matching ``role=tool`` results (no dangling tool calls).

  Args:
    original: The original message list (for the system-drop check).
    replacement: The hook-returned replacement list.

  Returns:
    True if the replacement passes all checks; False otherwise.
  """
  if not isinstance(replacement, list):
    return False
  # Shape: every item must be a dict with a role.
  for item in replacement:
    if not isinstance(item, dict) or "role" not in item:
      return False

  # No dropped role=system messages.
  original_system_count = sum(1 for m in original if m.get("role") == "system")
  replacement_system_count = sum(1 for m in replacement if m.get("role") == "system")
  if replacement_system_count < original_system_count:
    return False

  # Tool-call/tool-result pairing: collect referenced tool ids from
  # assistant tool_calls messages and the tool ids declared by role=tool
  # messages. Every tool result must reference an existing tool call, and
  # every tool call must have at least one matching tool result.
  referenced_tool_ids: set[str] = set()
  for msg in replacement:
    if msg.get("role") == "assistant" and isinstance(msg.get("tool_calls"), list):
      for tc in msg["tool_calls"]:
        if isinstance(tc, dict):
          tc_id = tc.get("id")
          if isinstance(tc_id, str):
            referenced_tool_ids.add(tc_id)

  result_tool_ids: set[str] = set()
  for msg in replacement:
    if msg.get("role") == "tool":
      tool_id = msg.get("tool_id") or msg.get("name")
      if isinstance(tool_id, str):
        result_tool_ids.add(tool_id)

  # No orphaned tool results: every result must reference a known call.
  if result_tool_ids and not result_tool_ids.issubset(referenced_tool_ids):
    return False
  # No dangling tool calls: every referenced id must have a result.
  if referenced_tool_ids and not referenced_tool_ids.issubset(result_tool_ids):
    return False

  return True


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


async def process_message(
  agent: Any,
  message: str,
  on_context_overflow: Callable[[OverflowContext], list[dict[str, Any]] | None] | None = None,
) -> str:
  """Process a single message and return the response.

  Before each backend call in the tool loop, the context size is estimated
  (hybrid: last turn's ``UsageStats.input_tokens`` primary, char/4 fallback).
  When the estimate exceeds ``config.context.max_tokens``, the framework
  default truncation fires: ``context.truncate_oldest_non_system()`` is
  called repeatedly until the estimate is under the cap or no more
  droppable messages remain. A ``ContextOverflowEvent`` is emitted once
  per overflow. When the backend does not support a provider-side
  ``context_management`` directive, thinking blocks are stripped from the
  message list before submission (always-on fallback, no config flag).

  The optional ``on_context_overflow`` hook is a future extension point
  and ships as ``None``. When provided, it receives an
  :class:`OverflowContext` and may return a replacement message list. The
  replacement is validated for shape, role=system preservation, and
  tool-call/tool-result pairing; on validation failure the framework
  default runs instead and a warning is logged.
  """
  logger.info("turn_started", message_preview=message[:50])
  await emit(TurnStartEvent(type=EventType.TURN_START, message=message), agent._event_handlers)
  agent.context.start_turn(message)

  # Last captured UsageStats.input_tokens — the primary signal for the
  # hybrid size check. Updated each turn from _consume_stream's stats.
  last_input_tokens: int | None = None

  while True:
    # Context overflow management: estimate, truncate, strip, emit.
    last_input_tokens = await _manage_context_overflow(
      agent,
      on_context_overflow,
      last_input_tokens,
    )

    stream = _chat_stream(agent)
    content, thinking, tool_calls, stats = await _consume_stream(agent, stream)

    # Capture input_tokens for the next iteration's size check.
    if stats.get("input_tokens"):
      last_input_tokens = stats["input_tokens"]
    elif stats.get("prompt_eval_count"):
      last_input_tokens = stats["prompt_eval_count"]

    if not tool_calls:
      agent.context.end_turn(content, thinking=thinking or None)
      await emit(_turn_end_event(content, tool_calls, stats), agent._event_handlers)
      logger.info("turn_completed", response_length=len(content), tool_calls_count=0)
      return content

    await _execute_tool_calls(agent, tool_calls, thinking, content)


async def _manage_context_overflow(
  agent: Any,
  on_context_overflow: Callable[[OverflowContext], list[dict[str, Any]] | None] | None,
  last_input_tokens: int | None,
) -> int | None:
  """Run the size check, truncation, event, and thinking-strip for one loop step.

  Returns the (possibly updated) ``last_input_tokens`` so the caller can
  thread it through the loop.
  """
  max_tokens = agent.config.context.max_tokens
  messages = agent.context.get_context()
  estimated = _estimate_tokens(messages, last_input_tokens)

  if estimated <= max_tokens:
    # Under the cap: still strip thinking blocks if the backend cannot
    # handle them provider-side. The strip is always-on for
    # non-supporting backends (no config flag).
    _maybe_strip_thinking(agent)
    return last_input_tokens

  # Over the cap: try the hook first, then the framework default.
  dropped_total = 0
  if on_context_overflow is not None:
    dropped_total = _apply_overflow_hook(
      agent,
      on_context_overflow,
      messages,
      estimated,
      max_tokens,
    )

  if dropped_total == 0:
    # No hook or hook returned nothing valid: framework default.
    dropped_total = _apply_framework_default(
      agent,
      last_input_tokens,
      max_tokens,
    )

  # Emit the audit-trail event once per overflow.
  final_count = len(agent.context.get_context())
  await emit(
    ContextOverflowEvent(
      type=EventType.CONTEXT_OVERFLOW,
      message_count=final_count,
      estimated_tokens=estimated,
      max_tokens=max_tokens,
      dropped_count=dropped_total,
    ),
    agent._event_handlers,
  )

  # Strip thinking blocks from the submitted messages when the backend
  # cannot handle them provider-side.
  _maybe_strip_thinking(agent)
  return last_input_tokens


def _apply_overflow_hook(
  agent: Any,
  hook: Callable[[OverflowContext], list[dict[str, Any]] | None],
  messages: list[dict[str, Any]],
  estimated: int,
  max_tokens: int,
) -> int:
  """Call the overflow hook and apply its replacement if valid.

  Returns the dropped count (0 if the hook returned nothing usable).
  """
  payload: OverflowContext = {
    "message_count": len(messages),
    "estimated_tokens": estimated,
    "max_tokens": max_tokens,
    "messages": messages,
  }
  try:
    replacement = hook(payload)
  except Exception as e:
    logger.warning("overflow_hook_error", error=str(e))
    return 0

  if replacement is None:
    return 0

  if not _validate_hook_output(messages, replacement):
    logger.warning(
      "overflow_hook_invalid",
      reason="replacement failed shape/pairing/system validation",
    )
    return 0

  # Apply the replacement via the context manager's API so wrappers
  # (Persisted, ContextManagerWrapper) forward correctly and persist the
  # new state.
  original_count = len(messages)
  agent.context.replace_messages(list(replacement))
  dropped = original_count - len(replacement)
  return max(dropped, 0)


def _apply_framework_default(
  agent: Any,
  last_input_tokens: int | None,
  max_tokens: int,
) -> int:
  """Run the framework-default truncation until under the cap.

  Returns the total number of messages dropped.
  """
  keep_first_user = agent.config.context.overflow_keep_first_user
  dropped_total = 0
  # Hard cap on iterations to avoid an infinite loop when truncation
  # cannot reduce the estimate (e.g. all messages are protected, or the
  # estimate is dominated by the protected prefix).
  max_iterations = len(agent.context.get_context()) + 1
  for _ in range(max_iterations):
    messages = agent.context.get_context()
    # Pass last_input_tokens=None so the char/4 heuristic recalculates on
    # the current (truncated) message list. Reusing the stale last-turn
    # usage would short-circuit _estimate_tokens and prevent the estimate
    # from decreasing as messages are dropped, evicting all droppable
    # history instead of just enough to fit under the cap.
    estimated = _estimate_tokens(messages, None)
    if estimated <= max_tokens:
      break
    # Drop one atomic unit per iteration so the event's dropped_count
    # reflects the cumulative total.
    dropped = agent.context.truncate_oldest_non_system(
      keep_first_user=keep_first_user,
      drop_count=1,
    )
    if dropped <= 0:
      # No more droppable messages; stop to avoid an infinite loop.
      break
    dropped_total += dropped
  return dropped_total


def _maybe_strip_thinking(agent: Any) -> None:
  """Strip thinking blocks from ``_messages`` when the backend lacks support.

  Always-on for non-supporting backends (no config flag). For supporting
  backends (Anthropic), the provider-side ``context_management`` directive
  is forwarded via ``_chat_stream`` instead, so no client-side strip runs.
  Replaces the message list via ``replace_messages`` so wrappers
  (Persisted) persist the stripped state — thinking blocks from prior
  turns would otherwise accumulate and blow up the context.
  """
  backend = agent._backend
  if getattr(backend, "supports_context_management", False):
    return
  messages = agent.context.get_context()
  if not any("thinking" in m for m in messages):
    return
  agent.context.replace_messages(_strip_thinking_blocks(messages))


async def _chat_stream(agent: Any) -> AsyncIterator[ChatChunk]:
  """Start a streaming chat request using the backend.

  For backends that support ``context_management`` (Anthropic), the
  thinking-clearing directive is forwarded so the provider drops thinking
  blocks from prior turns server-side. Non-supporting backends receive
  ``None`` (the client-side strip in ``_maybe_strip_thinking`` handles it).

  Returns an async iterator over ChatChunk events.
  """
  try:
    # Forward the Anthropic thinking-clearing directive only when the
    # backend supports it; None for non-supporting backends.
    context_management = (
      _ANTHROPIC_CLEAR_THINKING
      if getattr(agent._backend, "supports_context_management", False)
      else None
    )
    # chat_stream returns an async generator - iterate directly without await
    async for chunk in agent._backend.chat_stream(
      model=agent.model,
      messages=agent.context.get_context(),
      tools=agent.tools.get_schemas(),
      think=agent.thinking_mode.is_enabled,
      context_management=context_management,
    ):
      yield chunk
  except (
    # HTTP network errors (recoverable)
    httpx.RemoteProtocolError,
    httpx.ConnectError,
    httpx.ReadError,
    httpx.WriteError,
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    # LiteLLM transient errors (recoverable)
    litellm.ServiceUnavailableError,  # 503 - service temporarily unavailable
    litellm.RateLimitError,  # 429 - rate limit exceeded
    litellm.APIConnectionError,  # connection issues
    litellm.InternalServerError,  # 500 - internal server error
  ) as e:
    logger.error("network_error", error_type=type(e).__name__, message=str(e))
    # Extract user-friendly message
    message = _extract_user_friendly_message(e)
    raise NetworkError(message, original_error=e, recoverable=True) from e
  except (
    # LiteLLM authentication/permission errors (non-recoverable)
    litellm.AuthenticationError,
    litellm.PermissionDeniedError,
    litellm.NotFoundError,
  ) as e:
    logger.error("auth_error", error_type=type(e).__name__, message=str(e))
    message = _extract_user_friendly_message(e)
    raise NetworkError(message, original_error=e, recoverable=False) from e


def _extract_user_friendly_message(error: Exception) -> str:
  """Extract a user-friendly message from backend exceptions.

  LiteLLM exceptions often contain verbose error details. This function
  extracts the essential information for the user.

  For httpx errors, preserves the original "Network error" prefix for
  backward compatibility with tests.

  Args:
    error: The exception to extract a message from.

  Returns:
    A user-friendly error message.
  """
  error_type = type(error).__name__

  # For httpx errors, use the original format "Network error: {error}"
  # This maintains backward compatibility with tests
  if isinstance(
    error,
    (
      httpx.RemoteProtocolError,
      httpx.ConnectError,
      httpx.ReadError,
      httpx.WriteError,
      httpx.ConnectTimeout,
      httpx.ReadTimeout,
    ),
  ):
    return f"Network error: {error}"

  # Service Unavailable (503) - common with Vertex AI/Gemini during high demand
  if isinstance(error, litellm.ServiceUnavailableError):
    # Try to extract the actual message from the error
    error_str = str(error)
    # Vertex AI errors often contain JSON with message field
    if "This model is currently experiencing high demand" in error_str:
      return (
        f"{error_type}: The model is currently experiencing high demand. Please try again later."
      )
    return f"{error_type}: The service is temporarily unavailable. Please try again later."

  # Rate Limit (429)
  if isinstance(error, litellm.RateLimitError):
    return f"{error_type}: Rate limit exceeded. Please wait a moment and try again."

  # Connection errors
  if isinstance(error, litellm.APIConnectionError):
    return f"{error_type}: Unable to connect to the model provider. Please check your network connection."

  # Internal Server Error (500)
  if isinstance(error, litellm.InternalServerError):
    return (
      f"{error_type}: The model provider encountered an internal error. Please try again later."
    )

  # Authentication errors
  if isinstance(error, litellm.AuthenticationError):
    return f"{error_type}: Authentication failed. Please check your API key configuration."

  # Permission errors
  if isinstance(error, litellm.PermissionDeniedError):
    return f"{error_type}: Permission denied. Please check your API key permissions."

  # Not found errors
  if isinstance(error, litellm.NotFoundError):
    return f"{error_type}: Model or resource not found. Please check your model configuration."

  # Default: use the error type and message
  return f"{error_type}: {error}"


async def _consume_stream(
  agent: Any, stream: AsyncIterator[ChatChunk]
) -> tuple[str, str, list[Any], dict[str, int]]:
  """Consume the ChatChunk stream and return content, thinking, tool calls, stats."""
  content = ""
  thinking = ""
  tool_calls: list[Any] = []
  tool_call_buffers: dict[int, dict[str, Any]] = {}  # index -> accumulated tool call data
  in_thinking = False
  in_content = False
  stats = {
    "prompt_eval_count": 0,
    "eval_count": 0,
    "total_duration_ms": 0,
    "input_tokens": 0,
    "output_tokens": 0,
  }

  async for chunk in stream:
    if chunk.event == ChatChunkEvent.CONTENT_START:
      if in_thinking and agent.thinking_mode.is_visible:
        await emit(
          ThinkingEndEvent(type=EventType.THINKING_END, total_length=len(thinking)),
          agent._event_handlers,
        )
        in_thinking = False
      if not in_content:
        in_content = True
        await emit(ContentStartEvent(type=EventType.CONTENT_START), agent._event_handlers)

    elif chunk.event == ChatChunkEvent.CONTENT_DELTA:
      if not in_content:
        in_content = True
        await emit(ContentStartEvent(type=EventType.CONTENT_START), agent._event_handlers)
      text = chunk.text or ""
      content += text
      await emit(
        ContentChunkEvent(type=EventType.CONTENT_CHUNK, text=text, content_type="text/plain"),
        agent._event_handlers,
      )

    elif chunk.event == ChatChunkEvent.CONTENT_STOP:
      if in_content:
        await emit(
          ContentEndEvent(type=EventType.CONTENT_END, total_length=len(content)),
          agent._event_handlers,
        )
        in_content = False

    elif chunk.event == ChatChunkEvent.THINKING_START:
      if not in_thinking and agent.thinking_mode.is_visible:
        in_thinking = True
        await emit(ThinkingStartEvent(type=EventType.THINKING_START), agent._event_handlers)

    elif chunk.event == ChatChunkEvent.THINKING_DELTA:
      text = chunk.text or ""
      thinking += text
      if agent.thinking_mode.is_visible:
        if not in_thinking:
          in_thinking = True
          await emit(ThinkingStartEvent(type=EventType.THINKING_START), agent._event_handlers)
        await emit(
          ThinkingChunkEvent(type=EventType.THINKING_CHUNK, text=text), agent._event_handlers
        )

    elif chunk.event == ChatChunkEvent.THINKING_STOP:
      if in_thinking and agent.thinking_mode.is_visible:
        await emit(
          ThinkingEndEvent(type=EventType.THINKING_END, total_length=len(thinking)),
          agent._event_handlers,
        )
        in_thinking = False

    elif chunk.event == ChatChunkEvent.TOOL_CALL_START:
      if chunk.tool_call:
        index = chunk.tool_call.index
        tool_call_buffers[index] = {
          "id": chunk.tool_call.id,
          "name": chunk.tool_call.name,
          "arguments_json": "",
        }

    elif chunk.event == ChatChunkEvent.TOOL_CALL_DELTA:
      if chunk.tool_call:
        index = chunk.tool_call.index
        if index in tool_call_buffers:
          tool_call_buffers[index]["arguments_json"] += chunk.tool_call.arguments_delta or ""

    elif chunk.event == ChatChunkEvent.TOOL_CALL_STOP:
      if chunk.tool_call:
        index = chunk.tool_call.index
        if index in tool_call_buffers:
          # Build a tool call object compatible with the existing tool execution logic
          buffer = tool_call_buffers[index]
          tool_calls.append(_build_tool_call(buffer))

    elif chunk.event == ChatChunkEvent.USAGE:
      if chunk.usage:
        # Map UsageStats to stats dict for TurnEndEvent
        if chunk.usage.prompt_eval_count is not None:
          stats["prompt_eval_count"] = chunk.usage.prompt_eval_count
        if chunk.usage.eval_count is not None:
          stats["eval_count"] = chunk.usage.eval_count
        if chunk.usage.total_duration_ms is not None:
          stats["total_duration_ms"] = chunk.usage.total_duration_ms
        if chunk.usage.input_tokens is not None:
          stats["input_tokens"] = chunk.usage.input_tokens
        if chunk.usage.output_tokens is not None:
          stats["output_tokens"] = chunk.usage.output_tokens

    elif chunk.event == ChatChunkEvent.DONE:
      # Stream complete
      pass

  # Close any open streams
  await _close_streams(agent, in_content, in_thinking, content, thinking)

  return content, thinking, tool_calls, stats


def _build_tool_call(buffer: dict[str, Any]) -> Any:
  """Build a tool call object from accumulated buffer data.

  Returns an object compatible with the existing tool execution logic,
  with .id, .function.name, and .function.arguments attributes.
  """

  class Function:
    def __init__(self, name: str, arguments: str | dict[str, Any]):
      self.name = name
      # Parse arguments if it's a JSON string, otherwise use as-is
      if isinstance(arguments, str):
        try:
          self.arguments: dict[str, Any] = json.loads(arguments)
        except json.JSONDecodeError:
          self.arguments = {}
      else:
        self.arguments = arguments

  class ToolCall:
    def __init__(
      self, call_id: str | None, function_name: str, function_args: str | dict[str, Any]
    ):
      self.id = call_id or f"call_{id(self)}"
      self.function = Function(function_name, function_args)

  return ToolCall(buffer.get("id"), buffer.get("name", ""), buffer.get("arguments_json", ""))


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
    input_tokens=stats["input_tokens"],
    output_tokens=stats["output_tokens"],
  )


async def _execute_tool_calls(
  agent: Any,
  tool_calls: list[Any],
  thinking: str,
  content: str = "",
) -> None:
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
    agent.context.add_tool_calls(formatted, thinking=thinking or None, content=content)

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
  # Convert schema format (__) to canonical format (:) for display and lookup
  tool_name = (
    call.function.name.replace("__", ":", 1) if "__" in call.function.name else call.function.name
  )
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
    logger.warning(f"available: {list(agent.tools.keys())}")
    return f"Error: Unknown tool '{tool_name}'", False, None

  validation = _validate_tool_args(agent, spec, tool_args)
  if not validation.valid:
    logger.warning("guardrail_blocked", tool=tool_name, reason=validation.reason)
    return f"Error: {validation.reason}", False, None

  if agent.config.logging.include_permission_checks:
    logger.info("guardrail_allowed", tool=tool_name, path=tool_args.get("path"))

  # Protected-file approval hook (MBI-009 T12). When an approval handler is
  # wired on the agent, the PathGuardrail simple block is skipped and this
  # hook handles protected write/update interactively. On denial, return a
  # blocked ToolResult without executing the tool. On exception in the
  # handler, fail-safe to denial. On approval, fall through to _execute_tool.
  approval_block = await _maybe_block_protected(agent, tool_name, tool_args)
  if approval_block is not None:
    return approval_block

  try:
    with log_timing("tool_execution", tool=tool_name):
      tool_result = await _execute_tool(spec, agent, tool_args)
    success = tool_result.success
    result = str(tool_result.result) if success else f"Error: {tool_result.error}"
    return result, success, tool_result
  except Exception as e:
    logger.error("tool_error", tool=tool_name, error=str(e))
    return f"Error executing tool: {e}", False, None


async def _maybe_block_protected(
  agent: Any, tool_name: str, tool_args: dict[str, Any]
) -> tuple[str, bool, Any] | None:
  """Run the interactive approval flow for protected write/update, if active.

  Returns:
    - ``None`` when no approval is needed (non-protected path, no handler
      wired, or tool is not write/update) — the caller proceeds to execute
      the tool. Also ``None`` on approval.
    - A blocked ``(message, False, None)`` tuple when the user denies (or
      the handler raises) — the caller returns it directly.
  """
  base_name = tool_name.split(":")[-1] if ":" in tool_name else tool_name
  if base_name not in ("write", "update"):
    return None
  handler = getattr(agent, "_approval_handler", None)
  if handler is None:
    return None
  path = tool_args.get("path")
  if not isinstance(path, str):
    return None
  guardrail = agent._guardrails.get("path")
  if guardrail is None or not guardrail.is_protected(path):
    return None

  diff = _build_approval_diff(base_name, path, tool_args)
  try:
    approved = await handler(path, diff, "file")
  except Exception as e:
    logger.warning("approval_handler_error", tool=tool_name, error=str(e))
    approved = False

  if not approved:
    return f"Error: User denied write to protected file: {path}", False, None
  return None


def _build_approval_diff(tool_name: str, path: str, tool_args: dict[str, Any]) -> str:
  """Build a unified diff for an approval prompt.

  - ``update``: applies the tool's replace/delete/insert logic to the
    current file content and diffs the result. Falls back to empty old
    content when the file cannot be read (defensive — ``update`` requires
    an existing file, so this is unreachable in practice).
  - ``write``: diffs the current file content (if any) against the new
    content. New files produce an all-additions diff.
  """
  from pathlib import Path

  from yoker.tools.diff import generate_diff

  filename = Path(path).name

  if tool_name == "update":
    try:
      old_content = Path(path).read_text(encoding="utf-8")
    except OSError:
      old_content = ""
    operation = tool_args.get("operation", "replace")
    old_string = tool_args.get("old_string", "")
    new_string = tool_args.get("new_string", "")
    if operation == "replace":
      new_content = old_content.replace(old_string, new_string, 1)
    elif operation == "delete":
      new_content = old_content.replace(old_string, "", 1)
    elif operation in ("insert_before", "insert_after"):
      # Reproduce the update tool's _do_insert so the approval diff shows
      # the insertion in context rather than a misleading full-file
      # replacement. line_number is required by _do_insert; without it the
      # actual tool call would also fail validation, so fall back to the
      # new string alone (defensive).
      line_number = tool_args.get("line_number")
      if line_number is None:
        new_content = new_string
      else:
        new_content = _apply_insert(old_content, operation, line_number, new_string)
    else:
      new_content = new_string
  else:  # write
    new_content = tool_args.get("content", "")
    try:
      old_content = Path(path).read_text(encoding="utf-8")
    except OSError:
      old_content = ""

  return generate_diff(old_content, new_content, filename)


def _apply_insert(old_content: str, operation: str, line_number: Any, new_string: str) -> str:
  """Mirror ``yoker.builtin.update._do_insert`` for approval diff rendering.

  Inserts ``new_string`` before/after the 1-based ``line_number`` in
  ``old_content`` and returns the resulting full file content. Unlike
  ``_do_insert``, this helper does not raise on out-of-range line numbers
  — a bad range would make the diff unintelligible but the actual tool
  call would fail validation anyway, so we fall back to appending at the
  nearest boundary.
  """
  try:
    line_num = int(line_number)
  except (ValueError, TypeError):
    return new_string

  lines = old_content.splitlines(keepends=True)
  if not lines:
    return new_string + "\n"

  if lines and not lines[-1].endswith("\n"):
    lines[-1] = lines[-1] + "\n"

  total = len(lines)
  # Clamp to valid range so an out-of-range request still produces a
  # readable diff rather than raising.
  if operation == "insert_before":
    idx = max(0, min(line_num - 1, total))
  else:  # insert_after
    idx = max(0, min(line_num, total))
  lines.insert(idx, new_string + "\n")
  return "".join(lines)


async def _execute_tool(spec: ToolSpec, agent: Any, tool_args: dict[str, Any]) -> ToolResult:
  """Execute a tool with proper argument binding and context injection.

  Handles:
  - Extracting the auto-injected ``post_filter`` parameter before binding
  - Binding kwargs to the tool's signature
  - Injecting ToolContext if the tool expects it
  - Calling sync or async tools
  - Normalizing the result to ToolResult
  - Applying post-filter to the result string (grep-style line filtering)
  """
  # Get the original tool signature
  if spec.execute is None:
    return ToolResult(success=False, error=f"Tool '{spec.name}' has no execute function")
  sig = inspect.signature(spec.execute)

  # Extract post_filter without mutating the original tool_args dict.
  # tool_args is shared with the ToolCallEvent (emitted before _run_tool),
  # so popping from it would hide post_filter from the UI display and any
  # event handlers that inspect arguments after execution.
  post_filter = tool_args.get("post_filter", None)
  kwargs = {k: v for k, v in tool_args.items() if k != "post_filter"}
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
  if not isinstance(result, ToolResult):
    result = ToolResult(success=True, result=result)

  # Apply post-filter to the result string (grep-style line filtering).
  # Apply on both success and failure — on failure the error field carries
  # the useful output (e.g. test failures) that the LLM wants to filter.
  if post_filter:
    result = _apply_post_filter(result, post_filter)

  # Enforce output size limit AFTER post_filter has been applied. This
  # ensures the LLM can use post_filter to reduce output below the limit.
  # If the (filtered) output still exceeds max_output_kb, return an error
  # instead of silently truncating — truncation loses the end of the output
  # (typically where failures are), making the result useless.
  result = _enforce_output_limit(result, agent, spec)

  return result


def _apply_post_filter(result: ToolResult, pattern: str) -> ToolResult:
  """Filter a ToolResult's output line-by-line using a regex pattern.

  Filters both ``result`` and ``error`` fields:

  - **String results**: filtered line-by-line directly.
  - **Dict results** (e.g. from the make tool): each string value within the
    dict is filtered line-by-line. This is necessary because ``str(dict)``
    or ``json.dumps(dict)`` produces a single-line repr with escaped newlines
    for embedded string values, making line-based filtering useless. By
    filtering individual string values (e.g. ``stdout``, ``stderr``), the
    line structure of the original output is preserved.
  - **Error field**: filtered line-by-line if it's a string (failure case).

  Only lines matching the pattern are kept. A summary line is appended
  showing how many lines were kept out of the total. If the pattern is
  invalid regex, the original result is returned unchanged with a warning.
  """
  import re as _re

  try:
    regex = _re.compile(pattern)
  except _re.error as e:
    logger.warning("post_filter_invalid_regex", pattern=pattern, error=str(e))
    return result

  new_result = result.result
  new_error = result.error

  # Filter the result field.
  if isinstance(new_result, str) and new_result:
    new_result, changed = _filter_lines(new_result, regex, pattern)
  elif isinstance(new_result, dict) and new_result:
    new_result, changed = _filter_dict_values(new_result, regex, pattern)
  else:
    changed = False

  # Filter the error field if it's a string (failure case — e.g. make tool
  # puts combined stdout+stderr in error on failure)
  if isinstance(new_error, str) and new_error:
    new_error, error_changed = _filter_lines(new_error, regex, pattern)
    changed = changed or error_changed

  if not changed:
    return result

  return ToolResult(
    success=result.success,
    result=new_result,
    error=new_error,
    content_metadata=result.content_metadata,
  )


def _filter_lines(content: str, regex: re.Pattern[str], pattern: str) -> tuple[str, bool]:
  """Filter ``content`` line-by-line, keeping only lines matching ``regex``.

  Returns (filtered_content, changed). If all lines match, returns the
  original content unchanged with changed=False (no summary appended).
  """
  lines = content.splitlines()
  matched = [line for line in lines if regex.search(line)]
  total = len(lines)
  kept = len(matched)

  if kept == total:
    # No filtering happened — all lines matched.
    return content, False

  filtered = "\n".join(matched)
  filtered += f"\n\n[post_filter: {kept}/{total} lines matched pattern: {pattern}]"
  return filtered, True


def _filter_dict_values(
  data: dict[str, Any], regex: re.Pattern[str], pattern: str
) -> tuple[dict[str, Any], bool]:
  """Filter string values within a dict result line-by-line.

  Tools like ``make`` return a dict (e.g. ``{"exit_code": 0, "stdout": "...",
  "stderr": "..."}``). Converting the entire dict to ``str()`` or ``json.dumps``
  produces a single-line repr with escaped newlines for embedded strings,
  making line-based filtering useless. Instead, we filter each string value
  individually, preserving the dict structure and the line structure of the
  original content.

  Non-string values (ints, bools, None) are left unchanged.

  Returns (new_dict, changed). If no values were filtered, returns the
  original dict unchanged with changed=False.
  """
  changed = False
  new_data: dict[str, Any] = {}
  for key, value in data.items():
    if isinstance(value, str) and value:
      filtered, val_changed = _filter_lines(value, regex, pattern)
      if val_changed:
        new_data[key] = filtered
        changed = True
      else:
        new_data[key] = value
    else:
      new_data[key] = value
  return new_data, changed


def _enforce_output_limit(result: ToolResult, agent: Any, spec: ToolSpec) -> ToolResult:
  """Check if the result's string fields exceed the tool's max_output_kb.

  If the output exceeds the limit, return a ToolResult with a clear error
  telling the LLM to use post_filter to narrow the output. This runs AFTER
  post_filter has been applied, so the LLM can retry with a more specific
  filter.

  Only applies to tools whose config has ``max_output_kb`` (currently make
  and github). Tools without this config field are not checked.
  """
  base_name = spec.simple_name
  try:
    tool_config = agent.config.tools[base_name]
  except (AttributeError, KeyError, TypeError):
    return result

  max_output_kb = getattr(tool_config, "max_output_kb", None)
  if not isinstance(max_output_kb, int):
    return result

  max_bytes = max_output_kb * 1024

  # Check the relevant string field(s). On success, check result.result;
  # on failure, check result.error (the field the LLM sees).
  # Dict results (e.g. from the make tool) are converted to string — matching
  # what _run_tool does at line 863 (str(tool_result.result)).
  field_val: str | dict[str, Any] | None
  if result.success:
    field_val = result.result
  else:
    field_val = result.error

  if isinstance(field_val, dict):
    field_val = str(field_val)

  if not isinstance(field_val, str) or not field_val:
    return result

  encoded = field_val.encode("utf-8")
  if len(encoded) <= max_bytes:
    return result

  actual_kb = len(encoded) // 1024
  error_msg = (
    f"Output exceeds {max_output_kb}KB limit ({actual_kb}KB after post_filter). "
    f"Use a more specific post_filter pattern to narrow the output. "
    f"Avoid broad terms like 'error' that match test names. "
    f"Good patterns: 'FAILED|Traceback|assert|short test summary' for tests, "
    f"'class |def |import ' for code structure, 'CalledProcessError|exit code' for CI."
  )
  return ToolResult(success=False, error=error_msg)


def _validate_tool_args(agent: Any, spec: ToolSpec, tool_args: dict[str, Any]) -> ValidationResult:
  """Validate tool arguments using schema-driven guardrails."""
  for param_name, guard_type in spec.guards.items():
    value = tool_args.get(param_name)
    if value is None:
      continue

    guardrail: Guardrail | None = agent._guardrails.get(guard_type.value)
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
    if spec.execute is None:
      return False
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
        forward_arg: str = param.annotation.__forward_arg__
        return forward_arg == "ToolContext"
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

  # The Agent is Session-agnostic and does not carry a Session reference.
  # Session-aware tools (send_message, agent) capture the Session in their
  # closures at injection time, so ToolContext.session is left as None.
  return ToolContext(
    config=tool_config,
    shared=shared_config,
    backends=backends,
    session=None,
    approval_handler=getattr(agent, "_approval_handler", None),
  )
