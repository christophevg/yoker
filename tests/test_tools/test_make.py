"""Tests for the make tool implementation.

Verifies target validation (R2, R3), env_vars allowlist + hard-denylist +
value rules, output truncation, timeout enforcement with process-group
kill (R4), error handling, and the structured ToolResult contract.
"""

import sys
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from yoker.builtin import make
from yoker.config import Config, MakeToolConfig, PermissionsConfig, ToolsSharedConfig
from yoker.tools import ToolRegistry
from yoker.tools.context import ToolContext
from yoker.tools.guardrails.path import PathGuardrail

make_module = sys.modules["yoker.builtin.make"]


def _make_spec():
  """Register the make tool and return its spec."""
  registry = ToolRegistry()
  return registry.register(make, name="make")


def _make_context(config: MakeToolConfig | None = None) -> ToolContext:
  """Build a ToolContext for the make tool."""
  return ToolContext(
    config=config or MakeToolConfig(),
    shared=ToolsSharedConfig(),
    backends={},
  )


def _write_makefile(dir_path: Path, body: str) -> None:
  """Write a Makefile into dir_path."""
  (dir_path / "Makefile").write_text(body)


class TestMakeToolSchema:
  """Schema and registration tests."""

  def test_name(self) -> None:
    spec = _make_spec()
    assert spec.name == "make"

  def test_description_present(self) -> None:
    spec = _make_spec()
    assert spec.description
    assert "make" in spec.description.lower() or "Make" in spec.description

  def test_schema_target_required(self) -> None:
    """target is required; cwd/timeout_ms/env_vars are optional."""
    spec = _make_spec()
    required = spec.schema["function"]["parameters"]["required"]
    assert "target" in required
    assert "cwd" not in required
    assert "env_vars" not in required
    assert "timeout_ms" not in required

  def test_schema_has_cwd_path_guard(self) -> None:
    """cwd parameter is marked with the PATH guard."""
    spec = _make_spec()
    assert spec.guards.get("cwd") is not None
    from yoker.tools.annotations import GuardType

    assert spec.guards["cwd"] == GuardType.PATH


class TestMakeToolTargetValidation:
  """R2, R3: target name validation."""

  @pytest.fixture
  def makefile_dir(self, tmp_path: Path) -> Path:
    _write_makefile(tmp_path, "check:\n\t@echo ok\n")
    return tmp_path

  @pytest.mark.asyncio
  async def test_check_succeeds(self, makefile_dir: Path) -> None:
    """make check on a valid Makefile returns exit 0 and stdout."""
    spec = _make_spec()
    ctx = _make_context()
    result = await spec.execute(target="check", ctx=ctx, cwd=str(makefile_dir))
    assert result.success
    assert result.result["exit_code"] == 0
    assert "ok" in result.result["stdout"]

  @pytest.mark.asyncio
  async def test_target_with_space_rejected(self, makefile_dir: Path) -> None:
    """'rm -rf /' rejected — space not in _TARGET_RE."""
    spec = _make_spec()
    ctx = _make_context()
    result = await spec.execute(target="rm -rf /", ctx=ctx, cwd=str(makefile_dir))
    assert not result.success
    assert "invalid" in result.error.lower() or "forbidden" in result.error.lower()

  @pytest.mark.asyncio
  async def test_target_with_semicolon_rejected(self, makefile_dir: Path) -> None:
    """'check; cat /etc/passwd' rejected — ; and space forbidden."""
    spec = _make_spec()
    ctx = _make_context()
    result = await spec.execute(target="check; cat /etc/passwd", ctx=ctx, cwd=str(makefile_dir))
    assert not result.success

  @pytest.mark.asyncio
  async def test_target_with_newline_rejected(self, makefile_dir: Path) -> None:
    """Newline in target rejected (R3)."""
    spec = _make_spec()
    ctx = _make_context()
    result = await spec.execute(target="check\nrm -rf /", ctx=ctx, cwd=str(makefile_dir))
    assert not result.success

  @pytest.mark.asyncio
  async def test_leading_dash_rejected(self, makefile_dir: Path) -> None:
    """'--eval=...' rejected — leading '-' (R2)."""
    spec = _make_spec()
    ctx = _make_context()
    result = await spec.execute(target="--eval=pwn:\n\trm -rf /", ctx=ctx, cwd=str(makefile_dir))
    assert not result.success
    assert "-" in result.error or "flag" in result.error.lower()

  @pytest.mark.parametrize("bad_target", ["-i", "-j", "-C /tmp"])
  @pytest.mark.asyncio
  async def test_flag_injection_rejected(self, makefile_dir: Path, bad_target: str) -> None:
    """Leading-dash flag injection rejected (R2)."""
    spec = _make_spec()
    ctx = _make_context()
    result = await spec.execute(target=bad_target, ctx=ctx, cwd=str(makefile_dir))
    assert not result.success

  @pytest.mark.parametrize("bad_target", ["", "   ", "\t"])
  @pytest.mark.asyncio
  async def test_empty_target_rejected(self, makefile_dir: Path, bad_target: str) -> None:
    """Empty/whitespace target rejected (R2)."""
    spec = _make_spec()
    ctx = _make_context()
    result = await spec.execute(target=bad_target, ctx=ctx, cwd=str(makefile_dir))
    assert not result.success
    assert "empty" in result.error.lower()

  @pytest.mark.asyncio
  async def test_non_string_target_rejected(self, makefile_dir: Path) -> None:
    """Non-string target rejected."""
    spec = _make_spec()
    ctx = _make_context()
    result = await spec.execute(target=123, ctx=ctx, cwd=str(makefile_dir))  # type: ignore[arg-type]
    assert not result.success
    assert "string" in result.error.lower()

  @pytest.mark.asyncio
  async def test_overlong_target_rejected(self, makefile_dir: Path) -> None:
    """Target exceeding 256 chars rejected."""
    spec = _make_spec()
    ctx = _make_context()
    result = await spec.execute(target="a" * 257, ctx=ctx, cwd=str(makefile_dir))
    assert not result.success
    assert "256" in result.error


class TestMakeToolPathGuardrail:
  """R1: PathGuardrail on cwd."""

  def test_make_in_filesystem_tools(self) -> None:
    """make is in _FILESYSTEM_TOOLS so PathGuardrail fires on cwd."""
    from yoker.tools.guardrails.path import _FILESYSTEM_TOOLS

    assert "make" in _FILESYSTEM_TOOLS

  def test_guardrail_blocks_cwd_outside_allowed(self, tmp_path: Path) -> None:
    """cwd outside allowed paths is rejected (R1)."""
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = PathGuardrail(config)
    validation = guardrail.validate("make", "/etc")
    assert not validation.valid

  def test_guardrail_blocks_traversal(self, tmp_path: Path) -> None:
    """cwd traversal rejected (R1)."""
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = PathGuardrail(config)
    validation = guardrail.validate("make", "../../")
    assert not validation.valid

  def test_guardrail_allows_cwd_inside_allowed(self, tmp_path: Path) -> None:
    """cwd inside allowed paths passes."""
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = PathGuardrail(config)
    validation = guardrail.validate("make", str(tmp_path))
    assert validation.valid


class TestMakeToolEnvVars:
  """env_vars: per-target allowlist + hard-denylist + value rules."""

  @pytest.fixture
  def makefile_dir(self, tmp_path: Path) -> Path:
    # Makefile that echoes the TEST env var so we can verify it was set.
    _write_makefile(tmp_path, "test:\n\t@echo $(TEST)\n")
    return tmp_path

  @pytest.mark.asyncio
  async def test_env_var_allowed_and_propagated(self, makefile_dir: Path) -> None:
    """allowed_env_vars = {'test': ('TEST',)}; TEST is set and seen by make."""
    config = MakeToolConfig(allowed_env_vars={"test": ("TEST",)})
    spec = _make_spec()
    ctx = _make_context(config=config)
    result = await spec.execute(
      target="test",
      ctx=ctx,
      cwd=str(makefile_dir),
      env_vars={"TEST": "tests/test_foo.py"},
    )
    assert result.success
    assert "tests/test_foo.py" in result.result["stdout"]

  @pytest.mark.asyncio
  async def test_env_var_denied_when_target_not_in_allowlist(self, makefile_dir: Path) -> None:
    """Target not in allowlist dict → all env vars denied (deny-by-default)."""
    config = MakeToolConfig(allowed_env_vars={"test": ("TEST",)})
    spec = _make_spec()
    ctx = _make_context(config=config)
    result = await spec.execute(
      target="build",
      ctx=ctx,
      cwd=str(makefile_dir),
      env_vars={"TEST": "foo"},
    )
    assert not result.success
    assert "allowlist" in result.error.lower()

  @pytest.mark.asyncio
  async def test_env_var_denied_when_name_not_in_per_target_tuple(self, makefile_dir: Path) -> None:
    """TEST not in build's tuple → denied."""
    config = MakeToolConfig(allowed_env_vars={"test": ("TEST",), "build": ("BUILD",)})
    spec = _make_spec()
    ctx = _make_context(config=config)
    result = await spec.execute(
      target="build",
      ctx=ctx,
      cwd=str(makefile_dir),
      env_vars={"TEST": "foo"},
    )
    assert not result.success
    assert "allowlist" in result.error.lower()

  @pytest.mark.asyncio
  async def test_makeflags_denied_even_if_allowlisted(self, makefile_dir: Path) -> None:
    """MAKEFLAGS is on the hard-denylist; allowlisting it does not enable it."""
    config = MakeToolConfig(allowed_env_vars={"test": ("TEST", "MAKEFLAGS")})
    spec = _make_spec()
    ctx = _make_context(config=config)
    result = await spec.execute(
      target="test",
      ctx=ctx,
      cwd=str(makefile_dir),
      env_vars={"MAKEFLAGS": "--eval=pwn:\\n\\trm -rf /"},
    )
    assert not result.success
    assert "hard-denylist" in result.error.lower()

  @pytest.mark.asyncio
  async def test_oversize_value_rejected(self, makefile_dir: Path) -> None:
    """Value exceeding max_env_var_bytes rejected."""
    config = MakeToolConfig(
      allowed_env_vars={"test": ("TEST",)},
      max_env_var_bytes=4096,
    )
    spec = _make_spec()
    ctx = _make_context(config=config)
    result = await spec.execute(
      target="test",
      ctx=ctx,
      cwd=str(makefile_dir),
      env_vars={"TEST": "x" * 4097},
    )
    assert not result.success
    assert "exceeds" in result.error.lower()

  @pytest.mark.asyncio
  async def test_newline_in_value_rejected(self, makefile_dir: Path) -> None:
    """Newline in value rejected."""
    config = MakeToolConfig(allowed_env_vars={"test": ("TEST",)})
    spec = _make_spec()
    ctx = _make_context(config=config)
    result = await spec.execute(
      target="test",
      ctx=ctx,
      cwd=str(makefile_dir),
      env_vars={"TEST": "foo\nbar"},
    )
    assert not result.success
    assert "newline" in result.error.lower()

  @pytest.mark.asyncio
  async def test_nul_in_value_rejected(self, makefile_dir: Path) -> None:
    """NUL byte in value rejected."""
    config = MakeToolConfig(allowed_env_vars={"test": ("TEST",)})
    spec = _make_spec()
    ctx = _make_context(config=config)
    result = await spec.execute(
      target="test",
      ctx=ctx,
      cwd=str(makefile_dir),
      env_vars={"TEST": "foo\x00bar"},
    )
    assert not result.success
    assert "nul" in result.error.lower()

  @pytest.mark.asyncio
  async def test_empty_env_vars_ok(self, makefile_dir: Path) -> None:
    """Empty env_vars dict is fine (no validation needed)."""
    spec = _make_spec()
    ctx = _make_context()
    result = await spec.execute(target="test", ctx=ctx, cwd=str(makefile_dir), env_vars={})
    assert result.success

  @pytest.mark.asyncio
  async def test_env_vars_none_ok(self, makefile_dir: Path) -> None:
    """env_vars=None is fine (default)."""
    spec = _make_spec()
    ctx = _make_context()
    result = await spec.execute(target="test", ctx=ctx, cwd=str(makefile_dir))
    assert result.success

  @pytest.mark.asyncio
  async def test_env_vars_not_dict_rejected(self, makefile_dir: Path) -> None:
    """env_vars must be a dict."""
    spec = _make_spec()
    ctx = _make_context()
    result = await spec.execute(
      target="test",
      ctx=ctx,
      cwd=str(makefile_dir),
      env_vars="TEST=foo",  # type: ignore[arg-type]
    )
    assert not result.success
    assert "object" in result.error.lower() or "dict" in result.error.lower()


class TestMakeToolOutputTruncation:
  """Per-stream truncation at max_output_kb * 1024 bytes."""

  @pytest.mark.asyncio
  async def test_output_truncated_when_over_limit(self, tmp_path: Path) -> None:
    """stdout exceeding max_output_kb is truncated with a notice; truncated=True."""
    # Generate ~200KB of output; default cap is 100KB.
    _write_makefile(
      tmp_path,
      "check:\n\t@python3 -c \"print('x' * 200000)\"\n",
    )
    spec = _make_spec()
    ctx = _make_context(MakeToolConfig(max_output_kb=100))
    result = await spec.execute(target="check", ctx=ctx, cwd=str(tmp_path))
    assert result.success
    assert result.result["truncated"] is True
    assert "[truncated]" in result.result["stdout"]
    # stdout (truncated) is bounded by cap + notice length
    assert (
      len(result.result["stdout"].encode("utf-8")) <= 100 * 1024 + len("\n... [truncated]\n") + 4
    )

  @pytest.mark.asyncio
  async def test_small_output_not_truncated(self, tmp_path: Path) -> None:
    """Small output is not truncated; truncated=False."""
    _write_makefile(tmp_path, "check:\n\t@echo hello\n")
    spec = _make_spec()
    ctx = _make_context()
    result = await spec.execute(target="check", ctx=ctx, cwd=str(tmp_path))
    assert result.success
    assert result.result["truncated"] is False
    assert "[truncated]" not in result.result["stdout"]


class TestMakeToolTimeout:
  """R4: timeout enforced and process group killed."""

  @pytest.mark.asyncio
  async def test_timeout_returns_failure(self, tmp_path: Path) -> None:
    """A target that sleeps past the timeout returns a structured failure."""
    _write_makefile(
      tmp_path,
      "check:\n\t@sleep 10\n",
    )
    config = MakeToolConfig(timeout_ms=1000)
    spec = _make_spec()
    ctx = _make_context(config=config)
    result = await spec.execute(target="check", ctx=ctx, cwd=str(tmp_path), timeout_ms=1000)
    assert not result.success
    assert "timeout" in result.error.lower()
    assert "1000" in result.error or "exceeded" in result.error.lower()

  @pytest.mark.asyncio
  async def test_timeout_clamped_to_config_ceiling(self, tmp_path: Path) -> None:
    """timeout_ms above the config ceiling is clamped down."""
    _write_makefile(
      tmp_path,
      "check:\n\t@sleep 5\n",
    )
    # Config ceiling 1s; caller asks for 60s — clamped to 1s.
    config = MakeToolConfig(timeout_ms=1000)
    spec = _make_spec()
    ctx = _make_context(config=config)
    result = await spec.execute(target="check", ctx=ctx, cwd=str(tmp_path), timeout_ms=60000)
    assert not result.success
    assert "timeout" in result.error.lower()
    # Should mention the clamped value (1000ms), not 60000.
    assert "1000" in result.error

  @pytest.mark.asyncio
  async def test_timeout_minimum_one_second(self, tmp_path: Path) -> None:
    """timeout_ms below 1000 is clamped up to 1000ms."""
    _write_makefile(
      tmp_path,
      "check:\n\t@sleep 3\n",
    )
    config = MakeToolConfig(timeout_ms=30000)
    spec = _make_spec()
    ctx = _make_context(config=config)
    # Caller asks for 50ms — clamped up to 1000ms.
    result = await spec.execute(target="check", ctx=ctx, cwd=str(tmp_path), timeout_ms=50)
    assert not result.success
    assert "1000" in result.error

  @pytest.mark.asyncio
  async def test_process_group_killed_on_timeout(
    self, tmp_path: Path, mocker: MockerFixture
  ) -> None:
    """R4: os.killpg is called with the child's pid on timeout."""
    _write_makefile(
      tmp_path,
      "check:\n\t@sleep 10\n",
    )
    killpg = mocker.patch.object(make_module.os, "killpg")
    config = MakeToolConfig(timeout_ms=500)
    spec = _make_spec()
    ctx = _make_context(config=config)
    await spec.execute(target="check", ctx=ctx, cwd=str(tmp_path), timeout_ms=500)
    assert killpg.called
    # First positional arg is the pid (process group leader).
    _args, _kwargs = killpg.call_args
    assert isinstance(_args[0], int)
    assert _args[1] == make_module.signal.SIGKILL


class TestMakeToolErrorHandling:
  """Error paths: missing make binary, missing Makefile, non-zero exit."""

  @pytest.mark.asyncio
  async def test_make_not_installed(self, tmp_path: Path, mocker: MockerFixture) -> None:
    """FileNotFoundError → 'make is not installed or not found in PATH'."""
    _write_makefile(tmp_path, "check:\n\t@echo ok\n")
    mocker.patch.object(
      make_module.subprocess,
      "Popen",
      side_effect=FileNotFoundError(),
    )
    spec = _make_spec()
    ctx = _make_context()
    result = await spec.execute(target="check", ctx=ctx, cwd=str(tmp_path))
    assert not result.success
    assert "not installed" in result.error.lower() or "not found" in result.error.lower()

  @pytest.mark.asyncio
  async def test_missing_makefile_returns_nonzero(self, tmp_path: Path) -> None:
    """Missing Makefile → exit code != 0, stderr from make; no pre-check."""
    spec = _make_spec()
    ctx = _make_context()
    result = await spec.execute(target="check", ctx=ctx, cwd=str(tmp_path))
    assert not result.success
    assert result.result["exit_code"] != 0
    assert result.result["stderr"]  # make prints an error to stderr

  @pytest.mark.asyncio
  async def test_nonzero_exit_still_returns_structured_result(self, tmp_path: Path) -> None:
    """A failing target returns exit_code, stdout, stderr in the result dict."""
    _write_makefile(
      tmp_path,
      "check:\n\t@echo to-stdout\n\t@echo to-stderr 1>&2\n\t@exit 2\n",
    )
    spec = _make_spec()
    ctx = _make_context()
    result = await spec.execute(target="check", ctx=ctx, cwd=str(tmp_path))
    assert not result.success
    assert result.result["exit_code"] == 2
    assert "to-stdout" in result.result["stdout"]
    assert "to-stderr" in result.result["stderr"]
    assert result.error == result.result["stderr"]


class TestMakeToolResultStructure:
  """ToolResult.result dict shape: exit_code, stdout, stderr, truncated."""

  @pytest.mark.asyncio
  async def test_success_result_dict_keys(self, tmp_path: Path) -> None:
    _write_makefile(tmp_path, "check:\n\t@echo hi\n")
    spec = _make_spec()
    ctx = _make_context()
    result = await spec.execute(target="check", ctx=ctx, cwd=str(tmp_path))
    assert result.success
    assert set(result.result.keys()) == {"exit_code", "stdout", "stderr", "truncated"}
    assert result.result["exit_code"] == 0
    assert result.error is None

  @pytest.mark.asyncio
  async def test_stderr_separate_from_stdout(self, tmp_path: Path) -> None:
    """stdout and stderr are reported independently."""
    _write_makefile(
      tmp_path,
      "check:\n\t@echo OUT\n\t@echo ERR 1>&2\n",
    )
    spec = _make_spec()
    ctx = _make_context()
    result = await spec.execute(target="check", ctx=ctx, cwd=str(tmp_path))
    assert result.success
    assert "OUT" in result.result["stdout"]
    assert "ERR" in result.result["stderr"]
    assert "OUT" not in result.result["stderr"]
    assert "ERR" not in result.result["stdout"]


class TestMakeToolSubprocessSecurity:
  """No shell=True; command is a list of strings."""

  @pytest.mark.asyncio
  async def test_command_is_list_not_shell(self, tmp_path: Path, mocker: MockerFixture) -> None:
    """Popen is called with a list argv, no shell=True."""
    _write_makefile(tmp_path, "check:\n\t@echo ok\n")
    popen = mocker.patch.object(make_module.subprocess, "Popen")
    # Make communicate a sync callable that returns (stdout, stderr)
    popen.return_value.communicate = mocker.MagicMock(return_value=("ok\n", ""))
    popen.return_value.returncode = 0
    popen.return_value.pid = 12345

    spec = _make_spec()
    ctx = _make_context()
    await spec.execute(target="check", ctx=ctx, cwd=str(tmp_path))

    _args, kwargs = popen.call_args
    # First positional arg is the command list
    cmd = _args[0]
    assert isinstance(cmd, list)
    assert all(isinstance(item, str) for item in cmd)
    assert cmd == ["make", "check"]
    assert kwargs.get("shell") is not True
    assert kwargs.get("start_new_session") is True


class TestMakeToolIntegrationEndToEnd:
  """End-to-end: make check and make test against a real Makefile."""

  @pytest.fixture
  def makefile_dir(self, tmp_path: Path) -> Path:
    _write_makefile(
      tmp_path,
      "check:\n\t@echo running-check\n\ntest:\n\t@echo running-test TARGET=$(TARGET)\n",
    )
    return tmp_path

  @pytest.mark.asyncio
  async def test_make_check_end_to_end(self, makefile_dir: Path) -> None:
    spec = _make_spec()
    ctx = _make_context()
    result = await spec.execute(target="check", ctx=ctx, cwd=str(makefile_dir))
    assert result.success
    assert "running-check" in result.result["stdout"]

  @pytest.mark.asyncio
  async def test_make_test_with_env_end_to_end(self, makefile_dir: Path) -> None:
    config = MakeToolConfig(allowed_env_vars={"test": ("TARGET",)})
    spec = _make_spec()
    ctx = _make_context(config=config)
    result = await spec.execute(
      target="test",
      ctx=ctx,
      cwd=str(makefile_dir),
      env_vars={"TARGET": "tests/test_foo.py"},
    )
    assert result.success
    assert "tests/test_foo.py" in result.result["stdout"]
