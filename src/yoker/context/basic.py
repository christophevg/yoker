"""Basic in-memory context manager implementation.

Provides BasicContextManager, a simple list-like context manager that keeps
conversation history in memory only.
"""

from yoker.context.manager import ContextManager


class BasicContextManager(ContextManager):
  """In-memory context manager.

  Acts as a plain list of conversation messages. No persistence is performed.
  """


__all__ = ["BasicContextManager"]
