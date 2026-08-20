"""Guardrail interfaces for Yoker tools.

Provides the Guardrail abstract base class that concrete guardrail
implementations must follow. Guardrails validate tool parameters before
execution to enforce permission boundaries.
"""

from abc import ABC, abstractmethod
from typing import Any

from yoker.tools.schema import ValidationResult


class Guardrail(ABC):
  """Abstract base class for tool guardrails.

  Guardrails validate tool parameters against permission boundaries
  before a tool is executed. Each tool type will have specific
  guardrail implementations (e.g., path restrictions for filesystem tools).

  Example:
    class PathGuardrail(Guardrail):
      def validate(self, tool_name: str, params: dict[str, Any]) -> ValidationResult:
        path = params.get("path", "")
        if not path.startswith("/allowed"):
          return ValidationResult(valid=False, reason="Path not allowed")
        return ValidationResult(valid=True)
  """

  @abstractmethod
  def validate(
    self, tool_name: str, value: str | dict[str, Any], *, skip_protected: bool = False
  ) -> ValidationResult:
    """Validate tool parameters.

    Args:
      tool_name: Name of the tool being validated.
      value: Either the extracted parameter value or the full params dict.
      skip_protected: When True, skip the protected_files check (user
        approved interactively). The guardrail is responsible for honoring
        this flag.

    Returns:
      ValidationResult indicating whether parameters are valid.
    """


__all__ = [
  "Guardrail",
  "ValidationResult",
]
