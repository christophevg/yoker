"""CLI subcommand configuration and dispatch.

This package registers yoker's subcommands with Clevis via ``@configclass(cmd=...)``
and provides shared helpers for config loading. Subcommand handlers live in
dedicated modules: ``chat.py``, ``init.py``, ``config_cmd.py``, etc.
"""

from yoker.cli.commands import (
  ChatConfig,
  ConfigCmdConfig,
  ContainerConfig,
  InitConfig,
  InspectConfig,
  LoopConfig,
  RunConfig,
)
from yoker.cli.shared import abort, load_subcommand_config
from yoker.cli.sources import LoadedSource, ResolvedSource, load_source, resolve_source

__all__ = [
  "ChatConfig",
  "ConfigCmdConfig",
  "ContainerConfig",
  "InitConfig",
  "InspectConfig",
  "LoopConfig",
  "RunConfig",
  "abort",
  "load_subcommand_config",
  "LoadedSource",
  "ResolvedSource",
  "load_source",
  "resolve_source",
]
