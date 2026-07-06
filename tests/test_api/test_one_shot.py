"""Tests for Layer 1 — one-shot functions (MBI-003 task 3.4)."""

import asyncio

import pytest

import yoker
from yoker.agent import Agent
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

  monkeypatch.setattr("yoker.agent.process_message", handler)
  return seen


class TestAsk:
  """``yoker.ask`` runs a single turn and returns the response string."""

  async def test_ask_returns_response(self, patched_process) -> None:
    """ask() returns the assistant reply for the prompt."""
    result = await yoker.ask("hello")
    assert result == "reply:hello"
    assert patched_process == ["hello"]

  async def test_ask_constructs_and_discards_agent(self, patched_process) -> None:
    """ask() is stateless — each call builds a fresh agent."""
    await yoker.ask("first")
    await yoker.ask("second")
    assert patched_process == ["first", "second"]

  async def test_ask_with_model_override(self, monkeypatch) -> None:
    """model= is applied to the config backing the agent."""
    captured: dict[str, str] = {}

    async def handler(agent: Agent, message: str) -> str:
      captured["model"] = agent.model
      return "ok"

    monkeypatch.setattr("yoker.agent.process_message", handler)
    await yoker.ask("hi", model="qwen3.5:cloud")
    assert captured["model"] == "qwen3.5:cloud"

  async def test_ask_with_system_prompt(self, monkeypatch) -> None:
    """system_prompt= overrides the agent definition's system prompt."""
    captured: dict[str, str] = {}

    async def handler(agent: Agent, message: str) -> str:
      captured["prompt"] = agent.definition.system_prompt
      return "ok"

    monkeypatch.setattr("yoker.agent.process_message", handler)
    await yoker.ask("hi", system_prompt="You are a reviewer.")
    assert captured["prompt"] == "You are a reviewer."

  async def test_ask_with_tools_filter(self, monkeypatch) -> None:
    """tools=['read'] restricts the agent's tool registry to only 'read'."""
    captured: dict[str, list[str]] = {}

    async def handler(agent: Agent, message: str) -> str:
      captured["tools"] = sorted(agent.tools.names)
      return "ok"

    monkeypatch.setattr("yoker.agent.process_message", handler)
    await yoker.ask("hi", tools=["read"])
    # Only read-related tools remain; the exact set depends on the builtin
    # manifest but must be a strict subset of all tools and contain 'read'.
    assert any("read" in t for t in captured["tools"])
    assert len(captured["tools"]) < 20  # filtered, not all tools

  async def test_ask_with_empty_tools_disables_all(self, monkeypatch) -> None:
    """tools=[] removes every tool from the registry."""
    captured: dict[str, list[str]] = {}

    async def handler(agent: Agent, message: str) -> str:
      captured["tools"] = list(agent.tools.names)
      return "ok"

    monkeypatch.setattr("yoker.agent.process_message", handler)
    await yoker.ask("hi", tools=[])
    assert captured["tools"] == []

  async def test_ask_event_handler_receives_events(self, monkeypatch) -> None:
    """event_handler= is registered on the agent and receives events."""
    from yoker.events import TurnStartEvent

    received: list[Event] = []

    async def handler(agent: Agent, message: str) -> str:
      # Manually emit one event the way the real process_message would.
      from yoker.agent._processing import emit

      await emit(
        TurnStartEvent(type=EventType.TURN_START, message=message),
        agent._event_handlers,
      )
      return "ok"

    monkeypatch.setattr("yoker.agent.process_message", handler)
    await yoker.ask("hi", event_handler=lambda e: received.append(e))
    assert len(received) >= 1
    assert any(isinstance(e, TurnStartEvent) for e in received)


class TestRunSkill:
  """``yoker.run_skill`` injects skill context and runs a turn."""

  async def test_run_skill_unknown_raises(self, monkeypatch) -> None:
    """An unknown skill name raises SkillError."""
    from yoker.exceptions import SkillError

    async def handler(_agent: Agent, _message: str) -> str:
      return "ok"

    monkeypatch.setattr("yoker.agent.process_message", handler)
    with pytest.raises(SkillError):
      await yoker.run_skill("does-not-exist", "do something")

  async def test_run_skill_injects_context(self, monkeypatch, tmp_path) -> None:
    """run_skill injects the skill content as a user message before the prompt."""
    # Create a tiny skill on disk so it is loaded by the agent.
    skill_dir = tmp_path / "skills"
    skill_dir.mkdir()
    (skill_dir / "greet.md").write_text(
      "---\nname: greet\ndescription: Greet the user.\n---\nYou must greet warmly.\n"
    )

    seen: list[str] = []

    async def handler(agent: Agent, message: str) -> str:
      # Record all messages in the context so we can see the injected block.
      for msg in agent.context.get_messages():
        seen.append(msg.get("content", ""))
      return "ok"

    monkeypatch.setattr("yoker.agent.process_message", handler)
    # We need the skill directory to be picked up. Override config via the
    # skills kwarg on the helper by patching make_config to include the dir.
    import yoker.api._internal as internal

    orig = internal.build_agent

    def patched(**kwargs):
      kwargs.setdefault("config", None)

      from yoker.config import make_config

      cfg = make_config(skills_directories=(str(skill_dir),))
      return orig(config=cfg, **{k: v for k, v in kwargs.items() if k != "config"})

    monkeypatch.setattr(internal, "build_agent", patched)
    monkeypatch.setattr("yoker.api.one_shot.build_agent", patched)
    await yoker.run_skill("greet", "Hello there")
    # The injected skill block ends up in the agent's context (the skill
    # content is added as a user message by inject_skill_context).
    assert any("greet warmly" in s for s in seen)


class TestComplete:
  """``yoker.complete`` does pure text completion with no tools/skills."""

  async def test_complete_returns_response(self, patched_process) -> None:
    """complete() returns the reply string."""
    result = await yoker.complete("translate: hello")
    assert result == "reply:translate: hello"

  async def test_complete_has_no_tools(self, monkeypatch) -> None:
    """complete() builds an agent with an empty tool registry."""
    captured: dict[str, list[str]] = {}

    async def handler(agent: Agent, _message: str) -> str:
      captured["tools"] = list(agent.tools.names)
      return "ok"

    monkeypatch.setattr("yoker.agent.process_message", handler)
    await yoker.complete("hi")
    assert captured["tools"] == []

  async def test_complete_has_no_skills(self, monkeypatch) -> None:
    """complete() builds an agent with an empty skill registry."""
    captured: dict[str, list[str]] = {}

    async def handler(agent: Agent, _message: str) -> str:
      captured["skills"] = list(agent.skills.names)
      return "ok"

    monkeypatch.setattr("yoker.agent.process_message", handler)
    await yoker.complete("hi")
    assert captured["skills"] == []

  async def test_complete_has_empty_system_prompt(self, monkeypatch) -> None:
    """complete() uses an empty system prompt (pure text completion)."""
    captured: dict[str, str] = {}

    async def handler(agent: Agent, _message: str) -> str:
      captured["prompt"] = agent.definition.system_prompt
      return "ok"

    monkeypatch.setattr("yoker.agent.process_message", handler)
    await yoker.complete("hi")
    assert captured["prompt"] == ""


class TestSyncWrappers:
  """``*_sync`` helpers run async via asyncio.run."""

  def test_ask_sync_returns_response(self, patched_process) -> None:
    """ask_sync runs the async ask and returns the reply."""
    assert yoker.ask_sync("hello") == "reply:hello"

  def test_complete_sync_returns_response(self, patched_process) -> None:
    """complete_sync runs the async complete and returns the reply."""
    assert yoker.complete_sync("hi") == "reply:hi"

  def test_ask_sync_in_running_loop_raises(self, patched_process) -> None:
    """ask_sync inside a running loop raises RuntimeError (no nesting)."""

    async def inside_loop() -> None:
      with pytest.raises(RuntimeError, match="async variant"):
        yoker.ask_sync("hi")

    asyncio.run(inside_loop())
