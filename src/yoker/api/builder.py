"""Layer 2 — Agent builder.

A single factory function :func:`agent` that returns a fully constructed,
reusable :class:`yoker.Agent` configured declaratively. The returned object
is the existing :class:`Agent` class — all existing methods (``process``,
``inject_skill_context``, ``add_event_handler``, ``spawn``, ``on_event``)
work as expected.
"""

from __future__ import annotations

from pathlib import Path

from yoker.agent import Agent
from yoker.agents import AgentDefinition
from yoker.api._internal import build_agent
from yoker.api.one_shot import ThinkingLiteral
from yoker.config import Config
from yoker.context import ContextManager
from yoker.events import EventCallback


def agent(
  *,
  model: str | None = None,
  provider: str | None = None,
  system_prompt: str | None = None,
  tools: list[str] | None = None,
  skills: list[str] | None = None,
  plugins: list[str] | None = None,
  agent_path: str | Path | None = None,
  agent_definition: AgentDefinition | None = None,
  thinking: ThinkingLiteral = "on",
  event_handler: EventCallback | None = None,
  config: Config | None = None,
  context_manager: ContextManager | None = None,
) -> Agent:
  """Build a configured, reusable :class:`Agent`.

  Convenience factory over the existing :class:`Agent` constructor. Maps
  the most common configuration knobs (model, provider, system prompt,
  tools, skills, plugins, thinking mode, event handler) to keyword
  arguments so programmatic callers do not need to build a :class:`Config`
  or :class:`AgentDefinition` by hand.

  The returned agent is reusable across turns and async tasks. For a
  stateless one-shot call see :func:`yoker.ask`; for multi-turn
  conversations with context persistence see :func:`yoker.session`.

  Args:
    model: Optional model override applied to the active provider config.
    provider: Optional backend provider (``"ollama"``, ``"openai"``, ...).
    system_prompt: Optional override for the agent's system prompt.
    tools: Optional whitelist of tool names. ``None`` keeps all configured
      tools; ``[]`` disables all; ``["read"]`` keeps only ``read``.
    skills: Optional whitelist of skill names. ``None`` keeps all loaded
      skills; ``[]`` disables all; ``["commit"]`` keeps only ``commit``.
    plugins: Optional plugin packages to load (e.g. ``["pkgq"]``).
    agent_path: Optional path to an agent definition Markdown file.
    agent_definition: Optional explicit :class:`AgentDefinition`. Takes
      precedence over ``agent_path``.
    thinking: Thinking mode for the model.
    event_handler: Optional callback (sync or async) receiving every event
      emitted by the agent.
    config: Optional explicit :class:`Config`. When omitted a programmatic
      config is built via :func:`yoker.config.make_config` (no filesystem
      discovery). When provided, ``model`` / ``provider`` / ``plugins``
      overrides are applied on top of it via :func:`dataclasses.replace`.
    context_manager: Optional :class:`ContextManager` for the agent. When
      omitted a :class:`SimpleContextManager` is used (in-memory, no
      persistence).

  Returns:
    A fully constructed :class:`yoker.Agent` instance.
  """
  return build_agent(
    config=config,
    model=model,
    provider=provider,
    system_prompt=system_prompt,
    tools=tools,
    skills=skills,
    plugins=plugins,
    agent_path=agent_path,
    agent_definition=agent_definition,
    thinking=thinking,
    event_handler=event_handler,
    context_manager=context_manager,
    console_logging=True,
  )


__all__ = ["agent"]
