"""Example 8 — Sync usage in a script with ``yoker.run_sync``.

Run with:

    python examples/python_api/sync_usage.py

For scripts, notebooks, and REPLs where async is awkward. ``yoker.run_sync``
wraps :func:`asyncio.run` and raises a clear error if called from inside a
running event loop.
"""

import yoker

# One line, one answer — no asyncio boilerplate.
answer = yoker.run_sync(yoker.process("What files are in the current directory?"))
print(answer)

# Skills work synchronously too via Agent.do:
# agent = yoker.agent()
# result = yoker.run_sync(agent.do("commit", "stage and commit all changes"))
# print(result)
