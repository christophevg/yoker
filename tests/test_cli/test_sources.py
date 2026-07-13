"""Tests for source resolution (MBI-004 task 4.6).

Covers the two-phase resolve/load design and all security defenses:
zip-bomb, path traversal, symlink escape, SSRF, embedded credentials,
non-HTTPS URLs, and folder subpath containment.
"""

from __future__ import annotations

import io
import stat
import subprocess
import zipfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from yoker.cli.sources import (
  LoadedSource,
  ResolvedSource,
  _detect_kind,
  load_source,
  resolve_source,
)
from yoker.exceptions import PluginError

# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


class TestDetectKind:
  """Test ``_detect_kind`` source-type ordering."""

  def test_https_url_is_github(self) -> None:
    assert _detect_kind("https://github.com/x/y") == "github"

  def test_http_url_is_github(self) -> None:
    assert _detect_kind("http://example.com/x/y") == "github"

  def test_zip_extension_not_dir_is_zip(self, tmp_path: Path) -> None:
    z = tmp_path / "pkg.zip"
    z.write_bytes(b"PK\x05\x06" + b"\x00" * 18)
    assert _detect_kind(str(z)) == "zip"

  def test_existing_dir_is_folder(self, tmp_path: Path) -> None:
    assert _detect_kind(str(tmp_path)) == "folder"

  def test_bare_name_is_module(self) -> None:
    assert _detect_kind("pkgq") == "module"

  def test_dot_zip_name_that_is_a_dir_is_folder(self, tmp_path: Path) -> None:
    d = tmp_path / "thing.zip"
    d.mkdir()
    assert _detect_kind(str(d)) == "folder"

  def test_nonexistent_bare_path_is_module(self) -> None:
    assert _detect_kind("./does-not-exist") == "module"


# ---------------------------------------------------------------------------
# Module source
# ---------------------------------------------------------------------------


class TestResolveModule:
  """Phase-1 module source resolution (metadata only)."""

  def test_returns_module_kind(self) -> None:
    r = resolve_source("pkgq")
    assert r.kind == "module"
    assert r.source_string == "pkgq"

  def test_trust_key_is_module_prefix(self) -> None:
    r = resolve_source("pkgq")
    assert r.trust_key == "module:pkgq"

  def test_no_cleanup(self) -> None:
    r = resolve_source("pkgq")
    assert r.cleanup is None

  def test_no_manifest(self) -> None:
    r = resolve_source("pkgq")
    assert r.manifest is None


class TestLoadModuleSource:
  """Phase-2 module source loading (imports)."""

  def test_load_source_imports_and_reads_manifest_fields(self) -> None:
    """load_source delegates to load_plugin and reads __YOKER_MANIFEST__."""
    resolved = ResolvedSource(
      kind="module",
      source_string="fakepkg",
      path=Path("fakepkg"),
      trust_key="module:fakepkg",
    )
    fake_manifest = MagicMock(agent="coder", prompt="do stuff")
    fake_package = MagicMock(__YOKER_MANIFEST__=fake_manifest)
    fake_components = MagicMock()
    with (
      patch("yoker.plugins.loader.load_plugin", return_value=fake_components) as m_load,
      patch("importlib.import_module", return_value=fake_package) as m_imp,
    ):
      result = load_source(resolved)
    m_load.assert_called_once_with("fakepkg")
    m_imp.assert_called_once_with("fakepkg")
    assert isinstance(result, LoadedSource)
    assert result.components is fake_components
    assert result.agent == "coder"
    assert result.prompt == "do stuff"

  def test_load_module_missing_raises_plugin_error(self) -> None:
    resolved = ResolvedSource(
      kind="module",
      source_string="nope_pkg",
      path=Path("nope_pkg"),
      trust_key="module:nope_pkg",
    )
    with (
      patch("yoker.plugins.loader.load_plugin", side_effect=PluginError("nope_pkg", "missing")),
    ):
      with pytest.raises(PluginError):
        load_source(resolved)


# ---------------------------------------------------------------------------
# Folder source
# ---------------------------------------------------------------------------


class TestResolveFolder:
  """Phase-1 folder source resolution."""

  def test_resolves_absolute_path(self, tmp_path: Path) -> None:
    r = resolve_source(str(tmp_path))
    assert r.kind == "folder"
    assert r.path == tmp_path.resolve()
    assert r.trust_key == f"folder:{tmp_path.resolve()}"

  def test_no_agent_toml_yields_none_manifest(self, tmp_path: Path) -> None:
    r = resolve_source(str(tmp_path))
    assert r.manifest is None

  def test_loads_agent_toml(self, tmp_path: Path) -> None:
    (tmp_path / "agent.toml").write_text(
      '[run]\nagent = "researcher"\nprompt = "hi"\n', encoding="utf-8"
    )
    r = resolve_source(str(tmp_path))
    assert r.manifest is not None
    assert r.manifest.run_config.agent == "researcher"
    assert r.manifest.run_config.prompt == "hi"

  def test_nonexistent_path_falls_back_to_module(self) -> None:
    """A nonexistent path is not a folder — it falls back to module."""
    r = resolve_source("/nonexistent/path/that/does/not/exist")
    assert r.kind == "module"

  def test_skills_dir_with_dotdot_rejected(self, tmp_path: Path) -> None:
    (tmp_path / "agent.toml").write_text('[plugin]\nskills_dir = "../../etc"\n', encoding="utf-8")
    with pytest.raises(PluginError, match="escapes|\\.\\.|relative"):
      resolve_source(str(tmp_path))

  def test_agents_dir_absolute_rejected(self, tmp_path: Path) -> None:
    (tmp_path / "agent.toml").write_text('[plugin]\nagents_dir = "/etc/passwd"\n', encoding="utf-8")
    with pytest.raises(PluginError, match="absolute|relative"):
      resolve_source(str(tmp_path))

  def test_tools_module_with_slash_rejected(self, tmp_path: Path) -> None:
    (tmp_path / "agent.toml").write_text('[plugin]\ntools_module = "sub/dir"\n', encoding="utf-8")
    with pytest.raises(PluginError, match="dotted module name"):
      resolve_source(str(tmp_path))

  def test_no_cleanup_for_folder(self, tmp_path: Path) -> None:
    r = resolve_source(str(tmp_path))
    assert r.cleanup is None


class TestLoadFolderSource:
  """Phase-2 folder source loading."""

  def test_loads_skills_and_agents(self, tmp_path: Path) -> None:
    # Minimal skill dir with one skill file.
    skills = tmp_path / "skills"
    skills.mkdir()
    (skills / "greet.md").write_text(
      "---\nname: greet\ndescription: Greet\n---\nSay hi\n", encoding="utf-8"
    )
    # Minimal agent dir with one agent file.
    agents = tmp_path / "agents"
    agents.mkdir()
    (agents / "coder.md").write_text(
      "---\nname: coder\ndescription: Coder\nmodel: ollama:test\ntools: []\n---\nYou code\n",
      encoding="utf-8",
    )
    (tmp_path / "agent.toml").write_text(
      '[run]\nagent = "coder"\nprompt = "go"\n', encoding="utf-8"
    )

    resolved = resolve_source(str(tmp_path))
    result = load_source(resolved)
    assert isinstance(result, LoadedSource)
    assert result.agent == "coder"
    assert result.prompt == "go"
    assert len(result.components.skills) >= 1
    assert len(result.components.agents) >= 1
    # cleanup carried through
    assert result.cleanup is None

  def test_missing_skills_dir_is_ok(self, tmp_path: Path) -> None:
    (tmp_path / "agent.toml").write_text('[run]\nagent = "x"\n', encoding="utf-8")
    resolved = resolve_source(str(tmp_path))
    result = load_source(resolved)
    assert result.components.skills == []

  def test_tools_module_imported_in_phase2(self, tmp_path: Path) -> None:
    # Write a tiny tools module.
    (tmp_path / "mytools.py").write_text(
      'def greet(name: str) -> str:\n  """Greet someone."""\n  return f\'hi {name}\'\n__YOKER_TOOLS__ = [greet]\n',
      encoding="utf-8",
    )
    (tmp_path / "agent.toml").write_text('[plugin]\ntools_module = "mytools"\n', encoding="utf-8")
    resolved = resolve_source(str(tmp_path))
    result = load_source(resolved)
    assert len(result.components.tools) == 1
    assert result.tools_module == "mytools"


# ---------------------------------------------------------------------------
# GitHub source
# ---------------------------------------------------------------------------


class TestResolveGithub:
  """Phase-1 GitHub URL resolution (mocked git clone)."""

  def test_rejects_non_https(self) -> None:
    with pytest.raises(PluginError, match="HTTPS"):
      resolve_source("git://github.com/x/y")

  def test_rejects_ssh_scheme(self) -> None:
    with pytest.raises(PluginError, match="HTTPS"):
      resolve_source("ssh://git@github.com/x/y")

  def test_rejects_file_scheme(self) -> None:
    with pytest.raises(PluginError, match="HTTPS"):
      resolve_source("file:///repo")

  def test_rejects_embedded_credentials(self) -> None:
    with pytest.raises(PluginError, match="credentials"):
      resolve_source("https://user:pass@github.com/x/y")

  def test_rejects_ssrf_private_ip(self) -> None:
    with pytest.raises(PluginError, match="SSRF|private IP"):
      resolve_source("https://10.0.0.1/x/y")

  def test_rejects_ssrf_metadata_ip(self) -> None:
    with pytest.raises(PluginError, match="SSRF|metadata"):
      resolve_source("https://169.254.169.254/latest/meta-data")

  def test_rejects_ssrf_localhost(self) -> None:
    with pytest.raises(PluginError, match="SSRF|localhost"):
      resolve_source("https://localhost/x/y")

  def test_successful_clone(self, tmp_path: Path) -> None:
    """A mocked successful clone returns a github ResolvedSource with SHA."""
    fake_tmp = tmp_path / "clone-target"
    fake_tmp.mkdir()

    def fake_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
      # Simulate git clone writing a file, and rev-parse returning a SHA.
      if "clone" in args:
        (fake_tmp / "agent.toml").write_text('[run]\nagent = "r"\nprompt = "p"\n', encoding="utf-8")
        return subprocess.CompletedProcess(args, 0, "", "")
      if "rev-parse" in args:
        return subprocess.CompletedProcess(args, 0, "abc1234\n", "")
      return subprocess.CompletedProcess(args, 0, "", "")

    with (
      patch("yoker.cli.sources.tempfile.TemporaryDirectory") as mk_tmp,
      patch("yoker.cli.sources.subprocess.run", side_effect=fake_run) as m_run,
      patch("yoker.cli.sources._check_ssrf") as m_ssrf,
    ):
      mk_tmp.return_value = MagicMock(name=fake_tmp.name, cleanup=MagicMock())
      # Make the mock's name attribute an actual path for .name lookups.
      mk_tmp.return_value.name = str(fake_tmp)
      r = resolve_source("https://github.com/owner/repo")

    assert r.kind == "github"
    assert r.trust_key == "github:owner/repo@abc1234"
    assert r.manifest is not None
    assert r.manifest.run_config.agent == "r"
    assert r.cleanup is not None
    m_ssrf.assert_called_once()
    # clone used --depth 1
    clone_call = [c for c in m_run.call_args_list if "clone" in c.args[0]][0]
    assert "--depth" in clone_call.args[0]
    assert "1" in clone_call.args[0]

  def test_clone_failure_raises_plugin_error(self, tmp_path: Path) -> None:
    err = subprocess.CalledProcessError(1, "git", stderr="not found")
    fake_tmp = MagicMock()
    fake_tmp.name = str(tmp_path)
    with (
      patch("yoker.cli.sources.subprocess.run", side_effect=err),
      patch("yoker.cli.sources._check_ssrf"),
      patch("yoker.cli.sources._make_secure_tempdir", return_value=fake_tmp),
    ):
      with pytest.raises(PluginError, match="clone failed"):
        resolve_source("https://github.com/owner/repo")

  def test_git_not_installed(self, tmp_path: Path) -> None:
    fake_tmp = MagicMock()
    fake_tmp.name = str(tmp_path)
    with (
      patch("yoker.cli.sources.subprocess.run", side_effect=FileNotFoundError),
      patch("yoker.cli.sources._check_ssrf"),
      patch("yoker.cli.sources._make_secure_tempdir", return_value=fake_tmp),
    ):
      with pytest.raises(PluginError, match="git is not installed"):
        resolve_source("https://github.com/owner/repo")


# ---------------------------------------------------------------------------
# Zip source
# ---------------------------------------------------------------------------


def _make_zip(entries: dict[str, bytes]) -> bytes:
  """Build an in-memory zip from a mapping of name → content."""
  buf = io.BytesIO()
  with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
    for name, data in entries.items():
      zf.writestr(name, data)
  return buf.getvalue()


class TestResolveZip:
  """Phase-1 zip source resolution."""

  def test_nonexistent_zip_raises(self) -> None:
    with pytest.raises(PluginError, match="does not exist"):
      resolve_source("/no/such/file.zip")

  def test_non_zip_file_raises(self, tmp_path: Path) -> None:
    p = tmp_path / "not.zip"
    p.write_text("not a zip", encoding="utf-8")
    with pytest.raises(PluginError, match="not a valid zip"):
      resolve_source(str(p))

  def test_valid_zip_extracts_and_reads_manifest(self, tmp_path: Path) -> None:
    z = tmp_path / "pkg.zip"
    z.write_bytes(
      _make_zip(
        {
          "agent.toml": b'[run]\nagent = "x"\nprompt = "y"\n',
          "skills/greet.md": b"---\nname: greet\ndescription: G\n---\nHi\n",
        }
      )
    )
    r = resolve_source(str(z))
    assert r.kind == "zip"
    assert r.trust_key.startswith("zip:")
    assert r.manifest is not None
    assert r.manifest.run_config.agent == "x"
    assert r.cleanup is not None

  def test_path_traversal_dotdot_rejected(self, tmp_path: Path) -> None:
    z = tmp_path / "evil.zip"
    # Build a zip with a ../ entry.
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
      zf.writestr("../escape.txt", b"pwned")
    z.write_bytes(buf.getvalue())
    with pytest.raises(PluginError, match=r"\.\.|absolute|escapes|traversal"):
      resolve_source(str(z))

  def test_absolute_path_entry_rejected(self, tmp_path: Path) -> None:
    z = tmp_path / "evil2.zip"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
      # zipfile permits writing absolute paths on some platforms.
      info = zipfile.ZipInfo("/etc/passwd")
      zf.writestr(info, b"pwned")
    z.write_bytes(buf.getvalue())
    with pytest.raises(PluginError, match="absolute"):
      resolve_source(str(z))

  def test_symlink_entry_rejected(self, tmp_path: Path) -> None:
    z = tmp_path / "link.zip"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
      info = zipfile.ZipInfo("link.txt")
      # Set external_attr to S_IFLNK mode.
      info.external_attr = (stat.S_IFLNK | 0o777) << 16
      zf.writestr(info, b"/etc/passwd")
    z.write_bytes(buf.getvalue())
    with pytest.raises(PluginError, match="symlink"):
      resolve_source(str(z))

  def test_too_many_entries_rejected(self, tmp_path: Path) -> None:
    """A zip with more than _MAX_ZIP_ENTRIES entries is rejected."""
    from yoker.cli.sources import _MAX_ZIP_ENTRIES

    z = tmp_path / "many.zip"
    entries = {f"f{i}.txt": b"x" for i in range(_MAX_ZIP_ENTRIES + 1)}
    z.write_bytes(_make_zip(entries))
    with pytest.raises(PluginError, match="too many entries"):
      resolve_source(str(z))

  def test_zip_bomb_high_ratio_rejected(self, tmp_path: Path) -> None:
    """A single entry with compression ratio > 100:1 is rejected."""
    z = tmp_path / "bomb.zip"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
      # Highly compressible content → ratio far above 100:1.
      zf.writestr("bomb.txt", b"\x00" * (10 * 1024 * 1024))
    z.write_bytes(buf.getvalue())
    with pytest.raises(PluginError, match="compression ratio"):
      resolve_source(str(z))

  def test_cleanup_removes_temp_dir(self, tmp_path: Path) -> None:
    z = tmp_path / "ok.zip"
    z.write_bytes(_make_zip({"agent.toml": b'[run]\nagent = "x"\n'}))
    r = resolve_source(str(z))
    extract_path = r.path
    assert extract_path.exists()
    r.cleanup()
    assert not extract_path.exists()


# ---------------------------------------------------------------------------
# Two-phase security invariant
# ---------------------------------------------------------------------------


class TestTwoPhaseInvariant:
  """Phase 1 never imports tools_module; phase 2 does."""

  def test_resolve_folder_does_not_import_tools_module(
    self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
  ) -> None:
    (tmp_path / "agent.toml").write_text('[plugin]\ntools_module = "evil"\n', encoding="utf-8")
    # If phase 1 tries to import, this raises to surface the violation.
    import builtins

    real_import = builtins.__import__

    def guard(name: str, *args: Any, **kwargs: Any) -> Any:
      if name == "evil":
        raise AssertionError("Phase 1 must not import tools_module")
      return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guard)
    r = resolve_source(str(tmp_path))  # should not raise
    assert r.manifest is not None
    assert r.manifest.plugin_config.tools_module == "evil"

  def test_resolve_module_does_not_import_package(self, monkeypatch: pytest.MonkeyPatch) -> None:
    """resolve_source('some_pkg') must not importlib.import_module the pkg."""
    with patch("importlib.import_module") as m_imp:
      resolve_source("some_pkg_xyz")
      m_imp.assert_not_called()
