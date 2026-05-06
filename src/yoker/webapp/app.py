"""Quart application factory for Yoker webapp.

Creates and configures Quart application with:
- WebSocket support for real-time streaming
- CORS configuration for frontend integration
- Session management with limits and expiration
- Security middleware (origin validation, authentication hooks)
"""

from typing import TYPE_CHECKING

from quart import Quart

from yoker.config import Config
from yoker.logging import get_logger
from yoker.webapp.middleware.cors import configure_cors
from yoker.webapp.session.manager import SessionManager

if TYPE_CHECKING:
  pass

logger = get_logger(__name__)


def create_app(config: Config | None = None) -> Quart:
  """Create and configure Quart application.

  Args:
    config: Configuration object (loads default if not provided).

  Returns:
    Configured Quart application.
  """
  # Create Quart app
  app = Quart(__name__)

  # Load configuration
  if config is None:
    from yoker.config import load_config_with_defaults

    config = load_config_with_defaults()

  # Store config in app context
  app.config["YOKER_CONFIG"] = config

  # Configure CORS
  configure_cors(app, config.webapp.cors_origins)

  # Create session manager
  session_manager = SessionManager(
    max_sessions=config.webapp.max_sessions,
    session_timeout_seconds=config.webapp.session_timeout_seconds,
  )
  app.config["SESSION_MANAGER"] = session_manager

  # Register blueprints
  from yoker.webapp.routes.health import health_bp
  from yoker.webapp.routes.index import index_bp
  from yoker.webapp.routes.chat import chat_bp

  app.register_blueprint(index_bp)
  app.register_blueprint(health_bp)
  app.register_blueprint(chat_bp)

  logger.info(
    "webapp_initialized",
    extra={
      "host": config.webapp.host,
      "port": config.webapp.port,
      "debug": config.webapp.debug,
      "cors_origins": list(config.webapp.cors_origins),
    },
  )

  return app