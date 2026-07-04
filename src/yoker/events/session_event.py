"""SessionEvent envelope wrapper (MBI-007, PR #43 Clarification 9).

A :class:`SessionEvent` is a lightweight frozen envelope that tags an
:class:`yoker.events.Event` with the ``agent_id`` of the agent that produced it.
It is used by :class:`yoker.session.Session` to fan out sub-agent events to
session-level handlers (UIBridge, EventRecorder) without modifying the existing
frozen event dataclasses or their construction sites in
``agent/_processing.py``.

Session-level events emitted by the Session itself (``SessionStartEvent``,
``AgentSpawnedEvent``, ``AgentFinishedEvent``, ``AgentMessageEvent``,
``SessionEndEvent``) are **not** wrapped — they already carry the relevant
``session_id`` / ``agent_id`` fields. Only events emitted *by agents* (turn,
thinking, content, tool) are wrapped in this envelope.
"""

from dataclasses import dataclass

from yoker.events.types import Event


@dataclass(frozen=True)
class SessionEvent:
  """Envelope wrapping an :class:`Event` with its source agent's id.

  Attributes:
    agent_id: The unique session-assigned id of the agent that produced the
      wrapped event.
    event: The original event, unchanged.
  """

  agent_id: str
  event: Event


__all__ = ["SessionEvent"]
