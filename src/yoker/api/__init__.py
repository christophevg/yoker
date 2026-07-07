"""Thin Pythonic API for Yoker (MBI-003).

A minimal facade over the real :class:`yoker.session.Session` and
:class:`yoker.core.Agent` classes:

  - :func:`process` — one-shot turn; builds an agent, runs a single
    prompt, returns the response string. The agent is discarded.
  - :func:`do` — one-shot skill invocation; builds an agent, runs
    :meth:`Agent.do`, returns the response string.
  - :func:`agent` — builder that returns a configured, reusable
    :class:`yoker.Agent`.
  - :func:`session` — async context manager yielding the real
    :class:`yoker.session.Session` with a registered primary agent.

:func:`run_sync` wraps :func:`asyncio.run` for synchronous callers (scripts,
notebooks, REPLs). It is the only sync entry point — there are no per-call
``*_sync`` variants.

The facade constructs and drives the existing :class:`Agent` /
:class:`Session` classes — it adds no behaviour of its own. Existing
imports and classes keep working unchanged.
"""

from __future__ import annotations

import asyncio
import dataclasses
from collections.abc import AsyncIterator, Coroutine
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal, TypeVar

from yoker.agents import AgentDefinition, load_agent_definition
from yoker.backends import ModelBackend
from yoker.config import Config, make_config
from yoker.context import ContextManager, Persisted, SimpleContextManager
from yoker.core import Agent
from yoker.core.thinking import ThinkingMode
from yoker.events import EventCallback
from yoker.exceptions import SkillError
from yoker.session import Session

_T = TypeVar("_T")

ThinkingLiteral = Literal["on", "off", "visible", "silent"]

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


def _thinking_mode(value: str) -> ThinkingMode:
  """Map a public ``thinking`` string to :class:`ThinkingMode`.

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


def _build_agent_definition(
  system_prompt: str | None,
  tools: list[str] | None,
) -> AgentDefinition | None:
  """Build an :class:`AgentDefinition` for the custom-config case.

  Returns ``None`` when no customisation is needed (caller gets the default
  agent definition and the existing tool-filter logic is skipped). The
  pure-text path is expressed via ``tools=[]`` (an empty whitelist clears
  all tools); no separate ``no_tools`` branch is needed.
  """
  if system_prompt is None and tools is None:
    return None

  # Setting simple_name to a non-None value engages Agent._filter_tools_by_definition.
  # When tools is None but a system_prompt is given, we keep simple_name=None so the
  # default "keep all tools" behaviour applies.
  simple_name: str | None = None
  tools_tuple: tuple[str, ...] = ()
  if tools is not None:
    simple_name = "custom"
    tools_tuple = tuple(tools)

  prompt = system_prompt if system_prompt is not None else "You are a helpful assistant."
  return AgentDefinition(simple_name=simple_name, system_prompt=prompt, tools=tools_tuple)


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
  backend: ModelBackend | None = None,
  console_logging: bool = True,
) -> Agent:
  """Build a configured, reusable :class:`Agent`.

  Convenience factory over the :class:`Agent` constructor. Maps the most
  common configuration knobs (model, provider, system prompt, tools, skills,
  plugins, thinking mode, event handler) to keyword arguments so
  programmatic callers do not need to build a :class:`Config` or
  :class:`AgentDefinition` by hand.

  The returned agent is reusable across turns and async tasks. For a
  stateless one-shot call see :func:`yoker.process`; for multi-turn
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
    backend: Optional :class:`ModelBackend` (e.g. shared from a
      :class:`yoker.session.Session`). When provided the agent reuses it
      instead of creating one from ``config``.
    console_logging: Whether to enable console logging. The one-shot
      helpers (:func:`process`, :func:`do`) and :func:`session` set this
      to ``False`` so they stay quiet; the default here matches the
      :class:`Agent` constructor.

  Returns:
    A fully constructed :class:`yoker.Agent` instance.
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

  # 4. Resolve the agent definition: explicit > path > built-from-kwargs.
  resolved_definition: AgentDefinition | None = agent_definition
  if resolved_definition is None and agent_path is not None:
    resolved_definition = load_agent_definition(agent_path)
  if resolved_definition is None and agent_path is None:
    resolved_definition = _build_agent_definition(system_prompt, tools)

  built = Agent(
    config=base_config,
    thinking_mode=_thinking_mode(thinking),
    agent_definition=resolved_definition,
    agent_path=agent_path if resolved_definition is None else None,
    context_manager=context_manager,
    plugins=plugins if plugins is not None else None,
    console_logging=console_logging,
    backend=backend,
  )

  # 5. Filter skills to the requested subset (post-construction).
  if skills is not None:
    _filter_skills(built, skills)

  # 6. Register the optional event handler.
  if event_handler is not None:
    built.on_event(event_handler)

  return built


async def process(
  prompt: str,
  **common_kwargs: Any,
) -> str:
  """Ask the configured model a single question and return the response.

  Loads a programmatic :class:`Config`, constructs an :class:`Agent`, runs
  one turn, and returns the assistant's reply. The agent is discarded
  (stateless one-shot). For multi-turn conversations use
  :func:`yoker.session`; for a reusable agent use :func:`yoker.agent`.

  Args:
    prompt: The user's question or instruction.
    **common_kwargs: Same builder kwargs as :func:`yoker.agent`
      (``model``, ``provider``, ``system_prompt``, ``tools``, ``skills``,
      ``plugins``, ``thinking``, ``event_handler``, ``config``).

  Returns:
    The assistant's response string for the turn.
  """
  built = agent(console_logging=False, **common_kwargs)
  return await built.process(prompt)


async def do(
  skill_name: str,
  prompt: str,
  args: str = "",
  **common_kwargs: Any,
) -> str:
  """Invoke a skill as a one-shot command and return the response.

  Builds an agent via :func:`yoker.agent`, runs :meth:`Agent.do` with the
  given skill, and returns the assistant's reply. The agent is discarded
  (stateless one-shot).

  Args:
    skill_name: Name of the skill to invoke (bare or namespaced).
    prompt: The user's task. Sent as the user message after the skill
      context is injected.
    args: Optional arguments forwarded to the skill's invocation block.
    **common_kwargs: Same builder kwargs as :func:`yoker.agent`.

  Returns:
    The assistant's response string for the turn.
  """
  built = agent(console_logging=False, **common_kwargs)
  return await built.do(skill_name, prompt, args)


def _session_config(session_id: str | None) -> Config:
  """Build a base :class:`Config` for a session.

  Ensures the context session_id is honoured when provided so persistence
  resumes the right conversation.
  """
  if session_id is None:
    return make_config()
  base = Config()
  return make_config(
    context=dataclasses.replace(base.context, session_id=session_id, persist_after_turn=True)
  )


def _resolve_primary_definition(
  core: Session,
  base_config: Config,
  agent_definition: AgentDefinition | None,
  agent_path: str | Path | None,
) -> AgentDefinition | None:
  """Resolve the primary agent's definition for a session.

  The Session-agnostic Agent cannot resolve names from a registry, so the
  Session layer resolves the config/path/name reference and passes the
  definition in.
  """
  if agent_definition is not None:
    return agent_definition
  if agent_path is not None:
    return load_agent_definition(agent_path)
  reference = base_config.agent or base_config.agents.definition or None
  if reference:
    file_path = Path(reference).expanduser()
    if file_path.exists() and file_path.is_file():
      return load_agent_definition(reference)
    try:
      return core.agents.resolve(reference)
    except ValueError:
      return None
  return None


@asynccontextmanager
async def session(
  id: str | None = None,
  *,
  persist: bool = True,
  fresh: bool = False,
  **common_kwargs: Any,
) -> AsyncIterator[Session]:
  """Open a multi-turn session with automatic context persistence.

  Builds on the real :class:`yoker.session.Session` (MBI-007). A primary
  :class:`Agent` is constructed with the given builder kwargs and
  registered with the session. The primary agent is available via
  :attr:`Session.primary_agent`; sub-agents can be spawned via
  ``await session.spawn(name)``. Event handlers are registered via
  ``session.add_event_handler(...)``.

  Args:
    id: Optional session id. When the id matches an existing persisted
      session the conversation history is resumed. When omitted a fresh
      UUID-based id is generated.
    persist: When True (default) the primary agent's context is wrapped
      with :class:`yoker.context.Persisted` so turns survive across
      sessions with the same id. Set to False for an in-memory session.
    fresh: When True, ignore any persisted state for the given id and
      start with an empty context.
    **common_kwargs: Same builder kwargs as :func:`yoker.agent`
      (``model``, ``provider``, ``system_prompt``, ``tools``, ``skills``,
      ``plugins``, ``agent_path``, ``agent_definition``, ``thinking``,
      ``event_handler``, ``config``).

  Yields:
    The real :class:`yoker.session.Session` with a registered primary
    agent.
  """
  # Pull the config / agent_path / agent_definition / event_handler kwargs
  # out of common_kwargs (they are consumed here, not forwarded as-is).
  config: Config | None = common_kwargs.pop("config", None)
  agent_path: str | Path | None = common_kwargs.pop("agent_path", None)
  agent_definition: AgentDefinition | None = common_kwargs.pop("agent_definition", None)
  event_handler: EventCallback | None = common_kwargs.pop("event_handler", None)
  plugins: list[str] | None = common_kwargs.pop("plugins", None)

  base_config = config if config is not None else _session_config(id)
  extra_plugins = tuple(plugins) if plugins is not None else ()

  # Build the underlying core Session first (owns registry, backends, ...).
  core = Session(config=base_config, session_id=id, extra_plugins=extra_plugins)

  # Build the context manager: Persisted wraps SimpleContextManager when
  # persistence is requested. ``fresh`` deletes any prior persisted state.
  context_manager: ContextManager | None = None
  if persist:
    session_id = core.id
    context_manager = Persisted(SimpleContextManager(), session_id=session_id)
    if fresh:
      context_manager.delete()

  resolved_definition = _resolve_primary_definition(core, base_config, agent_definition, agent_path)
  backend = core.get_backend(base_config)

  primary = agent(
    config=base_config,
    agent_definition=resolved_definition,
    agent_path=agent_path if resolved_definition is None else None,
    context_manager=context_manager,
    backend=backend,
    plugins=plugins,
    console_logging=False,
    **common_kwargs,
  )
  core.register_primary_agent(primary)

  if event_handler is not None:
    core.add_event_handler(event_handler)

  async with core:
    yield core


__all__ = [
  # One-shot
  "process",
  "do",
  # Sync utility
  "run_sync",
  # Agent builder
  "agent",
  # Workflow primitives
  "session",
  # Shared types
  "ThinkingLiteral",
]
