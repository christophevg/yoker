"""Tests for /skills slash command."""

from unittest.mock import Mock

import pytest

from yoker.skills import Skill, SkillRegistry
from yoker.ui.commands import CommandRegistry
from yoker.ui.commands.skills import create_command as create_skills_command


class TestSkillsCommand:
  """Test /skills command creation and invocation."""

  def _make_agent(self, skills=None, directories=()):
    agent = Mock()
    agent.skills = skills
    agent.config.skills.directories = directories
    return agent

  @pytest.mark.asyncio
  async def test_create_skills_command_empty_registry(self):
    """Test /skills command with empty registry."""
    agent = self._make_agent(skills=SkillRegistry())
    command = create_skills_command()

    result = await command.handler("", agent, Mock())
    assert "Loaded skills:" in result
    assert "No skills loaded" in result

  @pytest.mark.asyncio
  async def test_create_skills_command_single_skill(self):
    """Test /skills command with one skill."""
    registry = SkillRegistry()
    skill = Skill(
      simple_name="commit",
      description="Guide git commits",
      content="Instructions for committing...",
    )
    registry.register(skill)

    agent = self._make_agent(skills=registry)
    command = create_skills_command()
    result = await command.handler("", agent, Mock())

    assert "Loaded skills:" in result
    assert "commit" in result
    assert "Guide git commits" in result

  @pytest.mark.asyncio
  async def test_create_skills_command_multiple_skills(self):
    """Test /skills command with multiple skills."""
    registry = SkillRegistry()

    skill1 = Skill(
      simple_name="commit",
      description="Guide git commits",
      content="Commit instructions...",
    )
    skill2 = Skill(
      simple_name="review",
      description="Review code changes",
      content="Review instructions...",
    )
    skill3 = Skill(
      simple_name="test",
      description="Run tests",
      content="Test instructions...",
    )

    registry.register(skill1)
    registry.register(skill2)
    registry.register(skill3)

    agent = self._make_agent(skills=registry)
    command = create_skills_command()
    result = await command.handler("", agent, Mock())

    assert "Loaded skills:" in result
    assert "commit" in result
    assert "Guide git commits" in result
    assert "review" in result
    assert "Review code changes" in result
    assert "test" in result
    assert "Run tests" in result

  @pytest.mark.asyncio
  async def test_skills_command_namespaced_skill(self):
    """Test /skills command with namespaced skill."""
    registry = SkillRegistry()
    skill = Skill(
      simple_name="commit",
      description="Guide git commits",
      content="Commit instructions...",
      namespace="c3",
    )
    registry.register(skill)

    agent = self._make_agent(skills=registry)
    command = create_skills_command()
    result = await command.handler("", agent, Mock())

    assert "Loaded skills:" in result
    assert "c3:commit" in result
    assert "Guide git commits" in result

  @pytest.mark.asyncio
  async def test_skills_command_registered_in_command_registry(self):
    """Test that /skills command can be registered in CommandRegistry."""
    skill_registry = SkillRegistry()
    skill = Skill(
      simple_name="commit",
      description="Guide git commits",
      content="Commit instructions...",
    )
    skill_registry.register(skill)

    command_registry = CommandRegistry()
    command_registry.register(create_skills_command())

    agent = self._make_agent(skills=skill_registry)

    # Test dispatch
    result = await command_registry.dispatch("/skills", agent, Mock())
    assert result is not None
    assert "Loaded skills:" in result
    assert "commit" in result

  @pytest.mark.asyncio
  async def test_skills_command_ignores_args(self):
    """Test that /skills command ignores arguments."""
    registry = SkillRegistry()
    skill = Skill(
      simple_name="commit",
      description="Guide git commits",
      content="Commit instructions...",
    )
    registry.register(skill)

    agent = self._make_agent(skills=registry)
    command = create_skills_command()

    # Arguments should be ignored
    result1 = await command.handler("", agent, Mock())
    result2 = await command.handler("ignored args", agent, Mock())

    assert result1 == result2
    assert "Loaded skills:" in result1
    assert "commit" in result1

  @pytest.mark.asyncio
  async def test_skills_command_sorted_output(self):
    """Test that skills are listed in sorted order."""
    registry = SkillRegistry()

    # Register skills in non-alphabetical order
    skill3 = Skill(
      simple_name="zebra",
      description="Zebra skill",
      content="Zebra content...",
    )
    skill1 = Skill(
      simple_name="alpha",
      description="Alpha skill",
      content="Alpha content...",
    )
    skill2 = Skill(
      simple_name="middle",
      description="Middle skill",
      content="Middle content...",
    )

    registry.register(skill3)
    registry.register(skill1)
    registry.register(skill2)

    agent = self._make_agent(skills=registry)
    command = create_skills_command()
    result = await command.handler("", agent, Mock())

    # Verify sorted order within the config section
    lines = result.split("\n")
    skill_lines = [line for line in lines if "✓" in line]

    assert len(skill_lines) == 3
    assert "alpha" in skill_lines[0]
    assert "middle" in skill_lines[1]
    assert "zebra" in skill_lines[2]

  @pytest.mark.asyncio
  async def test_skills_command_mixed_namespaced_and_regular(self):
    """Test /skills command with mix of namespaced and regular skills."""
    registry = SkillRegistry()

    skill1 = Skill(
      simple_name="commit",
      description="Guide git commits",
      content="...",
    )
    skill2 = Skill(
      simple_name="commit",
      description="Guide git commits",
      content="...",
      namespace="c3",
    )
    skill3 = Skill(
      simple_name="review",
      description="Review code",
      content="...",
    )

    registry.register(skill1)
    registry.register(skill2)
    registry.register(skill3)

    agent = self._make_agent(skills=registry)
    command = create_skills_command()
    result = await command.handler("", agent, Mock())

    assert "Loaded skills:" in result
    assert "c3:commit" in result
    assert "commit" in result
    assert "review" in result
