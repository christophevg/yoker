"""Session package — team-of-agents coordinator (MBI-007).

A :class:`Session` is an async context manager that owns a team of agents:
their lifecycle, registry, recursion depth tracking, event aggregation, and
inter-agent messaging. See ``analysis/session-concept-analysis.md`` for the
full design.

Phase 4 exports:

  - :class:`Session` — async context manager owning the team of agents.
  - :class:`Message` — frozen inter-agent message dataclass.
  - :class:`SpawnResult` — return value of :meth:`Session.spawn` carrying
    both the spawned agent's unique id and its response.
"""

from yoker.session.message import Message
from yoker.session.session import Session
from yoker.session.spawn_result import SpawnResult

__all__ = ["Session", "Message", "SpawnResult"]
