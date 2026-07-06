"""Example — Run a skill by name with ``yoker.run_skill``.

Run with:

    python examples/python_api/run_skill.py

The skill must be discoverable from the configured skill directories or
loaded plugins. Configure ``skills.directories`` in your ``yoker.toml``
or pass ``skills_directories=`` to :func:`yoker.config.make_config`.
"""

import asyncio

import yoker


async def main() -> None:
  # Inject the skill's content into the agent's context and run a turn.
  # The skill is found by name across all configured skill directories.
  result = await yoker.run_skill("commit", "stage and commit current changes")
  print(result)


if __name__ == "__main__":
  asyncio.run(main())
