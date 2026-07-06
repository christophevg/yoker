"""Tests for Layer 2 — the agent builder (MBI-003 task 3.5)."""

import pytest

import yoker
from yoker.core import Agent
from yoker.core.thinking import ThinkingMode
from yoker.events import Event


class TestAgentBuilderReturnsAgent:
  """``yoker.agent`` returns a fully constructed Agent instance."""

  def test_returns_agent_instance(self) -> None:
    """agent() returns a yoker.Agent."""
    a = yoker.agent()
    assert isinstance(a, Agent)

  def test_reusable_across_calls(self, monkeypatch) -> None:
    """The same agent can be awaited multiple times (stateful)."""
    seen: list[str] = []

    async def handler(_agent: Agent, message: str) -> str:
      seen.append(message)
      return f"r:{message}"

    monkeypatch.setattr("yoker.core.process_message", handler)
    a = yoker.agent()
    import asyncio

    r1 = asyncio.run(a.process("first"))
    r2 = asyncio.run(a.process("second"))
    assert r1 == "r:first"
    assert r2 == "r:second"
    assert seen == ["first", "second"]


class TestAgentBuilderModel:
  """``model`` / ``provider`` kwargs override the config."""

  def test_model_override(self) -> None:
    """model= sets the agent's resolved model."""
    a = yoker.agent(model="qwen3.5:cloud")
    assert a.model == "qwen3.5:cloud"

  def test_provider_override_openai(self) -> None:
    """provider=openai builds a config that validates and sets the provider."""
    a = yoker.agent(provider="openai", model="gpt-4o-mini")
    assert a.config.backend.provider == "openai"
    assert a.model == "gpt-4o-mini"


class TestAgentBuilderTools:
  """``tools`` kwarg filters the tool registry."""

  def test_tools_whitelist(self) -> None:
    """tools=['read'] keeps only the read tool (and its yoker: alias)."""
    a = yoker.agent(tools=["read"])
    names = sorted(a.tools.names)
    assert any("read" in n for n in names)
    # Other builtins like write/search/git are filtered out.
    assert not any("write" in n for n in names)
    assert not any("git" in n for n in names)

  def test_tools_empty_disables_all(self) -> None:
    """tools=[] produces an agent with no tools."""
    a = yoker.agent(tools=[])
    assert list(a.tools.names) == []

  def test_tools_none_keeps_all(self) -> None:
    """tools=None (default) keeps all built-in tools."""
    a = yoker.agent()
    assert len(a.tools.names) > 0


class TestAgentBuilderSkills:
  """``skills`` kwarg filters the skill registry."""

  def test_skills_unknown_raises(self) -> None:
    """An unknown skill name raises SkillError."""
    from yoker.exceptions import SkillError

    with pytest.raises(SkillError):
      yoker.agent(skills=["does-not-exist"])

  def test_skills_empty_disables_all(self) -> None:
    """skills=[] clears the skill registry."""
    a = yoker.agent(skills=[])
    assert list(a.skills.names) == []


class TestAgentBuilderSystemPrompt:
  """``system_prompt`` overrides the agent definition's prompt."""

  def test_system_prompt_override(self) -> None:
    """system_prompt= sets the definition's system_prompt."""
    a = yoker.agent(system_prompt="You are a reviewer.")
    assert a.definition.system_prompt == "You are a reviewer."

  def test_default_system_prompt(self) -> None:
    """Without system_prompt= the default agent prompt is used."""
    a = yoker.agent()
    assert a.definition.system_prompt == "You are a helpful assistant."


class TestAgentBuilderThinking:
  """``thinking`` kwarg maps to :class:`ThinkingMode`."""

  @pytest.mark.parametrize(
    "value,expected",
    [
      ("on", ThinkingMode.ON),
      ("visible", ThinkingMode.ON),
      ("off", ThinkingMode.OFF),
      ("silent", ThinkingMode.SILENT),
    ],
  )
  def test_thinking_mapping(self, value: str, expected: ThinkingMode) -> None:
    a = yoker.agent(thinking=value)  # type: ignore[arg-type]
    assert a.thinking_mode == expected

  def test_thinking_invalid_raises(self) -> None:
    """An unknown thinking value raises ValueError."""
    with pytest.raises(ValueError):
      yoker.agent(thinking="bogus")  # type: ignore[arg-type]


class TestAgentBuilderEventHandler:
  """``event_handler`` / ``on_event`` register handlers."""

  def test_event_handler_registered(self) -> None:
    """event_handler= is registered on construction."""
    received: list[Event] = []
    a = yoker.agent(event_handler=lambda e: received.append(e))
    assert a.get_event_handlers()[-1] is not None

  def test_on_event_returns_handler(self) -> None:
    """on_event returns the handler for chaining."""

    def handler(_e: object) -> None:
      return None

    returned = yoker.agent().on_event(handler)
    assert returned is handler

  def test_on_event_registers(self) -> None:
    """on_event adds the handler to the agent's handler list."""
    a = yoker.agent()

    def handler(_e: object) -> None:
      return None

    a.on_event(handler)
    assert handler in a.get_event_handlers()
