"""Tests for skill tool implementation."""

import pytest

from yoker.skills import SkillRegistry
from yoker.skills.schema import Skill
from yoker.tools import ToolRegistry, make_skill_tool


def _skill_spec(skill_registry: SkillRegistry):
  """Create and register the skill tool."""
  registry = ToolRegistry()
  return registry.register(make_skill_tool(skill_registry))


class TestSkillTool:
  """Tests for skill tool."""

  def test_skill_tool_name_and_description(self) -> None:
    """Skill tool spec has correct name and description."""
    registry = SkillRegistry()
    spec = _skill_spec(registry)

    assert spec.name == "skill"
    assert "invoke a skill" in spec.description.lower()

  def test_skill_tool_schema(self) -> None:
    """Skill tool returns valid Ollama-compatible schema."""
    registry = SkillRegistry()
    spec = _skill_spec(registry)

    schema = spec.schema

    assert schema["type"] == "function"
    assert schema["function"]["name"] == "skill"
    assert "skill_name" in schema["function"]["parameters"]["properties"]
    assert "args" in schema["function"]["parameters"]["properties"]
    assert "skill_name" in schema["function"]["parameters"]["required"]

  @pytest.mark.asyncio
  async def test_skill_tool_invokes_existing_skill(self) -> None:
    """Skill tool returns skill content when skill exists."""
    # Create skill
    skill = Skill(
      name="example",
      description="Example skill",
      content="# Example Skill\n\nThis is an example skill.",
      triggers=["use example skill"],
    )

    # Create registry with skill
    registry = SkillRegistry()
    registry.register(skill)

    # Create tool spec
    spec = _skill_spec(registry)

    # Invoke skill
    result = await spec.execute(skill_name="example")

    assert result.success is True
    assert "<command-name>example</command-name>" in result.result
    assert "Example Skill" in result.result

  @pytest.mark.asyncio
  async def test_skill_tool_invokes_skill_with_args(self) -> None:
    """Skill tool passes args to skill invocation."""
    # Create skill
    skill = Skill(
      name="commit",
      description="Guide git commits",
      content="# Commit Skill\n\nCreate atomic commits.",
      triggers=["commit changes"],
    )

    # Create registry with skill
    registry = SkillRegistry()
    registry.register(skill)

    # Create tool spec
    spec = _skill_spec(registry)

    # Invoke skill with args
    result = await spec.execute(skill_name="commit", args="fix authentication bug")

    assert result.success is True
    assert "<command-args>fix authentication bug</command-args>" in result.result
    assert "Commit Skill" in result.result

  @pytest.mark.asyncio
  async def test_skill_tool_returns_error_for_unknown_skill(self) -> None:
    """Skill tool returns error when skill doesn't exist."""
    # Create empty registry
    registry = SkillRegistry()

    # Create tool spec
    spec = _skill_spec(registry)

    # Try to invoke non-existent skill
    result = await spec.execute(skill_name="nonexistent")

    assert result.success is False
    assert result.error is not None
    assert "Unknown skill: nonexistent" in result.error

  @pytest.mark.asyncio
  async def test_skill_tool_lists_available_skills_in_error(self) -> None:
    """Skill tool error message lists available skills."""
    # Create registry with some skills
    registry = SkillRegistry()
    registry.register(Skill(name="commit", description="Guide commits", content="...", triggers=[]))
    registry.register(Skill(name="example", description="Example", content="...", triggers=[]))

    # Create tool spec
    spec = _skill_spec(registry)

    # Try to invoke non-existent skill
    result = await spec.execute(skill_name="nonexistent")

    assert result.success is False
    assert "commit" in result.error or "example" in result.error
    assert "Available skills:" in result.error

  @pytest.mark.asyncio
  async def test_skill_tool_works_with_namespaced_skill(self) -> None:
    """Skill tool handles namespaced skills (pkg:skill)."""
    # Create namespaced skill
    skill = Skill(
      name="create",
      namespace="pkgq",
      description="Create package docs",
      content="# Create\n\nGenerate PACKAGE.md",
      triggers=[],
    )

    # Create registry with skill
    registry = SkillRegistry()
    registry.register(skill)

    # Create tool spec
    spec = _skill_spec(registry)

    # Invoke skill with full name
    result = await spec.execute(skill_name="pkgq:create")

    assert result.success is True
    assert "<command-name>pkgq:create</command-name>" in result.result

  @pytest.mark.asyncio
  async def test_skill_tool_empty_args(self) -> None:
    """Skill tool handles empty args correctly."""
    # Create skill
    skill = Skill(
      name="example",
      description="Example",
      content="# Example",
      triggers=[],
    )

    registry = SkillRegistry()
    registry.register(skill)

    spec = _skill_spec(registry)

    # Invoke without args
    result = await spec.execute(skill_name="example", args="")

    assert result.success is True
    assert "<command-args></command-args>" in result.result
