"""SpawnResult dataclass — return value of :meth:`Session.spawn` (MBI-007 7.8.2).

PR #43 Clarification 5: ``Session.spawn()`` returns both the spawned agent's
unique session-assigned id and the response string. The ``SpawnAgent`` tool
(7.8.3) renders both fields into its ``ToolResult`` so the model can read the
spawned agent's id and address it later via ``SendMessage``.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class SpawnResult:
  """Result of spawning a child agent via :meth:`Session.spawn`.

  Attributes:
    agent_id: The unique session-assigned id of the spawned agent. Empty
      string when the spawn failed before the agent was registered
      (allowlist violation, capacity error, resolution failure).
    response: The spawned agent's response string, or an error message when
      the spawn failed (timeout, exception). Preserves the previous
      ``agent`` tool's "return error string, do not raise" contract at the
      tool boundary.
  """

  agent_id: str
  response: str


__all__ = ["SpawnResult"]
