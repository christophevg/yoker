"""Context validation functions.

Provides validation for session IDs and storage paths with security controls.
"""

import re
import secrets
from pathlib import Path

from yoker.exceptions import ValidationError

# Session ID format: URL-safe base64 characters
SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")

# Forbidden path prefixes to prevent access to system directories
# Be specific to avoid blocking legitimate temp directories
FORBIDDEN_PATH_PREFIXES = (
  "/etc",
  "/sys",
  "/proc",
  "/root",
  "/var/log",
  "/var/db",
  "/var/lib",
  "/usr",
  "/bin",
  "/sbin",
  "/lib",
  # macOS symlink targets (be specific, /private/var/folders is temp)
  "/private/etc",
  "/private/var/log",
  "/private/var/db",
  "/private/var/lib",
)

# Maximum session ID length
MAX_SESSION_ID_LENGTH = 128

# Minimum session ID length
MIN_SESSION_ID_LENGTH = 8


def validate_session_id(session_id: str, path: str = "session_id") -> str:
  """Validate and optionally generate a session ID.

  Args:
    session_id: The session ID to validate, or "auto" to generate.
    path: Configuration path for error messages.

  Returns:
    Validated session ID, or newly generated ID if "auto".

  Raises:
    ValidationError: If session ID is invalid.
  """
  # Auto-generate session ID
  if session_id == "auto":
    return secrets.token_urlsafe(16)

  # Check length
  if len(session_id) < MIN_SESSION_ID_LENGTH:
    raise ValidationError(
      path,
      session_id,
      f"must be at least {MIN_SESSION_ID_LENGTH} characters",
    )
  if len(session_id) > MAX_SESSION_ID_LENGTH:
    raise ValidationError(
      path,
      session_id,
      f"must be at most {MAX_SESSION_ID_LENGTH} characters",
    )

  # Prevent path traversal attempts (check before regex)
  if ".." in session_id:
    raise ValidationError(path, session_id, "must not contain path traversal")

  # Prevent hidden files (check before regex)
  if session_id.startswith("."):
    raise ValidationError(path, session_id, "must not start with a dot")

  # Check format (alphanumeric, dash, underscore)
  if not SESSION_ID_PATTERN.match(session_id):
    raise ValidationError(
      path,
      session_id,
      "must contain only alphanumeric characters, dash, or underscore",
    )

  return session_id


def validate_storage_path(storage_path: Path, path: str = "storage_path") -> Path:
  """Validate and resolve a storage path.

  Args:
    storage_path: The storage path to validate.
    path: Configuration path for error messages.

  Returns:
    Resolved absolute storage path.

  Raises:
    ValidationError: If storage path is invalid or forbidden.
  """
  # Resolve to absolute path
  resolved = storage_path.resolve()

  # Check for forbidden prefixes
  resolved_str = str(resolved)
  for forbidden in FORBIDDEN_PATH_PREFIXES:
    if resolved_str.startswith(forbidden):
      raise ValidationError(
        path,
        storage_path,
        f"must not be under {forbidden}",
      )

  return resolved


def is_safe_path(base_path: Path, target_path: Path) -> bool:
  """Check if target path is safely under base path.

  Args:
    base_path: The base directory path.
    target_path: The target path to check.

  Returns:
    True if target is safely under base path, False otherwise.
  """
  try:
    # Resolve both paths
    base_resolved = base_path.resolve()
    target_resolved = target_path.resolve()

    # Check if target is under base
    target_resolved.relative_to(base_resolved)
    return True
  except ValueError:
    return False


__all__ = [
  "validate_session_id",
  "validate_storage_path",
  "is_safe_path",
]
