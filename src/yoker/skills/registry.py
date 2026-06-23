"""Skill registry for Yoker.

Manages available skills and provides lookup by name.
"""

from collections import UserDict

from yoker.skills.schema import Skill


class SkillRegistry(UserDict[str, Skill]):
  """Registry for skill definitions.

  Provides name-based lookup and iteration over available skills.
  Supports namespaced skills (e.g., 'pkg:skill').

  Example:
    registry = SkillRegistry()
    registry.register(skill)
    skill = registry.get("commit")
    for name, skill in registry:
      print(f"{name}: {skill.description}")
  """

  def register(self, skill: Skill) -> None:
    """Register a skill in the registry.

    Args:
      skill: Skill object to register.

    Raises:
      ValueError: If a skill with the same name is already registered.
    """
    name = skill.name
    if name in self.data:
      raise ValueError(f"Skill '{name}' is already registered")
    self.data[name] = skill

  @property
  def skills(self) -> list[Skill]:
    """Return all registered skills sorted by name."""
    return sorted(self.data.values(), key=lambda spec: spec.name)

  @property
  def namespaces(self) -> list[str]:
    """Return all registered skill namespaces sorted alphabetically."""
    return sorted([skill.namespace for skill in self.data.values() if skill.namespace])

  @property
  def names(self) -> list[str]:
    """Get list of all registered skill names.

    Returns:
      List of skill names (may include namespaces).
    """
    return sorted(self.data.keys())


__all__ = ["SkillRegistry"]
