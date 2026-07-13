"""``yoker inspect <source>`` subcommand handler — read-only source report.

Resolves a source via :func:`yoker.cli.sources.resolve_source` (phase 1 only —
metadata, no imports, no code execution) and displays a human-readable report
about what the source contains, uses, and does.

Security: this command is **read-only**. It does NOT import ``tools_module``,
does NOT call :func:`load_source`, and does NOT require the trust gate. Skills
and agent definitions are read from disk (Markdown + YAML frontmatter parsing,
not code execution). For module sources, the Python ``__YOKER_MANIFEST__``
cannot be discovered without importing the package, so the report notes that
trust is required to inspect it.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TextIO

from structlog import get_logger

from yoker.cli.commands import InspectConfig
from yoker.cli.shared import abort, load_subcommand_config, safe_cleanup
from yoker.cli.sources import ResolvedSource, resolve_source
from yoker.exceptions import YokerError

logger = get_logger(__name__)


def run_inspect() -> None:
  """Run the ``yoker inspect <source>`` subcommand.

  Loads :class:`InspectConfig` via Clevis, resolves the source (phase 1 only),
  prints a read-only report, and exits. No trust gate, no code execution.
  """
  try:
    config = load_subcommand_config(InspectConfig)
  except ValueError as e:
    abort(f"Error: {e}\n", 1)

  if not config.source:
    abort("Error: yoker inspect requires a source. Usage: yoker inspect <source>\n", 1)

  # Phase 1: resolve source (metadata only — safe, no code execution).
  try:
    resolved = resolve_source(config.source)
  except YokerError as e:
    abort(f"Error: {e}\n", 1)

  try:
    _print_report(resolved)
  finally:
    safe_cleanup(resolved)


def _print_report(resolved: ResolvedSource) -> None:
  """Print the human-readable source report to stdout."""
  out: TextIO = sys.stdout
  out.write("Source Report\n")
  out.write("=============\n\n")
  out.write(f"Source:      {resolved.source_string}\n")
  out.write(f"Type:        {resolved.kind}\n")
  out.write(f"Trust key:   {resolved.trust_key}\n")
  out.write(f"Path:        {resolved.path}\n\n")

  _print_contains(resolved, out)
  _print_uses(resolved, out)
  _print_does(resolved, out)
  _print_overrides(resolved, out)

  out.write("\n(inspect — read-only, no code executed)\n")


def _print_contains(resolved: ResolvedSource, out: TextIO) -> None:
  """Print 'What it contains': skills, agents, tools (names only)."""
  out.write("What it contains\n")
  out.write("----------------\n")

  if resolved.kind == "module":
    # Cannot discover __YOKER_MANIFEST__ without importing (code execution).
    out.write("Skills:    (requires trust to inspect Python manifest)\n")
    out.write("Agents:    (requires trust to inspect Python manifest)\n")
    out.write("Tools:     (requires trust to inspect Python manifest)\n\n")
    return

  # folder / github / zip: read skills and agents from disk (no imports).
  folder = resolved.path
  plugin_config = resolved.manifest.plugin_config if resolved.manifest is not None else None
  skills_dir = getattr(plugin_config, "skills_dir", "skills") or "skills"
  agents_dir = getattr(plugin_config, "agents_dir", "agents") or "agents"
  tools_module = getattr(plugin_config, "tools_module", None)

  skills = _list_skills(folder / skills_dir)
  agents = _list_agents(folder / agents_dir)

  out.write(f"Skills:    {skills}\n")
  out.write(f"Agents:    {agents}\n")
  if tools_module is not None:
    out.write(f"Tools:     {tools_module} (declared, NOT imported)\n")
  else:
    out.write("Tools:     (no tools_module declared)\n")
  out.write("\n")


def _print_uses(resolved: ResolvedSource, out: TextIO) -> None:
  """Print 'What it uses': dependencies, tools_module declaration."""
  out.write("What it uses\n")
  out.write("------------\n")

  tools_module = None
  if resolved.manifest is not None:
    tools_module = resolved.manifest.plugin_config.tools_module

  out.write(f"tools_module: {tools_module if tools_module else '(not declared)'}\n")

  deps = _read_dependencies(resolved)
  out.write(f"Dependencies: {deps}\n\n")


def _print_does(resolved: ResolvedSource, out: TextIO) -> None:
  """Print 'What it does': agent and prompt from the manifest."""
  out.write("What it does\n")
  out.write("------------\n")

  agent = None
  prompt = None
  if resolved.manifest is not None:
    agent = resolved.manifest.run_config.agent
    prompt = resolved.manifest.run_config.prompt

  out.write(f"Agent:  {agent if agent else '(not set)'}\n")
  out.write(f"Prompt: {prompt if prompt else '(not set)'}\n\n")


def _print_overrides(resolved: ResolvedSource, out: TextIO) -> None:
  """Print config overrides from the manifest (if any)."""
  overrides = resolved.manifest.config_overrides if resolved.manifest else {}
  if not overrides:
    out.write("Config overrides: (none)\n")
    return

  out.write("Config overrides:\n")
  for key, value in overrides.items():
    out.write(f"  {key}: {value}\n")


def _list_skills(skills_path: Path) -> str:
  """List skill names from a skills directory (read-only, no imports)."""
  if not skills_path.is_dir():
    return "(no skills directory)"
  try:
    from yoker.skills import load_skills

    names = list(load_skills(skills_path).keys())
    return ", ".join(names) if names else "(none)"
  except Exception as e:
    logger.warning("inspect_skills_failed", error=str(e))
    return f"(error reading skills: {e})"


def _list_agents(agents_path: Path) -> str:
  """List agent definition names from an agents directory (read-only)."""
  if not agents_path.is_dir():
    return "(no agents directory)"
  try:
    from yoker.agents import load_agent_definitions

    names = [a.name for a in load_agent_definitions(agents_path)]
    return ", ".join(names) if names else "(none)"
  except Exception as e:
    logger.warning("inspect_agents_failed", error=str(e))
    return f"(error reading agents: {e})"


def _read_dependencies(resolved: ResolvedSource) -> str:
  """Read dependencies from pyproject.toml if present (read-only)."""
  if resolved.kind == "module":
    return "(cannot read pyproject.toml for module sources without trust)"

  pyproject = resolved.path / "pyproject.toml"
  if not pyproject.is_file():
    return "(no pyproject.toml found)"

  try:
    from clevis import _load_toml  # type: ignore[attr-defined]

    with pyproject.open("rb") as fh:
      data = dict(_load_toml(fh))
    deps = data.get("project", {}).get("dependencies", [])
    if not deps:
      return "(none declared)"
    return ", ".join(str(d) for d in deps)
  except Exception as e:
    logger.warning("inspect_dependencies_failed", error=str(e))
    return f"(error reading pyproject.toml: {e})"


__all__ = ["run_inspect"]
