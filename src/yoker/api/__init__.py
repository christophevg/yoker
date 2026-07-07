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
from yoker.context import ContextManager
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


def _build_config_and_definition(
  *,
  config: Config | None,
  model: str | None,
  provider: str | None,
  system_prompt: str | None,
  tools: list[str] | None,
  agent_path: str | Path | None,
  agent_definition: AgentDefinition | None,
  thinking: str,
  require_config: bool,
  load_path_inline: bool,
) -> tuple[Config | None, AgentDefinition | None, str | Path | None, ThinkingMode]:
  """Build the base Config, AgentDefinition, and thinking mode shared by agent()/session().

  Owns: base-config determination (explicit > Config() when overrides needed >
  None for filesystem discovery), model/provider overrides, agent-definition
  resolution (explicit > path-loaded-inline > built-from-kwargs), and thinking
  mapping. Does NOT own plugins-to-config application (agent()-only), skill
  filtering, context-manager construction, or Session/Agent wiring.
  """
  # base config: explicit > Config() when overrides needed > None (filesystem discovery)
  needs_overrides = model is not None or provider is not None
  if config is not None:
    base: Config | None = config
  elif require_config or needs_overrides:
    base = Config()
  else:
    base = None

  # apply model / provider overrides
  if (model is not None or provider is not None) and base is not None:
    backend_cfg = base.backend
    if provider is not None:
      if provider in KNOWN_PROVIDERS and getattr(backend_cfg, provider) is None:
        defaults: dict[str, type] = {
          "openai": OpenAIConfig,
          "anthropic": AnthropicConfig,
          "gemini": GeminiConfig,
        }
        setattr(backend_cfg, provider, defaults[provider]())
      backend_cfg.provider = provider
    if model is not None:
      backend_cfg.config.model = model
    backend_cfg.validate()

  # resolve agent definition: explicit > path (inline) > built-from-kwargs
  resolved_definition: AgentDefinition | None = agent_definition
  if resolved_definition is None and agent_path is not None and load_path_inline:
    resolved_definition = load_agent_definition(agent_path)
  if resolved_definition is None and agent_path is None:
    # tools=[] clears all tools; system_prompt alone needs a default prompt
    if system_prompt is not None or tools is not None:
      resolved_definition = AgentDefinition(
        simple_name="custom" if tools is not None else None,
        system_prompt=system_prompt
        if system_prompt is not None
        else "You are a helpful assistant.",
        tools=tuple(tools) if tools is not None else (),
      )

  thinking_mode = _THINKING_MAP.get(thinking)
  if thinking_mode is None:
    raise ValueError(
      f"Unknown thinking mode '{thinking}'. Expected one of: {', '.join(sorted(_THINKING_MAP))}"
    )

  # forward agent_path only when no definition resolved inline (else caller would re-resolve)
  forwarded_path = agent_path if (not load_path_inline or resolved_definition is None) else None
  return base, resolved_definition, forwarded_path, thinking_mode


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
  base, resolved_definition, forwarded_path, thinking_mode = _build_config_and_definition(
    config=config,
    model=model,
    provider=provider,
    system_prompt=system_prompt,
    tools=tools,
    agent_path=agent_path,
    agent_definition=agent_definition,
    thinking=thinking,
    require_config=False,
    load_path_inline=True,
  )

  # enable plugin loading when plugins explicitly requested
  if plugins is not None and base is not None:
    base.plugins.enabled = True
    base.plugins.packages = tuple(plugins)

  built = Agent(
    config=base,
    thinking_mode=thinking_mode,
    agent_definition=resolved_definition,
    agent_path=forwarded_path,
    context_manager=context_manager,
    plugins=plugins,
    console_logging=console_logging,
    backend=backend,
  )

  if skills is not None:
    Agent.filter_skills(built.skills, skills)
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
  # extract kwargs consumed here (not forwarded to Session.__init__)
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

  base, resolved_definition, forwarded_path, thinking_mode = _build_config_and_definition(
    config=config,
    model=model,
    provider=provider,
    system_prompt=system_prompt,
    tools=tools,
    agent_path=agent_path,
    agent_definition=agent_definition,
    thinking=thinking,
    require_config=True,
    load_path_inline=False,
  )
  assert base is not None  # require_config=True guarantees a non-None base

  # fold id/persist/fresh into context config — Session owns the lifecycle
  if id is not None:
    base.context.session_id = id
  base.context.persist_after_turn = persist
  base.context.fresh = fresh

  # Session.__init__ owns plugin loading, backend, and primary-agent creation
  core = Session(
    config=base,
    session_id=id,
    thinking_mode=thinking_mode,
    console_logging=False,
    agent_definition=resolved_definition,
    agent_path=forwarded_path,
    extra_plugins=tuple(plugins) if plugins is not None else (),
  )

  if skills is not None:
    Agent.filter_skills(core.agent.skills, skills)
  if event_handler is not None:
    core.on_event(event_handler)

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
