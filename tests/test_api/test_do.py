"""Tests for the one-shot ``yoker.do`` skill invocation (MBI-003)."""

import asyncio

import pytest

import yoker
from yoker.core import Agent
from yoker.exceptions import SkillError


@pytest.fixture
def patched_do(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, str]]:
  """Patch ``Agent.do`` to record calls and return canned replies.

  Returns a list that records every ``(skill_name, prompt, args)`` triple
  seen by the patched consumer.
  """
  seen: list[tuple[str, str, str]] = []

  async def fake_do(self: Agent, skill_name: str, prompt: str, args: str = "") -> str:
    seen.append((skill_name, prompt, args))
    return f"reply:{skill_name}:{prompt}"

  monkeypatch.setattr(Agent, "do", fake_do)
  return seen


class TestDo:
  """``yoker.do`` runs a skill as a one-shot command and returns the response."""

  async def test_do_returns_response(self, patched_do) -> None:
    """do() returns the assistant reply for the skill invocation."""
    result = await yoker.do("commit", "fix the bug")
    assert result == "reply:commit:fix the bug"
    assert patched_do == [("commit", "fix the bug", "")]

  async def test_do_forwards_args(self, patched_do) -> None:
    """do() forwards the args kwarg to the skill."""
    await yoker.do("commit", "fix the bug", args="--amend")
    assert patched_do == [("commit", "fix the bug", "--amend")]

  async def test_do_constructs_and_discards_agent(self, patched_do) -> None:
    """do() is stateless — each call builds a fresh agent."""
    await yoker.do("commit", "first")
    await yoker.do("commit", "second")
    assert patched_do == [
      ("commit", "first", ""),
      ("commit", "second", ""),
    ]

  async def test_do_unknown_skill_raises(self, monkeypatch) -> None:
    """An unknown skill name raises SkillError (propagated from Agent.do)."""

    async def fake_do(self: Agent, skill_name: str, prompt: str, args: str = "") -> str:
      raise SkillError(skill_name, "Unknown skill")

    monkeypatch.setattr(Agent, "do", fake_do)
    with pytest.raises(SkillError):
      await yoker.do("does-not-exist", "hi")


class TestRunSyncDo:
  """``yoker.run_sync`` wraps ``yoker.do`` for synchronous callers."""

  def test_run_sync_do_returns_response(self, patched_do) -> None:
    """run_sync runs the async do and returns the reply."""
    assert yoker.run_sync(yoker.do("commit", "fix the bug")) == "reply:commit:fix the bug"

  def test_run_sync_do_in_running_loop_raises(self, patched_do) -> None:
    """run_sync inside a running loop raises RuntimeError (no nesting)."""

    async def inside_loop() -> None:
      with pytest.raises(RuntimeError, match="async variant"):
        yoker.run_sync(yoker.do("commit", "hi"))

    asyncio.run(inside_loop())
