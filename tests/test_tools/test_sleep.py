"""Tests for the sleep tool implementation.

Verifies input validation (type, min/max bounds), clamping behaviour,
the asyncio.sleep call, and the structured ToolResult contract.
"""

from unittest.mock import AsyncMock, patch

import pytest

from yoker.builtin import sleep
from yoker.builtin.sleep import MAX_SLEEP_SECONDS, MIN_SLEEP_SECONDS
from yoker.tools import ToolRegistry


def _sleep_spec():
  """Register the sleep tool and return its spec."""
  registry = ToolRegistry()
  return registry.register(sleep, name="sleep")


class TestSleepValidation:
  """Input validation — no actual sleeping occurs."""

  @pytest.mark.asyncio
  async def test_rejects_non_integer(self) -> None:
    """Non-integer seconds must be rejected."""
    result = await sleep(seconds="30")  # type: ignore[arg-type]
    assert result.success is False
    assert "integer" in result.error

  @pytest.mark.asyncio
  async def test_rejects_float(self) -> None:
    """Float seconds must be rejected (integer-only)."""
    result = await sleep(seconds=1.5)  # type: ignore[arg-type]
    assert result.success is False
    assert "integer" in result.error

  @pytest.mark.asyncio
  async def test_rejects_zero(self) -> None:
    """Zero seconds is below the minimum and must be rejected."""
    result = await sleep(seconds=0)
    assert result.success is False
    assert str(MIN_SLEEP_SECONDS) in result.error

  @pytest.mark.asyncio
  async def test_rejects_negative(self) -> None:
    """Negative seconds must be rejected."""
    result = await sleep(seconds=-5)
    assert result.success is False
    assert str(MIN_SLEEP_SECONDS) in result.error


class TestSleepClamping:
  """Values above MAX_SLEEP_SECONDS are clamped, not rejected."""

  @pytest.mark.asyncio
  async def test_clamps_to_max(self) -> None:
    """Seconds above MAX_SLEEP_SECONDS are clamped down."""
    # Patch "asyncio.sleep": on 3.10 yoker.builtin.sleep is the sleep function, not the module.
    with patch(
      "asyncio.sleep",
      new_callable=AsyncMock,
    ) as mock_sleep:
      result = await sleep(seconds=999, reason="waiting for CI")

    assert result.success is True
    assert mock_sleep.await_count == 1
    assert mock_sleep.await_args.args[0] == MAX_SLEEP_SECONDS
    assert result.result["slept_seconds"] == MAX_SLEEP_SECONDS
    assert result.result["clamped"] is True

  @pytest.mark.asyncio
  async def test_exactly_max_not_clamped(self) -> None:
    """Seconds == MAX_SLEEP_SECONDS should not be clamped."""
    with patch(
      "asyncio.sleep",
      new_callable=AsyncMock,
    ) as mock_sleep:
      result = await sleep(seconds=MAX_SLEEP_SECONDS)

    assert result.success is True
    assert mock_sleep.await_args.args[0] == MAX_SLEEP_SECONDS
    assert result.result["clamped"] is False


class TestSleepExecution:
  """Successful sleep calls with mocked asyncio.sleep."""

  @pytest.mark.asyncio
  async def test_basic_sleep(self) -> None:
    """A valid sleep returns success with correct duration."""
    with patch(
      "asyncio.sleep",
      new_callable=AsyncMock,
    ) as mock_sleep:
      result = await sleep(seconds=30)

    assert result.success is True
    assert mock_sleep.await_count == 1
    assert mock_sleep.await_args.args[0] == 30
    assert result.result["slept_seconds"] == 30
    assert result.result["clamped"] is False

  @pytest.mark.asyncio
  async def test_sleep_with_reason(self) -> None:
    """The reason field is echoed back in the result."""
    with patch(
      "asyncio.sleep",
      new_callable=AsyncMock,
    ):
      result = await sleep(seconds=10, reason="waiting for CI run #12345")

    assert result.success is True
    assert result.result["reason"] == "waiting for CI run #12345"

  @pytest.mark.asyncio
  async def test_sleep_without_reason(self) -> None:
    """When no reason is given, result reason is None."""
    with patch(
      "asyncio.sleep",
      new_callable=AsyncMock,
    ):
      result = await sleep(seconds=5)

    assert result.success is True
    assert result.result["reason"] is None

  @pytest.mark.asyncio
  async def test_min_seconds_accepted(self) -> None:
    """MIN_SLEEP_SECONDS (1) is the smallest accepted value."""
    with patch(
      "asyncio.sleep",
      new_callable=AsyncMock,
    ) as mock_sleep:
      result = await sleep(seconds=MIN_SLEEP_SECONDS)

    assert result.success is True
    assert mock_sleep.await_args.args[0] == MIN_SLEEP_SECONDS


class TestSleepToolSpec:
  """Verify the tool registers correctly via build_tool_spec."""

  def test_registers_as_sleep(self) -> None:
    """The tool spec name should be 'sleep'."""
    spec = _sleep_spec()
    assert spec.name == "sleep"

  def test_has_description(self) -> None:
    """The tool spec should have a non-empty description."""
    spec = _sleep_spec()
    assert spec.description
    assert len(spec.description) > 0

  def test_in_builtin_manifest(self) -> None:
    """sleep should be importable from yoker.builtin."""
    from yoker.builtin import sleep as builtin_sleep

    assert builtin_sleep is sleep
