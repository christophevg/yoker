"""Health check endpoint for webapp.

Provides a simple health check endpoint that returns server status.
"""

from quart import Blueprint, Response, jsonify
from quart_cors import cors_exempt

health_bp = Blueprint("health", __name__)


@health_bp.route("/health", methods=["GET"])
@cors_exempt
async def health_check() -> Response:
  """Health check endpoint.

  Returns:
    JSON response with status and version.
  """
  # Get version from package
  try:
    from yoker import __version__

    version = __version__
  except ImportError:
    version = "unknown"

  return jsonify({"status": "healthy", "version": version})