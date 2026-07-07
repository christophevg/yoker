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
from yoker.config import (
  KNOWN_PROVIDERS,
  AnthropicConfig,
  Config,
  GeminiConfig,
  OpenAIConfig,
)
from yoker.context import ContextManager, Persisted, SimpleContextManager
from yoker.core import Agent
from yoker.core.thinking import ThinkingMode
from yoker.events import EventCallback
from yoker.session import Session

_T = TypeVar("_T")

ThinkingLiteral = Literal["on", "off", "visible", "silent"]

_THINKING_MAP: dict[str, ThinkingMode] = {
  "on": ThinkingMode.ON,
  "visible": ThinkingMode.ON,
  "off": ThinkingMode.OFF,
  "silent": ThinkingMode.SILENT,
}


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
    config: Optional explicit :class:`Config`. When omitted and no model /
      provider / plugins overrides are given, the Agent constructor
      discovers the config from the filesystem via :func:`get_yoker_config`.
      When provided (or when overrides need applying), a programmatic
      :class:`Config` is used as the base.
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
  # Determine whether we need a programmatic Config base. When the caller
  # passes an explicit config we start from it; when overrides (model /
  # provider / plugins) need applying we build a Config() base; otherwise
  # we pass None so the Agent constructor runs get_yoker_config() (filesystem
  # discovery), honouring the user's yoker.toml.
  needs_overrides = model is not None or provider is not None or plugins is not None
  if config is not None:
    base_config: Config | None = config
  elif needs_overrides:
    base_config = Config()
  else:
    base_config = None

  # Apply model / provider overrides on a derived frozen Config. This block
  # only runs when needs_overrides is True, so base_config is not None here.
  if model is not None or provider is not None:
    assert base_config is not None
    backend_cfg = base_config.backend
    if provider is not None:
      if provider in KNOWN_PROVIDERS and getattr(backend_cfg, provider) is None:
        defaults: dict[str, type] = {
          "openai": OpenAIConfig,
          "anthropic": AnthropicConfig,
          "gemini": GeminiConfig,
        }
        backend_cfg = dataclasses.replace(backend_cfg, **{provider: defaults[provider]()})
      backend_cfg = dataclasses.replace(backend_cfg, provider=provider)
    if model is not None:
      sub = backend_cfg.config
      new_sub = dataclasses.replace(sub, model=model)
      active = backend_cfg.provider
      backend_cfg = dataclasses.replace(backend_cfg, **{active: new_sub})  # type: ignore[arg-type]
    base_config = dataclasses.replace(base_config, backend=backend_cfg)

  # Enable plugin loading when plugins are explicitly requested.
  if plugins is not None and base_config is not None:
    base_config = dataclasses.replace(
      base_config,
      plugins=dataclasses.replace(base_config.plugins, enabled=True, packages=tuple(plugins)),
    )

  # Resolve the agent definition: explicit > path > built-from-kwargs.
  resolved_definition: AgentDefinition | None = agent_definition
  if resolved_definition is None and agent_path is not None:
    resolved_definition = load_agent_definition(agent_path)
  if resolved_definition is None and agent_path is None:
    # Build an AgentDefinition for the custom-config case. Returns None
    # when no customisation is needed. The pure-text path is expressed via
    # tools=[] (an empty whitelist clears all tools).
    if system_prompt is not None or tools is not None:
      simple_name: str | None = None
      tools_tuple: tuple[str, ...] = ()
      if tools is not None:
        simple_name = "custom"
        tools_tuple = tuple(tools)
      prompt = system_prompt if system_prompt is not None else "You are a helpful assistant."
      resolved_definition = AgentDefinition(
        simple_name=simple_name, system_prompt=prompt, tools=tools_tuple
      )

  thinking_mode = _THINKING_MAP.get(thinking)
  if thinking_mode is None:
    raise ValueError(
      f"Unknown thinking mode '{thinking}'. Expected one of: {', '.join(sorted(_THINKING_MAP))}"
    )

  built = Agent(
    config=base_config,
    thinking_mode=thinking_mode,
    agent_definition=resolved_definition,
    agent_path=agent_path if resolved_definition is None else None,
    context_manager=context_manager,
    plugins=plugins if plugins is not None else None,
    console_logging=console_logging,
    backend=backend,
  )

  # Filter skills to the requested subset (post-construction).
  if skills is not None:
    Agent.filter_skills(built.skills, skills)

  # Register the optional event handler.
  if event_handler is not None:
    built.on_event(event_handler)

  return built


async def process(
  prompt: str,
  **common_kwargs: Any,
) -> str:
  """Ask the configured model a single question and return the response.

  Loads a :class:`Config`, constructs an :class:`Agent`, runs one turn, and
  returns the assistant's reply. The agent is discarded (stateless one-shot).
  For multi-turn conversations use :func:`yoker.session`; for a reusable
  agent use :func:`yoker.agent`.

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


@asynccontextmanager
async def session(
  id: str | None = None,
  *,
  persist: bool = True,
  fresh: bool = False,
  **common_kwargs: Any,
) -> AsyncIterator[Session]:
  """Open a multi-turn session with automatic context persistence.

  Builds on the real :class:`yoker.session.Session` (MBI-007). The primary
  :class:`Agent` is constructed inside :meth:`Session.__init__` via the
  unified ``_create_agent`` flow with the given builder kwargs. The
  primary agent is available via :attr:`Session.agent`; sub-agents can be
  spawned via ``await session.spawn(name)``. Event handlers are
  registered via ``session.on_event(...)``.

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
  # Extract kwargs consumed here (not forwarded to Session.__init__).
  config: Config | None = common_kwargs.pop("config", None)
  agent_path: str | Path | None = common_kwargs.pop("agent_path", None)
  agent_definition: AgentDefinition | None = common_kwargs.pop("agent_definition", None)
  event_handler: EventCallback | None = common_kwargs.pop("event_handler", None)
  plugins: list[str] | None = common_kwargs.pop("plugins", None)
  model: str | None = common_kwargs.pop("model", None)
  provider: str | None = common_kwargs.pop("provider", None)
  thinking: str = common_kwargs.pop("thinking", "on")
  system_prompt: str | None = common_kwargs.pop("system_prompt", None)
  tools: list[str] | None = common_kwargs.pop("tools", None)
  skills: list[str] | None = common_kwargs.pop("skills", None)

  # config construction
  base_config = config if config is not None else Config()
  if id is not None:
    base_config = dataclasses.replace(
      base_config,
      context=dataclasses.replace(base_config.context, session_id=id, persist_after_turn=True),
    )
  if model is not None or provider is not None:
    backend_cfg = base_config.backend
    if provider is not None:
      if provider in KNOWN_PROVIDERS and getattr(backend_cfg, provider) is None:
        defaults: dict[str, type] = {
          "openai": OpenAIConfig,
          "anthropic": AnthropicConfig,
          "gemini": GeminiConfig,
        }
        backend_cfg = dataclasses.replace(backend_cfg, **{provider: defaults[provider]()})
      backend_cfg = dataclasses.replace(backend_cfg, provider=provider)
    if model is not None:
      sub = backend_cfg.config
      backend_cfg = dataclasses.replace(
        backend_cfg, **{backend_cfg.provider: dataclasses.replace(sub, model=model)}  # type: ignore[arg-type]
      )
    base_config = dataclasses.replace(base_config, backend=backend_cfg)

  # synthesize a definition from system_prompt/tools when no explicit one given;
  # agent_path-only resolution is delegated to Session._resolve_definition.
  resolved_definition: AgentDefinition | None = agent_definition
  if (
    resolved_definition is None
    and agent_path is None
    and (system_prompt is not None or tools is not None)
  ):
    resolved_definition = AgentDefinition(
      simple_name="custom" if tools is not None else None,
      system_prompt=system_prompt if system_prompt is not None else "You are a helpful assistant.",
      tools=tuple(tools) if tools is not None else (),
    )

  thinking_mode = _THINKING_MAP.get(thinking)
  if thinking_mode is None:
    raise ValueError(
      f"Unknown thinking mode '{thinking}'. Expected one of: {', '.join(sorted(_THINKING_MAP))}"
    )

  # Session.__init__ owns plugin loading, backend, and primary-agent creation.
  core = Session(
    config=base_config,
    session_id=id,
    extra_plugins=tuple(plugins) if plugins is not None else (),
    agent_definition=resolved_definition,
    agent_path=agent_path,
    thinking_mode=thinking_mode,
    console_logging=False,
  )

  # wire the persisted context manager onto the primary agent
  context_manager: ContextManager | None = None
  if persist:
    context_manager = Persisted(SimpleContextManager(), session_id=core.id)
    if fresh:
      context_manager.delete()
    context_manager.agent = core.agent
    core.agent.context = context_manager

  if skills is not None:
    Agent.filter_skills(core.agent.skills, skills)
  if event_handler is not None:
    core.on_event(event_handler)

  try:
    async with core:
      yield core
  finally:
    if context_manager is not None:
      context_manager.close()


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
