"""
Skills, Agents and Tools are namespaced. This schema exposes a reusable base class.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class NameSpaced:
  simple_name : str | None = None
  namespace : str | None = None

  @property
  def name(self) -> str:
    """Get the (full) tool name with namespace if present.

    Returns:
      'namespace:simple_name' if namespace is set, otherwise 'simple_name'.
    """
    simple_name = self.simple_name or self.default_simple_name
    if not simple_name:
      raise ValueError("A (simple_)name is required.")
    if self.namespace:
      return f"{self.namespace}:{simple_name}"
    return simple_name

  @property
  def default_simple_name(self) -> str | None:
    return None
