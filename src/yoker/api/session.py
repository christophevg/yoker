"""Layer 3 — Workflow primitives built on the real :class:`yoker.session.Session`.

This module provides :func:`session`, an async context manager that wraps
the MBI-007 :class:`yoker.session.Session` construct with single-agent
convenience methods (``ask``, ``run_skill``, ``spawn``, ``on_event``). It
is a facade — the underlying Session owns lifecycle, registry, recursion
depth, event aggregation, and backend sharing.
"""

from __future__ import annotations

import dataclasses
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from yoker.agent import Agent
from yoker.api._internal import build_agent
from yoker.api.one_shot import ThinkingLiteral
from yoker.config import Config
from yoker.context import ContextManager, Persisted, SimpleContextManager
from yoker.events import EventCallback
from yoker.session import Message
from yoker.session import Session as _CoreSession


class Session:
  """Facade over the real :class:`yoker.session.Session` for single-agent use.

  Constructed by :func:`session`. Exposes the most common operations
  (``ask``, ``run_skill``, ``spawn``, ``on_event``) on top of a primary
  :class:`Agent` registered with the underlying :class:`yoker.session.Session`.

  The underlying session and agent are available as ``self.core`` and
  ``self.agent`` for advanced use cases (direct ``session.spawn``, event
  aggregation, backend sharing, etc.).
  """

  def __init__(self, core: _CoreSession, primary: Agent, primary_id: str) -> None:
    self.core: _CoreSession = core
    self.agent: Agent = primary
    self.id: str = core.id
    self.agent_id: str = primary_id

  async def ask(self, prompt: str) -> str:
    """Send a prompt to the primary agent and return its response.

    Thin alias for ``await self.agent.process(prompt)``.
    """
    return await self.agent.process(prompt)

  async def run_skill(self, skill_name: str, prompt: str = "", *, args: str = "") -> str:
    """Inject a skill into the primary agent's context and run a turn."""
    self.agent.inject_skill_context(skill_name, args or None)
    return await self.agent.process(prompt)

  async def spawn(self, agent_name: str, prompt: str, *, timeout_seconds: int = 300) -> str:
    """Spawn a sub-agent by name through the underlying Session.

    Delegates to :meth:`yoker.session.Session.spawn` with the primary agent
    as the requester (so allowlist enforcement applies).
    """
    result = await self.core.spawn(
      agent_name,
      prompt,
      requester=self.agent,
      timeout_seconds=timeout_seconds,
    )
    return result.response

  async def send(self, message: Message) -> str:
    """Route an inter-agent message to another active agent in the session."""
    return await self.core.send(message)

  def on_event(self, handler: EventCallback) -> EventCallback:
    """Register a session-scoped event handler and return it for chaining."""
    self.core.add_event_handler(handler)
    return handler


@asynccontextmanager
async def session(
  id: str | None = None,
  *,
  persist: bool = True,
  model: str | None = None,
  provider: str | None = None,
  system_prompt: str | None = None,
  tools: list[str] | None = None,
  skills: list[str] | None = None,
  plugins: list[str] | None = None,
  agent_path: str | Path | None = None,
  agent_definition: object | None = None,
  thinking: ThinkingLiteral = "on",
  event_handler: EventCallback | None = None,
  config: Config | None = None,
  fresh: bool = False,
) -> AsyncIterator[Session]:
  """Open a multi-turn session with automatic context persistence.

  Builds on the real :class:`yoker.session.Session` (MBI-007). A primary
  :class:`Agent` is constructed with the given builder kwargs and
  registered with the session. ``ask`` / ``run_skill`` / ``spawn`` /
  ``on_event`` are exposed as conveniences; the underlying session and
  agent are available as ``session.core`` and ``session.agent``.

  Args:
    id: Optional session id. When the id matches an existing persisted
      session the conversation history is resumed. When omitted a fresh
      UUID-based id is generated.
    persist: When True (default) the primary agent's context is wrapped
      with :class:`yoker.context.Persisted` so turns survive across
      sessions with the same id. Set to False for an in-memory session.
    fresh: When True, ignore any persisted state for the given id and
      start with an empty context.
    model, provider, system_prompt, tools, skills, plugins, agent_path,
    agent_definition, thinking, event_handler, config: Same semantics as
      :func:`yoker.agent`.

  Yields:
    A :class:`Session` facade wrapping the underlying
    :class:`yoker.session.Session` and the primary :class:`Agent`.
  """
  base_config = config if config is not None else _session_config(id)

  # Build the underlying core Session first (owns registry, backends, ...).
  core = _CoreSession(config=base_config, session_id=id)

  # Build the context manager: Persisted wraps SimpleContextManager when
  # persistence is requested. ``fresh`` deletes any prior persisted state.
  context_manager: ContextManager | None = None
  if persist:
    session_id = core.id
    context_manager = Persisted(SimpleContextManager(), session_id=session_id)
    if fresh:
      context_manager.delete()

  # Build the primary agent and register it with the core Session.
  primary = build_agent(
    config=base_config,
    model=model,
    provider=provider,
    system_prompt=system_prompt,
    tools=tools,
    skills=skills,
    plugins=plugins,
    agent_path=agent_path,
    agent_definition=agent_definition,  # type: ignore[arg-type]
    thinking=thinking,
    event_handler=None,  # registered on the core Session below
    context_manager=context_manager,
    console_logging=False,
  )
  primary_id = core.register_primary_agent(primary)

  facade = Session(core=core, primary=primary, primary_id=primary_id)

  if event_handler is not None:
    facade.on_event(event_handler)

  async with core:
    yield facade


def _session_config(session_id: str | None) -> Config:
  """Build a base :class:`Config` for a session.

  Ensures the context session_id is honoured when provided so persistence
  resumes the right conversation.
  """
  from yoker.config import make_config

  if session_id is None:
    return make_config()
  base = Config()
  return make_config(
    context=dataclasses.replace(base.context, session_id=session_id, persist_after_turn=True)
  )


__all__ = ["session", "Session"]
