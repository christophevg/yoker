"""Plugin tool config bootstrap (TODO 7.2).

Augments Yoker's config schema at load time with one field per discovered
plugin that declares a ``config_class`` in its ``__YOKER_MANIFEST__``. The
single normal Clevis load then populates typed plugin config instances
reachable as ``config.tools.<plugin-package>.<tool>``, which
``_build_tool_context`` injects as ``ctx.config`` into tool functions that
declare a ``ctx: ToolContext`` parameter.

Flow (owner-validated design, see TODO 7.1/7.2):
  1. Probe: a plugins-only Clevis load yields ``plugins.packages`` +
     ``plugins.enabled`` — the ONLY TOML access path (no direct parsing).
  2. Discovery: import each plugin package and read the manifest's
     ``config_class``. Import failures warn + skip (startup proceeds).
  3. Schema augmentation: build dynamic subclasses of ``ToolsConfig``/``Config``
     (or a ``@configclass`` subcommand class) with one field per plugin.
  4. Single config load: the caller's untouched Clevis load populates the
     typed plugin config instances.

No plugin declares ``config_class`` -> classes pass through unchanged
(zero overhead). Known limitation: source plugins (``agent.toml``-declared
sources) load after the trust gate and are NOT bootstrap-augmented — their
tool config comes with defaults (TODO follow-up, see the 7.x section).

Spike-proven mechanics (tests/test_spike_plugin_config.py):
  (a) Fields inherit fine through subclassing; TOML
      ``[tools.<pkg>.<tool>]`` populates typed instances via dacite.
  (b) ``make_dataclass``-appended fields LOSE ``default_factory`` when
      ``@configclass`` rebuilds the class — use redeclared fields instead.
  (c) ``@configclass`` factory metadata (cmd/config) is not inherited through
      subclassing — re-apply the decorator using ``get_factory(original)``.
      (Clevis MRO-fallback improvement backlogged upstream: clevis P3-016.)
"""

import argparse
import os
from dataclasses import dataclass, field, fields, make_dataclass
from typing import Any, TypeVar, cast

from clevis import SecurityAction, SecurityConfig, build_default_cascade, get_config
from structlog import get_logger

from yoker.config import PluginsConfig, ToolConfig, ToolsConfig

logger = get_logger(__name__)

T = TypeVar("T")

# Memoized per process: the probe is the expensive part (TOML security checks
# + plugin imports). The augmented classes themselves are NOT cached — they
# must be rebuilt per call so they carry fresh Clevis factory state after
# clevis._reset_factories() (the pattern used by the CLI test suite).
_discovered_plugins: list[tuple[str, type[ToolConfig]]] | None = None


def reset_plugin_discovery() -> None:
  """Forget memoized plugin discovery (test isolation, config reloads)."""
  global _discovered_plugins
  _discovered_plugins = None


def _dev_test_security() -> SecurityConfig | None:
  """SecurityConfig mirroring get_yoker_config's dev/test bypass.

  Clevis's default security rejects world-readable TOML (mode 0o644), which
  breaks probe loads from tmp_path in tests. Under YOKER_DEV_MODE/pytest,
  permission violations are logged instead of rejected — the same bypass the
  production loaders use.
  """
  if os.environ.get("YOKER_DEV_MODE") == "1" or os.environ.get("PYTEST_CURRENT_TEST"):
    return SecurityConfig(
      file_permissions=SecurityAction.LOG,
      directory_permissions=SecurityAction.LOG,
    )
  return None


@dataclass
class BootstrapConfig:
  """Minimal probe schema: only the plugins section yoker.toml must provide.

  Kept deliberately tiny so unrelated TOML content (including unknown
  ``[tools.<plugin>...]`` tables) does not fail the probe (dacite is
  non-strict about extra keys — spike check 2).
  """

  plugins: PluginsConfig = field(default_factory=PluginsConfig)


def _discover_plugins() -> list[tuple[str, type[ToolConfig]]]:
  """Probe plugins config and import each package's manifest config_class.

  Returns an ordered list of (package_name, config_class) pairs. Import
  failures and manifests without a config_class are skipped with a warning;
  startup must proceed regardless. Memoized per process.
  """
  global _discovered_plugins
  if _discovered_plugins is not None:
    return _discovered_plugins

  discovered: list[tuple[str, type[ToolConfig]]] = []
  try:
    probe = get_config(
      BootstrapConfig,
      name="yoker",
      cascade=build_default_cascade("yoker", _dev_test_security()),
      cli=False,
    )
  except Exception as e:  # noqa: BLE001 — probe failure must not mask the main load's error
    logger.warning("plugin_config_probe_failed", error=str(e))
    _discovered_plugins = discovered
    return _discovered_plugins

  if probe.plugins.enabled:
    import importlib

    for package_name in probe.plugins.packages:
      try:
        package = importlib.import_module(package_name)
      except Exception as e:  # noqa: BLE001 — any import failure must not block startup
        logger.warning("plugin_config_probe_import_failed", package=package_name, error=str(e))
        continue
      manifest = getattr(package, "__YOKER_MANIFEST__", None)
      config_class = getattr(manifest, "config_class", None) if manifest is not None else None
      if config_class is None:
        continue
      if not (isinstance(config_class, type) and issubclass(config_class, ToolConfig)):
        logger.warning(
          "plugin_config_class_invalid", package=package_name, config_class=repr(config_class)
        )
        continue
      discovered.append((package_name, config_class))

  _discovered_plugins = discovered
  return _discovered_plugins


def _augmented_tools_config() -> type[ToolsConfig]:
  """Build a ToolsConfig subclass with one field per discovered plugin.

  Field name = plugin package name, type = plugin config_class. Collision
  with an existing ToolsConfig attribute skips that plugin with a warning.
  No plugin declares config_class -> ToolsConfig unchanged (zero overhead).
  """
  discovered = _discover_plugins()
  existing = {f.name for f in fields(ToolsConfig)}
  new_fields: list[tuple[str, Any, Any]] = []
  for package_name, config_class in discovered:
    if package_name in existing:
      logger.warning("plugin_config_field_collision", package=package_name, field=package_name)
      continue
    new_fields.append((package_name, config_class, field(default_factory=config_class)))
  if not new_fields:
    return ToolsConfig
  return cast(
    type[ToolsConfig],
    make_dataclass("AugmentedToolsConfig", new_fields, bases=(ToolsConfig,)),
  )


def _reapply_configclass(config_class: type, augmented: type) -> type:
  """Re-apply the @configclass factory metadata of config_class onto augmented.

  Factory metadata (cmd/config/default_cmd) lives on the decorated class
  itself and does not survive subclassing (spike finding c; Clevis MRO
  fallback backlogged: clevis P3-016).

  The augmented factory ALWAYS gets a private parser. Clevis dedups field
  registration per (owner class, field name) but conflicts on argument
  names per parser; the augmented class re-walks inherited top-level fields
  under a NEW owner identity, so on the shared default parser every
  ``_ensure_configured`` pass would re-register e.g. ``--enabled`` and
  raise ``ValueError: Alias '--enabled' conflicts ...``. Private parsers
  keep the per-load-rebuilt classes registry-isolated. Subcommand dispatch
  is unaffected: ``get_cmd()`` consults the shared parser before handlers
  run, and plain-Config loads only ever parse option arguments.
  """
  from clevis import configclass, get_factory

  original = get_factory(config_class)
  decorated: Any
  if original.cmd is None and original.config is None:
    # Plain Config family: no factory metadata to carry. Apply @dataclass
    # ourselves — the ONE decoration that reads the field defaults (spike
    # finding b: a second decoration would see them stripped).
    from dataclasses import dataclass as dc

    decorated = dc(augmented)
  else:
    kwargs: dict[str, Any] = {"cmd": original.cmd}
    if original.help is not None:
      kwargs["help"] = original.help
    if original.aliases:
      kwargs["aliases"] = original.aliases
    if original.config is not None:
      kwargs["config"] = original.config
    if original.default_cmd:
      kwargs["default_cmd"] = original.default_cmd
    decorated = cast(Any, configclass(**kwargs)(augmented))
  get_factory(decorated).parser = cast("Any", argparse.ArgumentParser())
  return cast(type, decorated)


def augmented_config_class(config_class: type[T]) -> type[T]:
  """Augment a Config-family class with discovered plugin config fields.

  The public entry point for all config loaders (TODO 7.2 STEP 4). Returns
  a dynamic subclass whose ``tools`` field carries one field per plugin that
  declared ``config_class``; the caller's normal Clevis load then populates
  typed instances at ``config.tools.<plugin>.<tool>``. When no plugin
  declares a config_class — or the class has no ``tools`` field (standalone
  subcommand configs) — the original class is returned unchanged.

  The subclass is built via plain ``type()`` WITHOUT decoration, so the
  single decoration happens inside _reapply_configclass (spike finding b:
  make_dataclass-appended fields lose default_factory when @configclass
  re-decorates — the first decoration deletes the class attribute).

  For ``@configclass``-decorated subcommand classes the factory metadata is
  re-applied to the subclass (spike finding c) on a private parser.
  """
  augmented_tools = _augmented_tools_config()
  if augmented_tools is ToolsConfig:
    return config_class

  if not any(f.name == "tools" for f in fields(cast("type[Any]", config_class))):
    return config_class

  augmented = type(
    "AugmentedConfig",
    (config_class,),
    {
      "__annotations__": {"tools": augmented_tools},
      "tools": field(default_factory=augmented_tools),
    },
  )
  return cast(type[T], _reapply_configclass(config_class, augmented))


__all__ = ["BootstrapConfig", "augmented_config_class", "reset_plugin_discovery"]
