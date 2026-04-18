"""Exception hierarchy for Yoker.

Provides structured exception classes for configuration errors,
validation failures, and other error conditions.
"""


class YokerError(Exception):
  """Base exception for all Yoker errors."""

  def __init__(self, message: str) -> None:
    self.message = message
    super().__init__(message)

  def __str__(self) -> str:
    return self.message


class ConfigurationError(YokerError):
  """Exception for configuration-related errors.

  Attributes:
    setting: The configuration setting that caused the error.
    expected: Description of expected value format.
    message: Custom error message.
  """

  def __init__(
    self,
    setting: str,
    expected: str | None = None,
    message: str | None = None,
  ) -> None:
    self.setting = setting
    self.expected = expected
    self._message = message
    super().__init__(str(self))

  def __str__(self) -> str:
    parts = [f"Configuration error for '{self.setting}'"]
    if self._message:
      parts.append(f": {self._message}")
    elif self.expected:
      parts.append(f". Expected {self.expected}")
    else:
      parts.append(".")
    return "".join(parts)


class ValidationError(YokerError):
  """Exception for validation failures.

  Attributes:
    path: Path to the invalid value (e.g., 'backend.ollama.base_url').
    value: The invalid value.
    reason: Explanation of why validation failed.
  """

  def __init__(
    self,
    path: str,
    value: object,
    reason: str,
  ) -> None:
    self.path = path
    self.value = value
    self.reason = reason
    super().__init__(str(self))

  def __str__(self) -> str:
    return f"Validation error at '{self.path}': {self.reason} (got: {self.value!r})"


class FileNotFoundError(YokerError):
  """Exception when a required file is not found.

  Attributes:
    path: Path to the missing file.
    file_type: Description of the file type (e.g., 'configuration').
  """

  def __init__(self, path: str, file_type: str = "file") -> None:
    self.path = path
    self.file_type = file_type
    super().__init__(str(self))

  def __str__(self) -> str:
    return f"{self.file_type.capitalize()} not found: {self.path}"


__all__ = [
  "YokerError",
  "ConfigurationError",
  "ValidationError",
  "FileNotFoundError",
]
