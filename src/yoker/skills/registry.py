"""Skill registry for Yoker.

Manages available skills and provides lookup by name.
"""

from collections import UserDict
from typing import TYPE_CHECKING

from structlog import get_logger

from yoker.skills.schema import Skill

if TYPE_CHECKING:
  from yoker.plugins import PluginComponents

logger = get_logger(__name__)


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

  def register_all(self, skills: list[Skill], namespace: str) -> None:
    """Register a list of skills under a namespace.

    Mirrors :meth:`AgentRegistry.register_all`. Skills are already
    namespaced from plugin load.
    """
    logger.info("register_skills_started", namespace=namespace, count=len(skills))
    for skill in skills:
      self.register(skill)
      logger.info("skill_registered", name=skill.name, namespace=namespace)

  def register_plugin_skills(self, plugins: list["PluginComponents"]) -> None:
    """Register skills from clean plugin list.

    Consumes the generator output of :func:`load_plugins`. No filtering
    or security checks here — those happen in ``load_plugins``.
    """
    for plugin in plugins:
      if not plugin.skills:
        continue
      self.register_all(plugin.skills, namespace=plugin.source)
      logger.info("skills_registered", package=plugin.source, count=len(plugin.skills))

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
