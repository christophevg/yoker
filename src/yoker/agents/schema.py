"""Agent definition schema for Yoker.

Provides dataclasses for agent definitions loaded from Markdown files.
"""

from dataclasses import dataclass, field

from yoker.schema import NameSpaced

# Unique sentinel meaning "all config-enabled tools" for AgentDefinition.tools.
# Checked with ``is ALL_TOOLS`` (identity) in exactly ONE place —
# Agent._filter_tools_by_definition — which resolves it to the real list of
# tool names from the registry. Everywhere else, ``tools`` is just a list.
ALL_TOOLS: list[str] = []


@dataclass
class AgentDefinition(NameSpaced):
  """Agent definition loaded from a Markdown file.

  Attributes:
    name: Agent identifier (unique within a configuration).
    description: Short description for LLM tool definition.
    system_prompt: The Markdown body content (agent's system prompt).
    source_path: Path to the source Markdown file.
    tools: Tools available to this agent. Three states:
      ``ALL_TOOLS`` (default — all config-enabled tools), ``[]`` (no tools),
      or a non-empty list (filter to those names). ``None`` and ``[]`` passed
      at construction normalize to ``[]`` (no tools). Test with ``is ALL_TOOLS``.
    color: Optional display color for UI integrations.
    model: Optional model override for this agent.
  """

  description: str = "The default/minimal Yoker agent."
  system_prompt: str = "You are a helpful assistant."
  source_path: str = ""
  # Three states: ALL_TOOLS (default — all config-enabled tools), [] (no
  # tools), or a non-empty list (filter). The declared type is broader so
  # callers may pass None / tuples at construction (normalized to [] in
  # __post_init__); after __post_init__ the runtime type is list[str].
  # default_factory returns the SAME ALL_TOOLS object so `is ALL_TOOLS` works.
  tools: "list[str] | None" = field(default_factory=lambda: ALL_TOOLS)
  color: str | None = None
  model: str | None = None
  # Allowlist of agent names this agent is permitted to spawn through the
  # Session. Empty tuple means "no spawns allowed". The Session checks
  # this before resolving/spawning.
  agents: tuple[str, ...] = ()

  def __post_init__(self) -> None:
    """Normalize ``tools`` to either the ``ALL_TOOLS`` sentinel or a list.

    The sentinel is preserved when set (the default or an explicit
    ``tools=ALL_TOOLS`` pass). Any other value — ``None``, ``[]``, or a
    non-empty list/tuple — is normalized to a list: ``None`` and ``[]``
    become ``[]`` (no tools); a non-empty tuple becomes a list of the
    same strings (filter).
    """
    if self.tools is ALL_TOOLS:
      return  # sentinel preserved — downstream checks `is ALL_TOOLS`
    if self.tools is None:
      self.tools = []
    elif isinstance(self.tools, tuple):
      self.tools = list(self.tools)
    # else: already a list (empty → no tools; non-empty → filter)

  @property
  def default_simple_name(self) -> str | None:
    return "default"


__all__ = [
  "AgentDefinition",
  "ALL_TOOLS",
]
