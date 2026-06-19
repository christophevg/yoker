"""Skill registry for Yoker.

Manages available skills and provides lookup by name.
"""

from collections.abc import Iterator

from yoker.skills.schema import Skill


class SkillRegistry:
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

  def __init__(self) -> None:
    """Initialize an empty skill registry."""
    self._skills: dict[str, Skill] = {}

  def register(self, skill: Skill) -> None:
    """Register a skill in the registry.

    Args:
      skill: Skill object to register.

    Raises:
      ValueError: If a skill with the same name is already registered.
    """
    name = skill.name
    if name in self._skills:
      raise ValueError(f"Skill '{name}' is already registered")
    self._skills[name] = skill

  def unregister(self, name: str) -> None:
    """Remove a skill from the registry.

    Args:
      name: Skill name to remove (may include namespace).

    Raises:
      KeyError: If skill is not registered.
    """
    if name not in self._skills:
      raise KeyError(f"Skill '{name}' is not registered")
    del self._skills[name]

  def get(self, name: str) -> Skill | None:
    """Get a skill by name.

    Args:
      name: Skill name (may include namespace like 'pkg:skill').

    Returns:
      Skill object if found, None otherwise.
    """
    return self._skills.get(name)

  def __contains__(self, name: str) -> bool:
    """Check if a skill is registered.

    Args:
      name: Skill name to check.

    Returns:
      True if skill is registered, False otherwise.
    """
    return name in self._skills

  def __getitem__(self, name: str) -> Skill:
    """Get a skill by name (raises if not found).

    Args:
      name: Skill name to get.

    Returns:
      Skill object.

    Raises:
      KeyError: If skill is not registered.
    """
    if name not in self._skills:
      raise KeyError(f"Skill '{name}' is not registered")
    return self._skills[name]

  @property
  def names(self) -> list[str]:
    """Get list of all registered skill names.

    Returns:
      List of skill names (may include namespaces).
    """
    return sorted(self._skills.keys())

  @property
  def count(self) -> int:
    """Get the number of registered skills.

    Returns:
      Number of skills in the registry.
    """
    return len(self._skills)

  def __len__(self) -> int:
    """Get the number of registered skills."""
    return self.count

  def __iter__(self) -> Iterator[tuple[str, Skill]]:
    """Iterate over all registered skills.

    Yields:
      Tuples of (name, skill) for each registered skill.
    """
    for name in sorted(self._skills.keys()):
      yield name, self._skills[name]

  def list_skills(self) -> list[Skill]:
    """Get list of all registered skills.

    Returns:
      List of all Skill objects in the registry.
    """
    return [self._skills[name] for name in sorted(self._skills.keys())]

  def clear(self) -> None:
    """Remove all skills from the registry."""
    self._skills.clear()

  def update(self, skills: dict[str, Skill]) -> None:
    """Update registry with multiple skills.

    Args:
      skills: Dictionary of skills to add.

    Raises:
      ValueError: If any skill name is already registered.
    """
    for name, skill in skills.items():
      if name in self._skills:
        raise ValueError(f"Skill '{name}' is already registered")
      self._skills[name] = skill


def create_default_skill_registry() -> SkillRegistry:
  """Create a skill registry with no default skills.

  Skills are loaded dynamically from:
  - Configuration file (yoker.toml)
  - Package plugins (yoker --with <package>)

  Returns:
    Empty SkillRegistry instance.
  """
  return SkillRegistry()


__all__ = [
  "SkillRegistry",
  "create_default_skill_registry",
]
