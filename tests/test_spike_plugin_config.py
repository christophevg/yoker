"""Spike: plugin config bootstrap mechanics (TODO 7.2, phase P0).

Owner-approved to KEEP as a permanent regression. These tests prove (and
then guard) the four mechanics the "Plugin Tool Config Bootstrap" design
depends on:

1. Dynamic ``ToolsConfig``/``Config`` subclass augmentation: Clevis
   (via dacite) populates an injected nested plugin config field from a
   ``[tools.<plugin>.<tool>]`` TOML table, alongside normal built-in
   tool sections.
2. Probe tolerance: a minimal plugins-only bootstrap config loads
   cleanly from a TOML file that also contains unknown plugin tool
   tables (non-strict dacite behavior).
3. Cascade reuse: ``build_default_cascade`` works for the probe load,
   same mechanism as ``get_yoker_config_with_manifest``.
4. Subcommand-class augmentation: a ``@configclass``-decorated config
   subclassed with an augmented ``tools`` field preserves Clevis
   factory metadata (``get_factory``).

Each check corresponds to a step of the bootstrap flow:
  probe (2,3) -> discover plugins -> augment schema (1,4) -> single load.

Environmental note (kept): Clevis's security check rejects world-readable
TOML (mode 0o644) in tmp_path. The probe/augmentation tests therefore run
with a dev/test-style SecurityConfig(LOG) — the same bypass production
loaders use under YOKER_DEV_MODE/pytest (see get_yoker_config). A plain
get_config without security is exercised in check 4's metadata test only.
"""

from dataclasses import dataclass, field, make_dataclass
from pathlib import Path

from clevis import SecurityAction, SecurityConfig, build_default_cascade, get_config

from yoker.config import Config, PluginsConfig, ToolConfig, ToolsConfig


def _test_security() -> SecurityConfig:
  """SecurityConfig matching get_yoker_config's dev/test bypass.

  Required in tests because Clevis rejects world-readable tmp_path TOML
  (SecurityError on mode 0o644); production code paths hit the same
  bypass via YOKER_DEV_MODE/PYTEST_CURRENT_TEST detection.
  """
  return SecurityConfig(
    file_permissions=SecurityAction.LOG,
    directory_permissions=SecurityAction.LOG,
  )


# -- plugin-side config shapes (the contract plugin authors will use) ------


@dataclass
class SpikeFindToolConfig(ToolConfig):
  """Per-tool config for the fake 'find' tool."""

  package_index_url: str = "https://pypi.org/simple"
  cache_ttl: int = 3600


@dataclass
class SpikePkgqToolConfig(ToolConfig):
  """Plugin-level config hierarchy, owned by the plugin."""

  find: SpikeFindToolConfig = field(default_factory=SpikeFindToolConfig)


def _augmented_classes() -> tuple[type, type]:
  """Build dynamically-augmented ToolsConfig/Config subclasses.

  Mirrors what ``augmented_config_class`` will do at runtime: one field
  per known plugin, added to a dynamic subclass of ``ToolsConfig``; the
  ``tools`` field of ``Config`` redeclared to use it.
  """
  aug_tools = make_dataclass(
    "AugmentedToolsConfig",
    [("pkgq", SpikePkgqToolConfig, field(default_factory=SpikePkgqToolConfig))],
    bases=(ToolsConfig,),
  )
  aug_config = make_dataclass(
    "AugmentedConfig",
    [("tools", aug_tools, field(default_factory=aug_tools))],
    bases=(Config,),
  )
  return aug_tools, aug_config


def _probe_load(aug_config: type, tmp_path: Path, monkeypatch, toml: str) -> None:
  """Load via build_default_cascade with the test security bypass.

  Uses the cascade mechanism (user→project TOML) exactly as
  get_yoker_config/get_yoker_config_with_manifest do in production.
  """
  monkeypatch.chdir(tmp_path)
  _write_project_toml(tmp_path, toml)
  return get_config(
    aug_config,
    name="yoker",
    cascade=build_default_cascade("yoker", _test_security()),
    cli=False,
  )


def _write_project_toml(tmp_path: Path, content: str) -> None:
  """Write a project-level yoker.toml and chdir to it."""
  (tmp_path / "yoker.toml").write_text(content)


# -- check 1: dynamic subclass augmentation through the real load ----------


def test_dynamic_augmented_config_populates_plugin_tool_config(tmp_path: Path, monkeypatch) -> None:
  """Clevis populates injected plugin config fields from TOML tables."""
  aug_tools, aug_config = _augmented_classes()

  cfg = _probe_load(
    aug_config,
    tmp_path,
    monkeypatch,
    """\
[tools.read]
enabled = true

[tools.pkgq.find]
package_index_url = "https://example.com/simple"
cache_ttl = 7200
""",
  )

  assert isinstance(cfg.tools, aug_tools)
  assert isinstance(cfg.tools.pkgq, SpikePkgqToolConfig)
  assert isinstance(cfg.tools.pkgq.find, SpikeFindToolConfig)
  assert cfg.tools.pkgq.find.package_index_url == "https://example.com/simple"
  assert cfg.tools.pkgq.find.cache_ttl == 7200
  # built-in tool sections parse normally alongside the plugin table
  assert cfg.tools.read.enabled is True
  # registry-style access (the _build_tool_context lookup path)
  assert isinstance(cfg.tools["pkgq"], SpikePkgqToolConfig)


def test_dynamic_augmented_config_defaults_without_toml_section(
  tmp_path: Path, monkeypatch
) -> None:
  """No [tools.<plugin>] table -> full default hierarchy, still typed."""
  aug_tools, aug_config = _augmented_classes()

  cfg = _probe_load(aug_config, tmp_path, monkeypatch, "[tools.read]\nenabled = false\n")

  assert isinstance(cfg.tools.pkgq, SpikePkgqToolConfig)
  assert cfg.tools.pkgq.find.package_index_url == "https://pypi.org/simple"
  assert cfg.tools.pkgq.find.cache_ttl == 3600
  assert cfg.tools.read.enabled is False


# -- check 2: probe tolerance for unknown plugin tool tables ----------------


def test_bootstrap_probe_ignores_unknown_plugin_tool_tables(tmp_path: Path, monkeypatch) -> None:
  """A plugins-only probe loads cleanly despite unknown [tools.*] tables."""

  @dataclass
  class SpikeBootstrapConfig:
    """Minimal schema: only what the probe needs."""

    plugins: PluginsConfig = field(default_factory=PluginsConfig)

  monkeypatch.chdir(tmp_path)
  _write_project_toml(
    tmp_path,
    """\
[plugins]
enabled = true
packages = ["pkgq"]

[tools.pkgq.find]
package_index_url = "https://example.com/simple"

[tools.someother.thing]
enabled = true
""",
  )

  probe = get_config(
    SpikeBootstrapConfig,
    name="yoker",
    cascade=build_default_cascade("yoker", _test_security()),
    cli=False,
  )

  assert probe.plugins.enabled is True
  assert tuple(probe.plugins.packages) == ("pkgq",)


# -- check 3: cascade reuse for the probe -----------------------------------


def test_bootstrap_probe_via_build_default_cascade(tmp_path: Path, monkeypatch) -> None:
  """The probe works through build_default_cascade, as the real loaders do."""
  from clevis import build_default_cascade

  @dataclass
  class SpikeBootstrapConfig:
    plugins: PluginsConfig = field(default_factory=PluginsConfig)

  monkeypatch.chdir(tmp_path)
  _write_project_toml(
    tmp_path,
    """\
[plugins]
enabled = true
packages = ["pkgq"]
""",
  )

  # dev/test-style security, mirroring get_yoker_config's bypass behavior
  security = _test_security()
  cascade = build_default_cascade("yoker", security)

  probe = get_config(SpikeBootstrapConfig, name="yoker", cascade=cascade, cli=False)

  assert probe.plugins.enabled is True
  assert tuple(probe.plugins.packages) == ("pkgq",)


# -- check 4: subcommand-class augmentation keeps factory metadata ----------


def test_configclass_subclass_augmentation_preserves_factory_metadata() -> None:
  """get_factory on an augmented subcommand config still sees cmd/config.

  Finding (spike round 1): bare make_dataclass subclassing LOSES Clevis
  factory metadata (cmd/config -> None) because @configclass stashes it
  on the decorated class itself, which the fresh subclass does not
  inherit. The fix the runtime augmentation must apply: re-apply the
  same @configclass(cmd=..., ...) decorator to the augmented subclass.
  """
  from clevis import configclass, get_factory

  from yoker.cli.commands import ConfigCmdConfig

  factory = get_factory(ConfigCmdConfig)
  aug_tools, _ = _augmented_classes()

  # Finding (spike round 2): make_dataclass-appended fields lose their
  # default_factory when @configclass rebuilds the class. The correct
  # augmentation pattern is a normal subclass REDECLARING the tools
  # field (ConfigCmdConfig inherits it from Config) — the same shape
  # augmented_config_class() will use at runtime.
  @configclass(cmd=factory.cmd)
  class AugmentedCmdConfig(ConfigCmdConfig):  # type: ignore[misc]
    tools: type = field(default_factory=aug_tools)  # type: ignore[valid-type]

  augmented = get_factory(AugmentedCmdConfig)

  assert augmented.cmd == factory.cmd
  assert augmented.config == factory.config
