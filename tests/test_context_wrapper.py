"""Tests for ContextManagerWrapper — the pure proxy implementing the Protocol."""

from unittest.mock import MagicMock

import pytest

from yoker.context import (
  BaseContextManager,
  ContextManager,
  ContextManagerWrapper,
  SimpleContextManager,
)


class TestContextManagerWrapperForwarding:
  """Verify ContextManagerWrapper forwards every Protocol method to wrapped."""

  def test_implements_protocol(self) -> None:
    wrapped = BaseContextManager()
    cm = ContextManagerWrapper(wrapped)
    assert isinstance(cm, ContextManager)

  def test_wrapped_is_stored(self) -> None:
    wrapped = BaseContextManager()
    cm = ContextManagerWrapper(wrapped)
    assert cm._wrapped is wrapped

  def test_get_context_forwards(self) -> None:
    wrapped = BaseContextManager()
    cm = ContextManagerWrapper(wrapped)
    wrapped.add_message("user", "hi")
    assert cm.get_context() == wrapped.get_context()

  def test_get_messages_forwards(self) -> None:
    wrapped = BaseContextManager()
    cm = ContextManagerWrapper(wrapped)
    wrapped.add_message("user", "hi")
    assert cm.get_messages() == wrapped.get_messages()

  def test_add_message_forwards(self) -> None:
    wrapped = BaseContextManager()
    cm = ContextManagerWrapper(wrapped)
    cm.add_message("user", "hi")
    assert wrapped.get_messages()[0]["content"] == "hi"

  def test_add_tool_result_forwards(self) -> None:
    wrapped = BaseContextManager()
    cm = ContextManagerWrapper(wrapped)
    cm.add_tool_result("read", "tool-1", "content", success=True)
    assert len(wrapped.get_context()) == 1
    assert wrapped.get_context()[0]["role"] == "tool"

  def test_add_tool_calls_forwards(self) -> None:
    wrapped = BaseContextManager()
    cm = ContextManagerWrapper(wrapped)
    cm.add_tool_calls([{"id": "call_1", "function": {"name": "read", "arguments": {}}}])
    assert len(wrapped.get_context()) == 1
    assert wrapped.get_context()[0]["role"] == "assistant"

  def test_start_turn_forwards(self) -> None:
    wrapped = BaseContextManager()
    cm = ContextManagerWrapper(wrapped)
    cm.start_turn("Hello")
    assert wrapped.get_messages()[-1]["content"] == "Hello"

  def test_end_turn_forwards(self) -> None:
    wrapped = BaseContextManager()
    cm = ContextManagerWrapper(wrapped)
    cm.end_turn("Hi")
    assert wrapped.get_messages()[-1]["content"] == "Hi"

  def test_clear_forwards(self) -> None:
    wrapped = BaseContextManager()
    wrapped.add_message("user", "hi")
    cm = ContextManagerWrapper(wrapped)
    cm.clear()
    assert wrapped.get_messages() == []

  def test_save_forwards(self) -> None:
    # save is a no-op on the base; just verify it doesn't raise
    wrapped = BaseContextManager()
    cm = ContextManagerWrapper(wrapped)
    cm.save()

  def test_load_forwards(self) -> None:
    wrapped = BaseContextManager()
    cm = ContextManagerWrapper(wrapped)
    assert cm.load() is False

  def test_delete_forwards(self) -> None:
    wrapped = BaseContextManager()
    cm = ContextManagerWrapper(wrapped)
    with pytest.raises(NotImplementedError):
      cm.delete()

  def test_close_forwards(self) -> None:
    wrapped = BaseContextManager()
    cm = ContextManagerWrapper(wrapped)
    cm.close()  # no-op, should not raise

  def test_get_statistics_forwards(self) -> None:
    wrapped = BaseContextManager()
    wrapped.start_turn("hi")
    cm = ContextManagerWrapper(wrapped)
    stats = cm.get_statistics()
    assert stats.message_count == 1
    assert stats.turn_count == 1

  def test_get_session_id_forwards(self) -> None:
    wrapped = BaseContextManager()
    cm = ContextManagerWrapper(wrapped)
    assert cm.get_session_id() == "in-memory"

  def test_setup_initial_context_forwards(self) -> None:
    # Use a mock to verify forwarding
    wrapped = MagicMock(spec=BaseContextManager)
    cm = ContextManagerWrapper(wrapped)
    cm.setup_initial_context()
    wrapped.setup_initial_context.assert_called_once()

  def test_add_skill_discovery_block_forwards(self) -> None:
    wrapped = MagicMock(spec=BaseContextManager)
    cm = ContextManagerWrapper(wrapped)
    cm.add_skill_discovery_block()
    wrapped.add_skill_discovery_block.assert_called_once()


class TestContextManagerWrapperAgentProperty:
  """Verify agent property/setter forwards to wrapped."""

  def test_agent_getter_forwards(self) -> None:
    wrapped = BaseContextManager()
    cm = ContextManagerWrapper(wrapped)
    # both return None initially
    assert cm.agent is wrapped.agent
    assert cm.agent is None

  def test_agent_setter_forwards(self) -> None:
    wrapped = BaseContextManager()
    cm = ContextManagerWrapper(wrapped)
    # use a MagicMock as a stand-in Agent; the wrapped setter will call
    # clear() + setup_initial_context() + add_skill_discovery_block(), which
    # access agent.definition/system_prompt and agent.config.skills.discovery.
    mock_agent = MagicMock()
    cm.agent = mock_agent
    assert wrapped.agent is mock_agent


class TestContextManagerWrapperWithSimpleContextManager:
  """Wrapping a SimpleContextManager preserves env reminder behavior."""

  def test_wrapping_simple_gives_env_reminder(self) -> None:
    """A ContextManagerWrapper(SimpleContextManager()) is a no-op pass-through;
    the env reminder is produced by the wrapped SimpleContextManager itself.
    """
    from yoker.agents import AgentDefinition
    from yoker.core import Agent

    agent_def = AgentDefinition(
      simple_name="test",
      description="Test agent",
      tools=("read",),
      system_prompt="Custom system prompt for context test.",
    )
    wrapped = SimpleContextManager()
    cm = ContextManagerWrapper(wrapped)
    Agent(config=None, agent_definition=agent_def, context_manager=cm)  # type: ignore[arg-type]

    messages = cm.get_messages()
    system_messages = [m for m in messages if m.get("role") == "system"]
    assert len(system_messages) == 1
    content = system_messages[0].get("content", "")
    assert "You are running inside the Yoker agent harness" in content
    assert "Custom system prompt for context test." in content

  def test_wrapping_base_does_not_give_env_reminder(self) -> None:
    """A ContextManagerWrapper(BaseContextManager()) yields only the raw
    system prompt (no env reminder).
    """
    from yoker.agents import AgentDefinition
    from yoker.core import Agent

    agent_def = AgentDefinition(
      simple_name="test",
      description="Test agent",
      tools=("read",),
      system_prompt="Custom system prompt for context test.",
    )
    wrapped = BaseContextManager()
    cm = ContextManagerWrapper(wrapped)
    Agent(config=None, agent_definition=agent_def, context_manager=cm)  # type: ignore[arg-type]

    messages = cm.get_messages()
    system_messages = [m for m in messages if m.get("role") == "system"]
    assert len(system_messages) == 1
    assert system_messages[0].get("content", "") == "Custom system prompt for context test."
