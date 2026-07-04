"""Legacy agent tool module — superseded by Session-injected SpawnAgent (MBI-007 Phase 4).

PR #43 Clarification 2: the built-in ``agent`` tool is replaced by
``SpawnAgent``, a Session-injected tool. ``SpawnAgent`` lives in
``yoker.session.tools`` and is registered on Agents by the
:class:`yoker.session.Session` (via ``Session.inject_tools`` /
``Session.register_primary_agent``), not by the Agent itself and not by the
plugin loader.

This module is kept as an empty placeholder so existing imports
(``from yoker.builtin.agent import ...``) fail loudly with a clear error
rather than silently importing the wrong thing. The transitional
``make_agent_tool`` factory, ``_create_subagent``, ``_run_with_timeout``,
and ``_clamp`` have been removed — their logic now lives on
:class:`yoker.session.Session` and in ``yoker.session.tools``.
"""

__all__: list[str] = []
