"""Inter-agent message dataclass (MBI-007, Decision 3).

A :class:`Message` is the unit of inter-agent communication routed through a
:class:`yoker.session.Session`. Content is a plain string (the prompt) —
streaming inter-agent messages are deferred (see analysis §6.6).
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Message:
  """A single inter-agent message.

  Attributes:
    from_: The unique session-assigned id of the sending agent.
    to: The unique session-assigned id of the receiving agent.
    content: Plain-string message content (the prompt). No streaming.
    metadata: Optional metadata bag (defaults to an empty dict).
  """

  from_: str
  to: str
  content: str
  metadata: dict = field(default_factory=dict)


__all__ = ["Message"]
