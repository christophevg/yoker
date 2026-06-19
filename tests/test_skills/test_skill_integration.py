"""Integration test for dynamic skill invocation."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from yoker.config import Config, SkillsConfig
from yoker.skills import Skill, SkillRegistry
from yoker.ui.commands import create_default_registry


def test_dynamic_skill_invocation_registration():
  """Test that skill names are dispatchable via the default registry."""
  registry = SkillRegistry()
  skill1 = Skill(
    name="commit",
    description="Guide git commits",
    content="# Commit Guide\n\nSteps for committing...",
  )
  skill2 = Skill(
    name="review",
    description="Review code",
    content="# Review Guide\n\nSteps for reviewing...",
  )
  registry.register(skill1)
  registry.register(skill2)

  command_registry = create_default_registry()
  agent = Mock()
  agent.skill_registry = registry
  agent.inject_skill_context = Mock()
  agent.process = AsyncMock()

  # Skill names are not explicit commands but handled dynamically.
  assert command_registry.get("commit") is None
  assert command_registry.get("review") is None


@pytest.mark.asyncio
async def test_dynamic_skill_invocation_dispatch():
  """Test dynamic dispatch of skill commands."""
  registry = SkillRegistry()
  skill1 = Skill(
    name="commit",
    description="Guide git commits",
    content="# Commit Guide\n\nSteps for committing...",
  )
  skill2 = Skill(
    name="review",
    description="Review code",
    content="# Review Guide\n\nSteps for reviewing...",
  )
  registry.register(skill1)
  registry.register(skill2)

  command_registry = create_default_registry()
  agent = Mock()
  agent.skill_registry = registry
  agent.inject_skill_context = Mock()
  agent.process = AsyncMock()

  result = await command_registry.dispatch("/commit fix bug", agent, Mock())
  assert result is None
  agent.inject_skill_context.assert_called_once_with("commit", "fix bug")
  agent.process.assert_awaited_once_with("fix bug")

  result = await command_registry.dispatch("/review", agent, Mock())
  assert result is None


def test_skill_loading_from_config():
  """Test loading skills from configured directories."""
  with tempfile.TemporaryDirectory() as tmpdir:
    # Create skill files
    skill_dir = Path(tmpdir) / "skills"
    skill_dir.mkdir()

    skill_file = skill_dir / "test.md"
    skill_file.write_text(
      """---
name: test-skill
description: A test skill
---
# Test Skill
This is a test skill.
"""
    )

    # Create config with skills directory
    config = Config(skills=SkillsConfig(directories=(str(skill_dir),)))

    # This test verifies the config structure is correct
    assert config.skills.directories == (str(skill_dir),)
    assert config.skills.discovery is True


@pytest.mark.asyncio
async def test_namespaced_skill_invocation():
  """Test that namespaced skills are dispatched using their full name."""
  registry = SkillRegistry()
  skill = Skill(
    name="commit",
    description="Guide commits",
    content="Content...",
    namespace="c3",
  )
  registry.register(skill)

  command_registry = create_default_registry()
  agent = Mock()
  agent.skill_registry = registry
  agent.inject_skill_context = Mock()
  agent.process = AsyncMock()

  result = await command_registry.dispatch("/c3:commit", agent, Mock())
  assert result is None
  agent.inject_skill_context.assert_called_once_with("c3:commit", "")
