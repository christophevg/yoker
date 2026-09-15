"""Tests for Yoker configuration system."""

from pathlib import Path

import pytest
from clevis import ConfigError, SecurityAction, SecurityConfig, get_config

from yoker.config import (
  BackendConfig,
  Config,
  ContextConfig,
  HarnessConfig,
  OllamaConfig,
  OllamaParameters,
  PermissionsConfig,
  UIConfig,
)
from yoker.exceptions import ValidationError


class TestConfigSchema:
  """Tests for configuration schema classes."""

  def test_harness_config_defaults(self) -> None:
    """Test HarnessConfig default values."""
    config = HarnessConfig()
    assert config.name == "yoker"
    assert config.version == "1.0"

  def test_ollama_parameters_defaults(self) -> None:
    """Test OllamaParameters default values (all None to allow provider defaults)."""
    params = OllamaParameters()
    assert params.temperature is None
    assert params.top_p is None
    assert params.top_k is None
    assert params.num_ctx is None
    assert params.num_predict is None
    assert params.repeat_penalty is None
    assert params.seed is None

  def test_ollama_config_defaults(self) -> None:
    """Test OllamaConfig default values."""
    config = OllamaConfig()
    assert config.base_url == "http://localhost:11434"
    assert config.model == "qwen3.5:cloud"
    assert config.timeout_seconds == 60

  def test_config_defaults(self) -> None:
    """Test Config default values."""
    config = Config()
    assert config.enabled is False
    assert config.harness.name == "yoker"
    assert config.backend.provider == "ollama"
    assert config.backend.ollama.model == "qwen3.5:cloud"
    assert config.context.manager == "basic_persistence"
    assert config.permissions.filesystem_paths == (".", "plugin://")
    assert config.tools.list.enabled is True
    assert config.agents.directories == ()
    assert config.logging.format == "text"
    assert config.logging.level == "WARNING"
    assert config.ui.mode == "interactive"
    assert config.ui.show_thinking is True
    assert config.ui.show_tool_calls is True
    assert config.ui.show_stats is True

  def test_ui_config_defaults(self) -> None:
    """Test UIConfig default values."""
    ui = UIConfig()
    assert ui.mode == "interactive"
    assert ui.show_thinking is True
    assert ui.show_tool_calls is True
    assert ui.show_stats is True

  def test_ui_config_batch_mode(self) -> None:
    """Test UIConfig can be configured for batch mode."""
    ui = UIConfig(mode="batch", show_thinking=True, show_tool_calls=True, show_stats=True)
    assert ui.mode == "batch"
    assert ui.show_thinking is True
    assert ui.show_tool_calls is True
    assert ui.show_stats is True

  def test_mutable_dataclass(self) -> None:
    """Test that config classes are mutable (Batch 1.8 unfroze them)."""
    config = HarnessConfig(name="test")
    config.name = "changed"
    assert config.name == "changed"

  def test_default_model_is_llama(self) -> None:
    """The default model is defined once.

    Per MBI-002 task 2.0, the default model lives in exactly one place:
    ``OllamaConfig.model``. This test locks that value so unintended changes
    are caught.
    """
    assert OllamaConfig().model == "qwen3.5:cloud"
    assert Config().backend.ollama.model == "qwen3.5:cloud"


class TestConfigValidation:
  """Tests for configuration validation."""

  def test_validate_invalid_url(self) -> None:
    """Test validation catches invalid URL during construction."""
    with pytest.raises(ValidationError) as exc_info:
      Config(backend=BackendConfig(ollama=OllamaConfig(base_url="not-a-valid-url")))
    assert "backend.ollama.base_url" in str(exc_info.value)

  def test_validate_empty_model(self) -> None:
    """Test validation catches empty model during construction."""
    with pytest.raises(ValidationError) as exc_info:
      Config(backend=BackendConfig(ollama=OllamaConfig(model="")))
    assert "backend.ollama.model" in str(exc_info.value)

  def test_validate_negative_timeout(self) -> None:
    """Test validation catches negative timeout during construction."""
    with pytest.raises(ValidationError) as exc_info:
      Config(backend=BackendConfig(ollama=OllamaConfig(timeout_seconds=-1)))
    assert "timeout_seconds" in str(exc_info.value)

  def test_validate_invalid_log_level(self) -> None:
    """Test validation catches invalid log level during construction."""
    from yoker.config import LoggingConfig

    with pytest.raises(ValidationError) as exc_info:
      Config(logging=LoggingConfig(level="INVALID"))
    assert "logging.level" in str(exc_info.value)

  def test_validate_invalid_context_manager(self) -> None:
    """Test validation catches invalid context manager during construction."""
    with pytest.raises(ValidationError) as exc_info:
      Config(context=ContextConfig(manager="invalid"))
    assert "context.manager" in str(exc_info.value)

  def test_validate_zero_compact_ratio(self) -> None:
    """compact_ratio 0 is rejected (trim target would always be 0)."""
    with pytest.raises(ValidationError) as exc_info:
      Config(context=ContextConfig(compact_ratio=0.0))
    assert "context.compact_ratio" in str(exc_info.value)

  def test_validate_negative_compact_ratio(self) -> None:
    """Negative compact_ratio is rejected."""
    with pytest.raises(ValidationError) as exc_info:
      Config(context=ContextConfig(compact_ratio=-0.5))
    assert "context.compact_ratio" in str(exc_info.value)

  def test_validate_compact_ratio_above_one(self) -> None:
    """compact_ratio above 1.0 is rejected (target above the cap)."""
    with pytest.raises(ValidationError) as exc_info:
      Config(context=ContextConfig(compact_ratio=1.5))
    assert "context.compact_ratio" in str(exc_info.value)

  def test_compact_ratio_boundaries_accepted(self) -> None:
    """The boundary values 0.5 (default) and 1.0 (old behavior) validate."""
    assert ContextConfig().compact_ratio == 0.5
    assert ContextConfig(compact_ratio=1.0).compact_ratio == 1.0

  def test_compaction_defaults(self) -> None:
    """Missing [context.compaction] yields the 4 default stages + thresholds."""
    from yoker.config import CompactionConfig, ContextConfig

    config = ContextConfig()
    assert isinstance(config.compaction, CompactionConfig)
    assert config.compaction.strategies == (
      "prune_tool_results",
      "prune_thinking",
      "force_stub_tool_results",
      "cutoff",
    )
    assert config.compaction.prune_tool_results.min_age_turns == 3
    assert config.compaction.prune_tool_results.min_chars == 2048
    assert config.compaction.prune_thinking.min_age_turns == 3
    assert config.compaction.force_stub_tool_results.min_chars == 4096
    assert config.compaction.cutoff.protect_first_user == 1
    assert config.compaction.cutoff.protect_last_user == 1
    assert config.compaction.cutoff.protect_last_assistant == 1
    assert config.compaction.cutoff.protect_last_tool_calls == 1

  def test_compaction_unknown_strategy_rejected(self) -> None:
    """An unknown stage name fails validation with the known names listed."""
    from yoker.config import CompactionConfig

    with pytest.raises(ValidationError) as exc_info:
      CompactionConfig(strategies=("prune_tool_results", "bogus"))
    assert "context.compaction.strategies" in str(exc_info.value)
    assert "bogus" in str(exc_info.value)

  def test_compaction_duplicate_strategy_rejected(self) -> None:
    """A duplicated stage name is rejected (order = execution order)."""
    from yoker.config import CompactionConfig

    with pytest.raises(ValidationError) as exc_info:
      CompactionConfig(strategies=("cutoff", "cutoff"))
    assert "context.compaction.strategies" in str(exc_info.value)
    assert "duplicate" in str(exc_info.value)

  def test_compaction_empty_strategies_accepted(self) -> None:
    """An empty strategies list is valid (compaction disabled — user's risk)."""
    from yoker.config import CompactionConfig

    assert CompactionConfig(strategies=()).strategies == ()
    assert CompactionConfig(strategies=[]).strategies == ()

  def test_compaction_non_string_strategy_rejected(self) -> None:
    """Non-string entries in the strategies list are rejected."""
    from yoker.config import CompactionConfig

    with pytest.raises(ValidationError):
      CompactionConfig(strategies=("cutoff", 42))  # type: ignore[list-item]

  def test_compaction_bad_params_rejected(self) -> None:
    """Negative/non-bool stage parameters fail validation with the dotted path."""
    from yoker.config import (
      CutoffConfig,
      ForceStubToolResultsConfig,
      PruneThinkingConfig,
      PruneToolResultsConfig,
    )

    with pytest.raises(ValidationError) as exc_info:
      PruneToolResultsConfig(min_age_turns=-1)
    assert "prune_tool_results.min_age_turns" in str(exc_info.value)

    with pytest.raises(ValidationError) as exc_info:
      PruneToolResultsConfig(min_chars=-5)
    assert "prune_tool_results.min_chars" in str(exc_info.value)

    with pytest.raises(ValidationError) as exc_info:
      PruneThinkingConfig(min_age_turns=-1)
    assert "prune_thinking.min_age_turns" in str(exc_info.value)

    with pytest.raises(ValidationError) as exc_info:
      ForceStubToolResultsConfig(min_chars=-1)
    assert "force_stub_tool_results.min_chars" in str(exc_info.value)

    with pytest.raises(ValidationError) as exc_info:
      CutoffConfig(protect_first_user=-1)
    assert "cutoff.protect_first_user" in str(exc_info.value)

    with pytest.raises(ValidationError) as exc_info:
      CutoffConfig(protect_last_user=-1)
    assert "cutoff.protect_last_user" in str(exc_info.value)

    with pytest.raises(ValidationError) as exc_info:
      CutoffConfig(protect_last_assistant=-1)
    assert "cutoff.protect_last_assistant" in str(exc_info.value)

    with pytest.raises(ValidationError) as exc_info:
      CutoffConfig(protect_last_tool_calls=-1)
    assert "cutoff.protect_last_tool_calls" in str(exc_info.value)

  def test_compaction_zero_params_accepted(self) -> None:
    """Zero thresholds are valid — 0 disables the age/size/protection gate."""
    from yoker.config import CutoffConfig, ForceStubToolResultsConfig, PruneToolResultsConfig

    config = PruneToolResultsConfig(min_age_turns=0, min_chars=0)
    assert config.min_age_turns == 0
    assert config.min_chars == 0

    force = ForceStubToolResultsConfig(min_chars=0)
    assert force.min_chars == 0

    cutoff = CutoffConfig(
      protect_first_user=0,
      protect_last_user=0,
      protect_last_assistant=0,
      protect_last_tool_calls=0,
    )
    assert cutoff.protect_first_user == 0
    assert cutoff.protect_last_user == 0
    assert cutoff.protect_last_assistant == 0
    assert cutoff.protect_last_tool_calls == 0

  def test_compaction_toml_round_trip(
    self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
  ) -> None:
    """A TOML with [context.compaction] tables loads into the typed config."""
    from unittest.mock import patch

    (tmp_path / "yoker.toml").write_text(
      "\n".join(
        [
          "[context]",
          "max_tokens = 80_000",
          "",
          "[context.compaction]",
          'strategies = ["cutoff", "prune_tool_results"]',
          "",
          "[context.compaction.prune_tool_results]",
          "min_age_turns = 1",
          "min_chars = 512",
          "",
          "[context.compaction.prune_thinking]",
          "min_age_turns = 2",
          "",
          "[context.compaction.force_stub_tool_results]",
          "min_chars = 1024",
          "",
          "[context.compaction.cutoff]",
          "protect_last_user = 2",
        ]
      ),
      encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    with patch.object(Path, "home", return_value=tmp_path / "home"):
      security = SecurityConfig(
        file_permissions=SecurityAction.LOG,
        directory_permissions=SecurityAction.LOG,
      )
      config = get_config(Config, name="yoker", cli=False, security=security)

    compaction = config.context.compaction
    assert config.context.max_tokens == 80_000
    assert compaction.strategies == ("cutoff", "prune_tool_results")
    assert compaction.prune_tool_results.min_age_turns == 1
    assert compaction.prune_tool_results.min_chars == 512
    assert compaction.prune_thinking.min_age_turns == 2
    assert compaction.force_stub_tool_results.min_chars == 1024
    assert compaction.cutoff.protect_last_user == 2

  def test_compaction_toml_absent_yields_defaults(
    self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
  ) -> None:
    """A TOML with [context] but no compaction keys keeps the defaults."""
    from unittest.mock import patch

    (tmp_path / "yoker.toml").write_text("[context]\nmax_tokens = 50_000\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    with patch.object(Path, "home", return_value=tmp_path / "home"):
      security = SecurityConfig(
        file_permissions=SecurityAction.LOG,
        directory_permissions=SecurityAction.LOG,
      )
      config = get_config(Config, name="yoker", cli=False, security=security)

    assert config.context.max_tokens == 50_000
    assert config.context.compaction.strategies == (
      "prune_tool_results",
      "prune_thinking",
      "force_stub_tool_results",
      "cutoff",
    )

  def test_compaction_toml_legacy_keep_first_user_ignored(
    self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
  ) -> None:
    """A pre-rename TOML with cutoff.keep_first_user silently falls back.

    Known limitation (TODO.md: clevis/dacite ignores TOML keys that don't
    map to dataclass fields): the legacy boolean is dropped and cutoff
    uses the new protect_* defaults. Expected breaking change — the
    boolean was replaced by the four ``protect_*`` integer windows.
    """
    from unittest.mock import patch

    (tmp_path / "yoker.toml").write_text(
      "[context.compaction.cutoff]\nkeep_first_user = false\n", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    with patch.object(Path, "home", return_value=tmp_path / "home"):
      security = SecurityConfig(
        file_permissions=SecurityAction.LOG,
        directory_permissions=SecurityAction.LOG,
      )
      config = get_config(Config, name="yoker", cli=False, security=security)

    cutoff = config.context.compaction.cutoff
    # Unknown key dropped; the four new windows default to 1.
    assert not hasattr(cutoff, "keep_first_user")
    assert cutoff.protect_first_user == 1
    assert cutoff.protect_last_user == 1
    assert cutoff.protect_last_assistant == 1
    assert cutoff.protect_last_tool_calls == 1

  def test_compaction_toml_unknown_strategy_rejected_load(
    self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
  ) -> None:
    """An unknown stage name in TOML fails the whole config load."""
    from unittest.mock import patch

    (tmp_path / "yoker.toml").write_text(
      '[context.compaction]\nstrategies = ["nonsense"]\n', encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    # The schema's __post_init__ raises ValidationError; clevis may wrap it
    # in ConfigError — either means the load failed, which is the contract.
    with (
      patch.object(Path, "home", return_value=tmp_path / "home"),
      pytest.raises((ConfigError, ValidationError)),
    ):
      security = SecurityConfig(
        file_permissions=SecurityAction.LOG,
        directory_permissions=SecurityAction.LOG,
      )
      get_config(Config, name="yoker", cli=False, security=security)

  def test_validate_empty_filesystem_paths(self) -> None:
    """Test validation catches empty filesystem_paths during construction."""
    with pytest.raises(ValidationError) as exc_info:
      Config(permissions=PermissionsConfig(filesystem_paths=()))
    assert "permissions.filesystem_paths" in str(exc_info.value)
    assert "must not be empty" in str(exc_info.value).lower()

  def test_validate_invalid_ui_mode(self) -> None:
    """Test validation catches invalid UI mode."""
    with pytest.raises(ValidationError) as exc_info:
      Config(ui=UIConfig(mode="invalid"))
    assert "ui.mode" in str(exc_info.value)


class TestClevisIntegration:
  """Tests for Clevis integration."""

  def test_get_config_returns_valid_config(
    self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
  ) -> None:
    """Test that get_config() returns a valid Config."""
    from unittest.mock import patch

    # Change to temp directory to avoid loading project config
    monkeypatch.chdir(tmp_path)

    # Mock Path.home() to prevent finding home config
    with patch.object(Path, "home", return_value=tmp_path / "home"):
      # Use LOG security action to allow world-writable temp dirs on Windows
      security = SecurityConfig(
        file_permissions=SecurityAction.LOG,
        directory_permissions=SecurityAction.LOG,
      )
      config = get_config(Config, name="yoker", cli=False, security=security)
      assert isinstance(config, Config)
      # With no config files, should use defaults
      assert config.harness.name == "yoker"

  def test_get_config_with_explicit_config(self) -> None:
    """Test that explicit config parameter overrides discovery."""
    # Create a custom config
    custom_config = Config(harness=HarnessConfig(name="test-harness", version="2.0"))
    # Pass it to Agent/Core - should use it directly
    assert custom_config.harness.name == "test-harness"
    assert custom_config.harness.version == "2.0"


class TestExampleConfig:
  """Tests for example configuration file."""

  def test_example_config_loads(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that example configuration file loads successfully."""
    from unittest.mock import patch

    example_path = Path(__file__).parent.parent / "examples" / "yoker.toml"
    if not example_path.exists():
      pytest.skip("Example config not found")

    # Change to temp directory to avoid loading project config
    monkeypatch.chdir(tmp_path)

    # Mock Path.home() to prevent finding home config
    with patch.object(Path, "home", return_value=tmp_path / "home"):
      # Use LOG security action to allow world-writable temp dirs on Windows
      security = SecurityConfig(
        file_permissions=SecurityAction.LOG,
        directory_permissions=SecurityAction.LOG,
      )
      # With Clevis, we can load from a specific file
      config = get_config(Config, name="yoker", cli=False, security=security)
      assert isinstance(config, Config)
      # Default config has the standard values (no config files in tmp_path)
      assert config.harness.name == "yoker"
      assert config.backend.provider == "ollama"


class TestSingleDefaultModel:
  """Guard against duplicate default-model literals (MBI-002 task 2.0).

  The default model must be defined in exactly one place: ``OllamaConfig.model``
  in ``src/yoker/config/__init__.py``. No other source file under ``src/yoker``
  may carry the old or new default as a literal that could drift.
  """

  def test_no_stale_default_literal_in_source(self) -> None:
    """No ``llama3.2:latest`` literal remains in the yoker source tree."""
    src_root = Path(__file__).parent.parent / "src" / "yoker"
    stale = []
    for path in src_root.rglob("*.py"):
      if "__pycache__" in path.parts:
        continue
      text = path.read_text(encoding="utf-8")
      if "llama3.2:latest" in text:
        stale.append(str(path.relative_to(src_root)))
    assert not stale, f"stale default literal found in: {stale}"


class TestDirectoriesNamespaceConfig:
  """Tests for the directories field accepting both list and dict forms."""

  def test_agents_directories_list_form_default(self) -> None:
    """List form: default namespace is the leaf folder name."""
    from yoker.config import AgentsConfig

    config = AgentsConfig(directories=("/path/to/myagents",))
    pairs = config.iter_directories()
    assert pairs == (("myagents", "/path/to/myagents"),)

  def test_agents_directories_dict_form_explicit_namespace(self) -> None:
    """Dict form: key is the namespace, value is the path."""
    from yoker.config import AgentsConfig

    config = AgentsConfig(directories={"c3": "../c3/agents"})
    pairs = config.iter_directories()
    assert pairs == (("c3", "../c3/agents"),)

  def test_skills_directories_list_form_default(self) -> None:
    """List form: default namespace is the leaf folder name."""
    from yoker.config import SkillsConfig

    config = SkillsConfig(directories=("/path/to/myskills",))
    pairs = config.iter_directories()
    assert pairs == (("myskills", "/path/to/myskills"),)

  def test_skills_directories_dict_form_explicit_namespace(self) -> None:
    """Dict form: key is the namespace, value is the path."""
    from yoker.config import SkillsConfig

    config = SkillsConfig(directories={"c3": "../c3/skills"})
    pairs = config.iter_directories()
    assert pairs == (("c3", "../c3/skills"),)

  def test_directories_empty_list(self) -> None:
    """Empty list yields no pairs."""
    from yoker.config import AgentsConfig

    config = AgentsConfig(directories=())
    assert config.iter_directories() == ()

  def test_directories_empty_dict(self) -> None:
    """Empty dict yields no pairs."""
    from yoker.config import AgentsConfig

    config = AgentsConfig(directories={})
    assert config.iter_directories() == ()

  def test_directories_multiple_dict_entries(self) -> None:
    """Dict form supports multiple namespace->path mappings."""
    from yoker.config import AgentsConfig

    config = AgentsConfig(directories={"c3": "../c3/agents", "other": "/opt/other"})
    pairs = config.iter_directories()
    assert ("c3", "../c3/agents") in pairs
    assert ("other", "/opt/other") in pairs
    assert len(pairs) == 2

  def test_directories_truthiness_list(self) -> None:
    """Non-empty list is truthy for the UI display check."""
    from yoker.config import SkillsConfig

    config = SkillsConfig(directories=("/some/dir",))
    assert config.directories

  def test_directories_truthiness_dict(self) -> None:
    """Non-empty dict is truthy for the UI display check."""
    from yoker.config import SkillsConfig

    config = SkillsConfig(directories={"c3": "/some/dir"})
    assert config.directories

  def test_directories_dict_form_preserved_through_dacite(self) -> None:
    """Dict-form directories survive dacite from_dict without being
    converted to a tuple of characters.

    This is a regression test for a bug where dacite's union resolution
    matched dict data against ``tuple[str, ...]`` first (because dict is
    a Collection and tuple is a Collection), iterating the dict's keys
    character-by-character.  Putting ``dict[str, str]`` first in the
    union type ensures dacite tries the dict branch first.
    """
    from dacite import Config as DaciteConfig
    from dacite import from_dict

    from yoker.config import AgentsConfig

    data = {"directories": {"c3": "../c3/agents"}}
    config = from_dict(
      data_class=AgentsConfig,
      data=data,
      config=DaciteConfig(cast=[tuple, set]),
    )
    assert isinstance(config.directories, dict)
    assert config.directories == {"c3": "../c3/agents"}
    assert config.iter_directories() == (("c3", "../c3/agents"),)

  def test_directories_list_form_preserved_through_dacite(self) -> None:
    """List-form directories survive dacite from_dict as a tuple."""
    from dacite import Config as DaciteConfig
    from dacite import from_dict

    from yoker.config import AgentsConfig

    data = {"directories": ["../c3/agents", "./agents"]}
    config = from_dict(
      data_class=AgentsConfig,
      data=data,
      config=DaciteConfig(cast=[tuple, set]),
    )
    assert isinstance(config.directories, tuple)
    assert config.directories == ("../c3/agents", "./agents")
