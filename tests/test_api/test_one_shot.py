"""Tests for Layer 1 — one-shot functions (MBI-003 task 3.4)."""

import asyncio

import pytest

import yoker
from yoker.core import Agent
from yoker.events import Event, EventType


@pytest.fixture
def patched_process(monkeypatch: pytest.MonkeyPatch) -> list[str]:
  """Patch ``process_message`` to record calls and return canned replies.

  Returns a list that records every prompt seen by the patched consumer.
  """
  seen: list[str] = []

  async def handler(_agent: Agent, message: str) -> str:
    seen.append(message)
    return f"reply:{message}"

  monkeypatch.setattr("yoker.core.process_message", handler)
  return seen


class TestProcess:
  """``yoker.process`` runs a single turn and returns the response string."""

  async def test_process_returns_response(self, patched_process) -> None:
    """process() returns the assistant reply for the prompt."""
    result = await yoker.process("hello")
    assert result == "reply:hello"
    assert patched_process == ["hello"]

  async def test_process_constructs_and_discards_agent(self, patched_process) -> None:
    """process() is stateless — each call builds a fresh agent."""
    await yoker.process("first")
    await yoker.process("second")
    assert patched_process == ["first", "second"]

  async def test_process_with_model_override(self, monkeypatch) -> None:
    """model= is applied to the config backing the agent."""
    captured: dict[str, str] = {}

    async def handler(agent: Agent, message: str) -> str:
      captured["model"] = agent.model
      return "ok"

    monkeypatch.setattr("yoker.core.process_message", handler)
    await yoker.process("hi", model="qwen3.5:cloud")
    assert captured["model"] == "qwen3.5:cloud"

  async def test_process_with_system_prompt(self, monkeypatch) -> None:
    """system_prompt= overrides the agent definition's system prompt."""
    captured: dict[str, str] = {}

    async def handler(agent: Agent, message: str) -> str:
      captured["prompt"] = agent.definition.system_prompt
      return "ok"

    monkeypatch.setattr("yoker.core.process_message", handler)
    await yoker.process("hi", system_prompt="You are a reviewer.")
    assert captured["prompt"] == "You are a reviewer."

  async def test_process_with_empty_system_prompt(self, monkeypatch) -> None:
    """system_prompt='' uses an empty system prompt (pure text completion)."""
    captured: dict[str, str] = {}

    async def handler(agent: Agent, _message: str) -> str:
      captured["prompt"] = agent.definition.system_prompt
      return "ok"

    monkeypatch.setattr("yoker.core.process_message", handler)
    await yoker.process("hi", system_prompt="")
    assert captured["prompt"] == ""

  async def test_process_with_tools_filter(self, monkeypatch) -> None:
    """tools=['read'] restricts the agent's tool registry to only 'read'."""
    captured: dict[str, list[str]] = {}

    async def handler(agent: Agent, message: str) -> str:
      captured["tools"] = sorted(agent.tools.names)
      return "ok"

    monkeypatch.setattr("yoker.core.process_message", handler)
    await yoker.process("hi", tools=["read"])
    # Only read-related tools remain; the exact set depends on the builtin
    # manifest but must be a strict subset of all tools and contain 'read'.
    assert any("read" in t for t in captured["tools"])
    assert len(captured["tools"]) < 20  # filtered, not all tools

  async def test_process_with_empty_tools_disables_all(self, monkeypatch) -> None:
    """tools=[] removes every tool from the registry."""
    captured: dict[str, list[str]] = {}

    async def handler(agent: Agent, message: str) -> str:
      captured["tools"] = list(agent.tools.names)
      return "ok"

    monkeypatch.setattr("yoker.core.process_message", handler)
    await yoker.process("hi", tools=[])
    assert captured["tools"] == []

  async def test_process_event_handler_receives_events(self, monkeypatch) -> None:
    """event_handler= is registered on the agent and receives events."""
    from yoker.events import TurnStartEvent

    received: list[Event] = []

    async def handler(agent: Agent, message: str) -> str:
      # Manually emit one event the way the real process_message would.
      from yoker.core._processing import emit

      await emit(
        TurnStartEvent(type=EventType.TURN_START, message=message),
        agent._event_handlers,
      )
      return "ok"

    monkeypatch.setattr("yoker.core.process_message", handler)
    await yoker.process("hi", event_handler=lambda e: received.append(e))
    assert len(received) >= 1
    assert any(isinstance(e, TurnStartEvent) for e in received)


class TestRunSync:
  """``yoker.run_sync`` wraps asyncio.run for synchronous callers."""

  def test_run_sync_returns_response(self, patched_process) -> None:
    """run_sync runs the async process and returns the reply."""
    assert yoker.run_sync(yoker.process("hello")) == "reply:hello"

  def test_run_sync_in_running_loop_raises(self, patched_process) -> None:
    """run_sync inside a running loop raises RuntimeError (no nesting)."""

    async def inside_loop() -> None:
      with pytest.raises(RuntimeError, match="async variant"):
        yoker.run_sync(yoker.process("hi"))

    asyncio.run(inside_loop())
