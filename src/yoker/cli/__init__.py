"""CLI subcommand configuration and dispatch.

This package registers yoker's subcommands with Clevis via ``@configclass(cmd=...)``
and provides shared helpers for config loading. The chat subcommand handler
stays in ``src/yoker/__main__.py`` for now; later tasks (4.2+) move per-subcommand
handlers into dedicated modules under this package.
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
from yoker.cli.shared import load_subcommand_config

__all__ = [
  "ChatConfig",
  "ConfigCmdConfig",
  "ContainerConfig",
  "InitConfig",
  "InspectConfig",
  "LoopConfig",
  "RunConfig",
  "load_subcommand_config",
]
