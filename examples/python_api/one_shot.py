"""Example 1 & 2 — One-shot functions: ``yoker.ask`` and ``yoker.complete``.

Run with:

    python examples/python_api/one_shot.py

Requires a configured backend (e.g. Ollama on http://localhost:11434, or
set ``YOKER_BACKEND_PROVIDER`` / model via a ``yoker.toml``).
"""

import asyncio

import yoker


async def main() -> None:
  # The simplest entry point: one function call, one response string.
  answer = await yoker.ask("What is 2+2?")
  print(f"ask: {answer}")

  # Pure text completion — no tools, no skills, no system prompt. Useful
  # inside Python pipelines where you just want the model's text output.
  translation = await yoker.complete(
    "Translate to French: 'Hello, how are you?'",
    model="gpt-4o-mini",
    provider="openai",
  )
  print(f"complete: {translation}")


if __name__ == "__main__":
  asyncio.run(main())
