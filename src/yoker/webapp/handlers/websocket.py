"""WebSocket event handler for bridging Agent events to WebSocket clients.

Implements EventCallback interface to receive events from Agent
and send them to connected WebSocket clients.
"""

import asyncio
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from yoker.events.types import Event
from yoker.events.recorder import serialize_event
from yoker.logging import get_logger

logger = get_logger(__name__)

if TYPE_CHECKING:
  from quart import Websocket


@dataclass
class WebSocketMessage:
  """WebSocket message schema.

  Attributes:
    type: Message type (must be "message").
    content: Message content.
  """

  type: Literal["message"]
  content: str

  @classmethod
  def from_json(cls, data: str, max_content_length: int = 100_000) -> "WebSocketMessage":
    """Parse and validate WebSocket message from JSON.

    Args:
      data: JSON string to parse.
      max_content_length: Maximum content length (DoS protection).

    Returns:
      Parsed WebSocketMessage.

    Raises:
      ValidationError: If message is invalid.

    Security Notes:
      - Validates message schema (type and content fields)
      - Checks content length for DoS protection
      - Rejects invalid types
    """
    try:
      obj = json.loads(data)
    except json.JSONDecodeError as e:
      logger.warning("websocket_invalid_json", extra={"error": str(e)})
      raise ValidationError(f"Invalid JSON: {e}")

    # Check required fields
    if "type" not in obj:
      logger.warning("websocket_missing_type")
      raise ValidationError("Missing required field: type")

    if "content" not in obj:
      logger.warning("websocket_missing_content")
      raise ValidationError("Missing required field: content")

    # Validate type
    if obj["type"] != "message":
      logger.warning("websocket_invalid_type", extra={"type": obj["type"]})
      raise ValidationError(f"Invalid message type: {obj['type']}")

    # Validate content
    content = obj["content"]

    if not isinstance(content, str):
      logger.warning("websocket_content_not_string")
      raise ValidationError("Content must be a string")

    if len(content) > max_content_length:
      logger.warning(
        "websocket_content_too_large",
        extra={"length": len(content), "max_length": max_content_length},
      )
      raise ValidationError(
        f"Content too large ({len(content)} chars, max {max_content_length})"
      )

    return cls(type="message", content=content)

  def to_json(self) -> str:
    """Serialize message to JSON.

    Returns:
      JSON string.
    """
    return json.dumps({"type": self.type, "content": self.content})


class ValidationError(Exception):
  """Raised when WebSocket message validation fails."""

  pass


class WebSocketEventHandler:
  """Handles events by sending them to WebSocket clients.

  Implements the EventCallback interface to receive events from Agent
  and send them to connected WebSocket clients in real-time.
  """

  def __init__(self, websocket: "Websocket") -> None:
    """Initialize WebSocket event handler.

    Args:
      websocket: Quart WebSocket connection.
    """
    self.websocket = websocket
    self._connected = True

  def __call__(self, event: Event) -> None:
    """Handle an event by sending it to the WebSocket.

    Args:
      event: Event to handle.
    """
    if not self._connected:
      logger.warning("websocket_not_connected")
      return

    try:
      # Serialize event to JSON
      event_dict = serialize_event(event)
      event_json = json.dumps(event_dict)

      # Send to WebSocket (sync method, Quart handles async internally)
      # Note: In Quart, we need to use the async send method
      # This is called from Agent context which may not be async
      # So we queue the message instead
      task = asyncio.create_task(self._send_event(event_json))
      task.add_done_callback(self._handle_task_exception)

    except Exception as e:
      logger.error("websocket_send_error", extra={"error": str(e)})
      self._connected = False

  def _handle_task_exception(self, task: asyncio.Task[None]) -> None:
    """Handle exceptions from async send task.

    Args:
      task: Completed async task.
    """
    try:
      task.result()
    except Exception as e:
      logger.error("websocket_send_failed", extra={"error": str(e)})
      self._connected = False

  async def _send_event(self, event_json: str) -> None:
    """Send event to WebSocket asynchronously.

    Args:
      event_json: JSON string to send.
    """
    try:
      await self.websocket.send(event_json)
    except Exception as e:
      logger.error("websocket_send_failed", extra={"error": str(e)})
      self._connected = False

  def connect(self) -> None:
    """Mark WebSocket as connected."""
    self._connected = True
    logger.info("websocket_handler_connected")

  def disconnect(self) -> None:
    """Mark WebSocket as disconnected."""
    self._connected = False
    logger.info("websocket_handler_disconnected")

  @property
  def is_connected(self) -> bool:
    """Check if WebSocket is connected.

    Returns:
      True if connected, False otherwise.
    """
    return self._connected