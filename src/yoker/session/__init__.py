"""Session package — team-of-agents coordinator.

A :class:`Session` is an async context manager that owns a team of agents:
their lifecycle, registry, recursion depth tracking, event aggregation, and
inter-agent messaging.

Exports:

  - :class:`Session` — async context manager owning the team of agents.
  - :class:`Message` — frozen inter-agent message dataclass.
"""

from yoker.session.message import Message
from yoker.session.session import Session

__all__ = ["Session", "Message"]
