"""UIBridge event dispatcher.

This module provides the bridge between agent events and the UIHandler
protocol, dispatching events to appropriate UI methods.

The bridge handles both wrapped (:class:`yoker.events.SessionEvent`) and
unwrapped (bare :class:`Event`) events. When a ``SessionEvent`` envelope is
received, the inner ``event`` is dispatched unchanged and the envelope's
``agent_id`` is available for tagging/display. Session-level events
(``AGENT_SPAWNED``, ``AGENT_FINISHED``) are dispatched to the optional
``UIHandler.agent_spawned`` / ``agent_finished`` methods, guarded by
``hasattr`` so handlers that do not implement them are unaffected.
"""

from __future__ import annotations

from yoker.events.session_event import SessionEvent
from yoker.events.types import (
  Event,
  EventType,
)
from yoker.ui.handler import UIHandler


class UIBridge:
  """Bridge between agent events and UIHandler.

  Receives events from Agent (or wrapped in SessionEvent from a Session)
  and calls appropriate UIHandler methods. This allows the agent to remain
  independent of UI implementation details.
  """

  def __init__(self, ui_handler: UIHandler):
    """Initialize bridge with UI handler.

    Args:
      ui_handler: The UI handler to dispatch events to.
    """
    self.ui = ui_handler
    # The agent_id from the most recent SessionEvent envelope, or None when
    # the bridge is on the single-agent (bare event) path. Available for
    # tagging/display by UI handlers that opt in.
    self._current_agent_id: str | None = None

  async def __call__(self, event: Event | SessionEvent) -> None:
    """Handle event by dispatching to UI handler.

    ``SessionEvent`` envelopes are unpacked: the inner ``event`` is
    dispatched to the existing UIHandler methods unchanged, and the
    envelope's ``agent_id`` is recorded on the bridge for any subsequent
    tagging. Bare events (single-agent path) are dispatched as today.

    SESSION_START and SESSION_END are no-ops here — the UI's ``start`` /
    ``shutdown`` are called directly by the caller. AGENT_SPAWNED and
    AGENT_FINISHED dispatch to the optional ``agent_spawned`` /
    ``agent_finished`` UIHandler methods when present.

    Args:
      event: Event to handle (bare ``Event`` or ``SessionEvent`` envelope).
    """
    if isinstance(event, SessionEvent):
      inner = event.event
      self._current_agent_id = event.agent_id
      await self._dispatch(inner)
      return
    self._current_agent_id = None
    await self._dispatch(event)

  async def _dispatch(self, event: Event) -> None:
    """Dispatch a bare (unwrapped) event to the UI handler."""
    match event.type:
      case EventType.TURN_START:
        # Internal state - UI doesn't need notification
        pass
      case EventType.TURN_END:
        self._handle_turn_end(event)
      case EventType.THINKING_START:
        self.ui.start_thinking_stream()
      case EventType.THINKING_CHUNK:
        self.ui.stream_thinking(event.text)  # type: ignore[attr-defined]
      case EventType.THINKING_END:
        self.ui.end_thinking_stream(event.total_length)  # type: ignore[attr-defined]
      case EventType.CONTENT_START:
        self.ui.start_content_stream()
      case EventType.CONTENT_CHUNK:
        # Use getattr to safely access content_type with fallback
        content_type = getattr(event, "content_type", "text/plain")
        self.ui.stream_content(event.text, content_type)  # type: ignore[attr-defined]
      case EventType.CONTENT_END:
        self.ui.end_content_stream(event.total_length)  # type: ignore[attr-defined]
      case EventType.TOOL_CALL:
        self.ui.output_tool_call(
          event.tool_name,  # type: ignore[attr-defined]
          event.arguments,  # type: ignore[attr-defined]
        )
      case EventType.TOOL_RESULT:
        self.ui.output_tool_result(
          event.tool_name,  # type: ignore[attr-defined]
          event.success,  # type: ignore[attr-defined]
          event.result,  # type: ignore[attr-defined]
        )
      case EventType.TOOL_CONTENT:
        self.ui.output_tool_content(
          event.tool_name,  # type: ignore[attr-defined]
          event.operation,  # type: ignore[attr-defined]
          event.path,  # type: ignore[attr-defined]
          event.content,  # type: ignore[attr-defined]
          event.content_type,  # type: ignore[attr-defined]
          event.metadata,  # type: ignore[attr-defined]
        )
      case EventType.COMMAND:
        self.ui.output_command_result(event.result)  # type: ignore[attr-defined]
      case EventType.AGENT_SPAWNED:
        self._maybe_agent_lifecycle(event, "agent_spawned")
      case EventType.AGENT_FINISHED:
        self._maybe_agent_lifecycle(event, "agent_finished")
      case EventType.SESSION_START | EventType.SESSION_END | EventType.AGENT_MESSAGE:
        # No UI action for these session-level events.
        pass
      case _:
        # Unknown event type - ignore
        pass

  def _handle_turn_end(self, event: Event) -> None:
    """Handle turn end event by outputting stats.

    Args:
      event: TurnEndEvent with statistics.
    """
    self.ui.output_stats(
      duration_ms=event.total_duration_ms,  # type: ignore[attr-defined]
      prompt_tokens=event.prompt_eval_count,  # type: ignore[attr-defined]
      eval_tokens=event.eval_count,  # type: ignore[attr-defined]
    )

  def _maybe_agent_lifecycle(self, event: Event, method: str) -> None:
    """Dispatch an agent lifecycle event to an optional UIHandler method.

    ``agent_spawned`` / ``agent_finished`` are optional protocol methods.
    Handlers that do not implement them (e.g. ``BatchUIHandler``) are
    silently skipped — the call is guarded by ``hasattr`` so no
    ``AttributeError`` is raised.

    Args:
      event: The lifecycle event (``AgentSpawnedEvent`` / ``AgentFinishedEvent``).
      method: The optional UIHandler method name (``"agent_spawned"`` or
        ``"agent_finished"``).
    """
    handler = getattr(self.ui, method, None)
    if handler is None:
      return
    # Both events carry ``agent_id``; pass it as the ``name`` argument.
    agent_id = getattr(event, "agent_id", "")
    handler(agent_id)
