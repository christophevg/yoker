"""Tests for the ``yoker run <source>`` subcommand handler (MBI-004 task 4.7).

Covers the security-critical paths: trust gate ordering (load_source MUST NOT
be called before check_source_allowed), dry-run, non-interactive rejection,
prompt length cap, missing agent/prompt errors, and CLI overrides.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from yoker.cli.run import (
  MAX_PROMPT_BYTES,
  _apply_config_overrides,
  _parse_run_overrides,
  run_run,
)
from yoker.config import Config
from yoker.plugins.file_manifest import FileManifestResult, PluginConfig
from yoker.plugins.file_manifest import RunConfig as ManifestRunConfig
from yoker.plugins.security import (
  ENV_TRUST_SOURCE,
  check_source_allowed,
  reset_session_trusted,
)


def _make_run_config(
  source: str = "pkgq",
  persist: bool = False,
  session_id: str | None = None,
  dry_run: bool = False,
) -> Config:
  """Build a minimal RunConfig-like object for testing."""
  cfg = Config()
  cfg.source = source  # type: ignore[attr-defined]
  cfg.persist = persist  # type: ignore[attr-defined]
  cfg.session_id = session_id  # type: ignore[attr-defined]
  cfg.dry_run = dry_run  # type: ignore[attr-defined]
  return cfg


def _make_resolved(
  kind: str = "module",
  trust_key: str = "module:pkgq",
  manifest: FileManifestResult | None = None,
  cleanup: MagicMock | None = None,
) -> MagicMock:
  """Build a mock ResolvedSource."""
  resolved = MagicMock()
  resolved.kind = kind
  resolved.source_string = "pkgq"
  resolved.path = Path("/tmp/fake")
  resolved.trust_key = trust_key
  resolved.manifest = manifest
  resolved.cleanup = cleanup
  return resolved


def _make_loaded(
  agent: str | None = "coder",
  prompt: str | None = "do stuff",
  cleanup: MagicMock | None = None,
) -> MagicMock:
  """Build a mock LoadedSource."""
  loaded = MagicMock()
  loaded.agent = agent
  loaded.prompt = prompt
  loaded.cleanup = cleanup
  loaded.components = MagicMock()
  loaded.components.tools = []
  loaded.components.skills = []
  loaded.components.agents = []
  loaded.components.source = "pkgq"
  return loaded


class TestParseRunOverrides:
  """Test ``--agent`` and ``--prompt`` local argparse extraction."""

  def test_extracts_agent_and_prompt(self) -> None:
    argv = ["yoker", "run", "pkgq", "--agent", "coder", "--prompt", "do X"]
    agent, prompt, cleaned = _parse_run_overrides(argv)
    assert agent == "coder"
    assert prompt == "do X"
    assert "--agent" not in cleaned
    assert "--prompt" not in cleaned
    assert "coder" not in cleaned[2:]  # value removed too

  def test_extracts_agent_only(self) -> None:
    argv = ["yoker", "run", "pkgq", "--agent", "coder"]
    agent, prompt, cleaned = _parse_run_overrides(argv)
    assert agent == "coder"
    assert prompt is None
    assert "--agent" not in cleaned

  def test_extracts_prompt_only(self) -> None:
    argv = ["yoker", "run", "pkgq", "--prompt", "do X"]
    agent, prompt, cleaned = _parse_run_overrides(argv)
    assert agent is None
    assert prompt == "do X"
    assert "--prompt" not in cleaned

  def test_no_overrides_returns_none(self) -> None:
    argv = ["yoker", "run", "pkgq"]
    agent, prompt, cleaned = _parse_run_overrides(argv)
    assert agent is None
    assert prompt is None
    assert cleaned == argv

  def test_preserves_other_flags(self) -> None:
    argv = ["yoker", "run", "pkgq", "--persist", "--agent", "x", "--dry-run"]
    agent, prompt, cleaned = _parse_run_overrides(argv)
    assert agent == "x"
    assert "--persist" in cleaned
    assert "--dry-run" in cleaned


class TestDryRun:
  """``--dry-run`` prints resolved info without executing."""

  def test_dry_run_prints_and_exits_without_load(self, capsys) -> None:
    resolved = _make_resolved(
      manifest=FileManifestResult(
        run_config=ManifestRunConfig(agent="coder", prompt="do X"),
        plugin_config=PluginConfig(),
        config_overrides={},
      )
    )
    config = _make_run_config(dry_run=True)

    with (
      patch("yoker.cli.run.load_subcommand_config", return_value=config),
      patch("yoker.cli.run.resolve_source", return_value=resolved) as m_resolve,
      patch("yoker.cli.run.load_source") as m_load,
      patch("yoker.cli.run.check_source_allowed", return_value=True) as m_check,
      patch("yoker.cli.run.configure_logging"),
    ):
      run_run([])

    m_resolve.assert_called_once_with("pkgq")
    # dry-run must NOT call the trust gate or load_source.
    m_check.assert_not_called()
    m_load.assert_not_called()
    out = capsys.readouterr().out
    assert "Kind:        module" in out
    assert "agent:  'coder'" in out
    assert "dry-run" in out


class TestTrustGateOrdering:
  """The trust gate MUST fire before load_source (security invariant)."""

  def test_load_source_not_called_when_untrusted(self) -> None:
    resolved = _make_resolved()
    config = _make_run_config()

    with (
      patch("yoker.cli.run.load_subcommand_config", return_value=config),
      patch("yoker.cli.run.resolve_source", return_value=resolved),
      patch("yoker.cli.run.check_source_allowed", return_value=False) as m_check,
      patch("yoker.cli.run.load_source") as m_load,
      patch("yoker.cli.run.configure_logging"),
    ):
      with pytest.raises(SystemExit) as exc:
        run_run([])

    assert exc.value.code == 1
    m_check.assert_called_once()
    m_load.assert_not_called()

  def test_load_source_called_when_trusted(self) -> None:
    resolved = _make_resolved()
    loaded = _make_loaded(cleanup=MagicMock())
    config = _make_run_config()

    with (
      patch("yoker.cli.run.load_subcommand_config", return_value=config),
      patch("yoker.cli.run.resolve_source", return_value=resolved),
      patch("yoker.cli.run.check_source_allowed", return_value=True),
      patch("yoker.cli.run.load_source", return_value=loaded) as m_load,
      patch("yoker.cli.run.configure_logging"),
      patch("yoker.cli.run.asyncio.run"),
    ):
      run_run([])

    m_load.assert_called_once_with(resolved)


class TestNonInteractiveRejection:
  """Non-interactive mode rejects untrusted sources by default."""

  def test_rejects_untrusted_in_non_interactive(self, monkeypatch) -> None:
    reset_session_trusted()
    monkeypatch.delenv(ENV_TRUST_SOURCE, raising=False)
    config = Config()
    config.plugins.trusted = {}
    # Non-interactive: no TTY.
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)

    result = check_source_allowed("github:evil/repo@abc", config)

    assert result is False

  def test_env_override_allows_non_interactive(self, monkeypatch) -> None:
    reset_session_trusted()
    monkeypatch.setenv(ENV_TRUST_SOURCE, "1")
    config = Config()
    config.plugins.trusted = {}
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)

    result = check_source_allowed("github:evil/repo@abc", config)

    assert result is True

  def test_pre_trusted_allows_non_interactive(self, monkeypatch) -> None:
    reset_session_trusted()
    monkeypatch.delenv(ENV_TRUST_SOURCE, raising=False)
    config = Config()
    config.plugins.trusted = {"github:evil/repo@abc": True}
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)

    result = check_source_allowed("github:evil/repo@abc", config)

    assert result is True


class TestPromptLengthCap:
  """Prompt length is capped at 10 KB (H2 remediation)."""

  def test_oversized_prompt_rejected(self) -> None:
    resolved = _make_resolved()
    loaded = _make_loaded(prompt="x" * (MAX_PROMPT_BYTES + 1))
    config = _make_run_config()

    with (
      patch("yoker.cli.run.load_subcommand_config", return_value=config),
      patch("yoker.cli.run.resolve_source", return_value=resolved),
      patch("yoker.cli.run.check_source_allowed", return_value=True),
      patch("yoker.cli.run.load_source", return_value=loaded),
      patch("yoker.cli.run.configure_logging"),
      patch("yoker.cli.run.asyncio.run"),
    ):
      with pytest.raises(SystemExit) as exc:
        run_run([])

    assert exc.value.code == 1

  def test_prompt_at_limit_accepted(self) -> None:
    resolved = _make_resolved()
    loaded = _make_loaded(prompt="x" * MAX_PROMPT_BYTES, cleanup=MagicMock())
    config = _make_run_config()

    with (
      patch("yoker.cli.run.load_subcommand_config", return_value=config),
      patch("yoker.cli.run.resolve_source", return_value=resolved),
      patch("yoker.cli.run.check_source_allowed", return_value=True),
      patch("yoker.cli.run.load_source", return_value=loaded),
      patch("yoker.cli.run.configure_logging"),
      patch("yoker.cli.run.asyncio.run") as m_run,
    ):
      run_run([])

    m_run.assert_called_once()


class TestMissingAgentOrPrompt:
  """Missing agent or prompt -> clear error, exit non-zero."""

  def test_missing_agent_errors(self) -> None:
    resolved = _make_resolved()
    loaded = _make_loaded(agent=None, prompt="do X")
    config = _make_run_config()

    with (
      patch("yoker.cli.run.load_subcommand_config", return_value=config),
      patch("yoker.cli.run.resolve_source", return_value=resolved),
      patch("yoker.cli.run.check_source_allowed", return_value=True),
      patch("yoker.cli.run.load_source", return_value=loaded),
      patch("yoker.cli.run.configure_logging"),
      patch("yoker.cli.run.asyncio.run"),
    ):
      with pytest.raises(SystemExit) as exc:
        run_run([])

    assert exc.value.code == 1

  def test_missing_prompt_errors(self) -> None:
    resolved = _make_resolved()
    loaded = _make_loaded(agent="coder", prompt=None)
    config = _make_run_config()

    with (
      patch("yoker.cli.run.load_subcommand_config", return_value=config),
      patch("yoker.cli.run.resolve_source", return_value=resolved),
      patch("yoker.cli.run.check_source_allowed", return_value=True),
      patch("yoker.cli.run.load_source", return_value=loaded),
      patch("yoker.cli.run.configure_logging"),
      patch("yoker.cli.run.asyncio.run"),
    ):
      with pytest.raises(SystemExit) as exc:
        run_run([])

    assert exc.value.code == 1

  def test_no_source_errors(self) -> None:
    config = _make_run_config(source="")

    with (
      patch("yoker.cli.run.load_subcommand_config", return_value=config),
      patch("yoker.cli.run.configure_logging"),
    ):
      with pytest.raises(SystemExit) as exc:
        run_run([])

    assert exc.value.code == 1


class TestCLIOverrides:
  """``--agent`` and ``--prompt`` CLI overrides take precedence over manifest."""

  def test_cli_agent_overrides_manifest(self) -> None:
    resolved = _make_resolved()
    loaded = _make_loaded(agent="manifest_agent", prompt="manifest_prompt")
    config = _make_run_config()

    with (
      patch("yoker.cli.run.load_subcommand_config", return_value=config),
      patch("yoker.cli.run.resolve_source", return_value=resolved),
      patch("yoker.cli.run.check_source_allowed", return_value=True),
      patch("yoker.cli.run.load_source", return_value=loaded),
      patch("yoker.cli.run.configure_logging"),
      patch("yoker.cli.run._run_source") as m_run_source,
      patch("yoker.cli.run.asyncio.run"),
      patch("sys.argv", ["yoker", "run", "pkgq", "--agent", "cli_agent", "--prompt", "cli_prompt"]),
    ):
      run_run([])

    # _run_source should be called with the CLI overrides (positional).
    call_args = m_run_source.call_args
    # Positional order: config, loaded, agent_name, prompt, plugin_packages, session_id
    assert call_args.args[2] == "cli_agent"
    assert call_args.args[3] == "cli_prompt"


class TestCleanup:
  """Source cleanup is called after run (removes temp dirs for github/zip)."""

  def test_cleanup_called_on_success(self) -> None:
    resolved = _make_resolved()
    cleanup = MagicMock()
    loaded = _make_loaded(cleanup=cleanup)
    config = _make_run_config()

    with (
      patch("yoker.cli.run.load_subcommand_config", return_value=config),
      patch("yoker.cli.run.resolve_source", return_value=resolved),
      patch("yoker.cli.run.check_source_allowed", return_value=True),
      patch("yoker.cli.run.load_source", return_value=loaded),
      patch("yoker.cli.run.configure_logging"),
      patch("yoker.cli.run.asyncio.run"),
    ):
      run_run([])

    cleanup.assert_called_once()

  def test_cleanup_called_on_error(self) -> None:
    resolved = _make_resolved()
    cleanup = MagicMock()
    loaded = _make_loaded(cleanup=cleanup)
    config = _make_run_config()

    with (
      patch("yoker.cli.run.load_subcommand_config", return_value=config),
      patch("yoker.cli.run.resolve_source", return_value=resolved),
      patch("yoker.cli.run.check_source_allowed", return_value=True),
      patch("yoker.cli.run.load_source", return_value=loaded),
      patch("yoker.cli.run.configure_logging"),
      patch("yoker.cli.run.asyncio.run", side_effect=ValueError("boom")),
    ):
      with pytest.raises(SystemExit):
        run_run([])

    cleanup.assert_called_once()


class TestApplyConfigOverrides:
  """Manifest config overrides deep-merge into the config dataclass."""

  def test_nested_dict_recurse(self) -> None:
    config = Config()
    overrides = {"backend": {"provider": "openai"}}
    _apply_config_overrides(config, overrides)
    assert config.backend.provider == "openai"

  def test_non_dict_replaces(self) -> None:
    config = Config()
    overrides = {"agent": "coder"}
    _apply_config_overrides(config, overrides)
    assert config.agent == "coder"

  def test_unknown_field_skipped(self) -> None:
    config = Config()
    overrides = {"nonexistent_field": "x"}
    _apply_config_overrides(config, overrides)
    assert not hasattr(config, "nonexistent_field")

  def test_deep_nested_override(self) -> None:
    config = Config()
    overrides = {"backend": {"ollama": {"model": "llama3"}}}
    _apply_config_overrides(config, overrides)
    assert config.backend.ollama.model == "llama3"


class TestCheckSourceAllowed:
  """Direct tests for the source trust gate."""

  def test_trusted_in_config(self) -> None:
    reset_session_trusted()
    config = Config()
    config.plugins.trusted = {"folder:/safe": True}
    assert check_source_allowed("folder:/safe", config)

  def test_session_trusted_short_circuits(self) -> None:
    reset_session_trusted()
    config = Config()
    config.plugins.trusted = {}
    # First call (interactive) trusts it; second call should short-circuit.
    with patch("sys.stdin.isatty", return_value=True), patch("builtins.input", return_value="y"):
      assert check_source_allowed("zip:abc", config)
    assert check_source_allowed("zip:abc", config)  # session-trusted now

  def test_interactive_reject(self) -> None:
    reset_session_trusted()
    config = Config()
    config.plugins.trusted = {}
    with patch("sys.stdin.isatty", return_value=True), patch("builtins.input", return_value="n"):
      assert not check_source_allowed("zip:abc", config)

  def test_interactive_accept(self) -> None:
    reset_session_trusted()
    config = Config()
    config.plugins.trusted = {}
    with patch("sys.stdin.isatty", return_value=True), patch("builtins.input", return_value="y"):
      assert check_source_allowed("zip:abc", config)

  def test_env_override(self, monkeypatch) -> None:
    reset_session_trusted()
    monkeypatch.setenv(ENV_TRUST_SOURCE, "1")
    config = Config()
    config.plugins.trusted = {}
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    assert check_source_allowed("zip:abc", config)
