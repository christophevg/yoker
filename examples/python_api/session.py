"""Example 5 — Multi-turn conversation with ``yoker.session``.

Run with:

    python examples/python_api/session.py

Context persists across turns automatically. The session id makes the
conversation resumable — re-opening the same id restores history.
"""

import asyncio

import yoker


async def main() -> None:
  async with yoker.session(id="refactor-auth") as session:
    await session.ask("Read src/auth.py and identify the main responsibilities.")
    await session.ask("Suggest a refactor that splits authentication from session management.")
    await session.ask("Apply the refactor. Write the new files.")
    await session.ask("Update the tests to match the new structure.")


if __name__ == "__main__":
  asyncio.run(main())
