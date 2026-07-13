"""Tests for the ``yoker inspect <source>`` subcommand handler (MBI-004 task 4.12)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from yoker.cli.inspect import run_inspect
from yoker.plugins.file_manifest import FileManifestResult, PluginConfig
from yoker.plugins.file_manifest import RunConfig as ManifestRunConfig


def _make_resolved(
  kind: str = "module",
  trust_key: str = "module:pkgq",
  source_string: str = "pkgq",
  path: Path | None = None,
  manifest: FileManifestResult | None = None,
  cleanup: MagicMock | None = None,
) -> MagicMock:
  """Build a mock ResolvedSource."""
  resolved = MagicMock()
  resolved.kind = kind
  resolved.source_string = source_string
  resolved.path = path or Path("/tmp/fake")
  resolved.trust_key = trust_key
  resolved.manifest = manifest
  resolved.cleanup = cleanup
  return resolved


def _make_manifest(
  agent: str | None = "coder",
  prompt: str | None = "do stuff",
  tools_module: str | None = "my_tools",
  overrides: dict | None = None,
) -> FileManifestResult:
  """Build a FileManifestResult for testing."""
  return FileManifestResult(
    run_config=ManifestRunConfig(agent=agent, prompt=prompt),
    plugin_config=PluginConfig(tools_module=tools_module),
    config_overrides=overrides or {},
  )


class TestRunInspectModule:
  """Module source inspect: read-only, notes trust required for Python manifest."""

  def test_module_report_prints_trust_notice(self, capsys) -> None:
    resolved = _make_resolved(kind="module", trust_key="module:pkgq")
    config = MagicMock()
    config.source = "pkgq"

    with (
      patch("yoker.cli.inspect.load_subcommand_config", return_value=config),
      patch("yoker.cli.inspect.resolve_source", return_value=resolved),
    ):
      run_inspect()

    out = capsys.readouterr().out
    assert "Type:        module" in out
    assert "module:pkgq" in out
    assert "requires trust to inspect Python manifest" in out
    assert "read-only" in out

  def test_module_does_not_import_tools_module(self) -> None:
    """inspect MUST NOT import tools_module (no code execution)."""
    resolved = _make_resolved(kind="module")
    config = MagicMock()
    config.source = "pkgq"

    with (
      patch("yoker.cli.inspect.load_subcommand_config", return_value=config),
      patch("yoker.cli.inspect.resolve_source", return_value=resolved),
      patch("yoker.cli.sources.load_source") as m_load,
    ):
      run_inspect()

    m_load.assert_not_called()

  def test_no_source_errors(self) -> None:
    config = MagicMock()
    config.source = ""

    with patch("yoker.cli.inspect.load_subcommand_config", return_value=config):
      with pytest.raises(SystemExit) as exc:
        run_inspect()

    assert exc.value.code == 1


class TestRunInspectFolder:
  """Folder source inspect: reads skills/agents from disk, no imports."""

  def test_folder_report_lists_skills_and_agents(self, tmp_path, capsys) -> None:
    """Folder inspect lists skills and agents by name (read from disk)."""
    # Create a skills dir and agents dir with minimal content.
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "my-skill.md").write_text("---\nname: my-skill\n---\nbody")

    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "coder.md").write_text("---\nname: coder\nmodel: x\n---\nbody")

    manifest = _make_manifest(agent="coder", prompt="do X", tools_module="tools")
    resolved = _make_resolved(
      kind="folder",
      trust_key=f"folder:{tmp_path}",
      source_string=str(tmp_path),
      path=tmp_path,
      manifest=manifest,
    )
    config = MagicMock()
    config.source = str(tmp_path)

    with (
      patch("yoker.cli.inspect.load_subcommand_config", return_value=config),
      patch("yoker.cli.inspect.resolve_source", return_value=resolved),
    ):
      run_inspect()

    out = capsys.readouterr().out
    assert "Type:        folder" in out
    assert "coder" in out  # agent name in "What it does"
    assert "do X" in out  # prompt
    assert "tools" in out  # tools_module name
    assert "declared, NOT imported" in out

  def test_folder_no_manifest_shows_not_set(self, tmp_path, capsys) -> None:
    resolved = _make_resolved(
      kind="folder",
      trust_key=f"folder:{tmp_path}",
      path=tmp_path,
      manifest=None,
    )
    config = MagicMock()
    config.source = str(tmp_path)

    with (
      patch("yoker.cli.inspect.load_subcommand_config", return_value=config),
      patch("yoker.cli.inspect.resolve_source", return_value=resolved),
    ):
      run_inspect()

    out = capsys.readouterr().out
    assert "(not set)" in out
    assert "(no tools_module declared)" in out

  def test_folder_config_overrides_displayed(self, tmp_path, capsys) -> None:
    manifest = _make_manifest(overrides={"backend": {"ollama": {"model": "llama3"}}})
    resolved = _make_resolved(
      kind="folder",
      path=tmp_path,
      manifest=manifest,
    )
    config = MagicMock()
    config.source = str(tmp_path)

    with (
      patch("yoker.cli.inspect.load_subcommand_config", return_value=config),
      patch("yoker.cli.inspect.resolve_source", return_value=resolved),
    ):
      run_inspect()

    out = capsys.readouterr().out
    assert "backend:" in out
    assert "ollama" in out or "llama3" in out


class TestInspectNoTrustGate:
  """inspect does NOT call check_source_allowed (read-only, no trust gate)."""

  def test_no_trust_gate_called(self, tmp_path) -> None:
    resolved = _make_resolved(kind="folder", path=tmp_path)
    config = MagicMock()
    config.source = str(tmp_path)

    with (
      patch("yoker.cli.inspect.load_subcommand_config", return_value=config),
      patch("yoker.cli.inspect.resolve_source", return_value=resolved),
      patch("yoker.plugins.security.check_source_allowed") as m_check,
    ):
      run_inspect()

    m_check.assert_not_called()


class TestInspectCleanup:
  """Cleanup is called for github/zip sources after the report."""

  def test_cleanup_called(self, tmp_path) -> None:
    cleanup = MagicMock()
    resolved = _make_resolved(kind="folder", path=tmp_path, cleanup=cleanup)
    config = MagicMock()
    config.source = str(tmp_path)

    with (
      patch("yoker.cli.inspect.load_subcommand_config", return_value=config),
      patch("yoker.cli.inspect.resolve_source", return_value=resolved),
    ):
      run_inspect()

    cleanup.assert_called_once()

  def test_cleanup_failure_does_not_raise(self, tmp_path, capsys) -> None:
    cleanup = MagicMock(side_effect=RuntimeError("boom"))
    resolved = _make_resolved(kind="folder", path=tmp_path, cleanup=cleanup)
    config = MagicMock()
    config.source = str(tmp_path)

    with (
      patch("yoker.cli.inspect.load_subcommand_config", return_value=config),
      patch("yoker.cli.inspect.resolve_source", return_value=resolved),
    ):
      # Should NOT raise — cleanup failure is logged, not propagated.
      run_inspect()

    cleanup.assert_called_once()
    # Report still printed.
    out = capsys.readouterr().out
    assert "Source Report" in out
