"""Tests for skill resource loading via the skill tool."""

from pathlib import Path

import pytest

from yoker.builtin import make_skill_tool
from yoker.skills import SkillRegistry
from yoker.skills.schema import Skill
from yoker.tools import ToolRegistry


def _skill_spec(skill_registry: SkillRegistry):
  """Create and register the skill tool."""
  registry = ToolRegistry()
  return registry.register(make_skill_tool(skill_registry))


class TestSkillGetResource:
  """Tests for Skill.get_resource() method."""

  def test_get_resource_returns_content(self, tmp_path: Path) -> None:
    """get_resource returns the content of a resource file."""
    # Create a resource file
    (tmp_path / "references").mkdir()
    (tmp_path / "references" / "info.md").write_text("Reference info here.")

    skill = Skill(
      simple_name="myskill",
      description="Test skill",
      content="# My Skill",
      _base_dir=tmp_path,
    )

    content = skill.get_resource("references/info.md")
    assert content == "Reference info here."

  def test_get_resource_nested_path(self, tmp_path: Path) -> None:
    """get_resource handles nested resource paths."""
    (tmp_path / "patterns").mkdir()
    (tmp_path / "patterns" / "atomic-commits.md").write_text("Atomic commit patterns.")

    skill = Skill(
      simple_name="commit",
      description="Commit skill",
      content="# Commit",
      _base_dir=tmp_path,
    )

    content = skill.get_resource("patterns/atomic-commits.md")
    assert content == "Atomic commit patterns."

  def test_get_resource_no_base_dir_raises(self) -> None:
    """get_resource raises FileNotFoundError when _base_dir is None."""
    skill = Skill(
      simple_name="inline",
      description="Inline skill",
      content="# Inline",
      _base_dir=None,
    )

    with pytest.raises(FileNotFoundError, match="no base directory"):
      skill.get_resource("references/info.md")

  def test_get_resource_missing_file_raises(self, tmp_path: Path) -> None:
    """get_resource raises FileNotFoundError for non-existent resource."""
    skill = Skill(
      simple_name="myskill",
      description="Test skill",
      content="# My Skill",
      _base_dir=tmp_path,
    )

    with pytest.raises(FileNotFoundError, match="not found"):
      skill.get_resource("nonexistent.md")

  def test_get_resource_path_traversal_rejected(self, tmp_path: Path) -> None:
    """get_resource rejects paths containing '..'."""
    skill = Skill(
      simple_name="myskill",
      description="Test skill",
      content="# My Skill",
      _base_dir=tmp_path,
    )

    with pytest.raises(ValueError, match=r"\.\."):
      skill.get_resource("../secret.txt")


class TestSkillToolResource:
  """Tests for the resource parameter on the skill tool."""

  @pytest.mark.asyncio
  async def test_skill_tool_returns_resource_content(self, tmp_path: Path) -> None:
    """Skill tool returns resource content when resource is provided."""
    # Create a resource file
    (tmp_path / "references").mkdir()
    (tmp_path / "references" / "info.md").write_text("Important reference info.")

    skill = Skill(
      simple_name="myskill",
      description="Test skill",
      content="# My Skill\n\nSee references/info.md for details.",
      _base_dir=tmp_path,
    )

    registry = SkillRegistry()
    registry.register(skill)

    spec = _skill_spec(registry)

    result = await spec.execute(skill_name="myskill", resource="references/info.md")

    assert result.success is True
    assert result.result == "Important reference info."

  @pytest.mark.asyncio
  async def test_skill_tool_resource_not_found(self, tmp_path: Path) -> None:
    """Skill tool returns error for missing resource."""
    skill = Skill(
      simple_name="myskill",
      description="Test skill",
      content="# My Skill",
      _base_dir=tmp_path,
    )

    registry = SkillRegistry()
    registry.register(skill)

    spec = _skill_spec(registry)

    result = await spec.execute(skill_name="myskill", resource="nonexistent.md")

    assert result.success is False
    assert "not found" in result.error

  @pytest.mark.asyncio
  async def test_skill_tool_resource_no_base_dir(self) -> None:
    """Skill tool returns error when skill has no base_dir (inline skill)."""
    skill = Skill(
      simple_name="inline",
      description="Inline skill",
      content="# Inline Skill",
      _base_dir=None,
    )

    registry = SkillRegistry()
    registry.register(skill)

    spec = _skill_spec(registry)

    result = await spec.execute(skill_name="inline", resource="references/info.md")

    assert result.success is False
    assert "no base directory" in result.error

  @pytest.mark.asyncio
  async def test_skill_tool_resource_path_traversal(self, tmp_path: Path) -> None:
    """Skill tool rejects path traversal in resource path."""
    skill = Skill(
      simple_name="myskill",
      description="Test skill",
      content="# My Skill",
      _base_dir=tmp_path,
    )

    registry = SkillRegistry()
    registry.register(skill)

    spec = _skill_spec(registry)

    result = await spec.execute(skill_name="myskill", resource="../etc/passwd")

    assert result.success is False
    assert ".." in result.error

  @pytest.mark.asyncio
  async def test_skill_tool_resource_with_unknown_skill(self) -> None:
    """Skill tool returns 'unknown skill' error before checking resource."""
    registry = SkillRegistry()
    spec = _skill_spec(registry)

    result = await spec.execute(skill_name="nonexistent", resource="references/info.md")

    assert result.success is False
    assert "Unknown skill: nonexistent" in result.error

  @pytest.mark.asyncio
  async def test_skill_tool_resource_takes_precedence_over_args(self, tmp_path: Path) -> None:
    """When resource is provided, it takes precedence over skill invocation."""
    (tmp_path / "patterns").mkdir()
    (tmp_path / "patterns" / "guide.md").write_text("Pattern guide content.")

    skill = Skill(
      simple_name="myskill",
      description="Test skill",
      content="# My Skill",
      _base_dir=tmp_path,
    )

    registry = SkillRegistry()
    registry.register(skill)

    spec = _skill_spec(registry)

    # Both args and resource provided — resource wins
    result = await spec.execute(
      skill_name="myskill",
      args="some args",
      resource="patterns/guide.md",
    )

    assert result.success is True
    assert result.result == "Pattern guide content."

  @pytest.mark.asyncio
  async def test_skill_tool_no_resource_returns_invocation(self, tmp_path: Path) -> None:
    """Without resource parameter, normal skill invocation happens."""
    skill = Skill(
      simple_name="myskill",
      description="Test skill",
      content="# My Skill\n\nInstructions here.",
      _base_dir=tmp_path,
    )

    registry = SkillRegistry()
    registry.register(skill)

    spec = _skill_spec(registry)

    result = await spec.execute(skill_name="myskill")

    assert result.success is True
    assert "<command-name>myskill</command-name>" in result.result
    assert "My Skill" in result.result


class TestLoadSkillsResourceBaseDir:
  """Tests that load_skills correctly sets _base_dir."""

  def test_flat_skill_base_dir_is_skills_dir(self, tmp_path: Path) -> None:
    """Flat layout: _base_dir is the skills directory."""
    from yoker.skills import load_skills

    # Create a flat skill file
    (tmp_path / "myskill.md").write_text("---\nname: myskill\ndescription: Test\n---\n# My Skill")

    skills = load_skills(tmp_path)
    # load_skills defaults namespace to dir name
    skill = skills[f"{tmp_path.name}:myskill"]
    assert skill._base_dir == tmp_path

  def test_nested_skill_base_dir_is_subdir(self, tmp_path: Path) -> None:
    """Nested layout: _base_dir is the skill's subdirectory."""
    from yoker.skills import load_skills

    # Create a nested skill
    skill_dir = tmp_path / "commit"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: commit\ndescription: Test\n---\n# Commit Skill")
    # Create a resource file alongside
    (skill_dir / "patterns").mkdir()
    (skill_dir / "patterns" / "atomic-commits.md").write_text("Atomic patterns.")

    skills = load_skills(tmp_path)
    skill = skills[f"{tmp_path.name}:commit"]
    assert skill._base_dir == skill_dir

    # Resource can be loaded
    content = skill.get_resource("patterns/atomic-commits.md")
    assert content == "Atomic patterns."

  def test_load_skill_single_file_base_dir(self, tmp_path: Path) -> None:
    """load_skill (single file) sets _base_dir to file's parent."""
    from yoker.skills import load_skill

    skill_file = tmp_path / "myskill.md"
    skill_file.write_text("---\nname: myskill\ndescription: Test\n---\n# My Skill")
    # Create a resource in the same directory
    (tmp_path / "reference.md").write_text("Reference content.")

    skill = load_skill(skill_file)
    assert skill._base_dir == tmp_path

    content = skill.get_resource("reference.md")
    assert content == "Reference content."

  def test_inline_skill_no_base_dir(self) -> None:
    """Skills constructed in code have _base_dir=None."""
    skill = Skill(
      simple_name="inline",
      description="Inline skill",
      content="# Inline",
    )
    assert skill._base_dir is None
