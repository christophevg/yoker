"""Tests for the UI-layer skill invocation command."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from yoker.agent import Agent
from yoker.exceptions import SkillError
from yoker.skills import Skill, SkillRegistry
from yoker.ui import BatchUIHandler
from yoker.ui.commands import create_default_registry
from yoker.ui.commands.skill_invoke import handle


class MockUI(BatchUIHandler):
  """UI handler that captures command output."""

  def __init__(self) -> None:
    super().__init__()
    self.command_results: list[str] = []

  def output_command_result(self, result: str) -> None:
    self.command_results.append(result)


class TestSkillInvokeCommand:
  """Tests for skill invocation via slash commands in the UI layer."""

  def _make_agent(self, skills=None):
    """Create a mock agent with skills registry."""
    agent = MagicMock(spec=Agent)
    agent.skills = skills if skills is not None else SkillRegistry()
    return agent

  @pytest.mark.asyncio
  async def test_invoke_with_args_processes_args(self):
    """Invoking a skill with args should inject context and process args."""
    registry = SkillRegistry()
    registry.register(Skill(simple_name="commit", description="Commit", content="..."))

    agent = self._make_agent(skills=registry)
    agent.process = AsyncMock(return_value="done")
    ui = MockUI()

    await handle("commit", "fix bug", agent, ui)

    agent.inject_skill_context.assert_called_once_with("commit", "fix bug")
    agent.process.assert_awaited_once_with("fix bug")

  @pytest.mark.asyncio
  async def test_invoke_without_args_processes_default_prompt(self):
    """Invoking a skill without args should use a default prompt."""
    registry = SkillRegistry()
    registry.register(Skill(simple_name="commit", description="Commit", content="..."))

    agent = self._make_agent(skills=registry)
    agent.process = AsyncMock(return_value="done")
    ui = MockUI()

    await handle("commit", "", agent, ui)

    agent.inject_skill_context.assert_called_once_with("commit", "")
    agent.process.assert_awaited_once_with("Execute the skill as requested.")

  @pytest.mark.asyncio
  async def test_invoke_unknown_skill_raises(self):
    """Invoking an unknown skill should raise SkillError."""
    agent = self._make_agent()
    ui = MockUI()

    # Configure the mock to raise SkillError when inject_skill_context is called
    agent.inject_skill_context.side_effect = SkillError("missing", "Unknown skill")

    with pytest.raises(SkillError):
      await handle("missing", "", agent, ui)

  @pytest.mark.asyncio
  async def test_invoke_no_registry_raises(self):
    """Invoking a skill with no registry should raise SkillError."""
    agent = self._make_agent(skills=None)
    ui = MockUI()

    # Configure the mock to raise SkillError when inject_skill_context is called
    agent.inject_skill_context.side_effect = SkillError("missing", "Unknown skill")

    with pytest.raises(SkillError):
      await handle("missing", "", agent, ui)

  @pytest.mark.asyncio
  async def test_dispatch_invokes_skill(self):
    """Registry dispatch should invoke skills dynamically."""
    registry = create_default_registry()
    skill_registry = SkillRegistry()
    skill_registry.register(
      Skill(simple_name="commit", description="Commit", content="commit instructions")
    )

    agent = self._make_agent(skills=skill_registry)
    agent.process = AsyncMock(return_value="done")
    ui = MockUI()

    with patch.object(agent, "inject_skill_context") as mock_inject:
      result = await registry.dispatch("/commit fix bug", agent, ui)

    mock_inject.assert_called_once_with("commit", "fix bug")
    agent.process.assert_awaited_once_with("fix bug")
    assert result is None
