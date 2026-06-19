"""Skill loading for plugins.

Thin delegate over :func:`yoker.skills.load_skills`: resolve the package's
skills directory via :mod:`yoker.resources`, then let the skills loader handle
flat/nested layouts, parsing and namespacing.
"""

from typing import TYPE_CHECKING

from structlog import get_logger

from yoker.resources import find_package_subdirectory
from yoker.skills import load_skills

if TYPE_CHECKING:
  from yoker.skills import Skill

log = get_logger(__name__)


def load_skills_from_package(
  package: str,
  skills_dir: str = "skills",
) -> list["Skill"]:
  """Load skills from a package's skills/ folder.

  Args:
    package: Package name.
    skills_dir: Directory name within the package.

  Returns:
    List of Skill objects loaded from the package (namespaced with the package
    name), or an empty list if the package has no such directory.
  """
  directory = find_package_subdirectory(package, skills_dir)
  if directory is None:
    return []
  return list(load_skills(directory, namespace=package).values())


__all__ = ["load_skills_from_package"]