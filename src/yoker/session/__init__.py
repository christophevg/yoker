"""Session package — team-of-agents coordinator.

A :class:`Session` is an async context manager that owns a team of agents:
their lifecycle, registry, recursion depth tracking, event aggregation, and
inter-agent messaging.
"""

from yoker.session.session import Session

__all__ = ["Session"]
