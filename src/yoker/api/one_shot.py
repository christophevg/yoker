"""Layer 1 — One-shot utility functions.

Stateless, single-call entry points that construct an :class:`Agent`, run a
single turn, and return the response string. The agent is discarded after
the call. For multi-turn or reusable agents use :func:`yoker.agent`.

The single one-shot function is :func:`process`. For skill invocation as a
command use :meth:`Agent.do`. For synchronous callers use
:func:`yoker.run_sync`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from yoker.api._internal import build_agent
from yoker.events import EventCallback

if TYPE_CHECKING:
  pass

ThinkingLiteral = Literal["on", "off", "visible", "silent"]


async def process(
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
  :func:`yoker.session`; for a reusable agent use :func:`yoker.agent`.

  Args:
    prompt: The user's question or instruction.
    model: Optional model override applied to the active provider config.
    provider: Optional backend provider (``"ollama"``, ``"openai"``, ...).
    system_prompt: Optional override for the agent's system prompt. Pass an
      empty string for pure text completion with no system prompt.
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


__all__ = ["process", "ThinkingLiteral"]
