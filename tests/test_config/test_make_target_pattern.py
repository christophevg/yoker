"""Tests for the shared make-target pattern (yoker.config.MAKE_TARGET_RE).

The pattern is the single source of truth for BOTH the make tool's target
validation and the allowed_env_vars key validation. These tests pin the
slash behavior (path-style targets like docs/html are valid) and identity
with yoker.builtin.make._TARGET_RE so the two validations cannot drift.
"""

import pytest

from yoker.config import MAKE_TARGET_RE

make_module = pytest.importorskip("yoker.builtin.make")


class TestMakeTargetRePattern:
  """Slash semantics and invariants of the shared pattern."""

  def test_path_style_target_accepted(self) -> None:
    """Slash in target name is allowed (GNU make path-style targets)."""
    assert MAKE_TARGET_RE.fullmatch("docs/html") is not None
    assert MAKE_TARGET_RE.fullmatch("build/all") is not None
    assert MAKE_TARGET_RE.fullmatch("a/b/c") is not None

  def test_plain_targets_still_accepted(self) -> None:
    """Pre-existing valid targets remain valid."""
    assert MAKE_TARGET_RE.fullmatch("check") is not None
    assert MAKE_TARGET_RE.fullmatch("test") is not None
    assert MAKE_TARGET_RE.fullmatch("a_b.c%d+e-f") is not None

  @pytest.mark.parametrize("bad", ["-flag", "--eval=x", "/etc/passwd", "; x", "a b", "", "a:b"])
  def test_rejections_unchanged(self, bad: str) -> None:
    """Leading dash, leading slash, and metachars stay rejected."""
    assert MAKE_TARGET_RE.fullmatch(bad) is None


class TestSingleSourceOfTruth:
  """The make tool must not carry its own copy of the pattern."""

  def test_make_tool_uses_shared_constant(self) -> None:
    """make._TARGET_RE IS the config constant — identity, not a copy."""
    assert make_module._TARGET_RE is MAKE_TARGET_RE
