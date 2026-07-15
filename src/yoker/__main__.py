"""Entry point for running Yoker as a module.

Usage: python -m yoker [SUBCOMMAND] [OPTIONS]

Subcommands (registered via Clevis ``@configclass(cmd=...)`` in
:mod:`yoker.cli.commands`):

  chat       Start the interactive REPL (default when no subcommand is given)
  run        Run an agentic package non-interactively
  loop       Run an agentic package at intervals
  inspect    Dump a report about a source without executing it
  init       Generate a default configuration file
  config     Display the effective configuration
  container  Generate container setup for an agentic package

Configuration is loaded from TOML config files (~/.yoker.toml and ./yoker.toml).
CLI arguments are automatically generated from the Config data classes by Clevis.
When no subcommand is given, ``chat`` runs as the default (via Clevis's
``default_cmd=True`` on ``ChatConfig``). Examples:

  python -m yoker                              # -> yoker chat
  python -m yoker chat --ui-mode batch          # explicit chat subcommand
  python -m yoker --backend-ollama-model MODEL  # -> yoker chat --backend-ollama-model MODEL
"""

import sys

from clevis import get_cmd

from yoker.cli import commands as cli_commands  # noqa: F401 — registers @configclass(cmd=...)
from yoker.cli.chat import run_chat
from yoker.cli.config_cmd import run_config_cmd
from yoker.cli.container import run_container
from yoker.cli.init import run_init
from yoker.cli.inspect import run_inspect
from yoker.cli.loop import run_loop
from yoker.cli.run import run_run
from yoker.cli.shared import abort


def main() -> None:
  """Run Yoker.

  Strips ``--with`` plugin args, then dispatches to the subcommand handler via
  Clevis's ``get_cmd()``. When no subcommand is given, Clevis runs ``chat``
  automatically (``default_cmd=True`` on ``ChatConfig``).
  """
  plugin_packages, sys.argv = _parse_plugin_args()

  cmd = get_cmd()

  if cmd == "chat":
    run_chat(plugin_packages)
  elif cmd == "run":
    run_run(plugin_packages)
  elif cmd == "loop":
    run_loop(plugin_packages)
  elif cmd == "inspect":
    run_inspect()
  elif cmd == "init":
    run_init()
  elif cmd == "config":
    run_config_cmd()
  elif cmd == "container":
    run_container()
  else:
    # Should not happen: argparse rejects unknown subcommands with a
    # valid-choice list before get_cmd() returns. Guard anyway.
    abort(f"Error: unknown subcommand: {cmd}\n", 1)


def _parse_plugin_args(argv: list[str] | None = None) -> tuple[list[str], list[str]]:
  """Extract --with plugin arguments before standard parsing."""
  plugin_packages: list[str] = []
  args_to_remove: list[int] = []
  i = 1
  if argv is None:
    argv = sys.argv
  while i < len(argv):
    arg = argv[i]
    if arg == "--with":
      if i + 1 < len(argv):
        plugin_packages.append(argv[i + 1])
        args_to_remove.extend([i, i + 1])
        i += 2
      else:
        abort("Error: --with requires a package name\n", 1)
    else:
      i += 1

  cleaned = list(argv)
  for idx in sorted(args_to_remove, reverse=True):
    cleaned.pop(idx)

  return plugin_packages, cleaned


if __name__ == "__main__":
  main()
