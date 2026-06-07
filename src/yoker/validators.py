"""Validation helper functions for configuration.

These functions validate configuration values and raise ValidationError
for invalid inputs.
"""

import logging
import re
from pathlib import Path
from urllib.parse import urlparse

from yoker.exceptions import ValidationError

logger = logging.getLogger(__name__)


def validate_url(value: str, path: str) -> None:
  """Validate that a value is a valid URL.

  Args:
    value: The value to validate.
    path: Configuration path for error messages.

  Raises:
    ValidationError: If the value is not a valid URL.
  """
  try:
    result = urlparse(value)
    if not result.scheme or not result.netloc:
      raise ValidationError(path, value, "must be a valid URL with scheme and host")
  except Exception as e:
    raise ValidationError(path, value, f"must be a valid URL: {e}") from None


def validate_non_empty_string(value: str, path: str) -> None:
  """Validate that a value is a non-empty string.

  Args:
    value: The value to validate.
    path: Configuration path for error messages.

  Raises:
    ValidationError: If the value is empty.
  """
  if not value or not value.strip():
    raise ValidationError(path, value, "must be a non-empty string")


def validate_positive_int(value: int, path: str) -> None:
  """Validate that a value is a positive integer.

  Args:
    value: The value to validate.
    path: Configuration path for error messages.

  Raises:
    ValidationError: If the value is not positive.
  """
  if value <= 0:
    raise ValidationError(path, value, "must be a positive integer")


def validate_non_negative_int(value: int, path: str) -> None:
  """Validate that a value is a non-negative integer.

  Args:
    value: The value to validate.
    path: Configuration path for error messages.

  Raises:
    ValidationError: If the value is negative.
  """
  if value < 0:
    raise ValidationError(path, value, "must be a non-negative integer")


def validate_choice(
  value: str,
  path: str,
  choices: tuple[str, ...],
) -> None:
  """Validate that a value is one of the allowed choices.

  Args:
    value: The value to validate.
    path: Configuration path for error messages.
    choices: Allowed values.

  Raises:
    ValidationError: If the value is not in choices.
  """
  if value not in choices:
    raise ValidationError(path, value, f"must be one of {choices}")


def validate_log_level(value: str, path: str) -> None:
  """Validate that a log level is valid.

  Args:
    value: The log level to validate.
    path: Configuration path for error messages.

  Raises:
    ValidationError: If the log level is invalid.
  """
  valid_levels = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
  if value.upper() not in valid_levels:
    raise ValidationError(path, value, f"must be one of {valid_levels}")


def validate_regex_patterns(
  patterns: tuple[str, ...],
  path: str,
) -> None:
  """Validate that regex patterns are valid.

  Args:
    patterns: The regex patterns to validate.
    path: Configuration path for error messages.

  Raises:
    ValidationError: If any pattern is invalid.
  """
  for pattern in patterns:
    try:
      re.compile(pattern)
    except re.error as e:
      raise ValidationError(path, pattern, f"invalid regex pattern: {e}") from None


def validate_directory_exists(value: str, path: str) -> None:
  """Validate that a directory exists (warning only).

  Args:
    value: The directory path to validate.
    path: Configuration path for error messages.
  """
  dir_path = Path(value)
  if not dir_path.exists():
    logger.warning(f"Configuration warning at '{path}': Directory does not exist: {value}")


__all__ = [
  "validate_url",
  "validate_non_empty_string",
  "validate_positive_int",
  "validate_non_negative_int",
  "validate_choice",
  "validate_log_level",
  "validate_regex_patterns",
  "validate_directory_exists",
]
