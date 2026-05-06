"""WebSocket chat endpoint for real-time streaming.

Provides WebSocket endpoint for real-time chat with:
- Origin validation (CSWSH protection)
- Authentication hooks (MVP allows all)
- Session management with limits
- Message schema validation
- Event streaming to client
"""

import json
from typing import TYPE_CHECKING

from quart import Blueprint, request

from yoker.logging import get_logger
from yoker.webapp.middleware.auth import check_authentication, login_required
from yoker.webapp.middleware.cors import validate_websocket_origin
from yoker.webapp.handlers.websocket import WebSocketMessage, ValidationError

if TYPE_CHECKING:
  pass

logger = get_logger(__name__)

chat_bp = Blueprint("chat", __name__)


@chat_bp.websocket("/ws/chat")
@login_required
async def chat_websocket() -> None:
  """WebSocket endpoint for real-time chat.

  Protocol:
    Client -> Server: {"type": "message", "content": "..."}
    Server -> Client: Event objects (serialized to JSON)

  Security:
    - Origin validation (CSWSH protection)
    - Authentication check (MVP allows all)
    - Session management (limits and expiration)
    - Message validation (schema and size)
  """
  from quart import current_app, websocket
  from yoker.config import Config

  # Get configuration
  config: Config = current_app.config["YOKER_CONFIG"]

  # Validate WebSocket origin (CSWSH protection)
  origin = websocket.origin
  if not validate_websocket_origin(origin, config.webapp.cors_origins):
    logger.warning("websocket_origin_rejected", extra={"origin": origin})
    await websocket.close(403, reason="Origin not allowed")
    return

  # Get session manager
  session_manager = current_app.config["SESSION_MANAGER"]

  # Create session
  try:
    session_id = await session_manager.create_session()
    logger.info("websocket_session_created", extra={"session_id": session_id})
  except Exception as e:
    logger.error("websocket_session_error", extra={"error": str(e)})
    await websocket.close(503, reason="Session limit reached")
    return

  try:
    # Message handling loop
    while True:
      # Receive message from client
      data = await websocket.receive()

      # Validate message
      try:
        message = WebSocketMessage.from_json(
          data,
          max_content_length=config.webapp.max_message_length,
        )
      except ValidationError as e:
        logger.warning("websocket_message_invalid", extra={"error": str(e)})
        error_msg = {"type": "error", "message": str(e)}
        await websocket.send(json.dumps(error_msg))
        continue

      # Update session activity
      session = await session_manager.get_session(session_id)
      if session:
        session.update_activity()

      # Process message (MVP: echo back for now)
      # In production, this would create Agent and process message
      response = {"type": "echo", "content": message.content}
      await websocket.send(json.dumps(response))

  except Exception as e:
    logger.error("websocket_error", extra={"session_id": session_id, "error": str(e)})

  finally:
    # Clean up session
    await session_manager.remove_session(session_id)
    logger.info("websocket_session_closed", extra={"session_id": session_id})