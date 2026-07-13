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
When no subcommand is given, ``chat`` is inserted as the default (backward
compatibility). Examples:

  python -m yoker                              # -> yoker chat
  python -m yoker chat --ui-mode batch          # explicit chat subcommand
  python -m yoker --backend-ollama-model MODEL  # -> yoker chat --backend-ollama-model MODEL
"""

import sys

from clevis import get_cmd

from yoker.cli import commands as cli_commands  # noqa: F401 — registers @configclass(cmd=...)
from yoker.cli.chat import run_chat
from yoker.cli.config_cmd import run_config_cmd
from yoker.cli.init import run_init
from yoker.cli.run import run_run
from yoker.cli.shared import abort

# Subcommand names registered with Clevis. Used to detect whether the first
# positional argument is a known subcommand (don't insert the default) or an
# unknown one (let argparse error with the valid-choice list).
KNOWN_COMMANDS = frozenset(
  {
    "chat",
    "run",
    "loop",
    "inspect",
    "init",
    "config",
    "container",
  }
)

# Subcommands that are stubbed out (not yet implemented). chat, init, config,
# and run are the working end-to-end subcommands; the rest print a notice and
# exit.
STUB_COMMANDS = frozenset({"loop", "inspect", "container"})


def main() -> None:
  """Run Yoker.

  Strips ``--with`` plugin args, defaults to the ``chat`` subcommand when none
  is given (backward compatibility), then dispatches to the subcommand handler
  via Clevis's ``get_cmd()``.
  """
  plugin_packages, sys.argv = _parse_plugin_args()

  # Default to chat when no subcommand is given. We patch sys.argv to insert
  # "chat" as the first positional so existing `yoker --backend-ollama-model X`
  # invocations route to `yoker chat --backend-ollama-model X`.
  #
  # TODO: submit a feature request to Clevis for configurable subcommand
  # defaults (e.g. a `default_cmd` on the subparser manager) so we can stop
  # patching sys.argv manually.
  if _needs_default_chat(sys.argv):
    sys.argv.insert(1, "chat")

  cmd = get_cmd()

  if cmd == "chat":
    run_chat(plugin_packages)
  elif cmd == "run":
    run_run(plugin_packages)
  elif cmd == "init":
    run_init()
  elif cmd == "config":
    run_config_cmd()
  elif cmd in STUB_COMMANDS:
    sys.stdout.write(f"yoker {cmd}: not yet implemented\n")
    sys.exit(0)
  else:
    # Should not happen: argparse rejects unknown subcommands with a
    # valid-choice list before get_cmd() returns. Guard anyway.
    abort(f"Error: unknown subcommand: {cmd}\n", 1)


def _needs_default_chat(argv: list[str]) -> bool:
  """Return True if we should insert "chat" as the default subcommand.

  We insert "chat" when:
  - No args follow the program name (bare ``yoker``), or
  - The first arg is a flag (e.g. ``yoker --backend-ollama-model X``), meaning
    the user expects the default command with config overrides.

  We leave argv untouched when:
  - The first arg is ``--help`` / ``-h`` (let the top-level parser show the
    subcommand list), or
  - The first arg is a known subcommand (let it route), or
  - The first arg is an unknown positional (let argparse reject it with the
    valid-choice list — this is how ``yoker <unknown>`` reports valid
    subcommands).
  """
  if len(argv) <= 1:
    return True
  first = argv[1]
  if first in ("--help", "-h"):
    return False
  if first.startswith("-"):
    return True
  # First positional: only default when it is not a known subcommand name.
  # For unknown positionals, let argparse error with the choice list.
  return False


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
