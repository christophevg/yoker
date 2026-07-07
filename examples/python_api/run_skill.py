"""Example — Run a skill by name with ``yoker.do``.

Run with:

    python examples/python_api/run_skill.py

The skill must be discoverable from the configured skill directories or
loaded plugins. Configure ``skills.directories`` in your ``yoker.toml``
or pass ``skills_directories=`` to :func:`yoker.config.make_config`.
"""

import asyncio

import yoker


async def main() -> None:
  # One-shot skill invocation: yoker.do builds an agent, injects the
  # skill's context, runs a single turn, and returns the response.
  result = await yoker.do("commit", "stage and commit current changes")
  print(result)


if __name__ == "__main__":
  asyncio.run(main())
