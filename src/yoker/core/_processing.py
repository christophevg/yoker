"""Message processing logic for the async Agent."""

import inspect
import json
import os
import re
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, TypedDict, cast

import httpx
import litellm
from structlog import get_logger

from yoker.backends import ChatChunk, ChatChunkEvent
from yoker.config import (
  DEFAULT_COMPACTION_STAGES,
  CompactionConfig,
  ToolConfig,
  ToolsConfig,
)
from yoker.context.manager import _prune_stub_text
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
from yoker.tools.annotations import GuardType
from yoker.tools.context import ToolContext
from yoker.tools.guardrails import Guardrail
from yoker.tools.schema import (
  ApprovalPrompt,
  ToolResult,
  ToolSpec,
  ValidationResult,
  describe_expected_arguments,
)
from yoker.usage.logger import log_call_usage

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

# System-side note injected into the context after the configured number of
# consecutive failed tool calls. Tells the model to stop retrying the same
# doomed approach and escalate instead.
_TOOL_FAILURE_ESCALATION_NOTE = (
  "SYSTEM NOTE: Your last {n} tool calls failed consecutively. Stop retrying "
  "the same approach — it is not working. Reconsider your strategy: read the "
  "error messages, adjust the arguments, use a different tool, or STOP and "
  "ask the user for help."
)


class _EscalationState:
  """Mutable retry-limit escalation state threaded through the tool loop.

  Attributes:
    consecutive_failures: Number of consecutive failed tool calls since the
      last success (reset on every success).
    injected: Whether the escalation note has been injected since the last
      reset — prevents re-injecting while failures continue.
  """

  __slots__ = ("consecutive_failures", "injected")

  def __init__(self, consecutive_failures: int = 0, injected: bool = False) -> None:
    self.consecutive_failures = consecutive_failures
    self.injected = injected


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
  called repeatedly until the estimate is under the trim target
  (``max_tokens * config.context.compact_ratio`` — hysteresis so a growing
  session does not re-cross the cap every turn) or no more droppable
  messages remain. A ``ContextOverflowEvent`` is emitted once per overflow.
  When the backend does not support a provider-side ``context_management``
  directive, thinking blocks are stripped from the message list before
  submission (always-on fallback, no config flag).

  The optional ``on_context_overflow`` hook is a future extension point
  and ships as ``None``. When provided, it receives an
  :class:`OverflowContext` and may return a replacement message list. The
  replacement is validated for shape, role=system preservation, and
  tool-call/tool-result pairing; on validation failure the framework
  default runs instead and a warning is logged.

  Retry-limit escalation: consecutive failed tool calls are counted
  (reset on every success). When the count reaches
  ``config.agent.max_consecutive_tool_failures``, a one-time system-side
  note is injected telling the model to stop retrying the same approach.
  The note can fire again only after the counter has reset and re-climbed
  to the threshold. A value of ``0`` disables the escalation.
  """
  logger.info("turn_started", message_preview=message[:50])
  await emit(TurnStartEvent(type=EventType.TURN_START, message=message), agent._event_handlers)
  agent.context.start_turn(message)

  # Wall-clock timing for the entire turn (all stream iterations + tool
  # calls).  Provider-supplied total_duration_ms only covers the last
  # chunk's latency; this measures the real elapsed time the user waited.
  turn_start = time.monotonic()

  # Retry-limit escalation state: consecutive failed tool calls this turn,
  # and whether the escalation note has been injected since the last reset.
  # Created once per message; updated in-place by the tool-execution path.
  escalation = _EscalationState()

  while True:
    # Context overflow management: estimate, truncate, strip, emit.
    # The estimate is calibrated from server usage captured in earlier
    # calls (persisted on the agent across turns).
    await _manage_context_overflow(agent, on_context_overflow)

    # Start the idle watchdog scoped to the LLM streaming phase only.
    # The watchdog detects when the backend stops sending data for
    # ``timeout_seconds`` — an LLM server hang. Tool execution time is
    # NOT monitored (the agent is actively working during tools).
    timeout_seconds = agent.config.agent.timeout_seconds
    agent._touch_activity()
    agent._start_idle_watchdog(timeout_seconds)
    try:
      stream = _chat_stream(agent)
      content, thinking, tool_calls, stats = await _consume_stream(agent, stream)
    finally:
      agent._stop_idle_watchdog()

    # Capture usage for the next iteration's size check, and update the
    # agent's persistent context-size calibration (fixed overhead +
    # density ratio) from the server-reported count.
    captured = stats.get("input_tokens") or stats.get("prompt_eval_count")
    if captured:
      _capture_calibration(agent, captured)

    # Log per-API-call token usage (atomic JSONL append).
    log_call_usage(agent, stats)

    if not tool_calls:
      agent.context.end_turn(content, thinking=thinking or None)
      elapsed_ms = int((time.monotonic() - turn_start) * 1000)
      usage_data = await _fetch_backend_usage(agent)
      await emit(
        _turn_end_event(content, tool_calls, stats, elapsed_ms, usage_data, agent=agent),
        agent._event_handlers,
      )
      logger.info("turn_completed", response_length=len(content), tool_calls_count=0)
      return content

    await _execute_tool_calls(agent, tool_calls, thinking, content, escalation)


def _capture_calibration(
  agent: Any,
  input_tokens: int,
) -> None:
  """Update the context-size calibration model from a server usage capture.

  Maintains on the agent:
    ``_context_fixed_tokens`` — the fixed prompt overhead (system prompt,
      tool schemas, definitions) in tokens, re-derived every capture as
      ``server − ratio × char4(messages)`` (self-correcting: drift in
      either parameter is absorbed on the next capture; clamped at 0).
      A smaller reading after a content drop is a real shrinkage and is
      learned as such.
    ``_context_ratio`` — real-tokens-per-char4 density of recently added
      content, learned from consecutive capture deltas (EMA-smoothed,
      clamped). Skipped when the delta spans a truncation (char4 shrank
      but content was not merely appended).
    ``_context_char4_at_capture`` / ``_context_last_input_tokens`` — the
      learning base pair for the next delta.

  With these, the overflow estimate becomes
  ``fixed + ratio * char4(messages)``, which tracks the server count far
  better than either the raw char/4 heuristic (overhead-blind) or the
  stale per-call total (blind to content added after the last call).
  """
  char4_now = _estimate_tokens(agent.context.get_context(), None)
  prev_server = agent._context_last_input_tokens
  prev_char4 = agent._context_char4_at_capture

  # Learn the density ratio from growth deltas between consecutive
  # captures: both the server count and char4 grew by (only) the content
  # added in between, so their quotient is that content's density. Skip
  # when char4 shrank (a truncation happened in between — deltas would
  # measure the truncation, not the density of added content).
  if (
    prev_server is not None
    and prev_char4 is not None
    and char4_now > prev_char4
    and input_tokens > prev_server
  ):
    observed = (input_tokens - prev_server) / (char4_now - prev_char4)
    # Clamp to a sane band; EMA-weight toward the new observation.
    clamped = min(max(observed, 0.25), 8.0)
    agent._context_ratio = agent._context_ratio * 0.5 + clamped * 0.5

  # Re-derive the fixed overhead from THIS capture using the current
  # ratio: fixed = server − ratio × char4. Re-deriving every capture
  # keeps the estimate ≈ the server count at capture time (drift in
  # either parameter self-corrects), instead of freezing a first-capture
  # guess made before the ratio was known. Clamped at 0 (the overhead
  # cannot be negative).
  agent._context_fixed_tokens = max(int(input_tokens - agent._context_ratio * char4_now), 0)

  agent._context_char4_at_capture = char4_now
  agent._context_last_input_tokens = input_tokens


def _calibrated_estimate(
  agent: Any,
  messages: list[dict[str, Any]],
) -> int | None:
  """Calibrated context-size estimate: ``fixed + ratio * char4(messages)``.

  Returns None when no server usage has been observed yet (caller falls
  back to the raw char/4 heuristic).
  """
  fixed = agent._context_fixed_tokens
  if fixed is None:
    return None
  ratio = agent._context_ratio
  estimate = fixed + int(ratio * _estimate_tokens(messages, None))
  return int(estimate)


def _first_remaining_summary(messages: list[dict[str, Any]]) -> str | None:
  """Summarize the first non-protected message of ``messages`` in one line.

  The protected prefix (system setup messages + the first user turn) is
  static, so retained *history* effectively starts right after it. The
  summary identifies where that history begins, giving a sense of the
  compaction's impact. Returns None when nothing beyond the protected
  prefix remains.

  Shape: ``role[: brief content preview]`` for plain messages, with
  ``role → tools: name ×N`` for assistant messages carrying tool calls
  (content preview when the assistant also has text content).
  """
  protected_end = 0
  n = len(messages)
  while protected_end < n and messages[protected_end].get("role") == "system":
    protected_end += 1
  if protected_end < n and messages[protected_end].get("role") == "user":
    # Skip the contiguous user prefix, then the first real user turn.
    while protected_end < n and messages[protected_end].get("role") == "user":
      protected_end += 1
  if protected_end >= n:
    return None

  msg = messages[protected_end]
  role = str(msg.get("role", "?"))
  tool_calls = msg.get("tool_calls")
  if isinstance(tool_calls, list) and tool_calls:
    names: list[str] = []
    for tc in tool_calls:
      if isinstance(tc, dict):
        fn = tc.get("function")
        name = fn.get("name") if isinstance(fn, dict) else tc.get("name")
        if name:
          names.append(str(name))
    counts: dict[str, int] = {}
    for name in names:
      counts[name] = counts.get(name, 0) + 1
    parts = [f"{name} ×{c}" if c > 1 else name for name, c in counts.items()]
    summary = f"{role} → tools: {', '.join(parts)}"
    content = msg.get("content")
    if isinstance(content, str) and content.strip():
      summary += f" | {content.strip()[:40]}"
      if len(content.strip()) > 40:
        summary += "…"
    return summary
  content = msg.get("content")
  if isinstance(content, str) and content.strip():
    trimmed: str = content.strip()
    preview = trimmed[:60]
    if len(trimmed) > 60:
      preview += "…"
    return f"{role}: {preview}"
  return role


async def _manage_context_overflow(
  agent: Any,
  on_context_overflow: Callable[[OverflowContext], list[dict[str, Any]] | None] | None,
) -> None:
  """Run the size check, truncation, event, and thinking-strip for one loop step.

  The estimate is calibrated (``fixed + ratio * char4``) whenever server
  usage has been captured, falling back to the raw char/4 heuristic only
  before the first capture. Calibration parameters persist on the agent
  across turns, so every turn's first check — including tool-less turns —
  sees a truthful size.
  """
  max_tokens = agent.config.context.max_tokens
  messages = agent.context.get_context()
  estimated = _calibrated_estimate(agent, messages)
  if estimated is None:
    estimated = _estimate_tokens(messages, agent._context_last_input_tokens)

  if estimated <= max_tokens:
    # Under the cap: nothing to do. Thinking handling happens entirely at
    # projection level in get_context (strip_thinking_in_view / pruned
    # flags) — no physical strip runs here anymore.
    return

  # Hysteresis: trim to a FRACTION of the cap, not the cap itself. A
  # growing session trimmed to the cap re-crosses it almost every turn —
  # and every trim invalidates the server's prefix (KV) cache, forcing a
  # full-price reprocess. Trimming deeper leaves headroom so the prefix
  # survives several turns between trims. 1.0 reproduces trim-to-cap.
  raw_ratio = getattr(agent.config.context, "compact_ratio", 1.0)
  ratio = raw_ratio if isinstance(raw_ratio, int | float) and 0 < raw_ratio <= 1.0 else 1.0
  target = int(max_tokens * ratio)

  # Over the cap: try the hook first, then the framework pipeline.
  dropped_total = 0
  stages: list[dict[str, Any]] = []
  run_id: str | None = None
  floor_tokens: int | None = None
  target_clamped = False
  hook_path = False
  if on_context_overflow is not None:
    hook_path = True
    dropped_total = _apply_overflow_hook(
      agent,
      on_context_overflow,
      messages,
      estimated,
      max_tokens,
    )

  if not hook_path or dropped_total == 0:
    # No hook, hook returned nothing valid, or a hook attended but
    # achieved nothing: run the framework pipeline.
    (
      dropped_total,
      stages,
      run_id,
      floor_tokens,
      target_clamped,
    ) = _run_compaction_pipeline(agent, estimated, target)

  # Post-pipeline truth: the ACHIEVED view estimate and sent-message count
  # (what the next submission actually contains — stubs shrink bodies,
  # dropped/flagged messages leave the view, so sent_count can be far
  # below the stored count). Fallback stays content-sensitive (None, not
  # the stale server total) — see _estimate_of.
  remaining = agent.context.get_context()
  remaining_estimate = _calibrated_estimate(agent, remaining)
  if remaining_estimate is None:
    remaining_estimate = _estimate_tokens(remaining, None)

  # No-op suppression: a pipeline pass that achieved nothing (no dropped
  # messages, no stage flagged anything) emits NO event — the overflow
  # was not actually resolved by compaction and the audit trail would be
  # noise. The hook path keeps its historical always-emit behavior.
  if (
    not hook_path
    and run_id is not None
    and dropped_total == 0
    and all(s["messages"] == 0 for s in stages)
  ):
    return

  # Record the compaction run for later persistence (chunk C) — even
  # when the event was suppressed, the run report is honest history.
  # A hook-attended overflow writes no record: the hook did the work.
  if not hook_path:
    agent.context.record_compaction(
      {
        "run_id": run_id,
        "timestamp": datetime.now().isoformat(),
        "trigger_estimate": estimated,
        "max_tokens": max_tokens,
        "target": target,
        "floor_tokens": floor_tokens,
        "target_clamped": target_clamped,
        "stages": stages,
        "dropped_count": dropped_total,
        "remaining_estimate": remaining_estimate,
        "sent_count": len(remaining),
        "first_remaining": _first_remaining_summary(remaining),
      }
    )

  # Emit the audit-trail event once per overflow, including where the
  # retained history starts (first non-protected message). The reported
  # sizes describe the TRIGGER state (message_count/dropped_count stay
  # stored-based for compatibility); remaining_estimated_tokens carries
  # the truthful post-pipeline result. target_tokens keeps the ORIGINAL
  # ratio target — floor_tokens/target_clamped carry the clamp truth.
  # A hook-attended overflow reports no run identity: the hook replaced
  # messages directly (no stage flags), so run_id/stages stay unset.
  event_run_id = None if hook_path else run_id
  await emit(
    ContextOverflowEvent(
      type=EventType.CONTEXT_OVERFLOW,
      message_count=len(agent.context.get_stored_messages()),
      estimated_tokens=estimated,
      max_tokens=max_tokens,
      dropped_count=dropped_total,
      first_remaining=_first_remaining_summary(remaining),
      target_tokens=target,
      stages=stages if not hook_path else [],
      sent_count=len(remaining),
      remaining_estimated_tokens=remaining_estimate,
      run_id=event_run_id,
      floor_tokens=None if hook_path else floor_tokens,
      target_clamped=False if hook_path else target_clamped,
    ),
    agent._event_handlers,
  )


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


def _noop_hook(ctx: OverflowContext) -> list[dict[str, Any]]:
  """A hook that accepts the overflow but changes nothing.

  Forces the HOOK PATH in ``_manage_context_overflow`` (no pipeline run —
  no stages, no run_id, no compaction record) while keeping the
  always-emit behavior of a hook-attended overflow. Used by tests that
  pin zero-drop event emission.
  """
  return list(ctx["messages"])


@dataclass
class StageParams:
  """Resolved compaction stage thresholds (per-stage, from config).

  Built by :func:`_resolve_stage_params` from the real
  ``[context.compaction]`` config; the defensive getattr fallbacks keep
  stub/mock configs (which carry no ``compaction`` attribute) working with
  the framework defaults.
  """

  min_age_turns: int = 3
  min_chars: int = 2048
  force_stub_min_chars: int = 4096
  protect_first_user: int = 1
  protect_last_user: int = 1
  protect_last_assistant: int = 1
  protect_last_tool_calls: int = 1


def _resolve_compaction_config(agent: Any) -> CompactionConfig | None:
  """Return the agent's compaction config, or None when absent.

  Read defensively (``__dict__`` lookup): a MagicMock would auto-create a
  truthy Mock on attribute access, so the attribute must come from the
  object itself, not the class's auto-attr machinery.
  """
  context_cfg = agent.config.context.__dict__.get("compaction")
  return context_cfg if isinstance(context_cfg, CompactionConfig) else None


def _resolve_stage_params(agent: Any) -> StageParams:
  """Resolve per-stage thresholds from config, falling back to defaults.

  Old/stub configs without ``context.compaction`` get the framework
  defaults (identical values).
  """
  compaction = _resolve_compaction_config(agent)
  if compaction is None:
    return StageParams()
  return StageParams(
    min_age_turns=compaction.prune_tool_results.min_age_turns,
    min_chars=compaction.prune_tool_results.min_chars,
    force_stub_min_chars=compaction.force_stub_tool_results.min_chars,
    protect_first_user=compaction.cutoff.protect_first_user,
    protect_last_user=compaction.cutoff.protect_last_user,
    protect_last_assistant=compaction.cutoff.protect_last_assistant,
    protect_last_tool_calls=compaction.cutoff.protect_last_tool_calls,
  )


def _resolve_stages(agent: Any) -> list[str]:
  """Resolve the compaction stage order from config.

  Real configs carry ``context.compaction.strategies`` (validated by the
  config schema); old/stub configs without the attribute fall back to the
  framework default order.
  """
  compaction = _resolve_compaction_config(agent)
  if compaction is not None:
    return list(compaction.strategies)
  return list(DEFAULT_COMPACTION_STAGES)


def _run_compaction_pipeline(
  agent: Any,
  estimated: int,
  target: int,
) -> tuple[int, list[dict[str, Any]], str | None, int | None, bool]:
  """Run the framework-default compaction pipeline (chunk B).

  Stages run in resolved order; each stage only FLAGS stored messages
  (stored=truth) through the context manager, then the view
  (``get_context``) is re-estimated. Content-preserving stages (the
  prunes and stubs) run UNCONDITIONALLY — they never drop messages, so
  early-stopping only saves an idempotent pass while losing the per-run
  audit record. Only the destructive cutoff stage may stop early: it
  targets the EFFECTIVE target, clamped up to the protection floor —
  the calibrated estimate of the protected view rendered exactly as
  ``get_context`` renders it — so cutoff can never aim below what the
  protected content alone already weighs.

  Flagging counts are per-run: every flagging call receives this run's
  id, stored in the flag's ``pruned.run`` metadata, and each stage
  reports the count of flags created by THIS run (not cumulative —
  earlier runs' flags must not inflate this run's report).

  Returns:
    (dropped_total, stages, run_id, floor_tokens, target_clamped) —
    dropped_total is the total newly flagged this run (the event's
    stored-based ``dropped_count``), ``stages`` the per-stage impact
    list, ``run_id`` None when no stages were configured,
    ``floor_tokens`` the protected-view estimate (None when no cutoff
    stage ran or no stages at all), and ``target_clamped`` whether the
    cutoff target was raised to the floor.
  """
  stages_config = _resolve_stages(agent)
  if not stages_config:
    return 0, [], None, None, False

  run_id = uuid.uuid4().hex[:8]
  dropped_total = 0
  stages: list[dict[str, Any]] = []
  floor_tokens: int | None = None
  target_clamped = False

  for stage in stages_config:
    # Per-stage flag kind — each stage marks messages with its own kind.
    params = _resolve_stage_params(agent)
    if stage == "prune_tool_results":
      flag_kind = "stub"
      flagged = agent.context.prune_tool_results(params.min_age_turns, params.min_chars, run=run_id)
    elif stage == "prune_thinking":
      flag_kind = "thinking"
      flagged = agent.context.prune_thinking(params.min_age_turns, run=run_id)
    elif stage == "force_stub_tool_results":
      flag_kind = "stub"
      flagged = agent.context.force_stub_tool_results(params.force_stub_min_chars, run=run_id)
    elif stage == "cutoff":
      flag_kind = "dropped"
      # The floor: calibrated estimate of the PROTECTED VIEW — rendered
      # exactly as get_context renders it, so the estimate matches what
      # the backend would receive. The effective cutoff target is the
      # ratio target clamped up to that floor: cutoff can never aim
      # below what the protected content alone already weighs.
      floor_view = agent.context.protected_view(
        protect_first_user=params.protect_first_user,
        protect_last_user=params.protect_last_user,
        protect_last_assistant=params.protect_last_assistant,
        protect_last_tool_calls=params.protect_last_tool_calls,
      )
      floor_tokens = _estimate_of_view(agent, floor_view)
      effective_target = max(target, floor_tokens)
      target_clamped = floor_tokens > target
      flagged = _cutoff_to_target(agent, params, effective_target, run_id)
      dropped_total = flagged
    else:
      # Unknown stage name (config typo): skip rather than crash.
      continue

    # Per-stage impact from FRESH view re-estimates (before = the view
    # state before this stage's flags; after = now), never from
    # credited deltas. Only content that actually shrank or vanished
    # changes the estimate, so the delta is the stage's real effect.
    after = _estimate_of(agent)
    before = after + _view_delta_of_run_flags(agent, stage, flag_kind, run_id)
    stages.append(
      {
        "name": stage,
        "messages": _count_flagged_for_stage(agent, stage, flag_kind, run_id),
        "tokens": before - after,
        "estimate": after,
        "run_id": run_id,
      }
    )
  return dropped_total, stages, run_id, floor_tokens, target_clamped


def _view_delta_of_run_flags(agent: Any, stage: str, flag_kind: str, run_id: str) -> int:
  """Estimate the view-char4 delta this run's flags for a stage account for.

  Reconstructs the pre-stage view char4 from the post-stage one: for
  each message flagged by THIS stage in THIS run, the view previously
  carried the full content (or the full thinking payload) and now
  carries the stub text (or nothing). ``dropped`` flags vanish from the
  view entirely; ``stub`` tool bodies shrink to the stub text;
  ``thinking`` flags lose the thinking payload. The estimate keeps the
  per-stage ``tokens`` impact honest without storing pre-stage views.
  """
  total_chars = 0
  for message in agent.context.get_stored_messages():
    flag = message.get("pruned")
    if (
      not isinstance(flag, dict)
      or flag.get("stage") != stage
      or flag.get("kind") != flag_kind
      or flag.get("run") != run_id
    ):
      continue
    kind = flag.get("kind")
    if kind == "dropped":
      total_chars += _stored_message_chars(message)
    elif kind == "stub" and message.get("role") == "tool":
      total_chars += len(message.get("content") or "") - len(_prune_stub_text(message))
    elif kind == "thinking":
      total_chars += len(message.get("thinking") or "")
  return total_chars // 4


def _stored_message_chars(message: dict[str, Any]) -> int:
  """The char4 input of one stored message, matching _estimate_tokens."""
  total_chars = 0
  content = message.get("content") or ""
  if isinstance(content, str):
    total_chars += len(content)
  thinking = message.get("thinking") or ""
  if isinstance(thinking, str):
    total_chars += len(thinking)
  tool_calls = message.get("tool_calls")
  if isinstance(tool_calls, list):
    total_chars += len(json.dumps(tool_calls))
  return total_chars


def _count_flagged_for_stage(
  agent: Any, stage: str, flag_kind: str, run_id: str | None = None
) -> int:
  """Count stored messages flagged by THIS stage, scoped to this run.

  Counts only flags whose ``pruned.run`` equals this run's id — earlier
  compaction runs' flags (same stage, same kind) must not inflate this
  run's report. Within one run a stage never re-flags an already-flagged
  message, so the per-run count equals the number this run newly
  flagged, including when the cutoff stage flags across repeated unit
  drops. Deterministic and contract-free: the flags are the truth.
  """
  return sum(
    1
    for message in agent.context.get_stored_messages()
    if (flag := message.get("pruned")) is not None
    and flag.get("stage") == stage
    and flag.get("kind") == flag_kind
    and (run_id is None or flag.get("run") == run_id)
  )


def _cutoff_to_target(
  agent: Any, params: StageParams, target: int, run_id: str | None = None
) -> int:
  """Flag the oldest units as dropped until the VIEW estimate is under target.

  Exactly the previous selection semantics (oldest-first, protection
  windows, atomic tool-call units, contiguous to preserve pairing) — but
  the stop decision is a FRESH view re-estimate after each unit, never an
  accumulated credited delta, so a learned ratio that underestimates
  code-dense content cannot cause an overshoot. The caller passes the
  EFFECTIVE target (ratio target clamped up to the protection floor) and
  this run's id, stored on every flag for per-run reporting.

  Returns the number of messages newly flagged as dropped.
  """
  dropped_total = 0
  max_units = len(agent.context.get_stored_messages()) + 1
  for _ in range(max_units):
    if _estimate_of(agent) <= target:
      break
    dropped = agent.context.truncate_oldest_non_system(
      protect_first_user=params.protect_first_user,
      protect_last_user=params.protect_last_user,
      protect_last_assistant=params.protect_last_assistant,
      protect_last_tool_calls=params.protect_last_tool_calls,
      drop_count=1,
      run=run_id,
    )
    if dropped <= 0:
      # No more droppable messages; stop to avoid an infinite loop.
      break
    dropped_total += dropped
  return dropped_total


def _estimate_of(agent: Any) -> int:
  """Calibrated estimate of the current view, raw char/4 fallback.

  The fallback must stay content-sensitive (``last_input_tokens=None``):
  passing the stale server total would return a constant that never
  decreases as the pipeline prunes, and the cutoff loop would drain the
  whole history. The calibrated path already satisfies this — the fixed
  overhead is defined against char4 at capture time, so
  ``fixed + ratio × char4(view)`` is monotone in the view's char4.
  """
  view = agent.context.get_context()
  estimate = _calibrated_estimate(agent, view)
  if estimate is None:
    estimate = _estimate_tokens(view, None)
  return estimate


def _estimate_of_view(agent: Any, view: list[dict[str, Any]]) -> int:
  """Calibrated estimate of an arbitrary rendered view (e.g. protected_view).

  Same policy as :func:`_estimate_of` — calibrated when server usage has
  been observed, raw content-sensitive char/4 fallback otherwise — but
  for an arbitrary rendered message list (the floor computation must
  estimate the PROTECTED subset, not the whole view).
  """
  estimate = _calibrated_estimate(agent, view)
  if estimate is None:
    estimate = _estimate_tokens(view, None)
  return estimate


async def _chat_stream(agent: Any) -> AsyncIterator[ChatChunk]:
  """Start a streaming chat request using the backend.

  For backends that support ``context_management`` (Anthropic), the
  thinking-clearing directive is forwarded so the provider drops thinking
  blocks from prior turns server-side. Non-supporting backends receive
  ``None`` — for them, get_context() already omits thinking from the
  submitted view (projection-level strip; stored history keeps it).

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
    "thinking_chars": 0,
    "content_chars": 0,
  }

  async for chunk in stream:
    # Reset the idle timer on every chunk received — the LLM backend is
    # actively producing data, so the agent is not idle.
    agent._touch_activity()
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

  # Token counts come from the API; chars are the client-side raw signal
  # used for thinking-share estimation (see yoker.usage.report).
  stats["thinking_chars"] = len(thinking)
  stats["content_chars"] = len(content)

  return content, thinking, tool_calls, stats


def _repair_json(raw: str) -> str | None:
  """Attempt to repair common LLM JSON mistakes.

  Returns the repaired JSON string if a fix was applied, or ``None`` if
  the raw string could not be repaired.  Only safe, well-understood
  transformations are applied — we never guess at content.

  Currently handles:
  - Literal newlines inside JSON string values (replaced with ``\\n``).
  - Literal tab characters inside JSON string values (replaced with ``\\t``).
  - Literal carriage returns inside JSON string values (replaced with ``\\r``).
  """
  # Fast path: if there are no control chars, nothing to repair.
  if not any(c in raw for c in "\n\t\r"):
    return None

  # Walk through the string, tracking whether we are inside a JSON string.
  # When inside a string, replace literal control chars with their escape
  # sequences.  This is safe because:
  # - Inside a string, a literal newline/tab/CR is always invalid JSON.
  # - Outside a string (in the structural part), whitespace is allowed
  #   and we leave it untouched.
  result: list[str] = []
  in_string = False
  escaped = False
  changed = False

  for ch in raw:
    if in_string:
      if escaped:
        result.append(ch)
        escaped = False
        continue
      if ch == "\\":
        result.append(ch)
        escaped = True
        continue
      if ch == '"':
        result.append(ch)
        in_string = False
        continue
      if ch == "\n":
        result.append("\\n")
        changed = True
        continue
      if ch == "\t":
        result.append("\\t")
        changed = True
        continue
      if ch == "\r":
        result.append("\\r")
        changed = True
        continue
      result.append(ch)
    else:
      if ch == '"':
        in_string = True
      result.append(ch)

  if not changed:
    return None
  repaired = "".join(result)
  # Validate the repair actually produces parseable JSON.
  try:
    json.loads(repaired)
  except json.JSONDecodeError:
    return None
  return repaired


def _build_tool_call(buffer: dict[str, Any]) -> Any:
  """Build a tool call object from accumulated buffer data.

  Returns an object compatible with the existing tool execution logic,
  with .id, .function.name, and .function.arguments attributes.

  When the accumulated JSON string fails to parse, a lenient repair pass
  is attempted (fixing literal control characters inside string values).
  If that also fails, ``arguments`` is set to an empty dict and
  ``parse_error`` is set to a descriptive message so the execution
  pipeline can return a meaningful error to the LLM instead of a
  confusing "missing required argument" message.
  """

  class Function:
    def __init__(self, name: str, arguments: str | dict[str, Any]):
      self.name = name
      self.parse_error: str | None = None
      # Parse arguments if it's a JSON string, otherwise use as-is
      if isinstance(arguments, str):
        if not arguments.strip():
          self.arguments: dict[str, Any] = {}
          return
        try:
          self.arguments = json.loads(arguments)
        except json.JSONDecodeError as exc:
          # Attempt lenient repair for common LLM mistakes (literal
          # newlines/tabs/CRs inside string values).
          repaired = _repair_json(arguments)
          if repaired is not None:
            logger.warning(
              "tool_call_json_repaired",
              tool=name,
              error=str(exc),
              raw_len=len(arguments),
            )
            self.arguments = json.loads(repaired)
          else:
            logger.warning(
              "tool_call_json_parse_failed",
              tool=name,
              error=str(exc),
              raw_len=len(arguments),
              raw_preview=arguments[:200],
            )
            self.arguments = {}
            self.parse_error = (
              f"Failed to parse tool arguments as JSON: {exc.msg}. "
              f"Raw arguments (truncated): {arguments[:500]}"
            )
      else:
        self.arguments = arguments

  class ToolCall:
    def __init__(
      self, call_id: str | None, function_name: str, function_args: str | dict[str, Any]
    ):
      self.id = call_id or f"call_{id(self)}"
      self.function = Function(function_name, function_args)
      self.parse_error = self.function.parse_error

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


async def _fetch_backend_usage(agent: Any) -> dict[str, Any] | None:
  """Fetch backend API usage data when available.

  Currently only the Ollama backend exposes a ``fetch_usage`` method.
  Returns ``None`` for backends that don't provide one.
  """
  fetch = getattr(agent._backend, "fetch_usage", None)
  if not inspect.iscoroutinefunction(fetch):
    return None
  result = await fetch()
  return result if isinstance(result, dict) else None


def _context_gauge(agent: Any) -> tuple[int, int, int] | None:
  """Compute the (estimate, cap, target) context gauge for the stats line.

  Returns None when context management is unavailable (no config cap), so
  the UI falls back to the plain token-count stats line.
  """
  config = getattr(agent, "config", None)
  max_tokens = getattr(getattr(config, "context", None), "max_tokens", None)
  if not max_tokens:
    return None
  messages = agent.context.get_context()
  estimate = _calibrated_estimate(agent, messages)
  if estimate is None:
    estimate = _estimate_tokens(messages, None)
  ratio = getattr(getattr(config, "context", None), "compact_ratio", 0.5)
  target = int(max_tokens * ratio)
  return (estimate, max_tokens, target)


def _turn_end_event(
  response: str,
  tool_calls: list[Any],
  stats: dict[str, int],
  elapsed_ms: int = 0,
  usage_data: dict[str, Any] | None = None,
  agent: Any = None,
) -> TurnEndEvent:
  """Build a TurnEndEvent from consumed stream stats.

  Uses ``elapsed_ms`` (wall-clock) for ``total_duration_ms`` rather than
  the backend-reported value, which may only reflect the last chunk.

  When the agent's config enables context management (``context.max_tokens``),
  the event also carries the context gauge (calibrated estimate of the next
  call's pre-compaction view, the soft cap, and the trim target) so the UI
  can render "how full is the context before compaction hits".
  """
  limits = None
  if usage_data and "limits" in usage_data:
    limits = usage_data["limits"]
  gauge: tuple[int, int, int] | None = None
  if agent is not None:
    gauge = _context_gauge(agent)
  estimate, cap, target = gauge or (None, None, None)
  return TurnEndEvent(
    type=EventType.TURN_END,
    response=response,
    tool_calls_count=len(tool_calls),
    prompt_eval_count=stats["prompt_eval_count"],
    eval_count=stats["eval_count"],
    total_duration_ms=elapsed_ms,
    input_tokens=stats["input_tokens"],
    output_tokens=stats["output_tokens"],
    usage_limits=limits,
    context_estimate=estimate,
    context_max_tokens=cap,
    context_target_tokens=target,
  )


async def _execute_tool_calls(
  agent: Any,
  tool_calls: list[Any],
  thinking: str,
  content: str = "",
  escalation: _EscalationState | None = None,
) -> None:
  """Deduplicate and execute tool calls, emitting events.

  When an ``escalation`` state object is provided, per-call outcomes update
  it (failures increment, successes reset) and the retry-limit escalation
  note is injected when the configured threshold is reached.
  """
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
    await _execute_single_tool_call(agent, call, escalation)
    if escalation is not None:
      _maybe_inject_escalation(agent, escalation)


def _maybe_inject_escalation(agent: Any, escalation: _EscalationState) -> None:
  """Inject the escalation note when the failure threshold is reached.

  Fires once per escalation cycle: while failures continue without a
  success, the note is not re-injected. A later success resets both the
  counter and the injected flag, so the note can fire again if failures
  re-accumulate. Disabled entirely when
  ``agent.config.agent.max_consecutive_tool_failures`` is ``0``.
  """
  limit = agent.config.agent.max_consecutive_tool_failures
  if limit <= 0 or escalation.injected:
    return
  if escalation.consecutive_failures < limit:
    return

  note = _TOOL_FAILURE_ESCALATION_NOTE.format(n=limit)
  agent.context.add_message("system", note)
  escalation.injected = True
  logger.warning(
    "tool_failure_escalation",
    consecutive_failures=escalation.consecutive_failures,
    limit=limit,
  )


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


def _expected_arguments_hint(agent: Any, tool_name: str) -> str:
  """Best-effort 'Expected arguments: ...' suffix for a known tool.

  Resolves the tool spec (including the bare-name fallback used by
  ``_run_tool``) and returns a schema-driven summary of its parameters.
  Returns an empty string when the tool cannot be resolved.
  """
  spec = agent.tools.get(tool_name)
  if spec is None:
    try:
      resolved = agent.tools.resolve(tool_name)
    except ValueError:
      resolved = None
    if resolved is not None:
      spec = agent.tools.get(resolved)
  if spec is None:
    return ""
  return f" Expected arguments: {describe_expected_arguments(spec)}"


async def _execute_single_tool_call(
  agent: Any, call: Any, escalation: _EscalationState | None = None
) -> None:
  """Execute a single tool call and emit result events.

  When an ``escalation`` state object is provided, a failed call
  increments ``consecutive_failures``; a successful call resets it to 0
  (and clears the ``injected`` flag so a future failure streak can
  re-trigger the escalation note).
  """
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

  # If JSON parsing failed in _build_tool_call, return a descriptive error
  # to the LLM so it can self-correct instead of getting a confusing
  # "missing required argument" message.
  parse_error = getattr(call, "parse_error", None)
  if parse_error:
    hint = _expected_arguments_hint(agent, tool_name)
    result = f"Error: {parse_error}.{hint}"
    success = False
    tool_result = None
  else:
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

  if success and tool_result is not None and tool_result.content_metadata is not None:
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

  if escalation is not None:
    if success:
      escalation.consecutive_failures = 0
      escalation.injected = False
    else:
      escalation.consecutive_failures += 1

  agent.context.add_tool_result(
    tool_name=tool_name,
    tool_id=getattr(call, "id", tool_name),
    result=str(result),
    success=success,
    images=getattr(tool_result, "images", None) if tool_result is not None else None,
  )


def _coerce_schema_aware_args(spec: ToolSpec, tool_args: dict[str, Any]) -> dict[str, Any]:
  """Coerce string-encoded object/array arguments using the tool's schema.

  Some models/backends (notably Ollama, ollama/ollama#6155) deliver
  object/array parameters as JSON strings, e.g. ``{"env_vars":
  "{\\"TEST\\": \\"foo\\"}"}``. Tool functions then fail their
  ``isinstance(value, dict)`` checks. Conversely, a string value that
  merely *looks* like JSON is legitimate data for a string-typed
  parameter (e.g. ``write(content='{"key": "value"}')``) and must be left
  verbatim.

  This function is therefore schema-aware: it coerces a string value only
  when **both** conditions hold:

  1. the tool's parameter schema declares the parameter as ``object`` or
     ``array``, and
  2. the value parses as a JSON object/array.

  Everything else passes through unchanged. Coercions are logged as
  ``tool_argument_coerced`` for debuggability. The input dict is never
  mutated; a new dict is returned (also the cheap no-coercion fast path).
  """
  try:
    properties = spec.schema["function"]["parameters"]["properties"]
  except (KeyError, AttributeError, TypeError):
    return tool_args

  changed = False
  coerced: dict[str, Any] = {}
  for key, value in tool_args.items():
    if (
      isinstance(value, str)
      and isinstance(properties, dict)
      and properties.get(key, {}).get("type") in ("object", "array")
    ):
      stripped = value.lstrip()
      if stripped[:1] in ("{", "["):
        try:
          parsed = json.loads(stripped)
        except json.JSONDecodeError:
          coerced[key] = value
        else:
          if isinstance(parsed, (dict, list)):
            logger.info(
              "tool_argument_coerced",
              tool=spec.name,
              key=key,
              from_type=type(value).__name__,
              to_type=type(parsed).__name__,
            )
            coerced[key] = parsed
            changed = True
          else:
            # Quoted scalar (e.g. '"123"') — not an object/array; keep it.
            coerced[key] = value
      else:
        coerced[key] = value
    else:
      coerced[key] = value

  return coerced if changed else tool_args


def _expand_tilde_args(spec: ToolSpec, tool_args: dict[str, Any]) -> dict[str, Any]:
  """Expand a leading ``~`` in path-guarded string arguments.

  None of the filesystem tools expand ``~`` themselves — ``Path("~/x")``
  is a literal relative path, so e.g. ``search(path="~/...")`` failed with
  "Path not found" (and ``existence`` worse: silent ``exists=False`` for a
  real file). Expansion happens HERE, before guardrails, so the
  filesystem_paths allowlist validates the real post-expansion path —
  expansion after validation would let ``~/../...`` pass as a relative
  path and then resolve outside the allowed roots.

  Only PATH_READ/PATH_WRITE-annotated parameters are touched; other
  string parameters (and the input dict) pass through unchanged.
  """
  if not spec.guards:
    return tool_args

  expanded: dict[str, Any] = {}
  changed = False
  for key, value in tool_args.items():
    if (
      isinstance(value, str)
      and value.startswith("~")
      and spec.guards.get(key) in (GuardType.PATH_READ, GuardType.PATH_WRITE)
    ):
      try:
        expanded[key] = os.path.expanduser(value)
        if expanded[key] != value:
          changed = True
          logger.info("tool_path_expanded", tool=spec.name, key=key, value=expanded[key])
      except (OSError, ValueError, RuntimeError):
        expanded[key] = value
    else:
      expanded[key] = value

  return expanded if changed else tool_args


async def _run_tool(agent: Any, tool_name: str, tool_args: dict[str, Any]) -> tuple[str, bool, Any]:
  """Run a tool and return (result, success, raw_tool_result)."""
  spec = agent.tools.get(tool_name)
  if spec is None:
    # Bare-name fallback: models sometimes emit the simple name (e.g.
    # ``list``) instead of the namespaced schema name (``yoker__list`` /
    # ``yoker:list``). Resolve via the registry before failing, mirroring
    # ``AgentRegistry.resolve()`` — on exactly one match, dispatch it.
    try:
      resolved = agent.tools.resolve(tool_name)
    except ValueError as e:
      logger.warning("tool_ambiguous", tool=tool_name, error=str(e))
      return f"Error: {e}", False, None
    if resolved is not None:
      logger.info("tool_name_resolved", requested=tool_name, resolved=resolved)
      spec = agent.tools.get(resolved)

  if spec is None:
    logger.warning("tool_not_found", tool=tool_name)
    logger.warning(f"available: {list(agent.tools.keys())}")
    return (
      f"Error: Unknown tool '{tool_name}'. Available tools: {', '.join(list(agent.tools.keys()))}",
      False,
      None,
    )

  # Schema-aware per-value argument coercion. Some backends (notably Ollama
  # #6155) string-encode object/array parameters; conversely a string value
  # that merely looks like JSON is legitimate data for a string-typed
  # parameter (e.g. write(content='{"key": "value"}')). Coerce only when the
  # tool's schema declares the parameter as object/array AND the value parses.
  tool_args = _coerce_schema_aware_args(spec, tool_args)

  # Expand a leading ``~`` in path-guarded arguments BEFORE the approval
  # hook and guardrails: the filesystem_paths allowlist must validate the
  # real post-expansion path, and the tools then receive the expanded path.
  tool_args = _expand_tilde_args(spec, tool_args)

  # Write-blocked-path approval hook. When an approval handler is wired on the
  # agent (interactive mode), it runs BEFORE the guardrail. This gives the
  # user a chance to approve a write-blocked-path write interactively. On
  # approval, the guardrail's blocked_write_paths check is skipped for this
  # call. On denial, the guardrail blocks the operation. When no handler
  # is wired (subagents, batch mode), the guardrail's blocked_write_paths
  # check is the sole enforcement point — it always blocks.
  skip_blocks = await _maybe_approve_write_blocked(agent, spec, tool_args)

  validation = _validate_tool_args(agent, spec, tool_args, skip_blocks=skip_blocks)
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


def _build_generic_approval_prompt(
  simple_name: str, blocked_path: str, tool_args: dict[str, Any]
) -> ApprovalPrompt:
  """Build the generic approval prompt for tools without their own builder.

  Honest by construction: it names the tool, the protected path, and what
  approval means — it never fabricates a content diff depicting a change
  the tool would not make.
  """
  del tool_args
  return ApprovalPrompt(
    label=blocked_path,
    preview=(
      f"Tool '{simple_name}' targets write-protected path: {blocked_path}\n"
      "Approving skips the protected-path check for this call only."
    ),
  )


def _resolve_approval_prompt(
  spec: ToolSpec, blocked_path: str, tool_args: dict[str, Any]
) -> ApprovalPrompt:
  """Resolve the approval prompt for a write-blocked tool call.

  Uses the tool's own ``__yoker_approval__`` builder when it provides one;
  otherwise falls back to the generic framework default.
  """
  simple_name = spec.simple_name or spec.name
  provider = spec.approval_prompt
  if provider is None:
    return _build_generic_approval_prompt(simple_name, blocked_path, tool_args)
  try:
    return provider(tool_args)
  except Exception as e:
    # A broken provider must not crash the approval flow — fall back to
    # the generic prompt so the user is still asked meaningfully.
    logger.warning("approval_prompt_provider_error", tool=spec.name, error=str(e))
    return _build_generic_approval_prompt(simple_name, blocked_path, tool_args)


async def _maybe_approve_write_blocked(
  agent: Any, spec: ToolSpec, tool_args: dict[str, Any]
) -> bool:
  """Run the interactive approval flow for write-blocked-path operations.

  Runs BEFORE the guardrail so that, when an approval handler is wired
  (interactive mode), the user can approve a write-blocked-path write. On
  approval, returns ``True`` so the caller skips the guardrail's
  blocked_write_paths check for this call. On denial, logs the denial and
  returns ``False`` — the guardrail will then block the operation.
  When no handler is wired (subagents, batch mode), returns ``False``
  — the guardrail is the sole enforcement point.

  Iterates over ``spec.guards`` to find all ``WritePath``-annotated
  parameters, so tools like ``file`` (with ``source`` and ``destination``)
  and ``make`` (with ``cwd``) are covered. Any tool declaring ``WritePath``
  gets the approval flow automatically — no hardcoded tool name list.

  The prompt itself is generic: tools may provide a tool-specific builder
  via ``__yoker_approval__`` (discovered into ``ToolSpec.approval_prompt``);
  tools without one get the generic default. The framework never
  inspects tool names or operation kinds here — tools stay fully generic.

  Returns:
    ``True`` when the user approved (skip guardrail blocked_write_paths),
    ``False`` when no approval flow is active or the user denied.
  """
  from yoker.tools.annotations import GuardType

  handler = getattr(agent, "_approval_handler", None)
  if handler is None:
    return False

  guardrail = agent._guardrails.get("path_write")
  if guardrail is None:
    return False

  # Find all WritePath-annotated parameters that resolve to a write-blocked
  # path. Skip paths that are outside the allowed scope — the guardrail
  # will block them regardless, so asking for approval is misleading.
  blocked_paths: list[str] = []
  for param_name, guard_type in spec.guards.items():
    if guard_type != GuardType.PATH_WRITE:
      continue
    value = tool_args.get(param_name)
    if not isinstance(value, str):
      continue
    # Only trigger approval for paths within allowed scope AND write-blocked.
    # Out-of-scope paths are a hard security boundary — no approval possible.
    resolved = guardrail._resolve_path(value)
    if resolved is None:
      continue
    if not guardrail._is_within_allowed_paths(resolved):
      continue
    if guardrail.is_write_blocked(value):
      blocked_paths.append(value)

  if not blocked_paths:
    return False

  prompt = _resolve_approval_prompt(spec, blocked_paths[0], tool_args)
  try:
    approved = await handler(prompt.label, prompt.preview, prompt.kind)
  except Exception as e:
    logger.warning("approval_handler_error", tool=spec.name, error=str(e))
    approved = False

  if not approved:
    logger.info("write_blocked_denied", tool=spec.name, path=blocked_paths[0])
  return bool(approved)


def _describe_binding_error(spec: ToolSpec, kwargs: dict[str, Any], original: TypeError) -> str:
  """Build a schema-driven invalid-argument error message.

  Classifies the binding failure against the tool's parameter schema so the
  model can self-correct on the next attempt: names every missing required
  argument, every unknown argument, and always appends the full list of
  expected arguments. Falls back to the original TypeError message for
  failure classes not covered by the schema (e.g. duplicate values).
  """
  expected = describe_expected_arguments(spec)
  prefix = f"Invalid arguments for tool '{spec.name}'"

  try:
    params = spec.schema["function"]["parameters"]["properties"]
    required = set(spec.schema["function"]["parameters"].get("required", []))
  except (KeyError, AttributeError, TypeError):
    return f"{prefix}: {original}. Expected arguments: {expected}"

  known = set(params) - {"post_filter"}
  provided = set(kwargs) - {"post_filter"}

  missing = sorted(required - provided)
  unknown = sorted(provided - known)

  problems: list[str] = []
  if missing:
    problems.append(f"missing required argument(s): {', '.join(missing)}")
  if unknown:
    problems.append(f"unknown argument(s): {', '.join(unknown)}")
  if not problems:
    # Not a missing/unknown failure (e.g. multiple values for a parameter) —
    # keep the original TypeError detail.
    problems.append(str(original))

  return f"{prefix}: {'; '.join(problems)}. Expected arguments: {expected}"


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
    kwargs["ctx"] = _build_tool_context(agent, spec)

  # Bind arguments
  try:
    bound = sig.bind(**kwargs)
    bound.apply_defaults()
  except TypeError as e:
    return ToolResult(
      success=False,
      error=f"Invalid tool arguments: {_describe_binding_error(spec, kwargs, e)}",
    )

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

  Filters ``result``, ``error``, and ``content_metadata.content`` fields:

  - **String results**: filtered line-by-line directly.
  - **Dict results** (e.g. from the make tool): each string value within the
    dict is filtered line-by-line. This is necessary because ``str(dict)``
    or ``json.dumps(dict)`` produces a single-line repr with escaped newlines
    for embedded string values, making line-based filtering useless. By
    filtering individual string values (e.g. ``stdout``, ``stderr``), the
    line structure of the original output is preserved.
  - **Error field**: filtered line-by-line if it's a string (failure case).
  - **content_metadata.content**: when it mirrors ``result.result`` (same
    string), the already-filtered result is reused — no duplicate work.
    When it differs (e.g. write tool: result is a summary, content is a
    diff), it is filtered separately. This ensures the UI display matches
    what the LLM receives without filtering the same content twice.

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
  new_metadata = result.content_metadata

  # Filter the result field.
  if isinstance(new_result, str) and new_result:
    new_result, changed = _filter_lines(new_result, regex, pattern)
  elif isinstance(new_result, dict) and new_result:
    new_result, changed = _filter_dict_values(new_result, regex, pattern)
  else:
    changed = False

  # Filter the error field if it's a string (failure case — e.g. make tool
  # puts combined stdout+stderr in error on failure). Short error messages
  # (≤ 3 lines) are tool-level diagnostics (e.g. "Agent not found: X.
  # Available agents: ...") that the LLM must see in full — skip filtering
  # to avoid stripping them to an empty string.
  if isinstance(new_error, str) and new_error:
    error_lines = len(new_error.splitlines())
    if error_lines > 3:
      new_error, error_changed = _filter_lines(new_error, regex, pattern)
      changed = changed or error_changed

  # Sync content_metadata.content with the filtered result.
  # When result.result is a string and content_metadata.content is the same
  # content (e.g. github workflow_logs, read tool), reuse the already-filtered
  # string instead of filtering again. When they differ (e.g. write tool
  # where result is a summary but content is a diff), filter content separately.
  if new_metadata is not None:
    md_content = new_metadata.get("content")
    if isinstance(md_content, str) and md_content:
      if isinstance(new_result, str) and md_content == result.result:
        # Same content — reuse the filtered result, no duplicate work.
        new_metadata = {**new_metadata, "content": new_result}
      else:
        md_content, md_changed = _filter_lines(md_content, regex, pattern)
        if md_changed:
          new_metadata = {**new_metadata, "content": md_content}

  if not changed:
    return result

  return ToolResult(
    success=result.success,
    result=new_result,
    error=new_error,
    content_metadata=new_metadata,
    images=result.images,
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
  if kept == 0:
    # #60: a zero-match filter is usually a pitfall (substring matching or the
    # line-number prefix on sliced read output), not a signal the content is
    # empty — give the LLM the two known causes so it can retry.
    filtered += (
      " Hint: matching is substring-based ('passed' also matches 'bypassed'; "
      "'.' matches every line). On sliced read output (offset/limit), lines "
      "carry a '  12\\t' line-number prefix — use non-anchored substrings, or "
      "'^\\s*\\d+\\t' to account for it."
    )
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

  T6 (agent feedback): short structural fields — ``verdict``, ``outcome``,
  ``passed_leg``, ``failed_leg`` — are exempt from filtering. They carry
  the pass/fail verdict, which is exactly what an aggressive error-oriented
  post_filter would otherwise strip (leaving the LLM unable to tell pass
  from fail in a filtered make run).

  Returns (new_dict, changed). If no values were filtered, returns the
  original dict unchanged with changed=False.
  """
  changed = False
  new_data: dict[str, Any] = {}
  for key, value in data.items():
    if key in _DICT_FILTER_EXEMPT_FIELDS:
      new_data[key] = value
    elif isinstance(value, str) and value:
      filtered, val_changed = _filter_lines(value, regex, pattern)
      if val_changed:
        new_data[key] = filtered
        changed = True
      else:
        new_data[key] = value
    else:
      new_data[key] = value
  return new_data, changed


# T6 (agent feedback): dict result fields exempt from post_filter. Short
# structural fields that carry the pass/fail verdict survive aggressive
# error-oriented filters (which would otherwise strip every string value).
_DICT_FILTER_EXEMPT_FIELDS: frozenset[str] = frozenset(
  {"verdict", "outcome", "passed_leg", "failed_leg"}
)


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
    f"Good patterns: 'FAILED|Traceback|assert|short test summary|ERROR collecting|ERRORS' "
    f"for tests, 'class |def |import ' for code structure, "
    f"'CalledProcessError|exit code|##[error]' for CI."
  )
  if "\n" not in field_val.strip():
    error_msg += (
      " Note: single-line output (e.g. JSON) cannot be narrowed by post_filter — "
      "reduce limit/state or request fewer fields instead."
    )
  return ToolResult(success=False, error=error_msg)


def _validate_tool_args(
  agent: Any, spec: ToolSpec, tool_args: dict[str, Any], *, skip_blocks: bool = False
) -> ValidationResult:
  """Validate tool arguments using schema-driven guardrails.

  Passes ``spec.simple_name`` (not the namespaced ``spec.name``) to the
  guardrail so tool-name checks inside the guardrail match against simple
  names (e.g. ``"write"``, not ``"yoker:write"``).

  When ``skip_blocks`` is True (user approved interactively), the
  guardrail's blocked_write_paths check is skipped for this call. The
  guardrail is responsible for honoring this flag.

  After the generic guardrail passes, tool-specific validators (file size,
  content size, diff size, directory depth) are run. These live alongside
  the tool definition and are discovered via ``__yoker_validators__``.
  """
  for param_name, guard_type in spec.guards.items():
    value = tool_args.get(param_name)
    if value is None:
      continue

    guardrail: Guardrail | None = agent._guardrails.get(guard_type.value)
    if not guardrail:
      continue

    validation = guardrail.validate(spec.simple_name or spec.name, value, skip_blocks=skip_blocks)
    if not validation.valid:
      return validation

  # Run tool-specific validators (operational constraints)
  if spec.validators:
    base_name = spec.simple_name or spec.name
    tool_config = _resolve_tool_config(agent, base_name, spec.namespace)
    for validator in spec.validators:
      validation = validator(tool_args, tool_config)
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


def _resolve_tool_config(agent: Any, base_name: str, namespace: str | None = None) -> ToolConfig:
  """Resolve a tool's ToolConfig: built-in flat lookup first, then plugin.

  Built-ins keep the flat ``config.tools.<name>`` mapping. Plugin tools
  always resolve to the plugin's TOP-LEVEL config instance
  (``config.tools.<plugin-package>``) — the plugin owns its hierarchy and
  navigates it inside the tool; the harness imposes no field-naming
  convention. Plugin tools previously crashed here with AttributeError
  (closed dataclass, ``__getitem__`` = getattr). Returns a default
  ToolConfig when neither path matches — never raises.
  """
  tools_config = agent.config.tools
  if hasattr(tools_config, base_name):
    config = getattr(tools_config, base_name)
    if isinstance(config, ToolConfig):
      return config
  # Plugin tool: the plugin's field on the augmented ToolsConfig is the
  # tool's config — the whole plugin-level instance, however the plugin
  # structured its internals. Field name == plugin namespace (package name).
  if namespace is not None and hasattr(tools_config, namespace):
    candidate = getattr(tools_config, namespace)
    if isinstance(candidate, ToolConfig) and not isinstance(candidate, ToolsConfig):
      return candidate
  return ToolConfig()


def _build_tool_context(agent: Any, spec: ToolSpec) -> ToolContext:
  """Build a ToolContext for the given tool.

  Args:
    agent: The agent instance.
    spec: The ToolSpec for the tool being executed.

  Returns:
    ToolContext with tool-specific config, shared config, and backends.
  """
  # Use the simple name (without namespace prefix) for config lookup.
  base_name = spec.simple_name or spec.name

  # Get tool-specific config from config.tools: plugin tools resolve to the
  # plugin's top-level config instance (see _resolve_tool_config).
  tool_config = _resolve_tool_config(agent, base_name, spec.namespace)

  # Get shared config
  shared_config = agent.config.tools_shared

  # Get backends dict (may be empty dict if backends not yet set up)
  backends = getattr(agent, "_tool_backends", {})

  # The Agent is Session-agnostic and does not carry a Session reference.
  # Session-aware tools (send_message, agent) capture the Session in their
  # closures at injection time, so ToolContext.session is left as None.
  # Compile blocked_path_patterns from the read guardrail for traversal
  # tools (search/list) to enforce internally on every file they touch.
  blocked_path_patterns: list[Any] = []
  read_guardrail = agent._guardrails.get("path_read")
  if read_guardrail is not None:
    blocked_path_patterns = list(getattr(read_guardrail, "_blocked_path_patterns", []))

  return ToolContext(
    config=tool_config,
    shared=shared_config,
    backends=backends,
    session=None,
    approval_handler=getattr(agent, "_approval_handler", None),
    blocked_path_patterns=blocked_path_patterns,
  )
