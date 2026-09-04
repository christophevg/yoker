"""Example 7 — Custom event handling with typed events.

Run with:

    python examples/python_api/event_handling.py

The event system is unchanged. ``on_event`` registers a callback that
receives every :class:`yoker.events.Event` emitted by the agent. Typed
events make filtering clean and static-analysis-friendly.
"""

import asyncio
from typing import Any

import yoker
from yoker.events import ContentChunkEvent, ToolCallEvent, TurnEndEvent


def handler(event: Any) -> None:
  """Stream content to stdout while logging tool calls and stats."""
  if isinstance(event, ContentChunkEvent):
    print(event.text, end="", flush=True)
  elif isinstance(event, ToolCallEvent):
    print(f"\n[tool] {event.tool_name}({event.arguments})")
  elif isinstance(event, TurnEndEvent):
    # Which pair is populated depends on the backend: LiteLLM backends fill
    # input_tokens/output_tokens, the native Ollama backend fills
    # prompt_eval_count/eval_count (the other pair stays 0).
    print(
      f"\n[tokens] in={event.input_tokens} out={event.output_tokens}"
      f" | ollama: prompt_eval={event.prompt_eval_count} eval={event.eval_count}"
    )


async def main() -> None:
  agent = yoker.agent(model="qwen3.5:cloud", event_handler=handler)
  await agent.process("List the files in the current directory and explain what each one does.")


if __name__ == "__main__":
  asyncio.run(main())
