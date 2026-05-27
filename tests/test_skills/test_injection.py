"""Tests for skill injection functions."""


from yoker.skills.injection import (
  build_skill_context_message,
  format_discovery_block,
  format_invocation_block,
  match_skill_by_trigger,
)
from yoker.skills.schema import Skill


class TestFormatDiscoveryBlock:
  """Tests for format_discovery_block function."""

  def test_format_empty_skills(self) -> None:
    """Format discovery block with no skills returns empty string."""
    result = format_discovery_block([])

    assert result == ""

  def test_format_single_skill(self) -> None:
    """Format discovery block with single skill."""
    skill = Skill(
      name="commit",
      description="Guide git commits",
      content="Full content...",
    )

    result = format_discovery_block([skill])

    assert "<system-reminder>" in result
    assert "</system-reminder>" in result
    assert "commit: Guide git commits" in result

  def test_format_multiple_skills(self) -> None:
    """Format discovery block with multiple skills."""
    skills = [
      Skill(name="commit", description="Guide commits", content="..."),
      Skill(name="test", description="Run tests", content="..."),
    ]

    result = format_discovery_block(skills)

    assert "commit: Guide commits" in result
    assert "test: Run tests" in result

  def test_format_namespaced_skill(self) -> None:
    """Format discovery block with namespaced skill."""
    skill = Skill(
      name="find",
      description="Find packages",
      content="...",
      namespace="pkgq",
    )

    result = format_discovery_block([skill])

    assert "pkgq:find: Find packages" in result

  def test_format_sorted_by_name(self) -> None:
    """Discovery block lists skills sorted by name."""
    skills = [
      Skill(name="zebra", description="Z skill", content="..."),
      Skill(name="alpha", description="A skill", content="..."),
      Skill(name="middle", description="M skill", content="..."),
    ]

    result = format_discovery_block(skills)

    # Check order in the output
    lines = result.split("\n")
    skill_lines = [line for line in lines if line.startswith("- ")]
    assert skill_lines[0] == "- alpha: A skill"
    assert skill_lines[1] == "- middle: M skill"
    assert skill_lines[2] == "- zebra: Z skill"


class TestFormatInvocationBlock:
  """Tests for format_invocation_block function."""

  def test_format_basic_invocation(self) -> None:
    """Format basic skill invocation."""
    skill = Skill(
      name="commit",
      description="Guide commits",
      content="# commit\n\nGuide git commits...",
    )

    result = format_invocation_block(skill)

    assert "<command-message>" in result
    assert "<command-name>commit</command-name>" in result
    assert "<command-args></command-args>" in result
    assert "</command-message>" in result
    assert "# commit" in result
    assert "Guide git commits..." in result

  def test_format_invocation_with_args(self) -> None:
    """Format skill invocation with arguments."""
    skill = Skill(
      name="commit",
      description="Guide commits",
      content="Content...",
    )

    result = format_invocation_block(skill, "fix authentication bug")

    assert "<command-args>fix authentication bug</command-args>" in result

  def test_format_invocation_namespaced_skill(self) -> None:
    """Format invocation of namespaced skill."""
    skill = Skill(
      name="find",
      description="Find packages",
      content="Content...",
      namespace="pkgq",
    )

    result = format_invocation_block(skill)

    assert "<command-name>pkgq:find</command-name>" in result

  def test_format_invocation_includes_base_directory(self) -> None:
    """Invocation block includes base directory context."""
    skill = Skill(
      name="test",
      description="Test skill",
      content="Content...",
    )

    result = format_invocation_block(skill)

    assert "Base directory for this skill:" in result

  def test_format_invocation_preserves_content(self) -> None:
    """Invocation block preserves full skill content."""
    skill = Skill(
      name="test",
      description="Test skill",
      content="""# Test Skill

This is a multi-line
skill content with:

- Lists
- More content

## Section

Details here.
""",
    )

    result = format_invocation_block(skill)

    assert "# Test Skill" in result
    assert "multi-line" in result
    assert "- Lists" in result
    assert "## Section" in result


class TestBuildSkillContextMessage:
  """Tests for build_skill_context_message function."""

  def test_build_discovery_context(self) -> None:
    """Build discovery context message."""
    skills = [
      Skill(name="commit", description="Guide commits", content="..."),
    ]

    result = build_skill_context_message(skills, is_discovery=True)

    assert "<system-reminder>" in result
    assert "commit:" in result

  def test_build_invocation_context(self) -> None:
    """Build invocation context message."""
    skill = Skill(
      name="commit",
      description="Guide commits",
      content="Full content...",
    )

    result = build_skill_context_message([skill], is_discovery=False)

    assert "<command-message>" in result
    assert "Full content..." in result

  def test_build_empty_invocation(self) -> None:
    """Build invocation with no skills returns empty string."""
    result = build_skill_context_message([], is_discovery=False)

    assert result == ""


class TestMatchSkillByTrigger:
  """Tests for match_skill_by_trigger function."""

  def test_match_by_trigger(self) -> None:
    """Match skill by trigger phrase."""
    skills = [
      Skill(
        name="commit",
        description="Guide commits",
        content="...",
        triggers=("commit these changes", "create a commit"),
      ),
      Skill(
        name="test",
        description="Run tests",
        content="...",
        triggers=("run tests", "test this"),
      ),
    ]

    skill, remaining = match_skill_by_trigger("commit these changes now", skills)

    assert skill is not None
    assert skill.name == "commit"
    assert remaining == "now"

  def test_match_first_trigger(self) -> None:
    """Match uses first matching trigger."""
    skills = [
      Skill(
        name="commit",
        description="Guide commits",
        content="...",
        triggers=("commit",),
      ),
      Skill(
        name="test",
        description="Run tests",
        content="...",
        triggers=("commit",),  # Same trigger
      ),
    ]

    skill, remaining = match_skill_by_trigger("commit changes", skills)

    assert skill is not None
    assert skill.name == "commit"

  def test_no_match_returns_none(self) -> None:
    """No match returns None and original message."""
    skills = [
      Skill(
        name="commit",
        description="Guide commits",
        content="...",
        triggers=("commit these changes",),
      ),
    ]

    skill, remaining = match_skill_by_trigger("do something else", skills)

    assert skill is None
    assert remaining == "do something else"

  def test_case_insensitive_match(self) -> None:
    """Match is case insensitive."""
    skills = [
      Skill(
        name="commit",
        description="Guide commits",
        content="...",
        triggers=("Commit These Changes",),
      ),
    ]

    skill, remaining = match_skill_by_trigger("COMMIT THESE CHANGES now", skills)

    assert skill is not None
    assert skill.name == "commit"

  def test_match_skill_without_triggers(self) -> None:
    """Skills without triggers don't match."""
    skills = [
      Skill(
        name="commit",
        description="Guide commits",
        content="...",
        triggers=(),
      ),
    ]

    skill, remaining = match_skill_by_trigger("commit changes", skills)

    assert skill is None

  def test_match_removes_trigger_from_message(self) -> None:
    """Match removes trigger from remaining message."""
    skills = [
      Skill(
        name="commit",
        description="Guide commits",
        content="...",
        triggers=("commit",),
      ),
    ]

    skill, remaining = match_skill_by_trigger("Please commit my changes", skills)

    assert skill is not None
    assert "commit" not in remaining
    assert "Please" in remaining or "my changes" in remaining
