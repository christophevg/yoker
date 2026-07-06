"""Shared helpers for the :mod:`yoker.api` layer.

These helpers are private to the API implementation and not re-exported from
``yoker``. They consolidate the common boilerplate (config merge, agent
construction, sync wrapper) so the three public layers stay thin.
"""

from __future__ import annotations

import asyncio
import dataclasses
from collections.abc import Coroutine
from pathlib import Path
from typing import Any, TypeVar

from yoker.agents import AgentDefinition, load_agent_definition
from yoker.backends import ModelBackend
from yoker.config import Config, make_config
from yoker.context import ContextManager
from yoker.core import Agent
from yoker.core.thinking import ThinkingMode
from yoker.events import EventCallback
from yoker.exceptions import SkillError
from yoker.tools import ToolRegistry

_T = TypeVar("_T")

# Map the public ``thinking`` string enum to :class:`ThinkingMode`.
# ``"on"`` is the default and matches the Agent's default (visible reasoning).
# ``"visible"`` is a semantic alias for ``"on"``. ``"silent"`` requests
# thinking without displaying it (background reasoning).
_THINKING_MAP: dict[str, ThinkingMode] = {
  "on": ThinkingMode.ON,
  "visible": ThinkingMode.ON,
  "off": ThinkingMode.OFF,
  "silent": ThinkingMode.SILENT,
}


def thinking_mode(value: str) -> ThinkingMode:
  """Map a public ``thinking`` string to :class:`ThinkingMode`.

  Args:
    value: One of ``"on"``, ``"off"``, ``"visible"``, ``"silent"``.

  Returns:
    The corresponding :class:`ThinkingMode`.

  Raises:
    ValueError: If ``value`` is not a recognised thinking mode.
  """
  mode = _THINKING_MAP.get(value)
  if mode is None:
    raise ValueError(
      f"Unknown thinking mode '{value}'. Expected one of: {', '.join(sorted(_THINKING_MAP))}"
    )
  return mode


def run_sync(coro: Coroutine[Any, Any, _T]) -> _T:
  """Run a coroutine from synchronous code.

  Uses :func:`asyncio.run` so a fresh event loop is created and torn down
  per call — appropriate for the sync convenience path, which by definition
  is not latency-sensitive. Raises a clear error when called from inside a
  running loop so users reach for the async variant instead.

  Args:
    coro: The coroutine to run to completion.

  Returns:
    The coroutine's result.

  Raises:
    RuntimeError: If an event loop is already running in the current thread.
  """
  try:
    asyncio.get_running_loop()
  except RuntimeError:
    return asyncio.run(coro)
  raise RuntimeError(
    "Sync helper called from inside a running event loop. "
    "Use the async variant (e.g. await yoker.process(...)) instead of yoker.run_sync(...)."
  )


def _filter_tools(agent: Agent, tools: list[str]) -> None:
  """Restrict ``agent.tools`` to the requested names (case-insensitive).

  Namespaced names (``pkg:tool``) are matched exactly. Bare names match both
  the bare key and the ``yoker:``-prefixed built-in key.
  """
  requested: set[str] = set()
  for name in tools:
    normalized = name.lower()
    if ":" in normalized:
      requested.add(normalized)
    else:
      requested.add(normalized)
      requested.add(f"yoker:{normalized}")

  to_remove = [key for key in list(agent.tools.data.keys()) if key.lower() not in requested]
  for key in to_remove:
    del agent.tools.data[key]


def _filter_skills(agent: Agent, skills: list[str]) -> None:
  """Restrict ``agent.skills`` to the requested names.

  Raises :class:`SkillError` if any requested skill is not in the registry.
  """
  available = {name.lower(): name for name in agent.skills.data.keys()}
  keep: set[str] = set()
  for requested in skills:
    normalized = requested.lower()
    if ":" in normalized:
      actual = available.get(normalized)
    else:
      actual = available.get(normalized) or available.get(f"yoker:{normalized}")
    if actual is None:
      raise SkillError(
        requested,
        f"Unknown skill. Available skills: {', '.join(sorted(agent.skills.names))}"
        if agent.skills.names
        else "Unknown skill (no skills loaded).",
      )
    keep.add(actual)

  to_remove = [key for key in list(agent.skills.data.keys()) if key not in keep]
  for key in to_remove:
    del agent.skills.data[key]


def _build_agent_definition(
  system_prompt: str | None,
  tools: list[str] | None,
  no_tools: bool,
) -> AgentDefinition | None:
  """Build an :class:`AgentDefinition` for the custom-config case.

  Returns ``None`` when no customisation is needed (caller gets the default
  agent definition and the existing tool-filter logic is skipped).
  """
  if system_prompt is None and tools is None and not no_tools:
    return None

  # Setting simple_name to a non-None value engages Agent._filter_tools_by_definition.
  # When tools is None but a system_prompt is given, we keep simple_name=None so the
  # default "keep all tools" behaviour applies.
  simple_name: str | None = None
  tools_tuple: tuple[str, ...] = ()
  if tools is not None or no_tools:
    simple_name = "custom"
    tools_tuple = tuple(tools) if tools is not None else ()

  prompt = system_prompt if system_prompt is not None else "You are a helpful assistant."
  return AgentDefinition(simple_name=simple_name, system_prompt=prompt, tools=tools_tuple)


def build_agent(
  *,
  config: Config | None = None,
  model: str | None = None,
  provider: str | None = None,
  system_prompt: str | None = None,
  tools: list[str] | None = None,
  skills: list[str] | None = None,
  plugins: list[str] | None = None,
  agent_path: str | Path | None = None,
  agent_definition: AgentDefinition | None = None,
  thinking: str = "on",
  event_handler: EventCallback | None = None,
  context_manager: ContextManager | None = None,
  no_tools: bool = False,
  no_skills: bool = False,
  console_logging: bool = True,
  backend: ModelBackend | None = None,
) -> Agent:
  """Construct a configured :class:`Agent` from the API kwargs.

  Centralises the boilerplate shared by :func:`yoker.process` and
  :func:`yoker.agent` (and the session facade). When ``backend`` is
  provided (e.g. shared from a :class:`yoker.session.Session`) it is
  passed to the :class:`Agent` constructor so the Agent stays
  Session-agnostic.
  """
  # 1. Resolve the base config (programmatic defaults; no filesystem).
  base_config = config if config is not None else make_config()

  # 2. Apply model / provider overrides on a derived frozen Config.
  if model is not None or provider is not None:
    base_config = _apply_model_provider(base_config, model=model, provider=provider)

  # 3. Enable plugin loading when plugins are explicitly requested.
  if plugins is not None:
    base_config = dataclasses.replace(
      base_config,
      plugins=dataclasses.replace(base_config.plugins, enabled=True, packages=tuple(plugins)),
    )

  # 4. For pure text completion (no_skills / no_tools) strip skill dirs and
  #    disable the skill tool so nothing besides the model is wired up.
  if no_skills:
    base_config = dataclasses.replace(
      base_config,
      skills=dataclasses.replace(base_config.skills, directories=()),
      tools=dataclasses.replace(
        base_config.tools,
        skill=dataclasses.replace(base_config.tools.skill, enabled=False),
      ),
    )

  # 5. Build the agent definition unless the caller provided one or a path.
  if agent_definition is None and agent_path is None:
    if no_tools or tools is not None or system_prompt is not None:
      agent_definition = _build_agent_definition(system_prompt, tools, no_tools)
  elif agent_path is not None and agent_definition is None:
    agent_definition = load_agent_definition(agent_path)

  agent = Agent(
    config=base_config,
    thinking_mode=thinking_mode(thinking),
    agent_definition=agent_definition,
    agent_path=agent_path if agent_definition is None else None,
    context_manager=context_manager,
    plugins=plugins if plugins is not None else None,
    console_logging=console_logging,
    backend=backend,
  )

  # 6. Filter skills to the requested subset (post-construction).
  if skills is not None:
    _filter_skills(agent, skills)

  # 7. Register the optional event handler.
  if event_handler is not None:
    agent.on_event(event_handler)

  return agent


def _apply_model_provider(config: Config, *, model: str | None, provider: str | None) -> Config:
  """Return a derived :class:`Config` with model / provider overrides applied."""
  from yoker.config import KNOWN_PROVIDERS, AnthropicConfig, GeminiConfig, OpenAIConfig

  backend = config.backend

  if provider is not None:
    if provider in KNOWN_PROVIDERS and getattr(backend, provider) is None:
      defaults: dict[str, type] = {
        "openai": OpenAIConfig,
        "anthropic": AnthropicConfig,
        "gemini": GeminiConfig,
      }
      backend = dataclasses.replace(backend, **{provider: defaults[provider]()})
    backend = dataclasses.replace(backend, provider=provider)

  if model is not None:
    sub = backend.config
    new_sub = dataclasses.replace(sub, model=model)
    active = backend.provider
    backend = dataclasses.replace(backend, **{active: new_sub})  # type: ignore[arg-type]

  return dataclasses.replace(config, backend=backend)


__all__ = [
  "build_agent",
  "run_sync",
  "thinking_mode",
  "ToolRegistry",
]
