"""Tests for the UI-layer /skills command."""

from unittest.mock import MagicMock

import pytest

from yoker.agent import Agent
from yoker.skills import Skill, SkillRegistry
from yoker.ui import BatchUIHandler
from yoker.ui.commands import create_default_registry
from yoker.ui.commands.skills import DESCRIPTION, handle


class MockUI(BatchUIHandler):
  """UI handler that captures command output."""

  def __init__(self) -> None:
    super().__init__()
    self.command_results: list[str] = []

  def output_command_result(self, result: str) -> None:
    self.command_results.append(result)


class TestSkillsCommand:
  """Tests for /skills command in the UI layer."""

  @pytest.mark.asyncio
  async def test_skills_empty_registry(self):
    """/skills with no skills should report none loaded."""
    agent = MagicMock(spec=Agent)
    agent.skill_registry = SkillRegistry()
    agent.config.skills.directories = []
    ui = MockUI()

    result = await handle("", agent, ui)

    assert "Loaded skills:" in result
    assert "No skills loaded" in result

  @pytest.mark.asyncio
  async def test_skills_lists_configured_directories(self):
    """/skills should show configured directories when no skills are loaded."""
    agent = MagicMock(spec=Agent)
    agent.skill_registry = SkillRegistry()
    agent.config.skills.directories = ["/path/to/skills"]
    ui = MockUI()

    result = await handle("", agent, ui)

    assert "/path/to/skills" in result

  @pytest.mark.asyncio
  async def test_skills_lists_regular_skills(self):
    """/skills should list regular (non-namespaced) skills."""
    registry = SkillRegistry()
    registry.register(Skill(name="commit", description="Guide commits", content="..."))
    registry.register(Skill(name="review", description="Review code", content="..."))

    agent = MagicMock(spec=Agent)
    agent.skill_registry = registry
    agent.config.skills.directories = []
    ui = MockUI()

    result = await handle("", agent, ui)

    assert "From config:" in result
    assert "commit" in result
    assert "Guide commits" in result
    assert "review" in result

  @pytest.mark.asyncio
  async def test_skills_lists_namespaced_skills(self):
    """/skills should separate namespaced plugin and built-in skills."""
    registry = SkillRegistry()
    registry.register(Skill(name="demo", description="Demo skill", content="...", namespace="demo"))
    registry.register(
      Skill(name="builtin", description="Built-in skill", content="...", namespace="yoker")
    )

    agent = MagicMock(spec=Agent)
    agent.skill_registry = registry
    agent.config.skills.directories = []
    ui = MockUI()

    result = await handle("", agent, ui)

    assert "From plugins:" in result
    assert "demo:demo" in result
    assert "Built-in:" in result
    assert "yoker:builtin" in result

  @pytest.mark.asyncio
  async def test_skills_sorted(self):
    """/skills should list skills in sorted order."""
    registry = SkillRegistry()
    registry.register(Skill(name="zebra", description="Z", content="..."))
    registry.register(Skill(name="alpha", description="A", content="..."))

    agent = MagicMock(spec=Agent)
    agent.skill_registry = registry
    agent.config.skills.directories = []
    ui = MockUI()

    result = await handle("", agent, ui)

    zebra_index = result.index("zebra")
    alpha_index = result.index("alpha")
    assert alpha_index < zebra_index

  @pytest.mark.asyncio
  async def test_skills_registered_in_default_registry(self):
    """/skills should be dispatchable from the default registry."""
    registry = create_default_registry()
    agent = MagicMock(spec=Agent)
    agent.skill_registry = SkillRegistry()
    agent.config.skills.directories = []
    ui = MockUI()

    result = await registry.dispatch("/skills", agent, ui)

    assert "Loaded skills:" in result

  def test_description(self):
    """The /skills command should describe itself."""
    assert "skills" in DESCRIPTION.lower()
