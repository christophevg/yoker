"""Example 5 — Multi-turn conversation with ``yoker.session``.

Run with:

    python examples/python_api/session.py

Context persists across turns automatically. The session id makes the
conversation resumable — re-opening the same id restores history. Access the
primary agent via ``session.primary_agent`` and call ``process()`` directly.
"""

import asyncio

import yoker


async def main() -> None:
  async with yoker.session(id="refactor-auth") as session:
    await session.primary_agent.process("Read src/auth.py and identify the main responsibilities.")
    await session.primary_agent.process(
      "Suggest a refactor that splits authentication from session management."
    )
    await session.primary_agent.process("Apply the refactor. Write the new files.")
    await session.primary_agent.process("Update the tests to match the new structure.")


if __name__ == "__main__":
  asyncio.run(main())
