"""Tests for the github tool implementation.

Verifies the operation enum + allowlist (the subcommand-blocking security
boundary), per-parameter validation, the make.py-style subprocess pattern
(Popen + start_new_session + os.killpg on timeout), output redaction,
truncation, the Windows platform gate, and the flat ``content_metadata``
shape consumed by ``core/_processing.py``.
"""

import subprocess
import sys
from typing import Any

import pytest
from pytest_mock import MockerFixture

from yoker.builtin import github
from yoker.config import GitHubToolConfig, ToolsSharedConfig
from yoker.exceptions import ValidationError
from yoker.tools import ToolRegistry
from yoker.tools.context import ToolContext

github_module = sys.modules["yoker.builtin.github"]


def _register():
  """Register the github tool and return its spec."""
  registry = ToolRegistry()
  return registry.register(github, name="github")


def _ctx(config: GitHubToolConfig | None = None) -> ToolContext:
  return ToolContext(
    config=config or GitHubToolConfig(),
    shared=ToolsSharedConfig(),
    backends={},
  )


def _mock_popen(
  mocker: MockerFixture,
  stdout: str = "",
  stderr: str = "",
  returncode: int = 0,
  pid: int = 12345,
  timeout: bool = False,
) -> Any:
  """Patch subprocess.Popen to a controllable mock. Returns the popen mock."""
  popen = mocker.patch.object(github_module.subprocess, "Popen")
  proc = popen.return_value
  proc.pid = pid
  proc.returncode = returncode
  if timeout:
    proc.communicate.side_effect = subprocess.TimeoutExpired(cmd=["gh"], timeout=1)
  else:
    proc.communicate.return_value = (stdout, stderr)
  return popen


# POSIX-only: the github tool uses os.killpg + SIGKILL + start_new_session
# to enforce the process-group-kill invariant on timeout. The Windows path
# is covered by TestWindowsPlatformGate below.
pytestmark = pytest.mark.skipif(
  sys.platform == "win32",
  reason="github tool requires POSIX process-group support",
)


class TestGithubSchema:
  """Schema and registration tests."""

  def test_name(self) -> None:
    assert _register().name == "github"

  def test_description_present(self) -> None:
    spec = _register()
    assert spec.description
    assert "github" in spec.description.lower() or "GitHub" in spec.description

  def test_operation_required(self) -> None:
    spec = _register()
    required = spec.schema["function"]["parameters"]["required"]
    assert "operation" in required
    assert "ctx" not in required  # injected
    assert "repo" not in required
    assert "number" not in required


class TestGithubOperations:
  """Each of the 9 operations builds the expected gh argv list."""

  @pytest.mark.asyncio
  async def test_repo_view(self, mocker: MockerFixture) -> None:
    popen = _mock_popen(mocker, stdout='{"name":"r"}')
    await github(operation="repo_view", ctx=_ctx())
    cmd = popen.call_args.args[0]
    assert cmd[:3] == ["gh", "repo", "view"]
    assert "--json" in cmd
    assert any("name,owner,description" in c for c in cmd)

  @pytest.mark.asyncio
  async def test_issue_list_with_filters(self, mocker: MockerFixture) -> None:
    popen = _mock_popen(mocker, stdout="[]")
    await github(
      operation="issue_list", ctx=_ctx(), repo="owner/repo", state="closed", label="bug", limit=5
    )
    cmd = popen.call_args.args[0]
    assert cmd[:3] == ["gh", "issue", "list"]
    assert "--repo" in cmd and "owner/repo" in cmd
    assert "--state" in cmd and "closed" in cmd
    assert "--label" in cmd and "bug" in cmd
    assert "--limit" in cmd and "5" in cmd
    assert "--json" in cmd

  @pytest.mark.asyncio
  async def test_issue_view_with_number(self, mocker: MockerFixture) -> None:
    popen = _mock_popen(mocker, stdout='{"number":123}')
    await github(operation="issue_view", ctx=_ctx(), repo="owner/repo", number=123)
    cmd = popen.call_args.args[0]
    assert cmd[:3] == ["gh", "issue", "view"]
    # -- separator before the user-supplied positional
    assert "--" in cmd
    idx = cmd.index("--")
    assert cmd[idx + 1] == "123"

  @pytest.mark.asyncio
  async def test_pr_list(self, mocker: MockerFixture) -> None:
    popen = _mock_popen(mocker, stdout="[]")
    await github(operation="pr_list", ctx=_ctx(), repo="owner/repo")
    cmd = popen.call_args.args[0]
    assert cmd[:3] == ["gh", "pr", "list"]
    assert "--state" in cmd  # pr_list accepts --state

  @pytest.mark.asyncio
  async def test_pr_list_json_includes_review_decision_and_ci_status(self, mocker: MockerFixture) -> None:
    """pr_list --json fields must include reviewDecision and statusCheckRollup."""
    popen = _mock_popen(mocker, stdout="[]")
    await github(operation="pr_list", ctx=_ctx(), repo="owner/repo")
    cmd = popen.call_args.args[0]
    json_idx = cmd.index("--json")
    fields = cmd[json_idx + 1]
    assert "reviewDecision" in fields
    assert "statusCheckRollup" in fields

  @pytest.mark.asyncio
  async def test_pr_view_json_includes_review_decision_and_ci_status(self, mocker: MockerFixture) -> None:
    """pr_view --json fields must include reviewDecision and statusCheckRollup."""
    popen = _mock_popen(mocker, stdout='{"number":42}')
    await github(operation="pr_view", ctx=_ctx(), number=42, repo="owner/repo")
    cmd = popen.call_args.args[0]
    json_idx = cmd.index("--json")
    fields = cmd[json_idx + 1]
    assert "reviewDecision" in fields
    assert "statusCheckRollup" in fields

  @pytest.mark.asyncio
  async def test_issue_list_json_includes_labels(self, mocker: MockerFixture) -> None:
    """issue_list --json fields must include labels."""
    popen = _mock_popen(mocker, stdout="[]")
    await github(operation="issue_list", ctx=_ctx(), repo="owner/repo")
    cmd = popen.call_args.args[0]
    json_idx = cmd.index("--json")
    fields = cmd[json_idx + 1]
    assert "labels" in fields

  @pytest.mark.asyncio
  async def test_pr_view(self, mocker: MockerFixture) -> None:
    popen = _mock_popen(mocker, stdout='{"number":42}')
    await github(operation="pr_view", ctx=_ctx(), number=42, repo="owner/repo")
    cmd = popen.call_args.args[0]
    assert cmd[:3] == ["gh", "pr", "view"]
    assert "--" in cmd
    assert "42" in cmd

  @pytest.mark.asyncio
  async def test_workflow_list(self, mocker: MockerFixture) -> None:
    popen = _mock_popen(mocker, stdout="[]")
    await github(operation="workflow_list", ctx=_ctx(), repo="owner/repo")
    cmd = popen.call_args.args[0]
    assert cmd[:3] == ["gh", "run", "list"]
    # workflow_list does NOT accept --state
    assert "--state" not in cmd

  @pytest.mark.asyncio
  async def test_workflow_view(self, mocker: MockerFixture) -> None:
    popen = _mock_popen(mocker, stdout='{"databaseId":99}')
    await github(operation="workflow_view", ctx=_ctx(), number=99, repo="owner/repo")
    cmd = popen.call_args.args[0]
    assert cmd[:3] == ["gh", "run", "view"]
    assert "--" in cmd and "99" in cmd

  @pytest.mark.asyncio
  async def test_release_list(self, mocker: MockerFixture) -> None:
    popen = _mock_popen(mocker, stdout="[]")
    await github(operation="release_list", ctx=_ctx(), repo="owner/repo")
    cmd = popen.call_args.args[0]
    assert cmd[:3] == ["gh", "release", "list"]

  @pytest.mark.asyncio
  async def test_release_view_with_tag(self, mocker: MockerFixture) -> None:
    popen = _mock_popen(mocker, stdout='{"tagName":"v1.0"}')
    await github(operation="release_view", ctx=_ctx(), tag="v1.0.0", repo="owner/repo")
    cmd = popen.call_args.args[0]
    assert cmd[:3] == ["gh", "release", "view"]
    assert "--" in cmd
    idx = cmd.index("--")
    assert cmd[idx + 1] == "v1.0.0"

  @pytest.mark.asyncio
  async def test_repo_auto_detect_when_empty(self, mocker: MockerFixture) -> None:
    """When repo is empty, --repo is omitted (gh auto-detects from git remote)."""
    popen = _mock_popen(mocker, stdout="{}")
    await github(operation="repo_view", ctx=_ctx())
    cmd = popen.call_args.args[0]
    assert "--repo" not in cmd


class TestGithubOperationAllowlist:
  """Operation enum + allowlist (the security boundary)."""

  @pytest.mark.asyncio
  async def test_unknown_operation_rejected(self, mocker: MockerFixture) -> None:
    _mock_popen(mocker)
    result = await github(operation="gh_api_bypass", ctx=_ctx())
    assert not result.success
    assert "Unknown operation" in result.error

  @pytest.mark.asyncio
  async def test_operation_not_in_allowlist_rejected(self, mocker: MockerFixture) -> None:
    _mock_popen(mocker)
    cfg = GitHubToolConfig(allowed_operations=("repo_view",))
    result = await github(operation="issue_list", ctx=_ctx(cfg))
    assert not result.success
    assert "not allowed" in result.error.lower()

  @pytest.mark.asyncio
  async def test_non_string_operation_rejected(self, mocker: MockerFixture) -> None:
    _mock_popen(mocker)
    result = await github(operation=123, ctx=_ctx())  # type: ignore[arg-type]
    assert not result.success

  @pytest.mark.asyncio
  async def test_default_allowlist_allows_all_nine(self, mocker: MockerFixture) -> None:
    _mock_popen(mocker, stdout="{}")
    cfg = GitHubToolConfig()
    for op in cfg.allowed_operations:
      _mock_popen(mocker, stdout="{}")
      kwargs: dict[str, Any] = {}
      if op in {"issue_view", "pr_view", "workflow_view"}:
        kwargs["number"] = 1
      if op == "release_view":
        kwargs["tag"] = "v1"
      result = await github(operation=op, ctx=_ctx(cfg), **kwargs)
      assert result.success, f"Default allowlist should permit {op}: {result.error}"

  @pytest.mark.asyncio
  async def test_empty_allowlist_blocks_all(self, mocker: MockerFixture) -> None:
    _mock_popen(mocker)
    cfg = GitHubToolConfig(allowed_operations=())
    result = await github(operation="repo_view", ctx=_ctx(cfg))
    assert not result.success

  @pytest.mark.asyncio
  async def test_disabled_tool_rejected(self, mocker: MockerFixture) -> None:
    _mock_popen(mocker)
    cfg = GitHubToolConfig(enabled=False)
    result = await github(operation="repo_view", ctx=_ctx(cfg))
    assert not result.success
    assert "disabled" in result.error.lower()

  @pytest.mark.asyncio
  async def test_invalid_config_type_rejected(self, mocker: MockerFixture) -> None:
    _mock_popen(mocker)
    bad_ctx = ToolContext(
      config=GitHubToolConfig(),  # will be re-typed below
      shared=ToolsSharedConfig(),
      backends={},
    )
    # Replace config with a wrong-type object
    object.__setattr__(bad_ctx, "config", "not a config")  # type: ignore[arg-type]
    result = await github(operation="repo_view", ctx=bad_ctx)
    assert not result.success
    assert "Invalid configuration" in result.error


class TestGithubParamValidation:
  """Per-parameter regex / enum / int validation."""

  @pytest.mark.asyncio
  async def test_invalid_repo_format_rejected(self, mocker: MockerFixture) -> None:
    _mock_popen(mocker)
    result = await github(operation="repo_view", ctx=_ctx(), repo="not-a-repo")
    assert not result.success
    assert "repo" in result.error.lower()

  @pytest.mark.asyncio
  async def test_repo_leading_dash_rejected(self, mocker: MockerFixture) -> None:
    _mock_popen(mocker)
    result = await github(operation="repo_view", ctx=_ctx(), repo="--jq=evil/x")
    assert not result.success
    assert "-" in result.error or "dash" in result.error.lower()

  @pytest.mark.asyncio
  async def test_repo_forbidden_char_rejected(self, mocker: MockerFixture) -> None:
    _mock_popen(mocker)
    result = await github(operation="repo_view", ctx=_ctx(), repo="owner/repo;rm -rf /")
    assert not result.success
    assert "forbidden" in result.error.lower() or "invalid" in result.error.lower()

  @pytest.mark.asyncio
  async def test_repo_too_long_rejected(self, mocker: MockerFixture) -> None:
    _mock_popen(mocker)
    result = await github(operation="repo_view", ctx=_ctx(), repo="a/" + "b" * 200)
    assert not result.success
    assert "exceeds" in result.error.lower()

  @pytest.mark.asyncio
  async def test_tag_leading_dash_rejected(self, mocker: MockerFixture) -> None:
    _mock_popen(mocker)
    result = await github(operation="release_view", ctx=_ctx(), tag="--evil")
    assert not result.success
    assert "-" in result.error or "dash" in result.error.lower()

  @pytest.mark.asyncio
  async def test_tag_forbidden_char_rejected(self, mocker: MockerFixture) -> None:
    _mock_popen(mocker)
    result = await github(operation="release_view", ctx=_ctx(), tag="v1.0;cat /etc/passwd")
    assert not result.success

  @pytest.mark.asyncio
  async def test_label_leading_dash_rejected(self, mocker: MockerFixture) -> None:
    _mock_popen(mocker)
    result = await github(operation="issue_list", ctx=_ctx(), label="--evil")
    assert not result.success
    assert "-" in result.error or "dash" in result.error.lower()

  @pytest.mark.asyncio
  async def test_label_newline_rejected(self, mocker: MockerFixture) -> None:
    _mock_popen(mocker)
    result = await github(operation="issue_list", ctx=_ctx(), label="bug\nrm -rf /")
    assert not result.success

  @pytest.mark.asyncio
  async def test_invalid_state_rejected(self, mocker: MockerFixture) -> None:
    _mock_popen(mocker)
    result = await github(operation="issue_list", ctx=_ctx(), state="merged")
    assert not result.success
    assert "state" in result.error.lower()

  @pytest.mark.asyncio
  async def test_invalid_limit_rejected(self, mocker: MockerFixture) -> None:
    _mock_popen(mocker)
    result = await github(operation="issue_list", ctx=_ctx(), limit=0)
    assert not result.success
    assert "limit" in result.error.lower()

  @pytest.mark.asyncio
  async def test_limit_clamped_to_max_results(self, mocker: MockerFixture) -> None:
    popen = _mock_popen(mocker, stdout="[]")
    cfg = GitHubToolConfig(max_results=50)
    await github(operation="issue_list", ctx=_ctx(cfg), limit=999)
    cmd = popen.call_args.args[0]
    idx = cmd.index("--limit")
    assert cmd[idx + 1] == "50"

  @pytest.mark.asyncio
  async def test_number_zero_rejected(self, mocker: MockerFixture) -> None:
    _mock_popen(mocker)
    result = await github(operation="issue_view", ctx=_ctx(), number=0)
    assert not result.success

  @pytest.mark.asyncio
  async def test_missing_number_for_view_rejected(self, mocker: MockerFixture) -> None:
    _mock_popen(mocker)
    result = await github(operation="issue_view", ctx=_ctx())
    assert not result.success
    assert "number" in result.error.lower()

  @pytest.mark.asyncio
  async def test_missing_tag_for_release_view_rejected(self, mocker: MockerFixture) -> None:
    _mock_popen(mocker)
    result = await github(operation="release_view", ctx=_ctx())
    assert not result.success
    assert "tag" in result.error.lower()

  @pytest.mark.asyncio
  async def test_require_explicit_repo_enforced(self, mocker: MockerFixture) -> None:
    _mock_popen(mocker)
    cfg = GitHubToolConfig(require_explicit_repo=True)
    result = await github(operation="repo_view", ctx=_ctx(cfg))
    assert not result.success
    assert "repo" in result.error.lower()


class TestGithubTimeout:
  """R4: timeout enforced and process group killed (make.py pattern)."""

  @pytest.mark.asyncio
  async def test_timeout_returns_failure(self, mocker: MockerFixture) -> None:
    _mock_popen(mocker, timeout=True)
    killpg = mocker.patch.object(github_module.os, "killpg")
    cfg = GitHubToolConfig(timeout_ms=1000)
    result = await github(operation="repo_view", ctx=_ctx(cfg), timeout_ms=1000)
    assert not result.success
    assert "timed out" in result.error.lower()
    assert "1000" in result.error
    assert killpg.called
    _args, _kwargs = killpg.call_args
    assert _args[1] == github_module.signal.SIGKILL

  @pytest.mark.asyncio
  async def test_timeout_clamped_to_config_ceiling(self, mocker: MockerFixture) -> None:
    _mock_popen(mocker, timeout=True)
    cfg = GitHubToolConfig(timeout_ms=1000)
    result = await github(operation="repo_view", ctx=_ctx(cfg), timeout_ms=60000)
    assert not result.success
    # Error mentions the clamped value (1000), not 60000.
    assert "1000" in result.error


class TestGithubOutputRedaction:
  """Credential patterns are redacted before truncation and return."""

  @pytest.mark.asyncio
  async def test_ghp_token_redacted_in_stderr(self, mocker: MockerFixture) -> None:
    token = "ghp_" + "a" * 36
    _mock_popen(mocker, stdout="{}", stderr=f"err {token} here", returncode=1)
    result = await github(operation="repo_view", ctx=_ctx())
    assert not result.success
    assert token not in result.error
    assert "<redacted>" in result.error

  @pytest.mark.asyncio
  async def test_url_creds_redacted_in_stdout(self, mocker: MockerFixture) -> None:
    _mock_popen(mocker, stdout='{"url":"https://user:secretpw@host/path"}', returncode=0)
    result = await github(operation="repo_view", ctx=_ctx())
    assert result.success
    assert "secretpw" not in result.result
    assert "<redacted>" in result.result

  @pytest.mark.asyncio
  async def test_aws_key_id_redacted(self, mocker: MockerFixture) -> None:
    _mock_popen(mocker, stdout="AKIAIOSFODNN7EXAMPLE", returncode=0)
    result = await github(operation="repo_view", ctx=_ctx())
    assert result.success
    assert "AKIAIOSFODNN7EXAMPLE" not in result.result


class TestGithubOutputTruncation:
  """Per-stream truncation at max_output_kb * 1024 bytes."""

  @pytest.mark.asyncio
  async def test_stdout_truncated_when_over_limit(self, mocker: MockerFixture) -> None:
    big = "x" * (150 * 1024)
    _mock_popen(mocker, stdout=big, returncode=0)
    cfg = GitHubToolConfig(max_output_kb=100)
    result = await github(operation="repo_view", ctx=_ctx(cfg))
    assert result.success
    md = result.content_metadata
    assert md["metadata"]["truncated"] is True
    assert "[truncated]" in md["content"]
    assert len(md["content"].encode("utf-8")) <= 100 * 1024 + len("\n... [truncated]\n") + 4

  @pytest.mark.asyncio
  async def test_small_output_not_truncated(self, mocker: MockerFixture) -> None:
    _mock_popen(mocker, stdout='{"name":"r"}', returncode=0)
    result = await github(operation="repo_view", ctx=_ctx())
    assert result.success
    assert result.content_metadata["metadata"]["truncated"] is False


class TestGithubResultShape:
  """Flat content_metadata shape consumed by core/_processing.py."""

  @pytest.mark.asyncio
  async def test_flat_content_metadata_keys(self, mocker: MockerFixture) -> None:
    _mock_popen(mocker, stdout='{"name":"r"}', returncode=0)
    result = await github(operation="repo_view", ctx=_ctx(), repo="owner/repo")
    assert result.success
    md = result.content_metadata
    assert set(md.keys()) == {"operation", "path", "content_type", "content", "metadata"}
    assert md["operation"] == "github"
    assert md["path"] == "owner/repo"
    assert md["content_type"] == "application/json"
    assert md["content"] == '{"name":"r"}'
    inner = md["metadata"]
    assert inner["returncode"] == 0
    assert inner["truncated"] is False
    assert inner["repo"] == "owner/repo"
    assert "gh_subcommand" in inner

  @pytest.mark.asyncio
  async def test_path_defaults_when_repo_empty(self, mocker: MockerFixture) -> None:
    _mock_popen(mocker, stdout="{}", returncode=0)
    result = await github(operation="repo_view", ctx=_ctx())
    assert result.content_metadata["path"] == "default"

  @pytest.mark.asyncio
  async def test_error_result_has_no_metadata(self, mocker: MockerFixture) -> None:
    _mock_popen(mocker, stderr="not found", returncode=1)
    result = await github(operation="repo_view", ctx=_ctx(), repo="owner/repo")
    assert not result.success
    assert result.content_metadata is None


class TestGithubErrorMapping:
  """gh failure modes → friendly, sanitized messages."""

  @pytest.mark.asyncio
  async def test_gh_not_installed(self, mocker: MockerFixture) -> None:
    mocker.patch.object(github_module.subprocess, "Popen", side_effect=FileNotFoundError())
    result = await github(operation="repo_view", ctx=_ctx())
    assert not result.success
    assert "not found" in result.error.lower()
    assert "cli.github.com" in result.error

  @pytest.mark.asyncio
  async def test_not_authenticated(self, mocker: MockerFixture) -> None:
    _mock_popen(mocker, stderr="You are not logged in", returncode=1)
    result = await github(operation="repo_view", ctx=_ctx())
    assert not result.success
    assert "authenticated" in result.error.lower()

  @pytest.mark.asyncio
  async def test_rate_limited(self, mocker: MockerFixture) -> None:
    _mock_popen(mocker, stderr="API rate limit exceeded", returncode=1)
    result = await github(operation="repo_view", ctx=_ctx())
    assert not result.success
    assert "rate limit" in result.error.lower()

  @pytest.mark.asyncio
  async def test_repo_not_found(self, mocker: MockerFixture) -> None:
    _mock_popen(mocker, stderr="could not resolve to a Repository", returncode=1)
    result = await github(operation="repo_view", ctx=_ctx(), repo="owner/missing")
    assert not result.success
    assert "not found" in result.error.lower()

  @pytest.mark.asyncio
  async def test_issue_not_found(self, mocker: MockerFixture) -> None:
    _mock_popen(mocker, stderr="no issue found", returncode=1)
    result = await github(operation="issue_view", ctx=_ctx(), number=999, repo="owner/repo")
    assert not result.success
    assert "not found" in result.error.lower()


class TestGithubSubprocessSecurity:
  """No shell=True; command is a list of strings; start_new_session set."""

  @pytest.mark.asyncio
  async def test_command_is_list_no_shell(self, mocker: MockerFixture) -> None:
    popen = _mock_popen(mocker, stdout="{}", returncode=0)
    await github(operation="repo_view", ctx=_ctx())
    _args, kwargs = popen.call_args
    cmd = _args[0]
    assert isinstance(cmd, list)
    assert all(isinstance(item, str) for item in cmd)
    assert cmd[0] == "gh"
    assert kwargs.get("shell") is not True
    assert kwargs.get("start_new_session") is True

  @pytest.mark.asyncio
  async def test_no_env_passthrough(self, mocker: MockerFixture) -> None:
    """The agent cannot inject env vars; only os.environ is inherited."""
    popen = _mock_popen(mocker, stdout="{}", returncode=0)
    await github(operation="repo_view", ctx=_ctx())
    _args, kwargs = popen.call_args
    # env is os.environ (no agent-supplied additions).
    assert kwargs.get("env") is github_module.os.environ


class TestGithubConfigValidation:
  """GitHubToolConfig validates allowed_operations against the enum."""

  def test_unknown_operation_in_allowlist_raises(self) -> None:
    with pytest.raises(ValidationError):
      GitHubToolConfig(allowed_operations=("repo_view", "bogus_op"))

  def test_default_allowlist_has_nine_ops(self) -> None:
    cfg = GitHubToolConfig()
    assert len(cfg.allowed_operations) == 9

  def test_invalid_timeout_raises(self) -> None:
    with pytest.raises(ValidationError):
      GitHubToolConfig(timeout_ms=0)

  def test_invalid_max_results_raises(self) -> None:
    with pytest.raises(ValidationError):
      GitHubToolConfig(max_results=-1)

  def test_invalid_max_output_kb_raises(self) -> None:
    with pytest.raises(ValidationError):
      GitHubToolConfig(max_output_kb=0)

  def test_empty_allowlist_valid(self) -> None:
    # Empty list is valid (tool effectively disabled via config).
    cfg = GitHubToolConfig(allowed_operations=())
    assert cfg.allowed_operations == ()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only platform gate test")
class TestWindowsPlatformGate:
  """The github tool refuses to run on Windows with a clear error."""

  @pytest.mark.asyncio
  async def test_github_rejected_on_windows(self, mocker: MockerFixture) -> None:
    # Popen must NOT be invoked on Windows.
    popen = mocker.patch.object(github_module.subprocess, "Popen")
    result = await github(operation="repo_view", ctx=_ctx())
    assert not result.success
    assert "not available on Windows" in result.error
    assert not popen.called
