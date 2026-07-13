"""Tests for the ``yoker container <source>`` subcommand handler (MBI-004 task 4.9)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from yoker.cli.container import (
  _build_dockerfile,
  _build_ignore_file,
  _extract_sha_from_trust_key,
  _source_build_steps,
  _validate_source_string,
  run_container,
)


def _make_resolved(
  kind: str = "module",
  trust_key: str = "module:pkgq",
  cleanup: MagicMock | None = None,
) -> MagicMock:
  resolved = MagicMock()
  resolved.kind = kind
  resolved.source_string = "pkgq"
  resolved.path = Path("/tmp/fake")
  resolved.trust_key = trust_key
  resolved.cleanup = cleanup
  return resolved


class TestValidateSourceString:
  """Shell metacharacter validation (H3 defense)."""

  def test_clean_source_accepted(self) -> None:
    # Should not raise.
    _validate_source_string("pkgq")

  def test_clean_url_accepted(self) -> None:
    _validate_source_string("https://github.com/owner/repo")

  def test_clean_folder_accepted(self) -> None:
    _validate_source_string("./my-folder")

  def test_semicolon_rejected(self) -> None:
    with pytest.raises(SystemExit) as exc:
      _validate_source_string("pkgq; rm -rf /")
    assert exc.value.code == 1

  def test_pipe_rejected(self) -> None:
    with pytest.raises(SystemExit) as exc:
      _validate_source_string("pkgq | cat")
    assert exc.value.code == 1

  def test_dollar_rejected(self) -> None:
    with pytest.raises(SystemExit) as exc:
      _validate_source_string("$(whoami)")
    assert exc.value.code == 1

  def test_backtick_rejected(self) -> None:
    with pytest.raises(SystemExit) as exc:
      _validate_source_string("pkgq`whoami`")
    assert exc.value.code == 1


class TestSourceBuildSteps:
  """Source-type-specific Dockerfile build steps."""

  def test_module_build_steps(self) -> None:
    resolved = _make_resolved(kind="module", trust_key="module:pkgq")
    steps, entrypoint = _source_build_steps(resolved, "pkgq")
    assert any("pip" in s and "pkgq" in s for s in steps)
    assert entrypoint == "pkgq"

  def test_github_build_steps_pin_sha(self) -> None:
    resolved = _make_resolved(kind="github", trust_key="github:owner/repo@abc1234")
    steps, entrypoint = _source_build_steps(resolved, "https://github.com/owner/repo")
    joined = "\n".join(steps)
    assert "git" in joined
    assert "clone" in joined
    assert "abc1234" in joined  # SHA pinned
    assert "checkout" in joined
    assert entrypoint == "/app/source"

  def test_folder_build_steps_copy(self) -> None:
    resolved = _make_resolved(kind="folder", trust_key="folder:/abs")
    steps, entrypoint = _source_build_steps(resolved, "./my-folder")
    joined = "\n".join(steps)
    assert "COPY" in joined
    assert "/app/source/" in joined
    assert entrypoint == "/app/source"

  def test_zip_build_steps_copy_and_extract(self) -> None:
    resolved = _make_resolved(kind="zip", trust_key="zip:abc123")
    steps, entrypoint = _source_build_steps(resolved, "./my.zip")
    joined = "\n".join(steps)
    assert "COPY" in joined
    assert "zipfile" in joined
    assert entrypoint == "/app/source"


class TestBuildDockerfile:
  """Dockerfile generation uses JSON-array form and includes USER directive."""

  def test_dockerfile_has_json_array_run(self) -> None:
    resolved = _make_resolved(kind="module", trust_key="module:pkgq")
    dockerfile = _build_dockerfile("python:3.12-slim", "0.7.0", resolved, "pkgq")
    assert 'RUN ["pip", "install"' in dockerfile

  def test_dockerfile_has_json_array_entrypoint(self) -> None:
    resolved = _make_resolved(kind="module", trust_key="module:pkgq")
    dockerfile = _build_dockerfile("python:3.12-slim", "0.7.0", resolved, "pkgq")
    assert 'ENTRYPOINT ["yoker", "run", "pkgq"]' in dockerfile

  def test_dockerfile_pins_yoker_version(self) -> None:
    resolved = _make_resolved(kind="module", trust_key="module:pkgq")
    dockerfile = _build_dockerfile("python:3.12-slim", "0.7.0", resolved, "pkgq")
    assert "yoker==0.7.0" in dockerfile

  def test_dockerfile_has_non_root_user(self) -> None:
    resolved = _make_resolved(kind="module", trust_key="module:pkgq")
    dockerfile = _build_dockerfile("python:3.12-slim", "0.7.0", resolved, "pkgq")
    assert "USER 1000" in dockerfile

  def test_dockerfile_does_not_copy_yoker_toml(self) -> None:
    resolved = _make_resolved(kind="module", trust_key="module:pkgq")
    dockerfile = _build_dockerfile("python:3.12-slim", "0.7.0", resolved, "pkgq")
    assert ".yoker.toml" not in dockerfile or "Do NOT bake" in dockerfile
    # Secret management note present instead.
    assert "Secret management" in dockerfile

  def test_dockerfile_uses_custom_base_image(self) -> None:
    resolved = _make_resolved(kind="module", trust_key="module:pkgq")
    dockerfile = _build_dockerfile("python:3.11-slim", "0.7.0", resolved, "pkgq")
    assert "FROM python:3.11-slim" in dockerfile

  def test_dockerfile_github_pins_sha(self) -> None:
    resolved = _make_resolved(kind="github", trust_key="github:owner/repo@abc1234")
    dockerfile = _build_dockerfile(
      "python:3.12-slim", "0.7.0", resolved, "https://github.com/owner/repo"
    )
    assert "abc1234" in dockerfile
    assert "checkout" in dockerfile


class TestBuildIgnoreFile:
  """.dockerignore/.containerignore excludes secrets and build artifacts."""

  def test_ignore_file_excludes_git(self) -> None:
    content = _build_ignore_file()
    assert ".git" in content

  def test_ignore_file_excludes_pycache(self) -> None:
    content = _build_ignore_file()
    assert "__pycache__" in content
    assert "*.pyc" in content

  def test_ignore_file_excludes_env(self) -> None:
    content = _build_ignore_file()
    assert ".env" in content

  def test_ignore_file_excludes_yoker_toml(self) -> None:
    content = _build_ignore_file()
    assert ".yoker.toml" in content

  def test_ignore_file_excludes_ssh(self) -> None:
    content = _build_ignore_file()
    assert ".ssh" in content

  def test_ignore_file_excludes_credentials(self) -> None:
    content = _build_ignore_file()
    assert "credentials" in content


class TestExtractShaFromTrustKey:
  """SHA extraction from GitHub trust keys."""

  def test_valid_sha_extracted(self) -> None:
    sha = _extract_sha_from_trust_key("github:owner/repo@abc1234")
    assert sha == "abc1234"

  def test_long_sha_extracted(self) -> None:
    long_sha = "a" * 40
    sha = _extract_sha_from_trust_key(f"github:owner/repo@{long_sha}")
    assert sha == long_sha

  def test_no_sha_returns_none(self) -> None:
    sha = _extract_sha_from_trust_key("github:owner/repo")
    assert sha is None

  def test_non_hex_sha_returns_none(self) -> None:
    sha = _extract_sha_from_trust_key("github:owner/repo@xyz123")
    assert sha is None


class TestRunContainer:
  """Top-level run_container dispatch."""

  def test_no_source_errors(self) -> None:
    config = MagicMock()
    config.source = ""

    with patch("yoker.cli.container.load_subcommand_config", return_value=config):
      with pytest.raises(SystemExit) as exc:
        run_container()

    assert exc.value.code == 1

  def test_generates_dockerfile_for_module(self, tmp_path) -> None:
    config = MagicMock()
    config.source = "pkgq"
    config.engine = "docker"
    config.output_dir = str(tmp_path)
    config.base_image = "python:3.12-slim"
    config.compose = False

    resolved = _make_resolved(kind="module", trust_key="module:pkgq")

    with (
      patch("yoker.cli.container.load_subcommand_config", return_value=config),
      patch("yoker.cli.container.resolve_source", return_value=resolved),
    ):
      run_container()

    dockerfile = (tmp_path / "Dockerfile").read_text()
    assert "FROM python:3.12-slim" in dockerfile
    assert "yoker==0.7.0" in dockerfile  # pinned version from yoker.__version__
    assert "USER 1000" in dockerfile
    assert 'ENTRYPOINT ["yoker", "run", "pkgq"]' in dockerfile

    ignore = (tmp_path / ".dockerignore").read_text()
    assert ".git" in ignore

  def test_generates_containerfile_for_podman(self, tmp_path) -> None:
    config = MagicMock()
    config.source = "pkgq"
    config.engine = "podman"
    config.output_dir = str(tmp_path)
    config.base_image = "python:3.12-slim"
    config.compose = False

    resolved = _make_resolved(kind="module", trust_key="module:pkgq")

    with (
      patch("yoker.cli.container.load_subcommand_config", return_value=config),
      patch("yoker.cli.container.resolve_source", return_value=resolved),
    ):
      run_container()

    assert (tmp_path / "Containerfile").exists()
    assert (tmp_path / ".containerignore").exists()
    assert not (tmp_path / "Dockerfile").exists()

  def test_generates_compose_file(self, tmp_path) -> None:
    config = MagicMock()
    config.source = "pkgq"
    config.engine = "docker"
    config.output_dir = str(tmp_path)
    config.base_image = "python:3.12-slim"
    config.compose = True

    resolved = _make_resolved(kind="module", trust_key="module:pkgq")

    with (
      patch("yoker.cli.container.load_subcommand_config", return_value=config),
      patch("yoker.cli.container.resolve_source", return_value=resolved),
    ):
      run_container()

    compose = (tmp_path / "docker-compose.yml").read_text()
    assert "services:" in compose
    assert "yoker-agent" in compose

  def test_invalid_engine_errors(self, tmp_path) -> None:
    config = MagicMock()
    config.source = "pkgq"
    config.engine = "invalid"
    config.output_dir = str(tmp_path)
    config.base_image = "python:3.12-slim"
    config.compose = False

    resolved = _make_resolved(kind="module", trust_key="module:pkgq")

    with (
      patch("yoker.cli.container.load_subcommand_config", return_value=config),
      patch("yoker.cli.container.resolve_source", return_value=resolved),
    ):
      with pytest.raises(SystemExit) as exc:
        run_container()

    assert exc.value.code == 1


class TestContainerCleanup:
  """Source cleanup is called after container generation."""

  def test_cleanup_called(self, tmp_path) -> None:
    config = MagicMock()
    config.source = "https://github.com/owner/repo"
    config.engine = "docker"
    config.output_dir = str(tmp_path)
    config.base_image = "python:3.12-slim"
    config.compose = False

    cleanup = MagicMock()
    resolved = _make_resolved(
      kind="github",
      trust_key="github:owner/repo@abc1234",
      cleanup=cleanup,
    )

    with (
      patch("yoker.cli.container.load_subcommand_config", return_value=config),
      patch("yoker.cli.container.resolve_source", return_value=resolved),
    ):
      run_container()

    cleanup.assert_called_once()
