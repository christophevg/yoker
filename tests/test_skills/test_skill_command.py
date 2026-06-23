"""Tests for dynamic skill invocation slash commands."""

from unittest.mock import AsyncMock, Mock

import pytest

from yoker.skills import Skill, SkillRegistry
from yoker.ui.commands import create_default_registry
from yoker.ui.commands.skill_invoke import handle


class TestSkillInvocation:
  """Test dynamic skill invocation via the UI command registry."""

  def _make_agent(self, skills=()):
    registry = SkillRegistry()
    for skill in skills:
      registry.register(skill)

    agent = Mock()
    agent.skills = registry
    agent.inject_skill_context = Mock()
    agent.process = AsyncMock()
    return agent, registry

  @pytest.mark.asyncio
  async def test_dynamic_skill_invocation_empty_registry(self):
    """Unknown skill command returns an error when registry is empty."""
    agent, _ = self._make_agent()
    registry = create_default_registry()

    result = await registry.dispatch("/commit", agent, Mock())
    assert result is not None
    assert "Unknown command" in result

  @pytest.mark.asyncio
  async def test_dynamic_skill_invocation_single_skill(self):
    """A skill name is dispatched to inject_skill_context and process."""
    agent, _ = self._make_agent(
      [
        Skill(
          simple_name="commit",
          description="Guide git commits",
          content="# Commit Guide\n\nSteps for committing...",
        )
      ]
    )
    registry = create_default_registry()

    result = await registry.dispatch("/commit", agent, Mock())
    assert result is None
    agent.inject_skill_context.assert_called_once_with("commit", "")
    agent.process.assert_awaited_once_with("Execute the skill as requested.")

  @pytest.mark.asyncio
  async def test_dynamic_skill_invocation_with_args(self):
    """Skill invocation passes arguments through."""
    agent, _ = self._make_agent(
      [
        Skill(
          simple_name="commit",
          description="Guide git commits",
          content="# Commit Guide\n\nSteps for committing...",
        )
      ]
    )
    registry = create_default_registry()

    result = await registry.dispatch("/commit fix authentication bug", agent, Mock())
    assert result is None
    agent.inject_skill_context.assert_called_once_with("commit", "fix authentication bug")
    agent.process.assert_awaited_once_with("fix authentication bug")

  @pytest.mark.asyncio
  async def test_dynamic_skill_invocation_namespaced_skill(self):
    """Namespaced skills are dispatched using their full name."""
    agent, _ = self._make_agent(
      [
        Skill(
          simple_name="commit",
          description="Guide git commits",
          content="Commit instructions...",
          namespace="c3",
        )
      ]
    )
    registry = create_default_registry()

    result = await registry.dispatch("/c3:commit", agent, Mock())
    assert result is None
    agent.inject_skill_context.assert_called_once_with("c3:commit", "")

  @pytest.mark.asyncio
  async def test_handle_unknown_skill_raises(self):
    """handle() raises SkillError for an unknown skill."""
    agent, _ = self._make_agent()

    from yoker.exceptions import SkillError

    # Configure the mock to raise SkillError when skill is not found
    def inject_context(skill_name, args):
      skill = agent.skills.get(skill_name)
      if skill is None:
        available = ", ".join(agent.skills.names)
        raise SkillError(
          skill_name,
          f"Unknown skill. Available skills: {available}" if available else "Unknown skill",
        )

    agent.inject_skill_context = inject_context

    with pytest.raises(SkillError):
      await handle("commit", "", agent, Mock())

  @pytest.mark.asyncio
  async def test_handle_with_args(self):
    """handle() forwards arguments as the follow-up prompt."""
    agent, _ = self._make_agent(
      [
        Skill(
          simple_name="search",
          description="Search for code",
          content="Search instructions...",
        )
      ]
    )

    await handle("search", "find the bug", agent, Mock())
    agent.inject_skill_context.assert_called_once_with("search", "find the bug")
    agent.process.assert_awaited_once_with("find the bug")

  @pytest.mark.asyncio
  async def test_handle_no_args_uses_default_prompt(self):
    """handle() uses a default prompt when no arguments are provided."""
    agent, _ = self._make_agent(
      [
        Skill(
          simple_name="help",
          description="Show help",
          content="Help content...",
        )
      ]
    )

    await handle("help", "", agent, Mock())
    agent.inject_skill_context.assert_called_once_with("help", "")
    agent.process.assert_awaited_once_with("Execute the skill as requested.")
