"""AgentDisplay — a read-only projection of Agent for UI rendering.

A frozen dataclass that carries only what the UI layer needs to render
agent-identified output (name, color, model, description). The UIBridge
constructs this from the full ``Agent`` instance; UI handlers receive
``AgentDisplay | None`` and never touch the ``Agent`` directly.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentDisplay:
  """Read-only projection of an Agent for UI display.

  Attributes:
    id: The session-assigned agent id (e.g. ``"researcher"``, ``"researcher-2"``).
    name: The agent's simple name from its definition (e.g. ``"researcher"``).
    color: Optional display color from the agent definition frontmatter.
      May be a hex color (``"#FF6B35"``) or a named color (``"blue"``).
    model: The model the agent is using (e.g. ``"llama3.2:latest"``).
    description: Short description from the agent definition.
  """

  id: str
  name: str
  color: str | None = None
  model: str | None = None
  description: str = ""


__all__ = ["AgentDisplay"]
