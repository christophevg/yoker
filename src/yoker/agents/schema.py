"""Agent definition schema for Yoker.

Provides frozen dataclasses for agent definitions loaded from Markdown files.
"""

from dataclasses import dataclass

from yoker.schema import NameSpaced


@dataclass
class AgentDefinition(NameSpaced):
  """Agent definition loaded from a Markdown file.

  Attributes:
    name: Agent identifier (unique within a configuration).
    description: Short description for LLM tool definition.
    system_prompt: The Markdown body content (agent's system prompt).
    source_path: Path to the source Markdown file.
    tools: Tuple of tool names available to this agent. The meaning depends on
      ``tools_unspecified``: when ``tools_unspecified`` is True the empty tuple
      means "all config-enabled tools"; when False the empty tuple means "no
      tools". A non-empty tuple always filters to those names.
    tools_unspecified: Side-channel flag distinguishing "no `tools` line in the
      YAML / no `tools` kwarg" (True, default) from "tools explicitly set to
      empty" (False). YAML ``tools:``/``null``/``~``/``""``/``[]`` and
      ``AgentDefinition(tools=None)``/``AgentDefinition(tools=[])`` both set
      this to False.
    color: Optional display color for UI integrations.
    model: Optional model override for this agent.
  """

  description: str = "The default/minimal Yoker agent."
  system_prompt: str = "You are a helpful assistant."
  source_path: str = ""
  # Tuple of tool names available to this agent. After ``__post_init__`` the
  # runtime type is always ``tuple[str, ...]``; the declared type is broader
  # so callers may pass ``None`` (no tools) or a list at construction.
  # The meaning of an empty tuple depends on ``tools_unspecified``:
  # ``tools_unspecified=True`` (default) means "all config-enabled tools";
  # ``tools_unspecified=False`` means "no tools". A non-empty tuple always
  # filters to those names.
  tools: tuple[str, ...] = ()
  # Side-channel: True means "no tools specified" → grant all config-enabled
  # tools at runtime. False means "tools explicitly given (even if empty)".
  tools_unspecified: bool = True
  color: str | None = None
  model: str | None = None
  # Allowlist of agent names this agent is permitted to spawn through the
  # Session. Empty tuple means "no spawns allowed". The Session checks
  # this before resolving/spawning.
  agents: tuple[str, ...] = ()

  def __post_init__(self) -> None:
    """Normalize ``tools`` to a tuple and set ``tools_unspecified``.

    Accepts ``None`` (no tools), a list, or a tuple at construction — the
    declared field type is ``tuple[str, ...]`` (the canonical post-init form)
    but callers in tests and the API surface pass the broader input shapes.
    Any explicit value — including ``None``/``[]`` — flips
    ``tools_unspecified`` to False so the runtime treats the agent as having
    "no tools" rather than "all tools". A default-constructed empty tuple
    keeps ``tools_unspecified=True`` (all tools).
    """
    if self.tools is None:
      self.tools = ()
      self.tools_unspecified = False
    elif isinstance(self.tools, list):
      self.tools = tuple(self.tools)
      self.tools_unspecified = False
    elif len(self.tools) > 0:
      self.tools_unspecified = False
    # tools == () with tools_unspecified left as passed (default True)

  @property
  def default_simple_name(self) -> str | None:
    return "default"


__all__ = [
  "AgentDefinition",
]
