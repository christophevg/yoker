"""Example 8 — Sync usage in a script with ``yoker.ask_sync``.

Run with:

    python examples/python_api/sync_usage.py

For scripts, notebooks, and REPLs where async is awkward. The ``*_sync``
wrappers run :func:`asyncio.run` internally and raise a clear error if
called from inside a running event loop.
"""

import yoker

# One line, one answer — no asyncio boilerplate.
answer = yoker.ask_sync("What files are in the current directory?")
print(answer)

# Skills work synchronously too.
# result = yoker.run_skill_sync("commit", "stage and commit all changes")
# print(result)
