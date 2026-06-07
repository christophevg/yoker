"""Tests for SkillTool implementation."""

import pytest

from yoker.skills import SkillRegistry
from yoker.skills.schema import Skill
from yoker.tools.skill import SkillTool


class TestSkillTool:
  """Tests for SkillTool class."""

  def test_skill_tool_name_and_description(self) -> None:
    """SkillTool has correct name and description."""
    registry = SkillRegistry()
    tool = SkillTool(skill_registry=registry)

    assert tool.name == "skill"
    assert "invoke a skill" in tool.description.lower()

  def test_skill_tool_schema(self) -> None:
    """SkillTool returns valid Ollama-compatible schema."""
    registry = SkillRegistry()
    tool = SkillTool(skill_registry=registry)

    schema = tool.get_schema()

    assert schema["type"] == "function"
    assert schema["function"]["name"] == "skill"
    assert "skill_name" in schema["function"]["parameters"]["properties"]
    assert "args" in schema["function"]["parameters"]["properties"]
    assert "skill_name" in schema["function"]["parameters"]["required"]

  @pytest.mark.asyncio
  async def test_skill_tool_invokes_existing_skill(self) -> None:
    """SkillTool returns skill content when skill exists."""
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

    # Create tool
    tool = SkillTool(skill_registry=registry)

    # Invoke skill
    result = await tool.execute(skill_name="example")

    assert result.success is True
    assert "<command-name>example</command-name>" in result.result
    assert "Example Skill" in result.result

  @pytest.mark.asyncio
  async def test_skill_tool_invokes_skill_with_args(self) -> None:
    """SkillTool passes args to skill invocation."""
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

    # Create tool
    tool = SkillTool(skill_registry=registry)

    # Invoke skill with args
    result = await tool.execute(skill_name="commit", args="fix authentication bug")

    assert result.success is True
    assert "<command-args>fix authentication bug</command-args>" in result.result
    assert "Commit Skill" in result.result

  @pytest.mark.asyncio
  async def test_skill_tool_returns_error_for_unknown_skill(self) -> None:
    """SkillTool returns error when skill doesn't exist."""
    # Create empty registry
    registry = SkillRegistry()

    # Create tool
    tool = SkillTool(skill_registry=registry)

    # Try to invoke non-existent skill
    result = await tool.execute(skill_name="nonexistent")

    assert result.success is False
    assert "Unknown skill: nonexistent" in result.result
    assert result.error is not None
    assert "Unknown skill: nonexistent" in result.error

  @pytest.mark.asyncio
  async def test_skill_tool_lists_available_skills_in_error(self) -> None:
    """SkillTool error message lists available skills."""
    # Create registry with some skills
    registry = SkillRegistry()
    registry.register(Skill(name="commit", description="Guide commits", content="...", triggers=[]))
    registry.register(Skill(name="example", description="Example", content="...", triggers=[]))

    # Create tool
    tool = SkillTool(skill_registry=registry)

    # Try to invoke non-existent skill
    result = await tool.execute(skill_name="nonexistent")

    assert result.success is False
    assert "commit" in result.result or "example" in result.result
    assert "Available skills:" in result.result

  @pytest.mark.asyncio
  async def test_skill_tool_works_with_namespaced_skill(self) -> None:
    """SkillTool handles namespaced skills (pkg:skill)."""
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

    # Create tool
    tool = SkillTool(skill_registry=registry)

    # Invoke skill with full name
    result = await tool.execute(skill_name="pkgq:create")

    assert result.success is True
    assert "<command-name>pkgq:create</command-name>" in result.result

  @pytest.mark.asyncio
  async def test_skill_tool_without_guardrail(self) -> None:
    """SkillTool works without guardrail (doesn't need one)."""
    registry = SkillRegistry()
    tool = SkillTool(skill_registry=registry)

    # Guardrail should be None for SkillTool
    assert tool._guardrail is None

  @pytest.mark.asyncio
  async def test_skill_tool_empty_args(self) -> None:
    """SkillTool handles empty args correctly."""
    # Create skill
    skill = Skill(
      name="example",
      description="Example",
      content="# Example",
      triggers=[],
    )

    registry = SkillRegistry()
    registry.register(skill)

    tool = SkillTool(skill_registry=registry)

    # Invoke without args
    result = await tool.execute(skill_name="example", args="")

    assert result.success is True
    assert "<command-args></command-args>" in result.result

