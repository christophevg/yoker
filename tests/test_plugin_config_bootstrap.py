"""Integration tests for plugin config bootstrap (TODO 7.2).

End-to-end: plugin manifests declare ``config_class`` -> augmented schema
fields -> user TOML ``[tools.<plugin>.<tool>]`` -> typed ``ctx.config``.
Complements tests/test_spike_plugin_config.py (permanent spike regression).
"""

import sys
from pathlib import Path

import pytest
from clevis import _reset_factories

from yoker.config.plugin_bootstrap import reset_plugin_discovery

TESTS_DIR = Path(__file__).parent


@pytest.fixture(autouse=True)
def _isolate_plugin_discovery(tmp_path: Path, monkeypatch):
  """Isolate bootstrap discovery: reset memoization and redirect TOML files.

  The probe reads ~/.yoker.toml + ./yoker.toml via the Clevis cascade; tests
  write their own TOML into an isolated cwd/HOME. Factory resets re-register
  @configclass subcommand configs afterwards (the test-suite-wide pattern).
  """
  reset_plugin_discovery()
  monkeypatch.setenv("YOKER_DEV_MODE", "1")
  monkeypatch.setenv("HOME", str(tmp_path))
  monkeypatch.chdir(tmp_path)
  yield
  reset_plugin_discovery()
  _reset_factories()
  from importlib import reload

  import yoker.cli.commands

  reload(yoker.cli.commands)


def _write_toml(toml: str, tmp_path: Path) -> None:
  (tmp_path / "yoker.toml").write_text(toml, encoding="utf-8")


# Standard TOML prologue: enable plugins, configure the demo plugin, trust it.
DEMO_PLUGIN_TOML = (
  '[plugins]\nenabled = true\npackages = ["yoker_plugin_demo"]\n'
  "\n[plugins.trusted]\nyoker_plugin_demo = true\n"
)


def _demo_toml(tool_table: str, tmp_path: Path) -> None:
  """Write the standard demo-plugin TOML plus an extra [tools.…] table."""
  _write_toml(DEMO_PLUGIN_TOML + "\n" + tool_table, tmp_path)


class TestAugmentedSchema:
  """augmented_config_class builds plugin fields into the schema."""

  def test_no_plugins_returns_original_class(self, tmp_path: Path) -> None:
    """With no plugin config_class discovered, Config passes through unchanged."""
    from yoker.config import Config
    from yoker.config.plugin_bootstrap import augmented_config_class

    _write_toml("[plugins]\nenabled = true\npackages = []\n", tmp_path)

    assert augmented_config_class(Config) is Config

  def test_demo_plugin_field_added(self, tmp_path: Path) -> None:
    """Demo plugin manifest config_class yields a typed tools field."""
    from dataclasses import fields

    from yoker_plugin_demo import DemoPluginConfig

    from yoker.config import Config
    from yoker.config.plugin_bootstrap import augmented_config_class

    _demo_toml("", tmp_path)

    augmented = augmented_config_class(Config)
    tools_field = next(f for f in fields(augmented) if f.name == "tools")
    plugin_field = next(f for f in fields(tools_field.type) if f.name == "yoker_plugin_demo")
    assert plugin_field.type is DemoPluginConfig

  def test_collision_skips_plugin(self, tmp_path: Path) -> None:
    """A plugin field name colliding with a built-in ToolsConfig field is skipped."""
    from unittest.mock import patch

    from yoker.config import ToolsConfig
    from yoker.config.plugin_bootstrap import _augmented_tools_config

    _demo_toml("", tmp_path)

    # Pretend the discovery returned a name that ToolsConfig already has.
    with patch(
      "yoker.config.plugin_bootstrap._discover_plugins",
      return_value=[("read", type("FakeToolConfig", (), {}))],
    ):
      assert _augmented_tools_config() is ToolsConfig


class TestConfigLoaders:
  """All four loaders populate typed plugin config instances (canary)."""

  def test_get_yoker_config_loads_demo_plugin_config(self, tmp_path: Path) -> None:
    """get_yoker_config: TOML [tools.yoker_plugin_demo.echo] -> typed instance."""
    from yoker_plugin_demo import DemoPluginConfig

    from yoker.config import get_yoker_config

    _demo_toml('[tools.yoker_plugin_demo.echo]\nprefix = "Custom: "\n', tmp_path)

    config = get_yoker_config()

    plugin_config = config.tools.yoker_plugin_demo
    assert isinstance(plugin_config, DemoPluginConfig)
    assert plugin_config.echo.prefix == "Custom: "

  def test_load_subcommand_config_loads_demo_plugin_config(self, tmp_path: Path) -> None:
    """load_subcommand_config: same TOML through the subcommand path (canary 2)."""
    import yoker.cli.commands
    from yoker.cli.shared import load_subcommand_config

    _demo_toml('[tools.yoker_plugin_demo.echo]\nprefix = "Sub: "\n', tmp_path)
    sys.argv = ["yoker", "chat"]

    config = load_subcommand_config(yoker.cli.commands.ChatConfig)

    plugin_config = config.tools.yoker_plugin_demo
    assert plugin_config.echo.prefix == "Sub: "

  def test_load_subcommand_config_with_manifest_loads_demo_plugin_config(
    self, tmp_path: Path
  ) -> None:
    """load_subcommand_config_with_manifest: same TOML via the manual cascade (canary 3)."""
    import yoker.cli.commands
    from yoker.cli.shared import load_subcommand_config_with_manifest

    _demo_toml('[tools.yoker_plugin_demo.echo]\nprefix = "Manifest: "\n', tmp_path)
    sys.argv = ["yoker", "run"]

    config = load_subcommand_config_with_manifest(yoker.cli.commands.RunConfig, {})

    plugin_config = config.tools.yoker_plugin_demo
    assert plugin_config.echo.prefix == "Manifest: "

  def test_get_yoker_config_with_manifest_loads_demo_plugin_config(self, tmp_path: Path) -> None:
    """get_yoker_config_with_manifest: same TOML through the manifest cascade (canary 4)."""
    import yoker.config
    from yoker.plugins.file_manifest import load_file_manifest

    _demo_toml('[tools.yoker_plugin_demo.echo]\nprefix = "Run: "\n', tmp_path)
    manifest_path = tmp_path / "agent.toml"
    manifest_path.write_text('[run]\nprompt = "hello"\n', encoding="utf-8")

    config, run_config, plugin_config = yoker.config.get_yoker_config_with_manifest(manifest_path)

    loaded = load_file_manifest(manifest_path)
    assert loaded is not None and run_config.prompt == "hello"
    tools_cfg = config.tools.yoker_plugin_demo
    assert tools_cfg.echo.prefix == "Run: "

  def test_bad_typed_toml_value_raises_clear_error(self, tmp_path: Path) -> None:
    """A wrong-typed TOML value fails the load with a ConfigError, not silence."""
    from clevis import ConfigError

    from yoker.config import get_yoker_config

    _demo_toml("[tools.yoker_plugin_demo.echo]\nprefix = 42\n", tmp_path)

    with pytest.raises(ConfigError):
      get_yoker_config()


class TestRuntimeResolution:
  """_build_tool_context resolves plugin tool config via ctx (TODO 7.2 STEP 5)."""

  def test_agent_invokes_echo_with_custom_prefix(self, tmp_path: Path) -> None:
    """End-to-end: Agent + demo tool -> ctx.config is the plugin-top config."""
    from yoker_plugin_demo import DemoPluginConfig

    from yoker.config import get_yoker_config
    from yoker.core import Agent
    from yoker.core._processing import _build_tool_context

    _demo_toml('[tools.yoker_plugin_demo.echo]\nprefix = "Custom: "\n', tmp_path)

    config = get_yoker_config()
    agent = Agent(config=config)

    spec = agent.tools.get("yoker_plugin_demo:echo")
    assert spec is not None

    # Build the echo tool's ToolContext and execute the tool through it.
    # ctx.config is the plugin's TOP-LEVEL instance; the tool navigates
    # its own hierarchy (no harness field-naming convention).
    ctx = _build_tool_context(agent, spec)
    assert isinstance(ctx.config, DemoPluginConfig)
    result = spec.execute(message="Hi", ctx=ctx)
    assert result == "Custom: Hi"

  def test_built_in_tool_config_unchanged(self, tmp_path: Path) -> None:
    """Built-in regression: flat lookup still resolves built-in tool configs."""
    from yoker.config import ReadToolConfig, get_yoker_config
    from yoker.core import Agent
    from yoker.core._processing import _build_tool_context

    _write_toml(
      "[tools.read]\nmax_file_size_kb = 42\n",
      tmp_path,
    )

    config = get_yoker_config()
    agent = Agent(config=config)

    spec = agent.tools.get("yoker:read")
    assert spec is not None
    ctx = _build_tool_context(agent, spec)
    assert isinstance(ctx.config, ReadToolConfig)
    assert ctx.config.max_file_size_kb == 42


class TestPluginEnabledGating:
  """Plugin tools are gated by the plugin config's enabled flags."""

  def test_plugin_root_enabled_false_drops_tools(self, tmp_path: Path) -> None:
    """[tools.<plugin>] enabled = false drops ALL of the plugin's tools."""
    from yoker.config import get_yoker_config
    from yoker.core import Agent

    _demo_toml("[tools.yoker_plugin_demo]\nenabled = false\n", tmp_path)

    config = get_yoker_config()
    agent = Agent(config=config)

    assert agent.tools.get("yoker_plugin_demo:echo") is None

  def test_per_tool_enabled_false_drops_that_tool(self, tmp_path: Path) -> None:
    """[tools.<plugin>.<tool>] enabled = false drops only that tool."""
    from yoker.config import get_yoker_config
    from yoker.core import Agent

    _demo_toml("[tools.yoker_plugin_demo.echo]\nenabled = false\n", tmp_path)

    config = get_yoker_config()
    agent = Agent(config=config)

    assert agent.tools.get("yoker_plugin_demo:echo") is None

  def test_plugin_enabled_true_keeps_tools(self, tmp_path: Path) -> None:
    """Explicit enabled = true keeps plugin tools registered."""
    from yoker.config import get_yoker_config
    from yoker.core import Agent

    _demo_toml("[tools.yoker_plugin_demo]\nenabled = true\n", tmp_path)

    config = get_yoker_config()
    agent = Agent(config=config)

    assert agent.tools.get("yoker_plugin_demo:echo") is not None

  def test_filter_plugin_tools_direct(self, tmp_path: Path) -> None:
    """Direct gating tests for _filter_plugin_tools with a fake augmented config."""
    from dataclasses import dataclass as dc
    from dataclasses import field as dc_field

    from yoker.config import Config, ToolConfig, ToolsConfig
    from yoker.tools.registry import _filter_enabled_tools
    from yoker.tools.schema import build_tool_spec

    @dc
    class FakeEchoConfig(ToolConfig):
      pass

    @dc
    class FakePluginConfig(ToolConfig):
      echo: FakeEchoConfig = dc_field(default_factory=FakeEchoConfig)
      gone: ToolConfig = dc_field(default_factory=lambda: ToolConfig(enabled=False))

    @dc
    class AugTools(ToolsConfig):
      fake_plugin: FakePluginConfig = dc_field(default_factory=FakePluginConfig)

    config = Config()
    config.tools = AugTools()

    def echo() -> str:
      """Fake echo tool (spec building only)."""
      return "x"

    def gone() -> str:
      """Fake disabled tool (spec building only)."""
      return "x"

    specs = [
      build_tool_spec(echo, namespace="fake_plugin"),
      build_tool_spec(gone, namespace="fake_plugin"),
    ]

    kept = _filter_enabled_tools(specs, config, "fake_plugin")

    assert [s.simple_name for s in kept] == ["echo"]

  def test_two_plugins_same_tool_name_resolve_via_namespace(self, tmp_path: Path) -> None:
    """Two plugins declaring the same tool simple_name resolve independently."""
    from dataclasses import dataclass as dc
    from dataclasses import field as dc_field

    from yoker.config import Config, ToolConfig, ToolsConfig
    from yoker.core._processing import _resolve_tool_config

    @dc
    class AlphaConfig(ToolConfig):
      echo: ToolConfig = dc_field(default_factory=ToolConfig)

    @dc
    class BetaConfig(ToolConfig):
      echo: ToolConfig = dc_field(default_factory=ToolConfig)

    @dc
    class AugTools(ToolsConfig):
      alpha: AlphaConfig = dc_field(default_factory=AlphaConfig)
      beta: BetaConfig = dc_field(default_factory=BetaConfig)

    config = Config()
    config.tools = AugTools()
    agent = type("FakeAgent", (), {"config": config})()

    # Plugin tools receive their plugin's TOP-LEVEL config instance —
    # resolution keys on the plugin namespace (package name), not the
    # tool name, so same-named tools never cross wires.
    resolved_alpha = _resolve_tool_config(agent, "echo", "alpha")
    resolved_beta = _resolve_tool_config(agent, "echo", "beta")

    assert resolved_alpha is config.tools.alpha
    assert resolved_beta is config.tools.beta

  def test_no_matching_config_returns_default(self, tmp_path: Path) -> None:
    """A tool name matching nothing resolves to a default ToolConfig (no crash)."""
    from yoker.config import Config, ToolConfig
    from yoker.core._processing import _resolve_tool_config

    config = Config()
    agent = type("FakeAgent", (), {"config": config})()

    resolved = _resolve_tool_config(agent, "nonexistent_tool", "no_such_plugin")

    assert isinstance(resolved, ToolConfig)
    assert resolved.enabled is True
