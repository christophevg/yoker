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


# Unique sentinel meaning "all registered agents" for AgentDefinition.agents.
# Checked with ``is ALL_AGENTS`` (identity) in the allowlist enforcement in
# Session._create_agent and in make_spawn_agent_tool. When the agent
# definition has no ``agents:`` frontmatter key, this sentinel is set so the
# agent can spawn any registered agent. An explicit empty tuple (``agents: []``)
# means no spawns allowed. Test with ``is ALL_AGENTS``.
#
# Implemented as a tuple subclass instance so it is still tuple-like (len,
# iteration, `in` checks all work as if empty) but has unique identity —
# unlike ``()`` which is a CPython singleton and cannot be distinguished
# from any user-supplied empty tuple via ``is``.
class _AllAgentsType(tuple):
  """Sentinel tuple subclass with unique identity for ALL_AGENTS."""

  __slots__ = ()

  def __repr__(self) -> str:
    return "ALL_AGENTS"


ALL_AGENTS: tuple[str, ...] = _AllAgentsType()


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
    agents: Allowlist of agent names this agent is permitted to spawn.
      Two states: ``ALL_AGENTS`` (default — any registered agent), or a tuple
      of names (only those may be spawned; empty tuple = no spawns).
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
  # Session. ALL_AGENTS sentinel (default — any registered agent), or a
  # tuple of names (only those may be spawned; empty tuple = no spawns).
  # default_factory returns the SAME ALL_AGENTS object so `is ALL_AGENTS` works.
  agents: tuple[str, ...] = field(default_factory=lambda: ALL_AGENTS)

  def __post_init__(self) -> None:
    """Normalize ``tools`` and ``agents`` sentinels.

    ``tools``: The ALL_TOOLS sentinel is preserved when set (the default or
    an explicit ``tools=ALL_TOOLS`` pass). Any other value — ``None``, ``[]``,
    or a non-empty list/tuple — is normalized to a list: ``None`` and ``[]``
    become ``[]`` (no tools); a non-empty tuple becomes a list of the same
    strings (filter).

    ``agents``: The ALL_AGENTS sentinel is preserved when set (the default).
    Any other value — ``None``, ``[]``, or a non-empty list/tuple — is
    normalized to a tuple: ``None`` and ``[]`` become ``()`` (no spawns); a
    non-empty list becomes a tuple of the same strings (allowlist).
    """
    if self.tools is ALL_TOOLS:
      pass  # sentinel preserved — downstream checks `is ALL_TOOLS`
    elif self.tools is None:
      self.tools = []
    elif isinstance(self.tools, tuple):
      self.tools = list(self.tools)
    # else: already a list (empty → no tools; non-empty → filter)

    if self.agents is ALL_AGENTS:
      pass  # sentinel preserved — downstream checks `is ALL_AGENTS`
    elif self.agents is None:
      self.agents = ()
    elif isinstance(self.agents, list):
      self.agents = tuple(self.agents)
    # else: already a tuple (empty → no spawns; non-empty → allowlist)

  @property
  def default_simple_name(self) -> str | None:
    return "default"


__all__ = [
  "AgentDefinition",
  "ALL_TOOLS",
  "ALL_AGENTS",
]
