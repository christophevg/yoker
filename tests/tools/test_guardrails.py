"""Tests for guardrail interfaces."""

import pytest

from yoker.tools.base import ValidationResult
from yoker.tools.guardrails import Guardrail


class TestGuardrailABC:
  """Tests for Guardrail abstract base class."""

  def test_cannot_instantiate(self) -> None:
    """Guardrail ABC cannot be instantiated directly."""
    with pytest.raises(TypeError):
      Guardrail()

  def test_concrete_guardrail(self) -> None:
    """Concrete Guardrail subclass works."""

    class AllowAll(Guardrail):
      def validate(self, tool_name: str, params: dict) -> ValidationResult:
        return ValidationResult(valid=True)

    class BlockAll(Guardrail):
      def validate(self, tool_name: str, params: dict) -> ValidationResult:
        return ValidationResult(valid=False, reason="blocked")

    allow = AllowAll()
    block = BlockAll()

    assert allow.validate("read", {}).valid is True
    result = block.validate("read", {})
    assert result.valid is False
    assert result.reason == "blocked"
