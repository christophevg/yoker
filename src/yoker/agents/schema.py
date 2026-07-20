"""Agent definition schema for Yoker.

Provides dataclasses for agent definitions loaded from Markdown files.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, NoReturn

from yoker.schema import NameSpaced


class AllToolsSentinel:
  """Sentinel meaning "all config-enabled tools" for ``AgentDefinition.tools``.

  Distinct from ``None`` / ``()`` (explicit no tools) and from a non-empty
  tuple (explicit filter). Use the module-level :data:`ALL_TOOLS` singleton as
  the default value of ``AgentDefinition.tools`` and test with ``is ALL_TOOLS``
  (identity, not equality).
  """

  _instance: "AllToolsSentinel | None" = None

  def __new__(cls) -> "AllToolsSentinel":
    if cls._instance is None:
      cls._instance = super().__new__(cls)
    return cls._instance

  def __repr__(self) -> str:
    return "ALL_TOOLS"

  def __bool__(self) -> bool:
    # "all tools" is truthy; distinguishes from None/() which are falsy.
    return True

  def __iter__(self) -> Iterator[NoReturn]:
    # The sentinel is not iterable — downstream code must guard with
    # ``is ALL_TOOLS`` before iterating ``definition.tools``.
    raise TypeError("ALL_TOOLS is a sentinel, not iterable; test with `is`")

  def __eq__(self, other: object) -> bool:
    return other is self

  def __hash__(self) -> int:
    return id(self)

  def __reduce__(self) -> tuple[Any, tuple[()]]:
    # Pickle support: round-trip back to the singleton.
    return (_resolve_all_tools, ())


def _resolve_all_tools() -> AllToolsSentinel:
  """Pickle resolver: return the :data:`ALL_TOOLS` singleton."""
  return ALL_TOOLS


ALL_TOOLS: AllToolsSentinel = AllToolsSentinel()


@dataclass
class AgentDefinition(NameSpaced):
  """Agent definition loaded from a Markdown file.

  Attributes:
    name: Agent identifier (unique within a configuration).
    description: Short description for LLM tool definition.
    system_prompt: The Markdown body content (agent's system prompt).
    source_path: Path to the source Markdown file.
    tools: Tools available to this agent. Three states (Option C):
      ``ALL_TOOLS`` (default — all config-enabled tools), ``()`` (no tools),
      or a non-empty tuple (filter to those names). ``None`` and ``[]`` passed
      at construction normalize to ``()`` (no tools). Test with ``is ALL_TOOLS``.
    color: Optional display color for UI integrations.
    model: Optional model override for this agent.
  """

  description: str = "The default/minimal Yoker agent."
  system_prompt: str = "You are a helpful assistant."
  source_path: str = ""
  # Three states: ALL_TOOLS (default — all config-enabled tools), () (no
  # tools), or a non-empty tuple (filter). The declared type is broader so
  # callers may pass None / [] at construction (normalized to () in
  # __post_init__); after __post_init__ the runtime type is
  # AllToolsSentinel | tuple[str, ...].
  tools: "tuple[str, ...] | AllToolsSentinel" = ALL_TOOLS
  color: str | None = None
  model: str | None = None
  # Allowlist of agent names this agent is permitted to spawn through the
  # Session. Empty tuple means "no spawns allowed". The Session checks
  # this before resolving/spawning.
  agents: tuple[str, ...] = ()

  def __post_init__(self) -> None:
    """Normalize ``tools`` to either the ``ALL_TOOLS`` sentinel or a tuple.

    The sentinel is preserved when set (the default or an explicit
    ``tools=ALL_TOOLS`` pass). Any other value — ``None``, ``[]``, or a
    non-empty list/tuple — is normalized to a tuple: ``None`` and ``[]``
    become ``()`` (no tools); a non-empty list becomes a tuple of the
    same strings (filter).
    """
    if self.tools is ALL_TOOLS:
      return  # sentinel preserved — downstream checks `is ALL_TOOLS`
    if self.tools is None:
      self.tools = ()
    elif isinstance(self.tools, list):
      self.tools = tuple(self.tools)
    # else: already a tuple (empty → no tools; non-empty → filter)

  @property
  def default_simple_name(self) -> str | None:
    return "default"


__all__ = [
  "AgentDefinition",
  "AllToolsSentinel",
  "ALL_TOOLS",
]
