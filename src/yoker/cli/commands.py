"""Subcommand config classes for the yoker CLI.

Each subcommand is registered with Clevis via ``@configclass(cmd="...")``. Clevis
generates a subparser with auto-generated CLI args from the dataclass fields and
handles dispatch via ``get_cmd()``.

Config-backed subcommands (``chat``, ``run``, ``loop``, ``config``) extend the
base :class:`yoker.config.Config` class, preserving all existing CLI args under
each subcommand. Config-free subcommands (``inspect``, ``init``, ``container``)
are standalone dataclasses with only their own fields — they bypass base config
loading entirely.

TOML extraction: when ``@configclass(cmd="X")`` is set, Clevis looks for an ``[X]``
section in the TOML config. If found, it extracts that section to root level before
populating the dataclass. If not found, root-level TOML is used as-is — so
existing ``~/.yoker.toml`` files with root-level fields continue to work as the
default (chat) config. Users can optionally organize config into ``[chat]``,
``[run]``, etc. sections.
"""

from clevis import configclass

from yoker.config import Config


@configclass(cmd="chat", help="Start the interactive REPL (default subcommand)")  # type: ignore[arg-type]
class ChatConfig(Config):
  """Config for ``yoker chat``.

  Same fields as :class:`Config`; no additions needed. ``chat`` is the default
  subcommand when no subcommand is given (handled in ``__main__.py``).
  """


@configclass(cmd="run", help="Run an agentic package non-interactively")  # type: ignore[arg-type]
class RunConfig(Config):
  """Config for ``yoker run``.

  Extends :class:`Config` with run-specific fields. The source to run, agent,
  and prompt come from the source's manifest (``agent.toml``); CLI overrides
  ``--agent`` and ``--prompt`` are handled by a local argparse in the run
  subcommand (not Config fields).
  """

  source: str = ""
  persist: bool = False
  session_id: str | None = None
  dry_run: bool = False


@configclass(cmd="loop", help="Run an agentic package at intervals")  # type: ignore[arg-type]
class LoopConfig(RunConfig):
  """Config for ``yoker loop``. Extends :class:`RunConfig` with loop fields."""

  interval: int = 300
  max_iterations: int = 100
  max_duration: int | None = None


@configclass(cmd="inspect", help="Dump a report about a source without executing it")  # type: ignore[arg-type]
class InspectConfig:
  """Config for ``yoker inspect``. No base Config needed — read-only."""

  source: str = ""


@configclass(cmd="init", help="Generate a default configuration file")  # type: ignore[arg-type]
class InitConfig:
  """Config for ``yoker init``. No base Config needed."""

  no_interactive: bool = False
  path: str | None = None
  force: bool = False


@configclass(cmd="config", help="Display the effective configuration")  # type: ignore[arg-type]
class ConfigCmdConfig(Config):
  """Config for ``yoker config``. Same fields as :class:`Config`; display only."""

  json: bool = False
  show_path: bool = False
  reveal: bool = False


@configclass(cmd="container", help="Generate container setup for an agentic package")  # type: ignore[arg-type]
class ContainerConfig:
  """Config for ``yoker container``. No base Config needed."""

  source: str = ""
  engine: str = "docker"
  output_dir: str = "."
  base_image: str = "python:3.12-slim"
  compose: bool = False


__all__ = [
  "ChatConfig",
  "RunConfig",
  "LoopConfig",
  "InspectConfig",
  "InitConfig",
  "ConfigCmdConfig",
  "ContainerConfig",
]
