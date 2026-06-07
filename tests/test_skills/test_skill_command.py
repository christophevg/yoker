"""Tests for skill slash command."""

import pytest

from yoker.commands import CommandRegistry, create_skill_commands
from yoker.skills import Skill, SkillRegistry


class TestSkillCommand:
  """Test skill command creation and invocation."""

  def test_create_skill_commands_empty_registry(self):
    """Test creating commands from empty registry."""
    registry = SkillRegistry()
    commands = create_skill_commands(registry, lambda: registry)
    assert commands == []

  def test_create_skill_commands_single_skill(self):
    """Test creating commands from registry with one skill."""
    registry = SkillRegistry()
    skill = Skill(
      name="commit",
      description="Guide git commits",
      content="Instructions for committing...",
    )
    registry.register(skill)

    commands = create_skill_commands(registry, lambda: registry)
    assert len(commands) == 1
    assert commands[0].name == "commit"
    assert commands[0].description == "Guide git commits"

  def test_create_skill_commands_multiple_skills(self):
    """Test creating commands from registry with multiple skills."""
    registry = SkillRegistry()

    skill1 = Skill(
      name="commit",
      description="Guide git commits",
      content="Commit instructions...",
    )
    skill2 = Skill(
      name="review",
      description="Review code changes",
      content="Review instructions...",
    )
    skill3 = Skill(
      name="test",
      description="Run tests",
      content="Test instructions...",
    )

    registry.register(skill1)
    registry.register(skill2)
    registry.register(skill3)

    commands = create_skill_commands(registry, lambda: registry)
    assert len(commands) == 3
    names = {cmd.name for cmd in commands}
    assert names == {"commit", "review", "test"}

  def test_skill_command_handler_no_args(self):
    """Test skill command handler with no arguments."""
    registry = SkillRegistry()
    skill = Skill(
      name="commit",
      description="Guide git commits",
      content="# Commit Guide\n\nSteps for committing...",
    )
    registry.register(skill)

    commands = create_skill_commands(registry, lambda: registry)
    command = commands[0]

    result = command.handler([])
    assert "commit" in result
    assert "Commit Guide" in result
    assert "Steps for committing" in result

  def test_skill_command_handler_with_args(self):
    """Test skill command handler with arguments."""
    registry = SkillRegistry()
    skill = Skill(
      name="commit",
      description="Guide git commits",
      content="# Commit Guide\n\nSteps for committing...",
    )
    registry.register(skill)

    commands = create_skill_commands(registry, lambda: registry)
    command = commands[0]

    result = command.handler(["fix", "authentication", "bug"])
    assert "<command-name>commit</command-name>" in result
    assert "<command-args>fix authentication bug</command-args>" in result
    assert "# Commit Guide" in result

  def test_skill_command_namespaced_skill(self):
    """Test skill command with namespaced skill."""
    registry = SkillRegistry()
    skill = Skill(
      name="commit",
      description="Guide git commits",
      content="Commit instructions...",
      namespace="c3",
    )
    registry.register(skill)

    commands = create_skill_commands(registry, lambda: registry)
    assert len(commands) == 1
    assert commands[0].name == "c3:commit"

  def test_skill_command_registered_in_command_registry(self):
    """Test that skill commands can be registered in CommandRegistry."""
    skill_registry = SkillRegistry()
    skill = Skill(
      name="commit",
      description="Guide git commits",
      content="Commit instructions...",
    )
    skill_registry.register(skill)

    command_registry = CommandRegistry()
    commands = create_skill_commands(skill_registry, lambda: skill_registry)

    for command in commands:
      command_registry.register(command)

    # Test dispatch
    result = command_registry.dispatch("/commit")
    assert result is not None
    assert "commit" in result.lower()

  def test_skill_command_with_triggers(self):
    """Test skill command with trigger phrases."""
    registry = SkillRegistry()
    skill = Skill(
      name="commit",
      description="Guide git commits",
      content="Commit instructions...",
      triggers=("commit changes", "create commit"),
    )
    registry.register(skill)

    commands = create_skill_commands(registry, lambda: registry)
    assert len(commands) == 1
    # Triggers don't affect command creation, they're for natural language matching
    assert commands[0].name == "commit"

  def test_skill_command_with_tools(self):
    """Test skill command with tool requirements."""
    registry = SkillRegistry()
    skill = Skill(
      name="review",
      description="Review code",
      content="Review instructions...",
      tools=("read", "search"),
    )
    registry.register(skill)

    commands = create_skill_commands(registry, lambda: registry)
    assert len(commands) == 1
    # Tools don't affect command creation, they're for skill metadata
    assert commands[0].name == "review"

  def test_skill_command_duplicate_handling(self):
    """Test that duplicate skill names raise error."""
    registry = SkillRegistry()
    skill1 = Skill(
      name="commit",
      description="First commit skill",
      content="Content 1",
    )
    skill2 = Skill(
      name="commit",
      description="Second commit skill",
      content="Content 2",
    )

    registry.register(skill1)
    with pytest.raises(ValueError, match="already registered"):
      registry.register(skill2)

  def test_skill_command_format_invocation_block(self):
    """Test that invocation block is properly formatted."""
    registry = SkillRegistry()
    skill = Skill(
      name="commit",
      description="Guide git commits",
      content="# Commit Guide\n\n1. Stage changes\n2. Write message\n3. Push",
    )
    registry.register(skill)

    commands = create_skill_commands(registry, lambda: registry)
    command = commands[0]

    result = command.handler(["fix bug"])

    # Check structure
    assert "<command-message>" in result
    assert "<command-name>commit</command-name>" in result
    assert "<command-args>fix bug</command-args>" in result
    assert "</command-message>" in result
    assert "Base directory for this skill:" in result
    assert "# Commit Guide" in result
    assert "1. Stage changes" in result

  def test_skill_command_empty_args(self):
    """Test skill command with empty args string."""
    registry = SkillRegistry()
    skill = Skill(
      name="help",
      description="Show help",
      content="Help content...",
    )
    registry.register(skill)

    commands = create_skill_commands(registry, lambda: registry)
    command = commands[0]

    result = command.handler([])
    assert "<command-args></command-args>" in result

  def test_skill_command_whitespace_args(self):
    """Test skill command with whitespace in args."""
    registry = SkillRegistry()
    skill = Skill(
      name="search",
      description="Search for code",
      content="Search instructions...",
    )
    registry.register(skill)

    commands = create_skill_commands(registry, lambda: registry)
    command = commands[0]

    result = command.handler(["find", "the", "bug"])
    assert "<command-args>find the bug</command-args>" in result

