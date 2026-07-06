"""Layer 1 — One-shot utility functions.

Stateless, single-call entry points that construct an :class:`Agent`, run a
single turn, and return the response string. The agent is discarded after
the call. For multi-turn or reusable agents use :func:`yoker.agent`.

Async variants are the primary API. ``*_sync`` variants are convenience
wrappers for scripts / notebooks / REPLs and use :func:`asyncio.run` under
the hood (no hidden event-loop nesting).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from yoker.api._internal import build_agent, run_sync
from yoker.events import EventCallback

if TYPE_CHECKING:
  from yoker.agent import Agent

ThinkingLiteral = Literal["on", "off", "visible", "silent"]


async def ask(
  prompt: str,
  *,
  model: str | None = None,
  provider: str | None = None,
  system_prompt: str | None = None,
  tools: list[str] | None = None,
  skills: list[str] | None = None,
  plugins: list[str] | None = None,
  thinking: ThinkingLiteral = "on",
  event_handler: EventCallback | None = None,
) -> str:
  """Ask the configured model a single question and return the response.

  Loads a programmatic :class:`Config`, constructs an :class:`Agent`, runs
  one turn, and returns the assistant's reply. The agent is discarded
  (stateless one-shot). For multi-turn conversations use
  :func:`yoker.session`.

  Args:
    prompt: The user's question or instruction.
    model: Optional model override applied to the active provider config.
    provider: Optional backend provider (``"ollama"``, ``"openai"``, ...).
    system_prompt: Optional override for the agent's system prompt.
    tools: Optional whitelist of tool names. ``None`` keeps all configured
      tools; ``[]`` disables all tools; ``["read"]`` keeps only ``read``.
    skills: Optional whitelist of skill names. ``None`` keeps all loaded
      skills; ``[]`` disables all; ``["commit"]`` keeps only ``commit``.
    plugins: Optional plugin packages to load (e.g. ``["pkgq"]``).
    thinking: Thinking mode for the model.
    event_handler: Optional callback (sync or async) receiving every event
      emitted during the turn.

  Returns:
    The assistant's response string for the turn.
  """
  agent = build_agent(
    model=model,
    provider=provider,
    system_prompt=system_prompt,
    tools=tools,
    skills=skills,
    plugins=plugins,
    thinking=thinking,
    event_handler=event_handler,
    console_logging=False,
  )
  return await agent.process(prompt)


async def run_skill(
  skill_name: str,
  prompt: str = "",
  *,
  args: str = "",
  model: str | None = None,
  provider: str | None = None,
  plugins: list[str] | None = None,
  thinking: ThinkingLiteral = "on",
  event_handler: EventCallback | None = None,
) -> str:
  """Run a skill by name and return the response.

  Injects the skill's content into the agent's context via
  :meth:`Agent.inject_skill_context`, then runs a single turn. The skill
  must be discoverable from the configured skill directories or loaded
  plugins.

  Args:
    skill_name: Name of the skill to invoke (bare or namespaced).
    prompt: The user's task. Sent as the user message after the skill
      context is injected. May be empty when the skill content alone is
      enough to drive the turn.
    args: Optional arguments forwarded to the skill's invocation block.
    model: Optional model override.
    provider: Optional backend provider.
    plugins: Optional plugin packages to load.
    thinking: Thinking mode for the model.
    event_handler: Optional event callback.

  Returns:
    The assistant's response string for the turn.
  """
  agent = build_agent(
    model=model,
    provider=provider,
    plugins=plugins,
    thinking=thinking,
    event_handler=event_handler,
    console_logging=False,
  )
  resolved = _resolve_skill_name(agent, skill_name)
  agent.inject_skill_context(resolved, args or None)
  return await agent.process(prompt)


def _resolve_skill_name(agent: Agent, skill_name: str) -> str:
  """Resolve a skill name to its registry key.

  Accepts either the full registry key (``"ns:skill"``) or a bare simple
  name (``"skill"``). When a bare name matches exactly one registered skill
  (across any namespace) that key is used; when it matches multiple, the
  first one (alphabetically) is used. Raises :class:`SkillError` if no
  match is found.
  """
  from yoker.exceptions import SkillError

  if skill_name in agent.skills.data:
    return skill_name
  # Bare-name match across namespaces.
  matches = [
    key for key, skill in agent.skills.data.items() if (skill.simple_name or "") == skill_name
  ]
  if matches:
    return sorted(matches)[0]
  available = ", ".join(sorted(agent.skills.names))
  raise SkillError(
    skill_name,
    f"Unknown skill. Available skills: {available}" if available else "Unknown skill",
  )


async def complete(
  prompt: str,
  *,
  model: str | None = None,
  provider: str | None = None,
  thinking: ThinkingLiteral = "on",
) -> str:
  """Pure text completion — no tools, no skills, no system prompt.

  The lowest-friction way to ask a model a question from Python. Useful
  inside pipelines where the caller wants the model's text output without
  any agentic machinery.

  Args:
    prompt: The prompt to send to the model.
    model: Optional model override.
    provider: Optional backend provider.
    thinking: Thinking mode for the model.

  Returns:
    The model's completion string.
  """
  agent = build_agent(
    model=model,
    provider=provider,
    system_prompt="",
    no_tools=True,
    no_skills=True,
    thinking=thinking,
    console_logging=False,
  )
  return await agent.process(prompt)


def ask_sync(
  prompt: str,
  *,
  model: str | None = None,
  provider: str | None = None,
  system_prompt: str | None = None,
  tools: list[str] | None = None,
  skills: list[str] | None = None,
  plugins: list[str] | None = None,
  thinking: ThinkingLiteral = "on",
  event_handler: EventCallback | None = None,
) -> str:
  """Synchronous variant of :func:`ask`.

  Runs the async call via :func:`asyncio.run`. Raises :class:`RuntimeError`
  if called from inside a running event loop — use :func:`ask` there instead.
  """
  return run_sync(
    ask(
      prompt,
      model=model,
      provider=provider,
      system_prompt=system_prompt,
      tools=tools,
      skills=skills,
      plugins=plugins,
      thinking=thinking,
      event_handler=event_handler,
    )
  )


def run_skill_sync(
  skill_name: str,
  prompt: str = "",
  *,
  args: str = "",
  model: str | None = None,
  provider: str | None = None,
  plugins: list[str] | None = None,
  thinking: ThinkingLiteral = "on",
  event_handler: EventCallback | None = None,
) -> str:
  """Synchronous variant of :func:`run_skill`."""
  return run_sync(
    run_skill(
      skill_name,
      prompt,
      args=args,
      model=model,
      provider=provider,
      plugins=plugins,
      thinking=thinking,
      event_handler=event_handler,
    )
  )


def complete_sync(
  prompt: str,
  *,
  model: str | None = None,
  provider: str | None = None,
  thinking: ThinkingLiteral = "on",
) -> str:
  """Synchronous variant of :func:`complete`."""
  return run_sync(complete(prompt, model=model, provider=provider, thinking=thinking))


__all__ = [
  "ask",
  "run_skill",
  "complete",
  "ask_sync",
  "run_skill_sync",
  "complete_sync",
  "ThinkingLiteral",
]
