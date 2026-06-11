"""UIBridge event dispatcher.

This module provides the bridge between the EventHandler protocol and
the UIHandler protocol, dispatching events to appropriate UI methods.
"""

from yoker.events.types import Event, EventType
from yoker.ui.handler import UIHandler


class UIBridge:
  """Bridge between EventHandler protocol and UIHandler.

  Receives events from Agent and calls appropriate UIHandler methods.
  This allows the agent to remain independent of UI implementation details.
  """

  def __init__(self, ui_handler: UIHandler):
    """Initialize bridge with UI handler.

    Args:
      ui_handler: The UI handler to dispatch events to.
    """
    self.ui = ui_handler

  async def __call__(self, event: Event) -> None:
    """Handle event by dispatching to UI handler.

    Note: SESSION_START and SESSION_END events are removed from Agent.
    UI calls start() and shutdown() directly, not via events.

    Args:
      event: Event to handle.
    """
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
      case EventType.ERROR:
        # Convert to exception for UI
        error_type = event.error_type  # type: ignore[attr-defined]
        message = event.message  # type: ignore[attr-defined]
        self.ui.output_error(Exception(f"{error_type}: {message}"))
      case EventType.COMMAND:
        self.ui.output_command_result(event.result)  # type: ignore[attr-defined]
      case EventType.SESSION_START | EventType.SESSION_END:
        # These should not be emitted anymore, but handle gracefully
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

