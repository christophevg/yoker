"""Tests for /skills slash command."""

from unittest.mock import Mock

from yoker.commands import CommandRegistry, create_skills_command
from yoker.skills import Skill, SkillRegistry


class TestSkillsCommand:
  """Test /skills command creation and invocation."""

  def test_create_skills_command_empty_registry(self):
    """Test /skills command with empty registry."""
    registry = SkillRegistry()
    config = Mock()
    config.skills.directories = []
    command = create_skills_command(registry, config)

    result = command.handler([])
    assert "Loaded skills:" in result
    assert "No skills loaded" in result

  def test_create_skills_command_single_skill(self):
    """Test /skills command with one skill."""
    registry = SkillRegistry()
    skill = Skill(
      name="commit",
      description="Guide git commits",
      content="Instructions for committing...",
    )
    registry.register(skill)
    config = Mock()
    config.skills.directories = []

    command = create_skills_command(registry, config)
    result = command.handler([])

    assert "Loaded skills:" in result
    assert "commit" in result
    assert "Guide git commits" in result

  def test_create_skills_command_multiple_skills(self):
    """Test /skills command with multiple skills."""
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
    config = Mock()
    config.skills.directories = []

    command = create_skills_command(registry, config)
    result = command.handler([])

    assert "Loaded skills:" in result
    assert "commit" in result
    assert "Guide git commits" in result
    assert "review" in result
    assert "Review code changes" in result
    assert "test" in result
    assert "Run tests" in result

  def test_skills_command_namespaced_skill(self):
    """Test /skills command with namespaced skill."""
    registry = SkillRegistry()
    skill = Skill(
      name="commit",
      description="Guide git commits",
      content="Commit instructions...",
      namespace="c3",
    )
    registry.register(skill)
    config = Mock()
    config.skills.directories = []

    command = create_skills_command(registry, config)
    result = command.handler([])

    assert "Loaded skills:" in result
    assert "c3:commit" in result
    assert "Guide git commits" in result

  def test_skills_command_registered_in_command_registry(self):
    """Test that /skills command can be registered in CommandRegistry."""
    skill_registry = SkillRegistry()
    skill = Skill(
      name="commit",
      description="Guide git commits",
      content="Commit instructions...",
    )
    skill_registry.register(skill)
    config = Mock()
    config.skills.directories = []

    command_registry = CommandRegistry()
    skills_command = create_skills_command(skill_registry, config)
    command_registry.register(skills_command)

    # Test dispatch
    result = command_registry.dispatch("/skills")
    assert result is not None
    assert "Loaded skills:" in result
    assert "commit" in result

  def test_skills_command_ignores_args(self):
    """Test that /skills command ignores arguments."""
    registry = SkillRegistry()
    skill = Skill(
      name="commit",
      description="Guide git commits",
      content="Commit instructions...",
    )
    registry.register(skill)
    config = Mock()
    config.skills.directories = []

    command = create_skills_command(registry, config)

    # Arguments should be ignored
    result1 = command.handler([])
    result2 = command.handler(["ignored", "args"])

    assert result1 == result2
    assert "Loaded skills:" in result1
    assert "commit" in result1

  def test_skills_command_sorted_output(self):
    """Test that skills are listed in sorted order."""
    registry = SkillRegistry()

    # Register skills in non-alphabetical order
    skill3 = Skill(
      name="zebra",
      description="Zebra skill",
      content="Zebra content...",
    )
    skill1 = Skill(
      name="alpha",
      description="Alpha skill",
      content="Alpha content...",
    )
    skill2 = Skill(
      name="middle",
      description="Middle skill",
      content="Middle content...",
    )

    registry.register(skill3)
    registry.register(skill1)
    registry.register(skill2)
    config = Mock()
    config.skills.directories = []

    command = create_skills_command(registry, config)
    result = command.handler([])

    # Verify sorted order (alpha, middle, zebra)
    lines = result.split("\n")
    skill_lines = [line for line in lines if "✓" in line]

    assert len(skill_lines) == 3
    assert "alpha" in skill_lines[0]
    assert "middle" in skill_lines[1]
    assert "zebra" in skill_lines[2]

  def test_skills_command_mixed_namespaced_and_regular(self):
    """Test /skills command with mix of namespaced and regular skills."""
    registry = SkillRegistry()

    skill1 = Skill(
      name="commit",
      description="Guide git commits",
      content="...",
    )
    skill2 = Skill(
      name="commit",
      description="Guide git commits",
      content="...",
      namespace="c3",
    )
    skill3 = Skill(
      name="review",
      description="Review code",
      content="...",
    )

    registry.register(skill1)
    registry.register(skill2)
    registry.register(skill3)
    config = Mock()
    config.skills.directories = []

    command = create_skills_command(registry, config)
    result = command.handler([])

    assert "Loaded skills:" in result
    # c3:commit should come before commit (alphabetically)
    assert "c3:commit" in result
    assert "commit" in result
    assert "review" in result
