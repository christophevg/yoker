"""Integration test for skill command loading."""

import os
import tempfile
from pathlib import Path

from yoker.commands import CommandRegistry, create_skill_commands
from yoker.config import Config
from yoker.skills import Skill, SkillRegistry


def test_skill_command_registration():
  """Test that skill commands are registered correctly."""
  # Create a skill registry with test skills
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

  # Create command registry and register skill commands
  command_registry = CommandRegistry()
  skill_commands = create_skill_commands(
    registry=registry,
    get_skill_registry=lambda: registry,
  )

  for command in skill_commands:
    command_registry.register(command)

  # Verify commands are registered
  assert command_registry.get("commit") is not None
  assert command_registry.get("review") is not None

  # Test command dispatch
  result = command_registry.dispatch("/commit fix bug")
  assert result is not None
  assert "<command-name>commit</command-name>" in result
  assert "<command-args>fix bug</command-args>" in result
  assert "# Commit Guide" in result

  result = command_registry.dispatch("/review")
  assert result is not None
  assert "<command-name>review</command-name>" in result
  assert "# Review Guide" in result


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
    from yoker.config.schema import SkillsConfig

    config = Config(skills=SkillsConfig(directories=(str(skill_dir),)))

    # Create agent (skills will be loaded in __main__.py)
    # This test verifies the config structure is correct
    assert config.skills.directories == (str(skill_dir),)
    assert config.skills.discovery is True


def test_skill_loading_from_env():
  """Test loading skills from YOKER_SKILLS_PATH environment variable."""
  with tempfile.TemporaryDirectory() as tmpdir:
    # Create skill files
    skill_dir = Path(tmpdir) / "env-skills"
    skill_dir.mkdir()

    skill_file = skill_dir / "env-skill.md"
    skill_file.write_text(
      """---
name: env-skill
description: Skill from env
---
# Env Skill
Loaded from environment variable.
"""
    )

    # Set environment variable
    old_env = os.environ.get("YOKER_SKILLS_PATH")
    try:
      os.environ["YOKER_SKILLS_PATH"] = str(skill_dir)

      # Load skills from env
      from yoker.skills import load_skills_from_env

      skills = load_skills_from_env()
      assert "env-skill" in skills
      assert skills["env-skill"].description == "Skill from env"
    finally:
      # Restore environment
      if old_env is not None:
        os.environ["YOKER_SKILLS_PATH"] = old_env
      else:
        os.environ.pop("YOKER_SKILLS_PATH", None)


def test_namespaced_skill_commands():
  """Test that namespaced skills create correct commands."""
  registry = SkillRegistry()
  skill = Skill(
    name="commit",
    description="Guide commits",
    content="Content...",
    namespace="c3",
  )
  registry.register(skill)

  commands = create_skill_commands(registry, lambda: registry)
  assert len(commands) == 1
  assert commands[0].name == "c3:commit"

  # Test dispatch
  command_registry = CommandRegistry()
  for command in commands:
    command_registry.register(command)

  result = command_registry.dispatch("/c3:commit")
  assert result is not None
  assert "<command-name>c3:commit</command-name>" in result
