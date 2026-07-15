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
from yoker.cli.shared import (
  MAX_PROMPT_BYTES,
  abort,
  load_subcommand_config,
  load_subcommand_config_with_manifest,
  parse_run_overrides,
  register_source_agents,
  resolve_agent_and_prompt,
  safe_cleanup,
)
from yoker.cli.sources import LoadedSource, ResolvedSource, load_source, resolve_source

__all__ = [
  "ChatConfig",
  "ConfigCmdConfig",
  "ContainerConfig",
  "InitConfig",
  "InspectConfig",
  "LoopConfig",
  "RunConfig",
  "MAX_PROMPT_BYTES",
  "abort",
  "load_subcommand_config",
  "load_subcommand_config_with_manifest",
  "parse_run_overrides",
  "register_source_agents",
  "resolve_agent_and_prompt",
  "safe_cleanup",
  "LoadedSource",
  "ResolvedSource",
  "load_source",
  "resolve_source",
]
