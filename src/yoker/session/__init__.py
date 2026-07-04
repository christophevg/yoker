"""Session package — team-of-agents coordinator (MBI-007).

A :class:`Session` is an async context manager that owns a team of agents:
their lifecycle, registry, recursion depth tracking, event aggregation, and
inter-agent messaging. See ``analysis/session-concept-analysis.md`` for the
full design.

Phase 1 exports the foundation primitives:

  - :class:`Session` — async context manager skeleton with lifecycle events,
    event handler registration, name disambiguation, and agent lookup.
  - :class:`Message` — frozen inter-agent message dataclass.
"""

from yoker.session.message import Message
from yoker.session.session import Session

__all__ = ["Session", "Message"]
