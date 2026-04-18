"""Configuration validation for Yoker.

Validates configuration values against schema requirements.
"""

import logging
import re
from pathlib import Path
from urllib.parse import urlparse

from yoker.config.schema import Config
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


def validate_directory_exists(value: str, path: str, warn_only: bool = True) -> None:
  """Validate that a directory exists.

  Args:
    value: The directory path to validate.
    path: Configuration path for error messages.
    warn_only: If True, log warning instead of raising error.

  Raises:
    ValidationError: If directory doesn't exist and warn_only is False.
  """
  dir_path = Path(value)
  if not dir_path.exists():
    msg = f"Directory does not exist: {value}"
    if warn_only:
      logger.warning(f"Configuration warning at '{path}': {msg}")
    else:
      raise ValidationError(path, value, msg)


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


def validate_config(config: Config) -> list[str]:
  """Validate a configuration object.

  Performs all validation checks and returns a list of warnings.

  Args:
    config: Configuration to validate.

  Returns:
    List of warning messages.

  Raises:
    ValidationError: If any critical validation fails.
  """
  warnings: list[str] = []

  # Validate harness configuration
  validate_non_empty_string(config.harness.name, "harness.name")
  validate_log_level(config.harness.log_level, "harness.log_level")

  # Validate backend configuration
  validate_choice(config.backend.provider, "backend.provider", ("ollama",))

  # Validate Ollama configuration
  validate_url(config.backend.ollama.base_url, "backend.ollama.base_url")
  validate_non_empty_string(config.backend.ollama.model, "backend.ollama.model")
  validate_positive_int(config.backend.ollama.timeout_seconds, "backend.ollama.timeout_seconds")

  # Validate Ollama parameters
  params_path = "backend.ollama.parameters"
  if not 0.0 <= config.backend.ollama.parameters.temperature <= 2.0:
    raise ValidationError(
      params_path + ".temperature",
      config.backend.ollama.parameters.temperature,
      "must be between 0.0 and 2.0",
    )
  if not 0.0 <= config.backend.ollama.parameters.top_p <= 1.0:
    raise ValidationError(
      params_path + ".top_p",
      config.backend.ollama.parameters.top_p,
      "must be between 0.0 and 1.0",
    )
  validate_positive_int(config.backend.ollama.parameters.top_k, params_path + ".top_k")
  validate_positive_int(config.backend.ollama.parameters.num_ctx, params_path + ".num_ctx")

  # Validate context configuration
  validate_choice(
    config.context.manager,
    "context.manager",
    ("basic_persistence", "compaction", "multi_tier"),
  )

  # Validate permissions configuration
  validate_choice(
    config.permissions.network_access,
    "permissions.network_access",
    ("none", "local", "all"),
  )
  validate_positive_int(config.permissions.max_file_size_kb, "permissions.max_file_size_kb")
  validate_non_negative_int(
    config.permissions.max_recursion_depth, "permissions.max_recursion_depth"
  )

  # Validate tool configurations
  tools_path = "tools"
  validate_positive_int(config.tools.list.max_depth, f"{tools_path}.list.max_depth")
  validate_positive_int(config.tools.list.max_entries, f"{tools_path}.list.max_entries")
  validate_positive_int(config.tools.write.max_size_kb, f"{tools_path}.write.max_size_kb")
  validate_positive_int(
    config.tools.update.max_diff_size_kb, f"{tools_path}.update.max_diff_size_kb"
  )
  validate_positive_int(config.tools.search.max_results, f"{tools_path}.search.max_results")
  validate_positive_int(config.tools.search.timeout_ms, f"{tools_path}.search.timeout_ms")
  validate_positive_int(
    config.tools.agent.max_recursion_depth, f"{tools_path}.agent.max_recursion_depth"
  )
  validate_positive_int(config.tools.agent.timeout_seconds, f"{tools_path}.agent.timeout_seconds")

  # Validate regex patterns
  validate_regex_patterns(config.tools.read.blocked_patterns, f"{tools_path}.read.blocked_patterns")

  # Validate agents directory (warning only)
  if config.agents.directory:
    validate_directory_exists(config.agents.directory, "agents.directory", warn_only=True)

  # Validate logging configuration
  validate_choice(config.logging.format, "logging.format", ("json", "text"))

  return warnings


__all__ = [
  "validate_config",
  "validate_url",
  "validate_non_empty_string",
  "validate_positive_int",
  "validate_non_negative_int",
  "validate_choice",
  "validate_directory_exists",
  "validate_log_level",
  "validate_regex_patterns",
]
