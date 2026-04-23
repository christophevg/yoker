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


class SessionNotFoundError(YokerError):
  """Exception when a session is not found in storage.

  Attributes:
    session_id: The session ID that was not found.
  """

  def __init__(self, session_id: str) -> None:
    self.session_id = session_id
    super().__init__(str(self))

  def __str__(self) -> str:
    return f"Session not found: {self.session_id}"


class ContextCorruptionError(YokerError):
  """Exception when context file is corrupted.

  Attributes:
    path: Path to the corrupted file.
    line_num: Line number where corruption was detected.
    message: Description of the corruption.
  """

  def __init__(self, path: str, line_num: int, message: str) -> None:
    self.path = path
    self.line_num = line_num
    self._message = message
    super().__init__(str(self))

  def __str__(self) -> str:
    return f"Corrupted context at {self.path}:{self.line_num}: {self._message}"


class PermissionViolationError(YokerError):
  """Exception when a tool operation violates permission guardrails.

  Attributes:
    operation: The operation that was blocked (e.g., 'read').
    reason: Explanation of why the operation was blocked.
  """

  def __init__(self, operation: str, reason: str) -> None:
    self.operation = operation
    self.reason = reason
    super().__init__(str(self))

  def __str__(self) -> str:
    return f"Permission violation for '{self.operation}': {self.reason}"


__all__ = [
  "YokerError",
  "ConfigurationError",
  "ValidationError",
  "FileNotFoundError",
  "SessionNotFoundError",
  "ContextCorruptionError",
  "PermissionViolationError",
]
