"""File-based manifest for Yoker sources (``agent.toml``).

The manifest is a **generic config-override layer** sitting between the
project TOML (``./yoker.toml``) and CLI arguments in the configuration
cascade::

    dataclass defaults
      -> user TOML (~/.yoker.toml)
      -> project TOML (./yoker.toml)
      -> manifest overrides (<source>/agent.toml)   <-- this module
      -> CLI arguments (highest priority)

A manifest lives in the *source root* (the package/folder being run) and is
named ``agent.toml`` (NOT ``yoker.toml``) to avoid collision with the
project-level configuration file. It has three parts:

``[run]``
    Source-specific run config. ``agent`` (the agent definition name to use)
    and ``prompt`` (the initial prompt). Both optional; default to ``None``.

``[plugin]``
    Source-specific plugin config. ``skills_dir`` (default ``"skills"``),
    ``agents_dir`` (default ``"agents"``), and optional ``tools_module``
    (a Python module to import tools from — imported lazily by the loader,
    NOT by this parser).

All other tables/keys
    **Config overrides** — any :class:`yoker.config.Config` field can be
    overridden. They are returned as a nested dict for the config loader to
    deep-merge into the base config dict (see
    :func:`yoker.config.get_yoker_config_with_manifest`).

Security: this module only parses TOML into plain dataclass/dict fields. It
does NOT import ``tools_module`` or execute any code — the ``tools_module``
import happens in the loader AFTER the trust gate
(:func:`yoker.plugins.security.check_plugin_allowed`).
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from yoker.exceptions import PluginError

# Sentinel section names extracted from the manifest before config merging.
_RUN_SECTION = "run"
_PLUGIN_SECTION = "plugin"


@dataclass
class RunConfig:
  """Source-specific run configuration (the ``[run]`` section of agent.toml).

  Attributes:
    agent: Agent definition name to use for ``yoker run``.
    prompt: Initial prompt for ``yoker run``.
  """

  agent: str | None = None
  prompt: str | None = None


@dataclass
class PluginConfig:
  """Source-specific plugin configuration (the ``[plugin]`` section).

  Attributes:
    skills_dir: Directory name containing skill definition files.
    agents_dir: Directory name containing agent definition files.
    tools_module: Optional Python module to import tools from. Parsed here
      as a string only; the actual import is deferred to the loader and
      gated by the plugin trust check.
  """

  skills_dir: str = "skills"
  agents_dir: str = "agents"
  tools_module: str | None = None


@dataclass
class FileManifestResult:
  """Parsed ``agent.toml`` contents.

  Attributes:
    run_config: The ``[run]`` section.
    plugin_config: The ``[plugin]`` section.
    config_overrides: All remaining tables/keys — config overrides to be
      deep-merged into the base config dict between project TOML and CLI args.
  """

  run_config: RunConfig
  plugin_config: PluginConfig
  config_overrides: dict[str, Any]


def load_file_manifest(path: Path) -> FileManifestResult | None:
  """Load and parse an ``agent.toml`` file manifest.

  Args:
    path: Path to the ``agent.toml`` file. Typically ``<source_root>/agent.toml``.

  Returns:
    A :class:`FileManifestResult` with ``[run]``, ``[plugin]``, and config
    overrides separated out. Returns ``None`` if the file does not exist
    (caller decides whether that is an error).

  Raises:
    PluginError: If the file exists but is malformed TOML or contains
      tables of the wrong type for ``[run]``/``[plugin]``.

  Security: this function only parses TOML. It does not import
    ``tools_module`` or execute any code.
  """
  if not path.exists():
    return None

  raw = _parse_toml(path)

  # Extract [run] and [plugin]; everything else is a config override.
  run_data = _pop_table(raw, _RUN_SECTION, path)
  plugin_data = _pop_table(raw, _PLUGIN_SECTION, path)

  run_config = _build_run_config(run_data, path)
  plugin_config = _build_plugin_config(plugin_data, path)

  return FileManifestResult(
    run_config=run_config,
    plugin_config=plugin_config,
    config_overrides=raw,
  )


def _parse_toml(path: Path) -> dict[str, Any]:
  """Parse a TOML file, raising PluginError on parse failure."""
  # Use clevis's selected parser so env-var interpolation (${VAR|default})
  # behaves the same as ~/.yoker.toml and ./yoker.toml.
  # TODO(clevis-feature-request): ask Clevis to expose a public TOML loader
  # and/or a config-override cascade API so we don't reach into internals.
  from clevis import _load_toml  # type: ignore[attr-defined]

  try:
    with path.open("rb") as fh:
      return dict(_load_toml(fh))
  except Exception as e:  # TOML parse errors vary by parser
    raise PluginError(
      package=str(path),
      message=f"Malformed agent.toml at {path}: {e}",
    ) from e


def _pop_table(raw: dict[str, Any], name: str, path: Path) -> dict[str, Any]:
  """Remove and return a top-level table; validate it's a table if present."""
  value = raw.pop(name, {})
  if value is None:
    return {}
  if not isinstance(value, dict):
    raise PluginError(
      package=str(path),
      message=f"[{name}] in {path} must be a TOML table, got {type(value).__name__}",
    )
  return value


def _build_run_config(data: dict[str, Any], path: Path) -> RunConfig:
  """Build RunConfig from the [run] table, validating field types."""
  agent = data.get("agent")
  prompt = data.get("prompt")
  if agent is not None and not isinstance(agent, str):
    raise PluginError(
      package=str(path),
      message=f"[run].agent in {path} must be a string, got {type(agent).__name__}",
    )
  if prompt is not None and not isinstance(prompt, str):
    raise PluginError(
      package=str(path),
      message=f"[run].prompt in {path} must be a string, got {type(prompt).__name__}",
    )
  extra = set(data) - {"agent", "prompt"}
  if extra:
    raise PluginError(
      package=str(path),
      message=f"Unknown keys in [run] of {path}: {sorted(extra)}",
    )
  return RunConfig(agent=agent, prompt=prompt)


def _build_plugin_config(data: dict[str, Any], path: Path) -> PluginConfig:
  """Build PluginConfig from the [plugin] table, validating field types."""
  skills_dir = data.get("skills_dir", "skills")
  agents_dir = data.get("agents_dir", "agents")
  tools_module = data.get("tools_module")
  if not isinstance(skills_dir, str):
    raise PluginError(
      package=str(path),
      message=f"[plugin].skills_dir in {path} must be a string, got {type(skills_dir).__name__}",
    )
  if not isinstance(agents_dir, str):
    raise PluginError(
      package=str(path),
      message=f"[plugin].agents_dir in {path} must be a string, got {type(agents_dir).__name__}",
    )
  if tools_module is not None and not isinstance(tools_module, str):
    raise PluginError(
      package=str(path),
      message=f"[plugin].tools_module in {path} must be a string, got {type(tools_module).__name__}",
    )
  extra = set(data) - {"skills_dir", "agents_dir", "tools_module"}
  if extra:
    raise PluginError(
      package=str(path),
      message=f"Unknown keys in [plugin] of {path}: {sorted(extra)}",
    )
  return PluginConfig(
    skills_dir=skills_dir,
    agents_dir=agents_dir,
    tools_module=tools_module,
  )


__all__ = [
  "FileManifestResult",
  "PluginConfig",
  "RunConfig",
  "load_file_manifest",
]
