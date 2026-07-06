"""Example 3 — Agent builder: configure a reusable agent with ``yoker.build_agent``.

Run with:

    python examples/python_api/agent_builder.py

Shows the fluent, declarative builder API. The returned object is a
:class:`yoker.Agent` — all existing methods (``process``, ``on_event``,
``inject_skill_context``, ``spawn``) work as expected.
"""

import asyncio

import yoker
from yoker.events import ToolCallEvent


async def main() -> None:
  # Build a security-focused code reviewer with a specific tool whitelist.
  reviewer = yoker.build_agent(
    model="qwen3.5:cloud",
    system_prompt=(
      "You are a security-focused code reviewer. Always cite file:line for every finding."
    ),
    tools=["read", "search", "list"],
    thinking="visible",
  )

  # Attach a typed event handler that logs every tool call.
  def log_tools(event: object) -> None:
    if isinstance(event, ToolCallEvent):
      print(f"[tool] {event.tool_name}({event.arguments})")

  reviewer.on_event(log_tools)

  # Reuse the same agent across turns.
  report = await reviewer.process("Review src/yoker/plugins/security.py for vulnerabilities.")
  print(report)


if __name__ == "__main__":
  asyncio.run(main())
