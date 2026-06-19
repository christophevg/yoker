"""Plugin URL parsing for Yoker.

Thin re-export of the generic ``plugin://`` parser in :mod:`yoker.resources`.
The parser is resource-type agnostic — it only splits a URL into a package and
a slash-separated subpath. Interpretation of the subpath (e.g. an ``agents/``
prefix denotes an agent resource) lives in the consuming layer
(:mod:`yoker.plugins.agents`, :mod:`yoker.tools.read`).
"""

from yoker.resources import PluginURL, parse_plugin_url

__all__ = ["PluginURL", "parse_plugin_url"]