"""Tests for skill registry."""

import pytest

from yoker.skills.registry import SkillRegistry, create_default_skill_registry
from yoker.skills.schema import Skill


class TestSkillRegistry:
  """Tests for SkillRegistry class."""

  def test_register_skill(self) -> None:
    """Register a skill in the registry."""
    registry = SkillRegistry()
    skill = Skill(
      name="test",
      description="Test skill",
      content="Test content",
    )

    registry.register(skill)

    assert "test" in registry
    assert registry.count == 1

  def test_register_duplicate_skill_raises(self) -> None:
    """Registering duplicate skill raises error."""
    registry = SkillRegistry()
    skill1 = Skill(name="test", description="First", content="Content 1")
    skill2 = Skill(name="test", description="Second", content="Content 2")

    registry.register(skill1)

    with pytest.raises(ValueError) as exc_info:
      registry.register(skill2)

    assert "already registered" in str(exc_info.value)

  def test_unregister_skill(self) -> None:
    """Unregister a skill from the registry."""
    registry = SkillRegistry()
    skill = Skill(name="test", description="Test", content="Content")

    registry.register(skill)
    registry.unregister("test")

    assert "test" not in registry
    assert registry.count == 0

  def test_unregister_nonexistent_raises(self) -> None:
    """Unregistering nonexistent skill raises error."""
    registry = SkillRegistry()

    with pytest.raises(KeyError) as exc_info:
      registry.unregister("nonexistent")

    assert "not registered" in str(exc_info.value)

  def test_get_skill(self) -> None:
    """Get a skill by name."""
    registry = SkillRegistry()
    skill = Skill(name="test", description="Test", content="Content")

    registry.register(skill)

    result = registry.get("test")
    assert result is not None
    assert result.name == "test"
    assert result.description == "Test"

  def test_get_nonexistent_skill(self) -> None:
    """Getting nonexistent skill returns None."""
    registry = SkillRegistry()

    result = registry.get("nonexistent")
    assert result is None

  def test_getitem_skill(self) -> None:
    """Get skill using bracket notation."""
    registry = SkillRegistry()
    skill = Skill(name="test", description="Test", content="Content")

    registry.register(skill)

    result = registry["test"]
    assert result.name == "test"

  def test_getitem_nonexistent_raises(self) -> None:
    """Getting nonexistent skill with brackets raises error."""
    registry = SkillRegistry()

    with pytest.raises(KeyError) as exc_info:
      registry["nonexistent"]

    assert "not registered" in str(exc_info.value)

  def test_contains_skill(self) -> None:
    """Check if skill is registered."""
    registry = SkillRegistry()
    skill = Skill(name="test", description="Test", content="Content")

    assert "test" not in registry

    registry.register(skill)

    assert "test" in registry

  def test_names_property(self) -> None:
    """Get list of registered skill names."""
    registry = SkillRegistry()
    skill1 = Skill(name="alpha", description="A", content="Content A")
    skill2 = Skill(name="beta", description="B", content="Content B")

    registry.register(skill1)
    registry.register(skill2)

    assert registry.names == ["alpha", "beta"]

  def test_count_property(self) -> None:
    """Get count of registered skills."""
    registry = SkillRegistry()

    assert registry.count == 0

    skill1 = Skill(name="a", description="A", content="Content A")
    skill2 = Skill(name="b", description="B", content="Content B")

    registry.register(skill1)
    registry.register(skill2)

    assert registry.count == 2

  def test_len(self) -> None:
    """Get length of registry."""
    registry = SkillRegistry()
    skill = Skill(name="test", description="Test", content="Content")

    assert len(registry) == 0

    registry.register(skill)

    assert len(registry) == 1

  def test_iterate_skills(self) -> None:
    """Iterate over registered skills."""
    registry = SkillRegistry()
    skill1 = Skill(name="alpha", description="A", content="Content A")
    skill2 = Skill(name="beta", description="B", content="Content B")

    registry.register(skill1)
    registry.register(skill2)

    names = []
    for name, skill in registry:
      names.append(name)
      assert isinstance(skill, Skill)

    assert names == ["alpha", "beta"]

  def test_list_skills(self) -> None:
    """Get list of all registered skills."""
    registry = SkillRegistry()
    skill1 = Skill(name="a", description="A", content="Content A")
    skill2 = Skill(name="b", description="B", content="Content B")

    registry.register(skill1)
    registry.register(skill2)

    skills = registry.list_skills()

    assert len(skills) == 2
    assert skills[0].name == "a"
    assert skills[1].name == "b"

  def test_clear_registry(self) -> None:
    """Clear all skills from registry."""
    registry = SkillRegistry()
    skill = Skill(name="test", description="Test", content="Content")

    registry.register(skill)
    registry.clear()

    assert registry.count == 0
    assert "test" not in registry

  def test_update_registry(self) -> None:
    """Update registry with multiple skills."""
    registry = SkillRegistry()
    skill1 = Skill(name="a", description="A", content="Content A")
    skill2 = Skill(name="b", description="B", content="Content B")

    registry.update({"a": skill1, "b": skill2})

    assert registry.count == 2
    assert "a" in registry
    assert "b" in registry

  def test_update_duplicate_raises(self) -> None:
    """Update with duplicate names raises error."""
    registry = SkillRegistry()
    skill1 = Skill(name="test", description="First", content="Content 1")
    skill2 = Skill(name="test", description="Second", content="Content 2")

    registry.register(skill1)

    with pytest.raises(ValueError) as exc_info:
      registry.update({"test": skill2})

    assert "already registered" in str(exc_info.value)

  def test_namespaced_skills(self) -> None:
    """Register and retrieve namespaced skills."""
    registry = SkillRegistry()
    skill1 = Skill(
      name="test",
      description="Test 1",
      content="Content 1",
      namespace="pkg",
    )
    skill2 = Skill(
      name="test",
      description="Test 2",
      content="Content 2",
      namespace="other",
    )

    registry.register(skill1)
    registry.register(skill2)

    # Both should be registered with full names
    assert "pkg:test" in registry
    assert "other:test" in registry

    # Get by full name
    result1 = registry.get("pkg:test")
    assert result1 is not None
    assert result1.namespace == "pkg"

    result2 = registry.get("other:test")
    assert result2 is not None
    assert result2.namespace == "other"


class TestCreateDefaultSkillRegistry:
  """Tests for create_default_skill_registry function."""

  def test_create_empty_registry(self) -> None:
    """Create default registry returns empty registry."""
    registry = create_default_skill_registry()

    assert registry.count == 0
    assert isinstance(registry, SkillRegistry)
