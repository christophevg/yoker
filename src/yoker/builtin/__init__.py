"""Built-in tools for Yoker.

These tools are registered by default when the yoker plugin is loaded.

MBI-007 Phase 4: the ``agent`` tool is replaced by ``SpawnAgent``, which is
Session-injected (see :mod:`yoker.session.tools`). ``SpawnAgent`` and
``SendMessage`` are NOT part of the static plugin manifest — they are
registered on Agents by the :class:`yoker.session.Session` at spawn/registration
time.
"""

from yoker.builtin.existence import existence
from yoker.builtin.git import git
from yoker.builtin.list import list
from yoker.builtin.mkdir import mkdir
from yoker.builtin.read import read
from yoker.builtin.search import search
from yoker.builtin.skill import make_skill_tool
from yoker.builtin.update import update
from yoker.builtin.webfetch import webfetch
from yoker.builtin.websearch import websearch
from yoker.builtin.write import write
from yoker.plugins.manifest import PluginManifest

__all__ = [
  "existence",
  "git",
  "list",
  "mkdir",
  "read",
  "search",
  "update",
  "webfetch",
  "websearch",
  "write",
  "make_skill_tool",
]

# Built-in Yoker plugin manifest.
# All built-in tools are registered here for discovery. The agent tool
# (now SpawnAgent) and the SendMessage tool are Session-injected and are
# NOT listed here — they are registered on Agents by the Session at
# spawn/registration time (PR #43 Clarifications 2 & 4). The skill tool
# uses a factory function (make_skill_tool) because it needs the
# SkillRegistry at runtime.

__YOKER_MANIFEST__ = PluginManifest(
  tools=[existence, git, list, mkdir, read, search, update, webfetch, websearch, write],
  skills_dir="skills",
  agents_dir="agents",
)

__all__.append("__YOKER_MANIFEST__")
