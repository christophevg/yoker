"""Pythonic utility API for Yoker.

Three layers, each building on the previous:

  - **Layer 1 — One-shot functions**: :func:`ask`, :func:`run_skill`,
    :func:`complete` (plus ``*_sync`` convenience wrappers).
  - **Layer 2 — Agent builder**: :func:`agent` returns a configured,
    reusable :class:`yoker.Agent`.
  - **Layer 3 — Workflow primitives**: :func:`session` opens a multi-turn
    :class:`Session` facade over the real :class:`yoker.session.Session`.

The facade constructs and drives the existing :class:`Agent` /
:class:`Session` classes — it adds no behaviour of its own. Existing
imports and classes keep working unchanged.
"""

from yoker.api.builder import agent
from yoker.api.one_shot import (
  ThinkingLiteral,
  ask,
  ask_sync,
  complete,
  complete_sync,
  run_skill,
  run_skill_sync,
)
from yoker.api.session import Session, session

__all__ = [
  # Layer 1 — one-shot
  "ask",
  "ask_sync",
  "complete",
  "complete_sync",
  "run_skill",
  "run_skill_sync",
  # Layer 2 — agent builder
  "agent",
  # Layer 3 — workflow primitives
  "session",
  "Session",
  # Shared types
  "ThinkingLiteral",
]
