"""Tests for the github tool implementation.

Verifies the operation enum + allowlist (the subcommand-blocking security
boundary), per-parameter validation, the make.py-style subprocess pattern
(Popen + start_new_session + os.killpg on timeout), output redaction,
truncation, the Windows platform gate, and the flat ``content_metadata``
shape consumed by ``core/_processing.py``.
"""

import asyncio
import json
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


async def _async_return(value: Any) -> Any:
  return value


def _mock_popen(
  mocker: MockerFixture,
  stdout: str = "",
  stderr: str = "",
  returncode: int = 0,
  pid: int = 12345,
  timeout: bool = False,
) -> Any:
  """Patch asyncio.create_subprocess_exec to a controllable mock. Returns the mock.

  The mock captures the command as a list in ``call_args.args[0]`` so tests
  can inspect it the same way they did with ``subprocess.Popen``.
  """
  proc = mocker.MagicMock()
  proc.pid = pid
  proc.returncode = returncode
  if timeout:
    proc.communicate = mocker.AsyncMock(side_effect=asyncio.TimeoutError())
  else:
    proc.communicate = mocker.AsyncMock(
      return_value=(stdout.encode("utf-8"), stderr.encode("utf-8"))
    )

  # Wrap so call_args.args[0] is the command list (matching old Popen interface)
  original_mock = mocker.patch.object(github_module.asyncio, "create_subprocess_exec")
  original_mock.side_effect = lambda *args, **kwargs: proc
  # Override call_args to present args as a single list (first positional)
  original_mock.call_args = None  # will be set after first call

  # Use a wrapper to track calls in list form
  calls: list = []
  real_side = original_mock.side_effect

  def wrapped(*args: Any, **kwargs: Any) -> Any:
    calls.append(mocker.call(list(args), **kwargs))
    original_mock.call_args = calls[-1]
    original_mock.call_args_list = calls
    return real_side(*args, **kwargs)

  original_mock.side_effect = wrapped
  return original_mock


def _track_gh_calls(mocker: MockerFixture) -> list[list[str]]:
  """Patch create_subprocess_exec with a per-call mock that records commands.

  Unlike ``_mock_popen`` (whose ``call_args_list`` is unreliable in this
  file), this helper appends each command list to the returned list and
  always returns a successful process with the standard issue-view JSON on
  stdout. Use ``seen_cmds[0]``, ``seen_cmds[1]`` etc. to assert per-step
  commands of multi-step operations (issue_edit, pr_comments, pr_draft).
  """
  seen_cmds: list[list[str]] = []

  def side_effect(*args: Any, **kwargs: Any) -> Any:
    seen_cmds.append(list(args))
    proc = mocker.MagicMock()
    proc.pid = 12345
    proc.returncode = 0
    proc.communicate = mocker.AsyncMock(return_value=(b'{"number": 42, "state": "open"}', b""))
    return proc

  mocker.patch.object(github_module.asyncio, "create_subprocess_exec", side_effect=side_effect)
  return seen_cmds


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
  async def test_issue_list_defaults_to_open_state(self, mocker: MockerFixture) -> None:
    """Omitting state applies the "open" list default (gh issue list default)."""
    popen = _mock_popen(mocker, stdout="[]")
    await github(operation="issue_list", ctx=_ctx(), repo="owner/repo")
    cmd = popen.call_args.args[0]
    assert "--state" in cmd and "open" in cmd

  @pytest.mark.asyncio
  async def test_issue_list_explicit_open_state(self, mocker: MockerFixture) -> None:
    """state="open" explicitly requested behaves identically to the default."""
    popen = _mock_popen(mocker, stdout="[]")
    await github(operation="issue_list", ctx=_ctx(), repo="owner/repo", state="open")
    cmd = popen.call_args.args[0]
    assert "--state" in cmd and "open" in cmd

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
  async def test_pr_list_json_includes_review_decision_and_ci_status(
    self, mocker: MockerFixture
  ) -> None:
    """pr_list --json fields must include reviewDecision and statusCheckRollup."""
    popen = _mock_popen(mocker, stdout="[]")
    await github(operation="pr_list", ctx=_ctx(), repo="owner/repo")
    cmd = popen.call_args.args[0]
    json_idx = cmd.index("--json")
    fields = cmd[json_idx + 1]
    assert "reviewDecision" in fields
    assert "statusCheckRollup" in fields

  @pytest.mark.asyncio
  async def test_pr_view_json_includes_review_decision_and_ci_status(
    self, mocker: MockerFixture
  ) -> None:
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
  async def test_workflow_logs(self, mocker: MockerFixture) -> None:
    popen = _mock_popen(mocker, stdout="some log output")
    await github(operation="workflow_logs", ctx=_ctx(), number=99, repo="owner/repo")
    cmd = popen.call_args.args[0]
    assert cmd[:4] == ["gh", "run", "view", "--log-failed"]
    assert "--json" not in cmd
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

  @pytest.mark.asyncio
  async def test_pr_reviews(self, mocker: MockerFixture) -> None:
    """pr_reviews uses gh api with the reviews endpoint."""
    popen = _mock_popen(mocker, stdout="[]")
    await github(operation="pr_reviews", ctx=_ctx(), repo="owner/repo", number=42)
    cmd = popen.call_args.args[0]
    assert cmd[:3] == ["gh", "api", "repos/owner/repo/pulls/42/reviews"]
    assert "--jq" in cmd
    assert "--json" not in cmd

  @pytest.mark.asyncio
  async def test_pr_comments(self, mocker: MockerFixture) -> None:
    """pr_comments uses gh api to fetch both issues and pulls comments endpoints."""
    proc = mocker.MagicMock()
    proc.pid = 12345
    proc.returncode = 0
    proc.communicate = mocker.AsyncMock(return_value=(b"[]", b""))
    captured_calls: list[Any] = []

    def _create(*args: Any, **kwargs: Any) -> Any:
      captured_calls.append(mocker.call(list(args), **kwargs))
      return proc

    mocker.patch.object(github_module.asyncio, "create_subprocess_exec", side_effect=_create)
    result = await github(operation="pr_comments", ctx=_ctx(), repo="owner/repo", number=42)
    assert result.success
    # Should make two API calls: one to issues comments, one to pulls comments
    assert len(captured_calls) == 2, f"Expected 2 calls, got {len(captured_calls)}"
    cmd1 = captured_calls[0].args[0]
    cmd2 = captured_calls[1].args[0]
    assert cmd1[:4] == ["gh", "api", "repos/owner/repo/issues/42/comments", "--jq"]
    assert cmd2[:4] == ["gh", "api", "repos/owner/repo/pulls/42/comments", "--jq"]

  @pytest.mark.asyncio
  async def test_pr_comments_merges_both_types(self, mocker: MockerFixture) -> None:
    """pr_comments returns both conversation and review comments with type tags."""
    conv_json = '[{"id": 1, "body": "plan approved", "user": "owner", "created_at": "2024-01-01"}]'
    review_json = '[{"id": 2, "body": "nit: typo", "user": "reviewer", "path": "x.py", "line": 5, "created_at": "2024-01-02"}]'
    call_count = 0

    def side_effect(*args: Any, **kwargs: Any) -> Any:
      nonlocal call_count
      call_count += 1
      proc = mocker.MagicMock()
      proc.pid = 12345
      proc.returncode = 0
      if call_count == 1:
        proc.communicate = mocker.AsyncMock(return_value=(conv_json.encode("utf-8"), b""))
      else:
        proc.communicate = mocker.AsyncMock(return_value=(review_json.encode("utf-8"), b""))
      return proc

    mocker.patch.object(github_module.asyncio, "create_subprocess_exec", side_effect=side_effect)
    result = await github(operation="pr_comments", ctx=_ctx(), repo="owner/repo", number=42)
    assert result.success
    import json as json_mod

    comments = json_mod.loads(result.result)
    assert len(comments) == 2
    types = {c["type"] for c in comments}
    assert "conversation" in types
    assert "review" in types
    # Conversation comment should not have path/line
    conv = [c for c in comments if c["type"] == "conversation"][0]
    assert conv["body"] == "plan approved"
    # Review comment should have path/line
    rev = [c for c in comments if c["type"] == "review"][0]
    assert rev["body"] == "nit: typo"
    assert rev["path"] == "x.py"

  @pytest.mark.asyncio
  async def test_pr_comments_empty_returns_empty_array(self, mocker: MockerFixture) -> None:
    """pr_comments with no comments on either endpoint returns empty array."""
    proc = mocker.MagicMock()
    proc.pid = 12345
    proc.returncode = 0
    proc.communicate = mocker.AsyncMock(return_value=(b"[]", b""))
    mocker.patch.object(github_module.asyncio, "create_subprocess_exec", return_value=proc)
    result = await github(operation="pr_comments", ctx=_ctx(), repo="owner/repo", number=42)
    assert result.success
    assert result.result == "[]"

  @pytest.mark.asyncio
  async def test_pr_reviews_empty_array_returns_success(self, mocker: MockerFixture) -> None:
    """pr_reviews with no reviews returns success (empty array from API)."""
    _mock_popen(mocker, stdout="[]")
    result = await github(operation="pr_reviews", ctx=_ctx(), repo="owner/repo", number=42)
    assert result.success
    assert result.result == "[]"

  @pytest.mark.asyncio
  async def test_pr_reviews_requires_repo(self, mocker: MockerFixture) -> None:
    _mock_popen(mocker)
    result = await github(operation="pr_reviews", ctx=_ctx(), number=42)
    assert not result.success
    assert "repo" in result.error.lower()

  @pytest.mark.asyncio
  async def test_pr_comments_requires_repo(self, mocker: MockerFixture) -> None:
    _mock_popen(mocker)
    result = await github(operation="pr_comments", ctx=_ctx(), number=42)
    assert not result.success
    assert "repo" in result.error.lower()

  @pytest.mark.asyncio
  async def test_pr_reviews_requires_number(self, mocker: MockerFixture) -> None:
    _mock_popen(mocker)
    result = await github(operation="pr_reviews", ctx=_ctx(), repo="owner/repo")
    assert not result.success
    assert "number" in result.error.lower()

  @pytest.mark.asyncio
  async def test_pr_comments_requires_number(self, mocker: MockerFixture) -> None:
    _mock_popen(mocker)
    result = await github(operation="pr_comments", ctx=_ctx(), repo="owner/repo")
    assert not result.success
    assert "number" in result.error.lower()

  @pytest.mark.asyncio
  async def test_pr_view_with_include_comments(self, mocker: MockerFixture) -> None:
    """pr_view with include_comments=True fetches both conversation and review comments."""
    pr_json = '{"number": 42, "title": "Fix"}'
    conv_comments = '[{"id": 1, "body": "LGTM", "user": "alice", "created_at": "2024-01-01"}]'
    review_comments = '[{"id": 2, "body": "nit: fix typo", "user": "bob", "path": "src/x.py", "line": 5, "created_at": "2024-01-02"}]'
    proc1 = mocker.MagicMock()
    proc1.returncode = 0
    proc1.communicate = mocker.AsyncMock(return_value=(pr_json.encode("utf-8"), b""))
    proc2 = mocker.MagicMock()
    proc2.returncode = 0
    proc2.communicate = mocker.AsyncMock(return_value=(conv_comments.encode("utf-8"), b""))
    proc3 = mocker.MagicMock()
    proc3.returncode = 0
    proc3.communicate = mocker.AsyncMock(return_value=(review_comments.encode("utf-8"), b""))
    procs = [proc1, proc2, proc3]
    captured_calls: list[Any] = []

    def _create(*args: Any, **kwargs: Any) -> Any:
      captured_calls.append(mocker.call(list(args), **kwargs))
      return procs.pop(0)

    mocker.patch.object(github_module.asyncio, "create_subprocess_exec", side_effect=_create)
    result = await github(
      operation="pr_view", ctx=_ctx(), repo="owner/repo", number=42, include_comments=True
    )
    assert result.success
    import json as json_mod

    merged = json_mod.loads(result.result)
    assert merged["number"] == 42
    assert "comments" in merged
    # Should have both conversation and review comments
    comment_types = {c.get("type") for c in merged["comments"]}
    assert "conversation" in comment_types
    assert "review" in comment_types

  @pytest.mark.asyncio
  async def test_pr_view_without_include_comments_no_extra_call(
    self, mocker: MockerFixture
  ) -> None:
    """pr_view without include_comments does NOT make a second gh api call."""
    popen = _mock_popen(mocker, stdout='{"number": 42}')
    result = await github(
      operation="pr_view", ctx=_ctx(), repo="owner/repo", number=42, include_comments=False
    )
    assert result.success
    # Only one Popen call (the pr_view itself)
    assert popen.call_count == 1

  @pytest.mark.asyncio
  async def test_include_comments_rejected_for_non_pr_view(self, mocker: MockerFixture) -> None:
    _mock_popen(mocker)
    result = await github(
      operation="issue_view", ctx=_ctx(), repo="owner/repo", number=1, include_comments=True
    )
    assert not result.success
    assert "include_comments" in result.error


class TestGithubWriteOperations:
  """Tests for pr_create and release_create write operations."""

  @pytest.mark.asyncio
  async def test_pr_create_builds_correct_command(self, mocker: MockerFixture) -> None:
    """pr_create builds gh pr create with --title= and --body=, no --json."""
    popen = _mock_popen(mocker, stdout="https://github.com/owner/repo/pull/42")
    cfg = GitHubToolConfig(allowed_operations=("pr_create",))
    await github(
      operation="pr_create",
      ctx=_ctx(cfg),
      repo="owner/repo",
      title="Fix bug",
      body="This fixes the bug.",
    )
    cmd = popen.call_args.args[0]
    assert cmd[:3] == ["gh", "pr", "create"]
    assert "--repo" in cmd and "owner/repo" in cmd
    assert "--title=Fix bug" in cmd
    assert "--body=This fixes the bug." in cmd
    assert "--json" not in cmd

  @pytest.mark.asyncio
  async def test_pr_create_with_head_and_base(self, mocker: MockerFixture) -> None:
    """pr_create includes --head and --base when provided."""
    popen = _mock_popen(mocker, stdout="https://github.com/owner/repo/pull/42")
    cfg = GitHubToolConfig(allowed_operations=("pr_create",))
    await github(
      operation="pr_create",
      ctx=_ctx(cfg),
      repo="owner/repo",
      title="Fix",
      body="body",
      head="feature-branch",
      base="main",
    )
    cmd = popen.call_args.args[0]
    assert "--head=feature-branch" in cmd
    assert "--base=main" in cmd

  @pytest.mark.asyncio
  async def test_pr_create_without_head_base_omits_them(self, mocker: MockerFixture) -> None:
    """pr_create omits --head and --base when not provided (gh uses defaults)."""
    popen = _mock_popen(mocker, stdout="https://github.com/owner/repo/pull/42")
    cfg = GitHubToolConfig(allowed_operations=("pr_create",))
    await github(
      operation="pr_create",
      ctx=_ctx(cfg),
      repo="owner/repo",
      title="Fix",
      body="body",
    )
    cmd = popen.call_args.args[0]
    assert not any(c.startswith("--head=") for c in cmd)
    assert not any(c.startswith("--base=") for c in cmd)

  @pytest.mark.asyncio
  async def test_pr_create_not_in_default_allowlist(self, mocker: MockerFixture) -> None:
    """pr_create is rejected with default config (not in default allowlist)."""
    _mock_popen(mocker)
    result = await github(
      operation="pr_create",
      ctx=_ctx(),  # default config, no pr_create in allowed_operations
      repo="owner/repo",
      title="Fix",
      body="body",
    )
    assert not result.success
    assert "not allowed" in result.error.lower()

  @pytest.mark.asyncio
  async def test_pr_create_requires_repo(self, mocker: MockerFixture) -> None:
    """pr_create requires the repo parameter."""
    _mock_popen(mocker)
    cfg = GitHubToolConfig(allowed_operations=("pr_create",))
    result = await github(
      operation="pr_create",
      ctx=_ctx(cfg),
      title="Fix",
      body="body",
    )
    assert not result.success
    assert "repo" in result.error.lower()

  @pytest.mark.asyncio
  async def test_pr_create_requires_title(self, mocker: MockerFixture) -> None:
    """pr_create requires a non-empty title."""
    _mock_popen(mocker)
    cfg = GitHubToolConfig(allowed_operations=("pr_create",))
    result = await github(
      operation="pr_create",
      ctx=_ctx(cfg),
      repo="owner/repo",
      title="",
      body="body",
    )
    assert not result.success
    assert "title" in result.error.lower()

  @pytest.mark.asyncio
  async def test_pr_create_requires_body(self, mocker: MockerFixture) -> None:
    """pr_create requires a non-empty body."""
    _mock_popen(mocker)
    cfg = GitHubToolConfig(allowed_operations=("pr_create",))
    result = await github(
      operation="pr_create",
      ctx=_ctx(cfg),
      repo="owner/repo",
      title="Fix",
      body="",
    )
    assert not result.success
    assert "body" in result.error.lower()

  @pytest.mark.asyncio
  async def test_pr_create_rejects_nul_in_title(self, mocker: MockerFixture) -> None:
    """pr_create rejects NUL byte in title."""
    _mock_popen(mocker)
    cfg = GitHubToolConfig(allowed_operations=("pr_create",))
    result = await github(
      operation="pr_create",
      ctx=_ctx(cfg),
      repo="owner/repo",
      title="Fix\x00evil",
      body="body",
    )
    assert not result.success
    assert "forbidden" in result.error.lower()

  @pytest.mark.asyncio
  async def test_pr_create_allows_newlines_in_body(self, mocker: MockerFixture) -> None:
    """pr_create allows newlines in body (multi-line PR description)."""
    popen = _mock_popen(mocker, stdout='{"number": 42}')
    cfg = GitHubToolConfig(allowed_operations=("pr_create",))
    result = await github(
      operation="pr_create",
      ctx=_ctx(cfg),
      repo="owner/repo",
      title="Fix",
      body="Line 1\nLine 2\nLine 3",
    )
    assert result.success
    cmd = popen.call_args.args[0]
    body_arg = [c for c in cmd if c.startswith("--body=")][0]
    assert "\n" in body_arg

  @pytest.mark.asyncio
  async def test_pr_create_rejects_leading_dash_head(self, mocker: MockerFixture) -> None:
    """pr_create rejects head starting with dash (flag injection)."""
    _mock_popen(mocker)
    cfg = GitHubToolConfig(allowed_operations=("pr_create",))
    result = await github(
      operation="pr_create",
      ctx=_ctx(cfg),
      repo="owner/repo",
      title="Fix",
      body="body",
      head="--evil",
    )
    assert not result.success
    assert "dash" in result.error.lower() or "-" in result.error

  # --- pr_comment ---

  @pytest.mark.asyncio
  async def test_pr_comment_builds_correct_command(self, mocker: MockerFixture) -> None:
    """pr_comment builds gh pr comment <number> --body=..., no --json."""
    popen = _mock_popen(mocker, stdout="https://github.com/owner/repo/pull/42#issuecomment-123")
    cfg = GitHubToolConfig(allowed_operations=("pr_comment",))
    await github(
      operation="pr_comment",
      ctx=_ctx(cfg),
      number=42,
      body="LGTM!",
    )
    cmd = popen.call_args.args[0]
    assert cmd[:3] == ["gh", "pr", "comment"]
    assert "--body=LGTM!" in cmd
    assert "--json" not in cmd
    # The -- separator and positional number must come AFTER --body
    sep_idx = cmd.index("--")
    body_idx = cmd.index("--body=LGTM!")
    assert body_idx < sep_idx, "--body must come before -- separator"
    assert str(42) in cmd[sep_idx + 1 :], "number must come after -- separator"

  @pytest.mark.asyncio
  async def test_pr_comment_with_repo(self, mocker: MockerFixture) -> None:
    """pr_comment includes --repo when provided."""
    popen = _mock_popen(mocker, stdout="https://github.com/owner/repo/pull/42#issuecomment-123")
    cfg = GitHubToolConfig(allowed_operations=("pr_comment",))
    await github(
      operation="pr_comment",
      ctx=_ctx(cfg),
      repo="owner/repo",
      number=42,
      body="Comment",
    )
    cmd = popen.call_args.args[0]
    assert "--repo" in cmd and "owner/repo" in cmd

  @pytest.mark.asyncio
  async def test_pr_comment_not_in_default_allowlist(self, mocker: MockerFixture) -> None:
    """pr_comment is rejected with default config (not in default allowlist)."""
    _mock_popen(mocker)
    result = await github(
      operation="pr_comment",
      ctx=_ctx(),  # default config
      number=42,
      body="LGTM!",
    )
    assert not result.success
    assert "not allowed" in result.error.lower() or "allowed" in result.error.lower()

  @pytest.mark.asyncio
  async def test_pr_comment_requires_body(self, mocker: MockerFixture) -> None:
    """pr_comment requires a non-empty body."""
    _mock_popen(mocker)
    cfg = GitHubToolConfig(allowed_operations=("pr_comment",))
    result = await github(
      operation="pr_comment",
      ctx=_ctx(cfg),
      number=42,
      body="",
    )
    assert not result.success
    assert "body" in result.error.lower()

  @pytest.mark.asyncio
  async def test_pr_comment_requires_number(self, mocker: MockerFixture) -> None:
    """pr_comment requires a positive number."""
    _mock_popen(mocker)
    cfg = GitHubToolConfig(allowed_operations=("pr_comment",))
    result = await github(
      operation="pr_comment",
      ctx=_ctx(cfg),
      body="LGTM!",
    )
    assert not result.success
    assert "number" in result.error.lower()

  @pytest.mark.asyncio
  async def test_pr_comment_returns_success_with_url(self, mocker: MockerFixture) -> None:
    """pr_comment returns success with the comment URL."""
    url = "https://github.com/owner/repo/pull/42#issuecomment-123"
    _mock_popen(mocker, stdout=url)
    cfg = GitHubToolConfig(allowed_operations=("pr_comment",))
    result = await github(
      operation="pr_comment",
      ctx=_ctx(cfg),
      number=42,
      body="LGTM!",
    )
    assert result.success
    import json

    parsed = json.loads(result.result)
    assert parsed["url"] == url

  # --- issue_comment ---

  @pytest.mark.asyncio
  async def test_issue_comment_builds_correct_command(self, mocker: MockerFixture) -> None:
    """issue_comment builds gh issue comment <number> --body=..., no --json."""
    popen = _mock_popen(mocker, stdout="https://github.com/owner/repo/issues/7#issuecomment-456")
    cfg = GitHubToolConfig(allowed_operations=("issue_comment",))
    await github(
      operation="issue_comment",
      ctx=_ctx(cfg),
      number=7,
      body="Fixed in #42.",
    )
    cmd = popen.call_args.args[0]
    assert cmd[:3] == ["gh", "issue", "comment"]
    assert "--body=Fixed in #42." in cmd
    assert "--json" not in cmd
    # The -- separator and positional number must come AFTER --body
    sep_idx = cmd.index("--")
    body_idx = cmd.index("--body=Fixed in #42.")
    assert body_idx < sep_idx, "--body must come before -- separator"
    assert str(7) in cmd[sep_idx + 1 :], "number must come after -- separator"

  @pytest.mark.asyncio
  async def test_issue_comment_with_repo(self, mocker: MockerFixture) -> None:
    """issue_comment includes --repo when provided."""
    popen = _mock_popen(mocker, stdout="https://github.com/owner/repo/issues/7#issuecomment-456")
    cfg = GitHubToolConfig(allowed_operations=("issue_comment",))
    await github(
      operation="issue_comment",
      ctx=_ctx(cfg),
      repo="owner/repo",
      number=7,
      body="Comment",
    )
    cmd = popen.call_args.args[0]
    assert "--repo" in cmd and "owner/repo" in cmd

  @pytest.mark.asyncio
  async def test_issue_comment_not_in_default_allowlist(self, mocker: MockerFixture) -> None:
    """issue_comment is rejected with default config (not in default allowlist)."""
    _mock_popen(mocker)
    result = await github(
      operation="issue_comment",
      ctx=_ctx(),  # default config
      number=7,
      body="LGTM!",
    )
    assert not result.success
    assert "not allowed" in result.error.lower() or "allowed" in result.error.lower()

  @pytest.mark.asyncio
  async def test_issue_comment_requires_body(self, mocker: MockerFixture) -> None:
    """issue_comment requires a non-empty body."""
    _mock_popen(mocker)
    cfg = GitHubToolConfig(allowed_operations=("issue_comment",))
    result = await github(
      operation="issue_comment",
      ctx=_ctx(cfg),
      number=7,
      body="",
    )
    assert not result.success
    assert "body" in result.error.lower()

  @pytest.mark.asyncio
  async def test_issue_comment_requires_number(self, mocker: MockerFixture) -> None:
    """issue_comment requires a positive number."""
    _mock_popen(mocker)
    cfg = GitHubToolConfig(allowed_operations=("issue_comment",))
    result = await github(
      operation="issue_comment",
      ctx=_ctx(cfg),
      body="LGTM!",
    )
    assert not result.success
    assert "number" in result.error.lower()

  @pytest.mark.asyncio
  async def test_issue_comment_returns_success_with_url(self, mocker: MockerFixture) -> None:
    """issue_comment returns success with the comment URL."""
    url = "https://github.com/owner/repo/issues/7#issuecomment-456"
    _mock_popen(mocker, stdout=url)
    cfg = GitHubToolConfig(allowed_operations=("issue_comment",))
    result = await github(
      operation="issue_comment",
      ctx=_ctx(cfg),
      number=7,
      body="LGTM!",
    )
    assert result.success
    import json

    parsed = json.loads(result.result)
    assert parsed["url"] == url

  # --- pr_ready ---

  @pytest.mark.asyncio
  async def test_pr_ready_builds_correct_command(self, mocker: MockerFixture) -> None:
    """pr_ready builds gh pr ready <number>, no --json."""
    popen = _mock_popen(mocker, stdout="")
    cfg = GitHubToolConfig(allowed_operations=("pr_ready",))
    await github(
      operation="pr_ready",
      ctx=_ctx(cfg),
      number=42,
    )
    cmd = popen.call_args.args[0]
    assert cmd[:3] == ["gh", "pr", "ready"]
    assert "--json" not in cmd
    assert "--" in cmd
    assert "42" in cmd

  @pytest.mark.asyncio
  async def test_pr_ready_with_repo(self, mocker: MockerFixture) -> None:
    """pr_ready includes --repo when provided."""
    popen = _mock_popen(mocker, stdout="")
    cfg = GitHubToolConfig(allowed_operations=("pr_ready",))
    await github(
      operation="pr_ready",
      ctx=_ctx(cfg),
      repo="owner/repo",
      number=42,
    )
    cmd = popen.call_args.args[0]
    assert "--repo" in cmd and "owner/repo" in cmd

  @pytest.mark.asyncio
  async def test_pr_ready_not_in_default_allowlist(self, mocker: MockerFixture) -> None:
    """pr_ready is rejected with default config (not in default allowlist)."""
    _mock_popen(mocker)
    result = await github(
      operation="pr_ready",
      ctx=_ctx(),
      number=42,
    )
    assert not result.success
    assert "not allowed" in result.error.lower() or "allowed" in result.error.lower()

  @pytest.mark.asyncio
  async def test_pr_ready_requires_number(self, mocker: MockerFixture) -> None:
    """pr_ready requires a positive number."""
    _mock_popen(mocker)
    cfg = GitHubToolConfig(allowed_operations=("pr_ready",))
    result = await github(
      operation="pr_ready",
      ctx=_ctx(cfg),
    )
    assert not result.success
    assert "number" in result.error.lower()

  @pytest.mark.asyncio
  async def test_pr_ready_returns_success(self, mocker: MockerFixture) -> None:
    """pr_ready returns success with ready=true."""
    _mock_popen(mocker, stdout="")
    cfg = GitHubToolConfig(allowed_operations=("pr_ready",))
    result = await github(
      operation="pr_ready",
      ctx=_ctx(cfg),
      number=42,
    )
    assert result.success
    import json

    parsed = json.loads(result.result)
    assert parsed["ready"] is True

  # --- pr_create with draft ---

  @pytest.mark.asyncio
  async def test_pr_create_with_draft(self, mocker: MockerFixture) -> None:
    """pr_create includes --draft flag when draft=True."""
    popen = _mock_popen(mocker, stdout="https://github.com/owner/repo/pull/42")
    cfg = GitHubToolConfig(allowed_operations=("pr_create",))
    await github(
      operation="pr_create",
      ctx=_ctx(cfg),
      repo="owner/repo",
      title="Fix",
      body="body",
      draft=True,
    )
    cmd = popen.call_args.args[0]
    assert "--draft" in cmd

  @pytest.mark.asyncio
  async def test_pr_create_without_draft_omits_flag(self, mocker: MockerFixture) -> None:
    """pr_create omits --draft when draft=False (default)."""
    popen = _mock_popen(mocker, stdout="https://github.com/owner/repo/pull/42")
    cfg = GitHubToolConfig(allowed_operations=("pr_create",))
    await github(
      operation="pr_create",
      ctx=_ctx(cfg),
      repo="owner/repo",
      title="Fix",
      body="body",
    )
    cmd = popen.call_args.args[0]
    assert "--draft" not in cmd

  # --- pr_draft ---

  @pytest.mark.asyncio
  async def test_pr_draft_not_in_default_allowlist(self, mocker: MockerFixture) -> None:
    """pr_draft is rejected with default config (not in default allowlist)."""
    _mock_popen(mocker)
    result = await github(
      operation="pr_draft",
      ctx=_ctx(),
      number=42,
      repo="owner/repo",
    )
    assert not result.success
    assert "not allowed" in result.error.lower() or "allowed" in result.error.lower()

  @pytest.mark.asyncio
  async def test_pr_draft_requires_number(self, mocker: MockerFixture) -> None:
    """pr_draft requires a positive number."""
    _mock_popen(mocker)
    cfg = GitHubToolConfig(allowed_operations=("pr_draft",))
    result = await github(
      operation="pr_draft",
      ctx=_ctx(cfg),
      repo="owner/repo",
    )
    assert not result.success
    assert "number" in result.error.lower()

  @pytest.mark.asyncio
  async def test_pr_draft_requires_repo(self, mocker: MockerFixture) -> None:
    """pr_draft requires the repo parameter."""
    _mock_popen(mocker)
    cfg = GitHubToolConfig(allowed_operations=("pr_draft",))
    result = await github(
      operation="pr_draft",
      ctx=_ctx(cfg),
      number=42,
    )
    assert not result.success
    assert "repo" in result.error.lower()

  @pytest.mark.asyncio
  async def test_pr_draft_success(self, mocker: MockerFixture) -> None:
    """pr_draft succeeds with two-step API calls and returns draft=true."""
    # _convert_to_draft makes two gh api calls sequentially.
    # First: gh api repos/{repo}/pulls/{number} --jq .node_id → returns node_id
    # Second: gh api graphql -f query=... → returns GraphQL result
    call_count = 0

    def side_effect(*args: Any, **kwargs: Any) -> Any:
      nonlocal call_count
      call_count += 1
      proc = mocker.MagicMock()
      proc.pid = 12345
      proc.returncode = 0
      if call_count == 1:
        proc.communicate = mocker.AsyncMock(return_value=(b"PR_node_id_123", b""))
      else:
        proc.communicate = mocker.AsyncMock(
          return_value=(
            b'{"data":{"convertPullRequestToDraft":{"pullRequest":{"isDraft":true}}}}',
            b"",
          )
        )
      return proc

    mocker.patch.object(github_module.asyncio, "create_subprocess_exec", side_effect=side_effect)
    cfg = GitHubToolConfig(allowed_operations=("pr_draft",))
    result = await github(
      operation="pr_draft",
      ctx=_ctx(cfg),
      number=42,
      repo="owner/repo",
    )
    assert result.success
    import json as json_mod

    parsed = json_mod.loads(result.result)
    assert parsed["draft"] is True
    assert parsed["number"] == 42

  @pytest.mark.asyncio
  async def test_pr_draft_first_call_fails(self, mocker: MockerFixture) -> None:
    """pr_draft fails when the first API call (fetch node_id) returns error."""
    proc = mocker.MagicMock()
    proc.pid = 12345
    proc.returncode = 1
    proc.communicate = mocker.AsyncMock(return_value=(b"", b"not found"))
    mocker.patch.object(github_module.asyncio, "create_subprocess_exec", return_value=proc)
    cfg = GitHubToolConfig(allowed_operations=("pr_draft",))
    result = await github(
      operation="pr_draft",
      ctx=_ctx(cfg),
      number=42,
      repo="owner/repo",
    )
    assert not result.success

  @pytest.mark.asyncio
  async def test_pr_draft_empty_node_id(self, mocker: MockerFixture) -> None:
    """pr_draft fails when node_id is empty."""
    proc = mocker.MagicMock()
    proc.pid = 12345
    proc.returncode = 0
    proc.communicate = mocker.AsyncMock(return_value=(b"", b""))
    mocker.patch.object(github_module.asyncio, "create_subprocess_exec", return_value=proc)
    cfg = GitHubToolConfig(allowed_operations=("pr_draft",))
    result = await github(
      operation="pr_draft",
      ctx=_ctx(cfg),
      number=42,
      repo="owner/repo",
    )
    assert not result.success
    assert "node_id" in result.error.lower()

  @pytest.mark.asyncio
  async def test_release_create_builds_correct_command(self, mocker: MockerFixture) -> None:
    """release_create builds gh release create with tag, --title=, --notes=, no --json."""
    popen = _mock_popen(mocker, stdout="https://github.com/owner/repo/releases/tag/v1.0.0")
    cfg = GitHubToolConfig(allowed_operations=("release_create",))
    await github(
      operation="release_create",
      ctx=_ctx(cfg),
      repo="owner/repo",
      tag="v1.0.0",
      title="Release v1.0.0",
      notes="Changes here.",
    )
    cmd = popen.call_args.args[0]
    assert cmd[:3] == ["gh", "release", "create"]
    assert "--repo" in cmd and "owner/repo" in cmd
    # tag is positional (no -- separator, avoids --title/--notes being treated as positional)
    assert "v1.0.0" in cmd
    assert "--title=Release v1.0.0" in cmd
    assert "--notes=Changes here." in cmd
    assert "--json" not in cmd

  @pytest.mark.asyncio
  async def test_release_create_with_draft_and_prerelease(self, mocker: MockerFixture) -> None:
    """release_create includes --draft and --prerelease flags when set."""
    popen = _mock_popen(mocker, stdout="https://github.com/owner/repo/releases/tag/v2.0.0-beta")
    cfg = GitHubToolConfig(allowed_operations=("release_create",))
    await github(
      operation="release_create",
      ctx=_ctx(cfg),
      repo="owner/repo",
      tag="v2.0.0-beta",
      title="Beta",
      notes="Beta release.",
      draft=True,
      prerelease=True,
    )
    cmd = popen.call_args.args[0]
    assert "--draft" in cmd
    assert "--prerelease" in cmd

  @pytest.mark.asyncio
  async def test_release_create_without_draft_prerelease_omits_them(
    self, mocker: MockerFixture
  ) -> None:
    """release_create omits --draft and --prerelease when not set."""
    popen = _mock_popen(mocker, stdout="https://github.com/owner/repo/releases/tag/v1.0.0")
    cfg = GitHubToolConfig(allowed_operations=("release_create",))
    await github(
      operation="release_create",
      ctx=_ctx(cfg),
      repo="owner/repo",
      tag="v1.0.0",
      title="Release",
      notes="Notes",
    )
    cmd = popen.call_args.args[0]
    assert "--draft" not in cmd
    assert "--prerelease" not in cmd

  @pytest.mark.asyncio
  async def test_release_create_not_in_default_allowlist(self, mocker: MockerFixture) -> None:
    """release_create is rejected with default config."""
    _mock_popen(mocker)
    result = await github(
      operation="release_create",
      ctx=_ctx(),
      repo="owner/repo",
      tag="v1.0.0",
      title="Release",
      notes="Notes",
    )
    assert not result.success
    assert "not allowed" in result.error.lower()

  @pytest.mark.asyncio
  async def test_release_create_requires_repo(self, mocker: MockerFixture) -> None:
    """release_create requires the repo parameter."""
    _mock_popen(mocker)
    cfg = GitHubToolConfig(allowed_operations=("release_create",))
    result = await github(
      operation="release_create",
      ctx=_ctx(cfg),
      tag="v1.0.0",
      title="Release",
      notes="Notes",
    )
    assert not result.success
    assert "repo" in result.error.lower()

  @pytest.mark.asyncio
  async def test_release_create_requires_tag(self, mocker: MockerFixture) -> None:
    """release_create requires a tag."""
    _mock_popen(mocker)
    cfg = GitHubToolConfig(allowed_operations=("release_create",))
    result = await github(
      operation="release_create",
      ctx=_ctx(cfg),
      repo="owner/repo",
      tag="",
      title="Release",
      notes="Notes",
    )
    assert not result.success
    assert "tag" in result.error.lower()

  @pytest.mark.asyncio
  async def test_release_create_requires_title(self, mocker: MockerFixture) -> None:
    """release_create requires a title."""
    _mock_popen(mocker)
    cfg = GitHubToolConfig(allowed_operations=("release_create",))
    result = await github(
      operation="release_create",
      ctx=_ctx(cfg),
      repo="owner/repo",
      tag="v1.0.0",
      title="",
      notes="Notes",
    )
    assert not result.success
    assert "title" in result.error.lower()

  @pytest.mark.asyncio
  async def test_release_create_requires_notes(self, mocker: MockerFixture) -> None:
    """release_create requires notes."""
    _mock_popen(mocker)
    cfg = GitHubToolConfig(allowed_operations=("release_create",))
    result = await github(
      operation="release_create",
      ctx=_ctx(cfg),
      repo="owner/repo",
      tag="v1.0.0",
      title="Release",
      notes="",
    )
    assert not result.success
    assert "notes" in result.error.lower()

  @pytest.mark.asyncio
  async def test_release_create_rejects_nul_in_title(self, mocker: MockerFixture) -> None:
    """release_create rejects NUL byte in title."""
    _mock_popen(mocker)
    cfg = GitHubToolConfig(allowed_operations=("release_create",))
    result = await github(
      operation="release_create",
      ctx=_ctx(cfg),
      repo="owner/repo",
      tag="v1.0.0",
      title="Release\x00evil",
      notes="Notes",
    )
    assert not result.success
    assert "forbidden" in result.error.lower()

  @pytest.mark.asyncio
  async def test_release_create_allows_newlines_in_notes(self, mocker: MockerFixture) -> None:
    """release_create allows newlines in notes (multi-line release notes)."""
    popen = _mock_popen(mocker, stdout='{"url": "https://example.com"}')
    cfg = GitHubToolConfig(allowed_operations=("release_create",))
    result = await github(
      operation="release_create",
      ctx=_ctx(cfg),
      repo="owner/repo",
      tag="v1.0.0",
      title="Release",
      notes="Line 1\nLine 2\nLine 3",
    )
    assert result.success
    cmd = popen.call_args.args[0]
    notes_arg = [c for c in cmd if c.startswith("--notes=")][0]
    assert "\n" in notes_arg

  @pytest.mark.asyncio
  async def test_release_create_allows_markdown_in_notes(self, mocker: MockerFixture) -> None:
    """release_create allows Markdown chars (backticks, pipes, etc.) in notes."""
    popen = _mock_popen(mocker, stdout='{"url": "https://example.com"}')
    cfg = GitHubToolConfig(allowed_operations=("release_create",))
    markdown_notes = (
      "## Changes\n\n"
      "### Bug Fixes\n\n"
      "- Fix `crash` on startup\n"
      "- Fix `null` pointer | pipe issue\n\n"
      "```python\nx = 1; y = 2\n```\n\n"
      "Cost: $5 & $10\n"
    )
    result = await github(
      operation="release_create",
      ctx=_ctx(cfg),
      repo="owner/repo",
      tag="v1.0.0",
      title="Release v1.0.0",
      notes=markdown_notes,
    )
    assert result.success
    cmd = popen.call_args.args[0]
    notes_arg = [c for c in cmd if c.startswith("--notes=")][0]
    assert "`crash`" in notes_arg
    assert "|" in notes_arg
    assert ";" in notes_arg
    assert "$5" in notes_arg
    assert "&" in notes_arg

  @pytest.mark.asyncio
  async def test_release_create_rejects_invalid_tag(self, mocker: MockerFixture) -> None:
    """release_create rejects tag with shell metacharacters."""
    _mock_popen(mocker)
    cfg = GitHubToolConfig(allowed_operations=("release_create",))
    result = await github(
      operation="release_create",
      ctx=_ctx(cfg),
      repo="owner/repo",
      tag="v1.0;rm -rf /",
      title="Release",
      notes="Notes",
    )
    assert not result.success
    assert "tag" in result.error.lower()

  @pytest.mark.asyncio
  async def test_write_op_returns_success_with_json(self, mocker: MockerFixture) -> None:
    """pr_create returns success with parsed JSON from URL output."""
    pr_url = "https://github.com/owner/repo/pull/42"
    _mock_popen(mocker, stdout=pr_url)
    cfg = GitHubToolConfig(allowed_operations=("pr_create",))
    result = await github(
      operation="pr_create",
      ctx=_ctx(cfg),
      repo="owner/repo",
      title="Fix",
      body="Body",
    )
    assert result.success
    assert result.content_metadata is not None
    assert result.content_metadata["operation"] == "github"
    assert result.content_metadata["path"] == "owner/repo"
    # The URL output should be parsed into JSON with url and number
    import json as json_mod

    parsed = json_mod.loads(result.result)
    assert parsed["url"] == pr_url
    assert parsed["number"] == 42

  @pytest.mark.asyncio
  async def test_release_create_returns_success_with_parsed_url(
    self, mocker: MockerFixture
  ) -> None:
    """release_create returns success with parsed JSON from URL output."""
    release_url = "https://github.com/owner/repo/releases/tag/v1.0.0"
    _mock_popen(mocker, stdout=release_url)
    cfg = GitHubToolConfig(allowed_operations=("release_create",))
    result = await github(
      operation="release_create",
      ctx=_ctx(cfg),
      repo="owner/repo",
      tag="v1.0.0",
      title="Release",
      notes="Notes",
    )
    assert result.success
    import json as json_mod

    parsed = json_mod.loads(result.result)
    assert parsed["url"] == release_url
    assert parsed["tagName"] == "v1.0.0"

  # --- pr_edit ---

  @pytest.mark.asyncio
  async def test_pr_edit_not_in_default_allowlist(self, mocker: MockerFixture) -> None:
    """pr_edit is rejected with default config (not in default allowlist)."""
    _mock_popen(mocker)
    result = await github(
      operation="pr_edit",
      ctx=_ctx(),
      number=42,
      add_assignee="user",
    )
    assert not result.success
    assert "not allowed" in result.error.lower() or "allowed" in result.error.lower()

  @pytest.mark.asyncio
  async def test_pr_edit_requires_number(self, mocker: MockerFixture) -> None:
    """pr_edit requires a positive number."""
    _mock_popen(mocker)
    cfg = GitHubToolConfig(allowed_operations=("pr_edit",))
    result = await github(
      operation="pr_edit",
      ctx=_ctx(cfg),
      add_assignee="user",
    )
    assert not result.success
    assert "number" in result.error.lower()

  @pytest.mark.asyncio
  async def test_pr_edit_requires_at_least_one_param(self, mocker: MockerFixture) -> None:
    """pr_edit requires at least one edit parameter."""
    _mock_popen(mocker)
    cfg = GitHubToolConfig(allowed_operations=("pr_edit",))
    result = await github(
      operation="pr_edit",
      ctx=_ctx(cfg),
      number=42,
    )
    assert not result.success
    assert "at least one" in result.error.lower()

  @pytest.mark.asyncio
  async def test_pr_edit_add_assignee_builds_command(self, mocker: MockerFixture) -> None:
    """pr_edit with add_assignee builds gh pr edit --add-assignee=user -- 42."""
    popen = _mock_popen(mocker, stdout="")
    cfg = GitHubToolConfig(allowed_operations=("pr_edit",))
    await github(
      operation="pr_edit",
      ctx=_ctx(cfg),
      number=42,
      add_assignee="christophevg",
    )
    cmd = popen.call_args.args[0]
    assert cmd[:3] == ["gh", "pr", "edit"]
    assert "--add-assignee=christophevg" in cmd
    assert "--json" not in cmd
    assert "--" in cmd
    assert "42" in cmd

  @pytest.mark.asyncio
  async def test_pr_edit_add_reviewer_builds_command(self, mocker: MockerFixture) -> None:
    """pr_edit with add_reviewer builds gh pr edit --add-reviewer=user -- 42."""
    popen = _mock_popen(mocker, stdout="")
    cfg = GitHubToolConfig(allowed_operations=("pr_edit",))
    await github(
      operation="pr_edit",
      ctx=_ctx(cfg),
      number=42,
      add_reviewer="christophevg",
    )
    cmd = popen.call_args.args[0]
    assert "--add-reviewer=christophevg" in cmd

  @pytest.mark.asyncio
  async def test_pr_edit_add_label_builds_command(self, mocker: MockerFixture) -> None:
    """pr_edit with add_label builds gh pr edit --add-label=label -- 42."""
    popen = _mock_popen(mocker, stdout="")
    cfg = GitHubToolConfig(allowed_operations=("pr_edit",))
    await github(
      operation="pr_edit",
      ctx=_ctx(cfg),
      number=42,
      add_label="bug,wip",
    )
    cmd = popen.call_args.args[0]
    assert "--add-label=bug,wip" in cmd

  @pytest.mark.asyncio
  async def test_pr_edit_multiple_params(self, mocker: MockerFixture) -> None:
    """pr_edit with multiple edit params includes all flags."""
    popen = _mock_popen(mocker, stdout="")
    cfg = GitHubToolConfig(allowed_operations=("pr_edit",))
    await github(
      operation="pr_edit",
      ctx=_ctx(cfg),
      number=42,
      add_assignee="user1",
      add_reviewer="user2",
      add_label="label1",
    )
    cmd = popen.call_args.args[0]
    assert "--add-assignee=user1" in cmd
    assert "--add-reviewer=user2" in cmd
    assert "--add-label=label1" in cmd

  @pytest.mark.asyncio
  async def test_pr_edit_with_repo(self, mocker: MockerFixture) -> None:
    """pr_edit includes --repo when provided."""
    popen = _mock_popen(mocker, stdout="")
    cfg = GitHubToolConfig(allowed_operations=("pr_edit",))
    await github(
      operation="pr_edit",
      ctx=_ctx(cfg),
      repo="owner/repo",
      number=42,
      add_assignee="user",
    )
    cmd = popen.call_args.args[0]
    assert "--repo" in cmd and "owner/repo" in cmd

  @pytest.mark.asyncio
  async def test_pr_edit_returns_success(self, mocker: MockerFixture) -> None:
    """pr_edit returns success on exit code 0."""
    _mock_popen(mocker, stdout="")
    cfg = GitHubToolConfig(allowed_operations=("pr_edit",))
    result = await github(
      operation="pr_edit",
      ctx=_ctx(cfg),
      number=42,
      add_assignee="user",
    )
    assert result.success

  @pytest.mark.asyncio
  async def test_pr_edit_rejects_forbidden_char_in_assignee(self, mocker: MockerFixture) -> None:
    """pr_edit rejects forbidden characters in add_assignee."""
    _mock_popen(mocker)
    cfg = GitHubToolConfig(allowed_operations=("pr_edit",))
    result = await github(
      operation="pr_edit",
      ctx=_ctx(cfg),
      number=42,
      add_assignee="user;rm -rf",
    )
    assert not result.success
    assert "forbidden" in result.error.lower()

  @pytest.mark.asyncio
  async def test_pr_edit_remove_params_builds_command(self, mocker: MockerFixture) -> None:
    """pr_edit with remove_* params builds correct flags."""
    popen = _mock_popen(mocker, stdout="")
    cfg = GitHubToolConfig(allowed_operations=("pr_edit",))
    await github(
      operation="pr_edit",
      ctx=_ctx(cfg),
      number=42,
      remove_assignee="user1",
      remove_reviewer="user2",
      remove_label="label1",
    )
    cmd = popen.call_args.args[0]
    assert "--remove-assignee=user1" in cmd
    assert "--remove-reviewer=user2" in cmd
    assert "--remove-label=label1" in cmd


class TestGithubIssueEdit:
  """Tests for issue_edit write operation.

  issue_edit is a multi-step operation: gh issue edit (labels/assignees),
  optional gh issue close/reopen (state), and a final gh issue view that
  returns the updated issue summary.
  """

  @pytest.mark.asyncio
  async def test_issue_edit_not_in_default_allowlist(self, mocker: MockerFixture) -> None:
    """issue_edit is rejected with default config (not in default allowlist)."""
    _mock_popen(mocker)
    result = await github(
      operation="issue_edit",
      ctx=_ctx(),
      number=42,
      add_label="bug",
    )
    assert not result.success
    assert "not allowed" in result.error.lower() or "allowed" in result.error.lower()

  @pytest.mark.asyncio
  async def test_issue_edit_requires_number(self, mocker: MockerFixture) -> None:
    """issue_edit requires a positive number."""
    _mock_popen(mocker)
    cfg = GitHubToolConfig(allowed_operations=("issue_edit",))
    result = await github(
      operation="issue_edit",
      ctx=_ctx(cfg),
      add_label="bug",
    )
    assert not result.success
    assert "number" in result.error.lower()

  @pytest.mark.asyncio
  async def test_issue_edit_requires_at_least_one_param(self, mocker: MockerFixture) -> None:
    """issue_edit requires at least one edit parameter."""
    _mock_popen(mocker)
    cfg = GitHubToolConfig(allowed_operations=("issue_edit",))
    result = await github(
      operation="issue_edit",
      ctx=_ctx(cfg),
      number=42,
    )
    assert not result.success
    assert "at least one" in result.error.lower()

  @pytest.mark.asyncio
  async def test_issue_edit_state_all_rejected(self, mocker: MockerFixture) -> None:
    """issue_edit rejects state="all" — it is a list filter, not a state."""
    _mock_popen(mocker)
    cfg = GitHubToolConfig(allowed_operations=("issue_edit",))
    result = await github(
      operation="issue_edit",
      ctx=_ctx(cfg),
      number=42,
      state="all",
    )
    assert not result.success
    assert "state" in result.error.lower()

  @pytest.mark.asyncio
  async def test_issue_edit_add_label_builds_command(self, mocker: MockerFixture) -> None:
    """issue_edit with add_label builds gh issue edit --add-label=... -- 42 + view."""
    seen_cmds = _track_gh_calls(mocker)
    cfg = GitHubToolConfig(allowed_operations=("issue_edit",))
    result = await github(
      operation="issue_edit",
      ctx=_ctx(cfg),
      number=42,
      add_label="status:in-progress",
    )
    assert result.success
    assert len(seen_cmds) == 2
    edit_cmd, view_cmd = seen_cmds
    assert edit_cmd[:3] == ["gh", "issue", "edit"]
    assert "--add-label=status:in-progress" in edit_cmd
    assert "--json" not in edit_cmd
    assert edit_cmd[-1] == "42" and edit_cmd[-2] == "--"
    # The view returns the updated issue summary as JSON.
    assert view_cmd[:3] == ["gh", "issue", "view"]
    assert "--json" in view_cmd
    assert "number,title,state,labels,assignees,url" in view_cmd
    assert str(42) in view_cmd[view_cmd.index("--") :]
    parsed = json.loads(result.result)
    assert parsed["number"] == 42

  @pytest.mark.asyncio
  async def test_issue_edit_remove_label_builds_command(self, mocker: MockerFixture) -> None:
    """issue_edit with remove_label builds --remove-label=... before the separator."""
    seen_cmds = _track_gh_calls(mocker)
    cfg = GitHubToolConfig(allowed_operations=("issue_edit",))
    await github(
      operation="issue_edit",
      ctx=_ctx(cfg),
      number=42,
      remove_label="status:backlog",
    )
    edit_cmd = seen_cmds[0]
    assert edit_cmd[:3] == ["gh", "issue", "edit"]
    assert "--remove-label=status:backlog" in edit_cmd

  @pytest.mark.asyncio
  async def test_issue_edit_add_assignee_builds_command(self, mocker: MockerFixture) -> None:
    """issue_edit with add_assignee builds --add-assignee=... before the separator."""
    seen_cmds = _track_gh_calls(mocker)
    cfg = GitHubToolConfig(allowed_operations=("issue_edit",))
    await github(
      operation="issue_edit",
      ctx=_ctx(cfg),
      number=42,
      add_assignee="christophevg",
    )
    edit_cmd = seen_cmds[0]
    assert edit_cmd[:3] == ["gh", "issue", "edit"]
    assert "--add-assignee=christophevg" in edit_cmd

  @pytest.mark.asyncio
  async def test_issue_edit_remove_assignee_builds_command(self, mocker: MockerFixture) -> None:
    """issue_edit with remove_assignee builds --remove-assignee=... before the separator."""
    seen_cmds = _track_gh_calls(mocker)
    cfg = GitHubToolConfig(allowed_operations=("issue_edit",))
    await github(
      operation="issue_edit",
      ctx=_ctx(cfg),
      number=42,
      remove_assignee="christophevg",
    )
    edit_cmd = seen_cmds[0]
    assert edit_cmd[:3] == ["gh", "issue", "edit"]
    assert "--remove-assignee=christophevg" in edit_cmd

  @pytest.mark.asyncio
  async def test_issue_edit_multiple_params(self, mocker: MockerFixture) -> None:
    """issue_edit with multiple edit params includes all flags in one edit call."""
    seen_cmds = _track_gh_calls(mocker)
    cfg = GitHubToolConfig(allowed_operations=("issue_edit",))
    await github(
      operation="issue_edit",
      ctx=_ctx(cfg),
      number=42,
      add_label="bug,wip",
      remove_label="status:backlog",
      add_assignee="user1",
      remove_assignee="user2",
    )
    # Exactly two gh calls: one edit + one view (no state change).
    assert len(seen_cmds) == 2
    edit_cmd = seen_cmds[0]
    assert "--add-label=bug,wip" in edit_cmd
    assert "--remove-label=status:backlog" in edit_cmd
    assert "--add-assignee=user1" in edit_cmd
    assert "--remove-assignee=user2" in edit_cmd

  @pytest.mark.asyncio
  async def test_issue_edit_with_repo(self, mocker: MockerFixture) -> None:
    """issue_edit includes --repo on every step when provided."""
    seen_cmds = _track_gh_calls(mocker)
    cfg = GitHubToolConfig(allowed_operations=("issue_edit",))
    await github(
      operation="issue_edit",
      ctx=_ctx(cfg),
      repo="owner/repo",
      number=42,
      add_label="bug",
    )
    assert len(seen_cmds) == 2
    edit_cmd, view_cmd = seen_cmds
    assert "--repo" in edit_cmd and "owner/repo" in edit_cmd
    assert "--repo" in view_cmd and "owner/repo" in view_cmd

  @pytest.mark.asyncio
  async def test_issue_edit_state_closed_runs_close(self, mocker: MockerFixture) -> None:
    """issue_edit with state="closed" runs gh issue close after the edit, then view."""
    seen_cmds = _track_gh_calls(mocker)
    cfg = GitHubToolConfig(allowed_operations=("issue_edit",))
    result = await github(
      operation="issue_edit",
      ctx=_ctx(cfg),
      number=42,
      add_label="status:done",
      state="closed",
    )
    assert result.success
    assert len(seen_cmds) == 3
    edit_cmd, close_cmd, view_cmd = seen_cmds
    assert edit_cmd[:3] == ["gh", "issue", "edit"]
    assert "--add-label=status:done" in edit_cmd
    assert close_cmd[:3] == ["gh", "issue", "close"]
    assert close_cmd[-1] == "42" and close_cmd[-2] == "--"
    assert view_cmd[:3] == ["gh", "issue", "view"]
    # The mocked gh returns the (updated) issue; verify the view ran after close.
    parsed = json.loads(result.result)
    assert parsed["number"] == 42

  @pytest.mark.asyncio
  async def test_issue_edit_state_open_runs_reopen(self, mocker: MockerFixture) -> None:
    """issue_edit with state="open" runs gh issue reopen, then view."""
    seen_cmds = _track_gh_calls(mocker)
    cfg = GitHubToolConfig(allowed_operations=("issue_edit",))
    await github(
      operation="issue_edit",
      ctx=_ctx(cfg),
      number=42,
      state="open",
    )
    assert len(seen_cmds) == 2
    reopen_cmd, _view_cmd = seen_cmds
    assert reopen_cmd[:3] == ["gh", "issue", "reopen"]
    assert reopen_cmd[-1] == "42"

  @pytest.mark.asyncio
  async def test_issue_edit_state_only_skips_edit_call(self, mocker: MockerFixture) -> None:
    """issue_edit with only state runs close/reopen directly — no gh issue edit."""
    seen_cmds = _track_gh_calls(mocker)
    cfg = GitHubToolConfig(allowed_operations=("issue_edit",))
    await github(
      operation="issue_edit",
      ctx=_ctx(cfg),
      number=42,
      state="closed",
    )
    assert len(seen_cmds) == 2
    close_cmd, view_cmd = seen_cmds
    assert close_cmd[:3] == ["gh", "issue", "close"]
    assert view_cmd[:3] == ["gh", "issue", "view"]

  @pytest.mark.asyncio
  async def test_issue_edit_rejects_pr_only_param_with_allowed_set(
    self, mocker: MockerFixture
  ) -> None:
    """issue_edit rejects PR-only edit parameters, naming the allowed set."""
    _mock_popen(mocker)
    cfg = GitHubToolConfig(allowed_operations=("issue_edit",))
    result = await github(
      operation="issue_edit",
      ctx=_ctx(cfg),
      number=42,
      add_reviewer="user1",
    )
    assert not result.success
    assert "add_reviewer" in result.error
    assert "add_label" in result.error
    assert "issue_edit" in result.error

  @pytest.mark.asyncio
  async def test_issue_edit_rejects_forbidden_char_in_label(self, mocker: MockerFixture) -> None:
    """issue_edit rejects forbidden characters in add_label."""
    _mock_popen(mocker)
    cfg = GitHubToolConfig(allowed_operations=("issue_edit",))
    result = await github(
      operation="issue_edit",
      ctx=_ctx(cfg),
      number=42,
      add_label="bug;rm -rf",
    )
    assert not result.success
    assert "forbidden" in result.error.lower()

  @pytest.mark.asyncio
  async def test_issue_edit_edit_failure_propagates(self, mocker: MockerFixture) -> None:
    """issue_edit maps a genuine issue-not-found to the issue number."""
    _mock_popen(mocker, stderr="could not resolve to an Issue", returncode=1)
    cfg = GitHubToolConfig(allowed_operations=("issue_edit",))
    result = await github(
      operation="issue_edit",
      ctx=_ctx(cfg),
      number=42,
      add_label="bug",
    )
    assert not result.success
    # The issue itself is the missing resource here — blame the number.
    assert "42" in result.error
    assert "not found" in result.error.lower()

  @pytest.mark.asyncio
  async def test_issue_edit_missing_label_names_the_label_not_the_issue(
    self, mocker: MockerFixture
  ) -> None:
    """A missing LABEL must not be misreported as 'Resource not found: 42'.

    gh issue edit does not auto-create labels; it fails with
    "could not add label: 'x' not found". The bug this guards against: the
    generic not-found mapping blamed the issue number while the issue was
    fine and the label was missing.
    """
    _mock_popen(mocker, stderr="could not add label: 'test-issue-edit' not found", returncode=1)
    cfg = GitHubToolConfig(allowed_operations=("issue_edit",))
    result = await github(
      operation="issue_edit",
      ctx=_ctx(cfg),
      number=69,
      add_label="test-issue-edit",
    )
    assert not result.success
    # Names the label as the missing resource — not the issue number alone.
    assert "test-issue-edit" in result.error
    assert "label not found" in result.error.lower()
    assert "does not auto-create" in result.error.lower()
    # And does NOT claim the issue is missing.
    assert "Resource not found: 69" not in result.error

  @pytest.mark.asyncio
  async def test_issue_edit_missing_remove_label_reports_label(self, mocker: MockerFixture) -> None:
    """remove-label failure with unknown label names the label, not the issue."""
    _mock_popen(mocker, stderr="could not remove label: 'status:backlog' not found", returncode=1)
    cfg = GitHubToolConfig(allowed_operations=("issue_edit",))
    result = await github(
      operation="issue_edit",
      ctx=_ctx(cfg),
      number=69,
      remove_label="status:backlog",
    )
    assert not result.success
    assert "status:backlog" in result.error
    assert "could not remove" in result.error.lower()

  @pytest.mark.asyncio
  async def test_issue_edit_missing_assignee_reports_assignee(self, mocker: MockerFixture) -> None:
    """A missing assignee login is named in the error, not the issue number."""
    _mock_popen(mocker, stderr="could not add assignee: 'ghost-user' not found", returncode=1)
    cfg = GitHubToolConfig(allowed_operations=("issue_edit",))
    result = await github(
      operation="issue_edit",
      ctx=_ctx(cfg),
      number=69,
      add_assignee="ghost-user",
    )
    assert not result.success
    assert "ghost-user" in result.error
    assert "assignee not found" in result.error.lower()

  @pytest.mark.asyncio
  async def test_issue_edit_view_failure_propagates(self, mocker: MockerFixture) -> None:
    """issue_edit surfaces the gh error when the final view step fails."""
    _mock_popen(mocker, stderr="API rate limit exceeded", returncode=1)
    cfg = GitHubToolConfig(allowed_operations=("issue_edit",))
    result = await github(
      operation="issue_edit",
      ctx=_ctx(cfg),
      number=42,
      add_label="bug",
    )
    assert not result.success
    assert "rate limit" in result.error.lower()


class TestGithubIssueCreate:
  """Tests for issue_create write operation."""

  @pytest.mark.asyncio
  async def test_issue_create_builds_correct_command(self, mocker: MockerFixture) -> None:
    """issue_create builds gh issue create with --title= and --body=, no --json."""
    popen = _mock_popen(mocker, stdout="https://github.com/owner/repo/issues/42")
    cfg = GitHubToolConfig(allowed_operations=("issue_create",))
    await github(
      operation="issue_create",
      ctx=_ctx(cfg),
      repo="owner/repo",
      title="Bug report",
      body="Something is broken.",
    )
    cmd = popen.call_args.args[0]
    assert cmd[:3] == ["gh", "issue", "create"]
    assert "--repo" in cmd and "owner/repo" in cmd
    assert "--title=Bug report" in cmd
    assert "--body=Something is broken." in cmd
    assert "--json" not in cmd

  @pytest.mark.asyncio
  async def test_issue_create_with_label_and_assignee(self, mocker: MockerFixture) -> None:
    """issue_create includes --label and --assignee when provided."""
    popen = _mock_popen(mocker, stdout="https://github.com/owner/repo/issues/42")
    cfg = GitHubToolConfig(allowed_operations=("issue_create",))
    await github(
      operation="issue_create",
      ctx=_ctx(cfg),
      repo="owner/repo",
      title="Bug",
      body="Details.",
      label="bug,priority",
      assignee="user1,user2",
    )
    cmd = popen.call_args.args[0]
    assert "--label" in cmd
    label_idx = cmd.index("--label")
    assert cmd[label_idx + 1] == "bug,priority"
    assert "--assignee" in cmd
    assignee_idx = cmd.index("--assignee")
    assert cmd[assignee_idx + 1] == "user1,user2"

  @pytest.mark.asyncio
  async def test_issue_create_without_label_assignee_omits_them(
    self, mocker: MockerFixture
  ) -> None:
    """issue_create omits --label and --assignee when not provided."""
    popen = _mock_popen(mocker, stdout="https://github.com/owner/repo/issues/42")
    cfg = GitHubToolConfig(allowed_operations=("issue_create",))
    await github(
      operation="issue_create",
      ctx=_ctx(cfg),
      repo="owner/repo",
      title="Bug",
      body="body",
    )
    cmd = popen.call_args.args[0]
    assert "--label" not in cmd
    assert "--assignee" not in cmd

  @pytest.mark.asyncio
  async def test_issue_create_not_in_default_allowlist(self, mocker: MockerFixture) -> None:
    """issue_create is rejected with default config (not in default allowlist)."""
    _mock_popen(mocker)
    result = await github(
      operation="issue_create",
      ctx=_ctx(),
      repo="owner/repo",
      title="Bug",
      body="body",
    )
    assert not result.success
    assert "not allowed" in result.error.lower()

  @pytest.mark.asyncio
  async def test_issue_create_requires_repo(self, mocker: MockerFixture) -> None:
    """issue_create requires the repo parameter."""
    _mock_popen(mocker)
    cfg = GitHubToolConfig(allowed_operations=("issue_create",))
    result = await github(
      operation="issue_create",
      ctx=_ctx(cfg),
      title="Bug",
      body="body",
    )
    assert not result.success
    assert "repo" in result.error.lower()

  @pytest.mark.asyncio
  async def test_issue_create_requires_title(self, mocker: MockerFixture) -> None:
    """issue_create requires a non-empty title."""
    _mock_popen(mocker)
    cfg = GitHubToolConfig(allowed_operations=("issue_create",))
    result = await github(
      operation="issue_create",
      ctx=_ctx(cfg),
      repo="owner/repo",
      title="",
      body="body",
    )
    assert not result.success
    assert "title" in result.error.lower()

  @pytest.mark.asyncio
  async def test_issue_create_requires_body(self, mocker: MockerFixture) -> None:
    """issue_create requires a non-empty body."""
    _mock_popen(mocker)
    cfg = GitHubToolConfig(allowed_operations=("issue_create",))
    result = await github(
      operation="issue_create",
      ctx=_ctx(cfg),
      repo="owner/repo",
      title="Bug",
      body="",
    )
    assert not result.success
    assert "body" in result.error.lower()

  @pytest.mark.asyncio
  async def test_issue_create_parses_url_output(self, mocker: MockerFixture) -> None:
    """issue_create parses the issue URL into JSON with number and url."""
    _mock_popen(mocker, stdout="https://github.com/owner/repo/issues/42")
    cfg = GitHubToolConfig(allowed_operations=("issue_create",))
    result = await github(
      operation="issue_create",
      ctx=_ctx(cfg),
      repo="owner/repo",
      title="Bug",
      body="body",
    )
    assert result.success
    import json as _json

    parsed = _json.loads(result.result)
    assert parsed["url"] == "https://github.com/owner/repo/issues/42"
    assert parsed["number"] == 42

  @pytest.mark.asyncio
  async def test_issue_create_returns_success(self, mocker: MockerFixture) -> None:
    """issue_create returns success on exit code 0."""
    _mock_popen(mocker, stdout="https://github.com/owner/repo/issues/1")
    cfg = GitHubToolConfig(allowed_operations=("issue_create",))
    result = await github(
      operation="issue_create",
      ctx=_ctx(cfg),
      repo="owner/repo",
      title="Issue",
      body="Body text.",
    )
    assert result.success

  @pytest.mark.asyncio
  async def test_issue_create_in_github_operations(self) -> None:
    """issue_create is in the _GITHUB_OPERATIONS frozenset."""
    assert "issue_create" in github_module._GITHUB_OPERATIONS

  @pytest.mark.asyncio
  async def test_issue_create_in_write_ops(self) -> None:
    """issue_create is in the _WRITE_OPS frozenset (requires explicit opt-in)."""
    assert "issue_create" in github_module._WRITE_OPS


class TestGithubLabelCreate:
  """Tests for label_create write operation."""

  @pytest.mark.asyncio
  async def test_label_create_builds_correct_command(self, mocker: MockerFixture) -> None:
    """label_create builds gh label create --repo owner/repo <name> with no --json."""
    popen = _mock_popen(mocker, stdout='✓ Label "status:triage" created in owner/repo')
    cfg = GitHubToolConfig(allowed_operations=("label_create",))
    await github(
      operation="label_create",
      ctx=_ctx(cfg),
      repo="owner/repo",
      label="status:triage",
    )
    cmd = popen.call_args.args[0]
    assert cmd[:3] == ["gh", "label", "create"]
    assert "--repo" in cmd and "owner/repo" in cmd
    assert "status:triage" in cmd
    assert "--json" not in cmd
    assert "--" not in cmd  # no number/tag positional

  @pytest.mark.asyncio
  async def test_label_create_with_color_and_description(self, mocker: MockerFixture) -> None:
    """label_create passes --color= and --description= flags in = format."""
    popen = _mock_popen(mocker, stdout='✓ Label "bug" created in owner/repo')
    cfg = GitHubToolConfig(allowed_operations=("label_create",))
    await github(
      operation="label_create",
      ctx=_ctx(cfg),
      repo="owner/repo",
      label="bug",
      color="E99695",
      description="Something isn't working",
    )
    cmd = popen.call_args.args[0]
    assert "--color=E99695" in cmd
    assert "--description=Something isn't working" in cmd
    # Name positional comes before the flags.
    assert cmd.index("bug") < cmd.index("--color=E99695")

  @pytest.mark.asyncio
  async def test_label_create_omits_optional_flags(self, mocker: MockerFixture) -> None:
    """label_create omits --color/--description when not provided."""
    popen = _mock_popen(mocker, stdout='✓ Label "x" created in owner/repo')
    cfg = GitHubToolConfig(allowed_operations=("label_create",))
    await github(
      operation="label_create",
      ctx=_ctx(cfg),
      repo="owner/repo",
      label="x",
    )
    cmd = popen.call_args.args[0]
    assert "--color" not in cmd
    assert "--description" not in cmd

  @pytest.mark.asyncio
  async def test_label_create_returns_success_summary(self, mocker: MockerFixture) -> None:
    """label_create parses gh's success message into a JSON summary."""
    _mock_popen(mocker, stdout='✓ Label "status:triage" created in owner/repo')
    cfg = GitHubToolConfig(allowed_operations=("label_create",))
    result = await github(
      operation="label_create",
      ctx=_ctx(cfg),
      repo="owner/repo",
      label="status:triage",
    )
    assert result.success
    parsed = json.loads(result.result)
    assert parsed["created"] is True
    assert parsed["label"] == "status:triage"
    assert parsed["repo"] == "owner/repo"

  @pytest.mark.asyncio
  async def test_label_create_empty_stdout_still_success(self, mocker: MockerFixture) -> None:
    """label_create with empty gh stdout returns a minimal created summary."""
    _mock_popen(mocker, stdout="")
    cfg = GitHubToolConfig(allowed_operations=("label_create",))
    result = await github(
      operation="label_create",
      ctx=_ctx(cfg),
      repo="owner/repo",
      label="x",
    )
    assert result.success
    parsed = json.loads(result.result)
    assert parsed["created"] is True
    assert "label" not in parsed

  @pytest.mark.asyncio
  async def test_label_create_not_in_default_allowlist(self, mocker: MockerFixture) -> None:
    """label_create is rejected with default config (not in default allowlist)."""
    _mock_popen(mocker)
    result = await github(
      operation="label_create",
      ctx=_ctx(),
      repo="owner/repo",
      label="x",
    )
    assert not result.success
    assert "not allowed" in result.error.lower() or "allowed" in result.error.lower()

  @pytest.mark.asyncio
  async def test_label_create_requires_repo(self, mocker: MockerFixture) -> None:
    """label_create requires an explicit repo (no auto-detect for creation)."""
    _mock_popen(mocker)
    cfg = GitHubToolConfig(allowed_operations=("label_create",))
    result = await github(
      operation="label_create",
      ctx=_ctx(cfg),
      label="x",
    )
    assert not result.success
    assert "repo" in result.error.lower()

  @pytest.mark.asyncio
  async def test_label_create_requires_label(self, mocker: MockerFixture) -> None:
    """label_create requires a non-empty label name."""
    _mock_popen(mocker)
    cfg = GitHubToolConfig(allowed_operations=("label_create",))
    result = await github(
      operation="label_create",
      ctx=_ctx(cfg),
      repo="owner/repo",
      label="",
    )
    assert not result.success
    assert "label" in result.error.lower()

  @pytest.mark.asyncio
  async def test_label_create_rejects_leading_dash_label(self, mocker: MockerFixture) -> None:
    """label_create rejects a label starting with '-' (flag injection)."""
    _mock_popen(mocker)
    cfg = GitHubToolConfig(allowed_operations=("label_create",))
    result = await github(
      operation="label_create",
      ctx=_ctx(cfg),
      repo="owner/repo",
      label="--force",
    )
    assert not result.success
    assert (
      "dash" in result.error.lower()
      or "-'" in result.error
      or "must not start" in result.error.lower()
    )

  @pytest.mark.asyncio
  async def test_label_create_rejects_invalid_color(self, mocker: MockerFixture) -> None:
    """label_create rejects colors that are not 6-char hex without '#'."""
    _mock_popen(mocker)
    cfg = GitHubToolConfig(allowed_operations=("label_create",))
    result = await github(
      operation="label_create",
      ctx=_ctx(cfg),
      repo="owner/repo",
      label="x",
      color="#E99695",
    )
    assert not result.success
    assert "color" in result.error.lower()

  @pytest.mark.asyncio
  async def test_label_create_rejects_short_color(self, mocker: MockerFixture) -> None:
    """label_create rejects 5-character color values."""
    _mock_popen(mocker)
    cfg = GitHubToolConfig(allowed_operations=("label_create",))
    result = await github(
      operation="label_create",
      ctx=_ctx(cfg),
      repo="owner/repo",
      label="x",
      color="E9969",
    )
    assert not result.success
    assert "color" in result.error.lower()

  @pytest.mark.asyncio
  async def test_label_create_accepts_label_names_with_spaces(self, mocker: MockerFixture) -> None:
    """label_create accepts names like 'good first issue' and 'status:backlog'."""
    _mock_popen(mocker, stdout='✓ Label "good first issue" created in owner/repo')
    cfg = GitHubToolConfig(allowed_operations=("label_create",))
    result = await github(
      operation="label_create",
      ctx=_ctx(cfg),
      repo="owner/repo",
      label="good first issue",
      description="Good for newcomers",
    )
    assert result.success

  @pytest.mark.asyncio
  async def test_label_create_already_exists_error(self, mocker: MockerFixture) -> None:
    """label_create surfaces gh's already-exists error verbatim (no --force)."""
    _mock_popen(
      mocker,
      stderr='label with name "bug" already exists; use `--force` to update its color and description',
      returncode=1,
    )
    cfg = GitHubToolConfig(allowed_operations=("label_create",))
    result = await github(
      operation="label_create",
      ctx=_ctx(cfg),
      repo="owner/repo",
      label="bug",
    )
    assert not result.success
    assert "already exists" in result.error.lower()


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
    # #68: the rejection names the enabling key and where to set it.
    assert "tools.github.allowed_operations" in result.error
    assert "yoker.toml" in result.error

  @pytest.mark.asyncio
  async def test_non_string_operation_rejected(self, mocker: MockerFixture) -> None:
    _mock_popen(mocker)
    result = await github(operation=123, ctx=_ctx())  # type: ignore[arg-type]
    assert not result.success

  @pytest.mark.asyncio
  async def test_default_allowlist_allows_all_twelve(self, mocker: MockerFixture) -> None:
    cfg = GitHubToolConfig()
    for op in cfg.allowed_operations:
      # pr_comments and pr_reviews return arrays; others return objects
      mock_stdout = "[]" if op in {"pr_reviews", "pr_comments"} else "{}"
      _mock_popen(mocker, stdout=mock_stdout)
      kwargs: dict[str, Any] = {}
      if op in {
        "issue_view",
        "pr_view",
        "workflow_view",
        "workflow_logs",
        "pr_reviews",
        "pr_comments",
      }:
        kwargs["number"] = 1
      if op in {"pr_reviews", "pr_comments"}:
        kwargs["repo"] = "owner/repo"
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


class TestGithubOutputNoTruncation:
  """The github tool returns full output — size enforcement is handled
  centrally by _execute_tool after post_filter is applied (same pattern
  as the make tool)."""

  @pytest.mark.asyncio
  async def test_large_output_returned_in_full(self, mocker: MockerFixture) -> None:
    big = "x" * (150 * 1024)
    _mock_popen(mocker, stdout=big, returncode=0)
    cfg = GitHubToolConfig(max_output_kb=20)
    result = await github(operation="repo_view", ctx=_ctx(cfg))
    assert result.success
    assert result.result == big
    assert "[truncated]" not in result.result

  @pytest.mark.asyncio
  async def test_small_output_returned_as_is(self, mocker: MockerFixture) -> None:
    _mock_popen(mocker, stdout='{"name":"r"}', returncode=0)
    result = await github(operation="repo_view", ctx=_ctx())
    assert result.success
    assert "truncated" not in result.content_metadata["metadata"]


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
    assert inner["repo"] == "owner/repo"
    assert "gh_subcommand" in inner

  @pytest.mark.asyncio
  async def test_path_defaults_when_repo_empty(self, mocker: MockerFixture) -> None:
    _mock_popen(mocker, stdout="{}", returncode=0)
    result = await github(operation="repo_view", ctx=_ctx())
    assert result.content_metadata["path"] == "default"

  @pytest.mark.asyncio
  async def test_issue_edit_metadata_shape(self, mocker: MockerFixture) -> None:
    _mock_popen(mocker, stdout='{"number": 42, "state": "open"}', returncode=0)
    cfg = GitHubToolConfig(allowed_operations=("issue_edit",))
    result = await github(operation="issue_edit", ctx=_ctx(cfg), number=42, add_label="bug")
    assert result.success
    md = result.content_metadata
    assert set(md.keys()) == {"operation", "path", "content_type", "content", "metadata"}
    assert md["operation"] == "github"
    assert md["path"] == "default"
    assert md["content_type"] == "application/json"
    inner = md["metadata"]
    assert inner["returncode"] == 0
    assert inner["repo"] == ""
    assert inner["number"] == 42
    assert "gh_subcommand" in inner

  @pytest.mark.asyncio
  async def test_issue_edit_metadata_state_none_when_omitted(self, mocker: MockerFixture) -> None:
    _mock_popen(mocker, stdout='{"number": 42, "state": "open"}', returncode=0)
    cfg = GitHubToolConfig(allowed_operations=("issue_edit",))
    await github(operation="issue_edit", ctx=_ctx(cfg), number=42, add_label="bug")
    # With default config the list-op state default never leaks into issue_edit.
    result = await github(operation="issue_edit", ctx=_ctx(cfg), number=42, add_label="bug")
    assert result.success
    assert result.content_metadata["metadata"]["state"] is None

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
    mocker.patch.object(
      github_module.asyncio, "create_subprocess_exec", side_effect=FileNotFoundError()
    )
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
    cmd = popen.call_args.args[0]
    kwargs = popen.call_args.kwargs
    assert isinstance(cmd, list)
    assert all(isinstance(item, str) for item in cmd)
    assert cmd[0] == "gh"
    # asyncio.create_subprocess_exec has no shell parameter (inherently no-shell).
    assert "shell" not in kwargs
    assert kwargs.get("start_new_session") is True

  @pytest.mark.asyncio
  async def test_no_env_passthrough(self, mocker: MockerFixture) -> None:
    """The agent cannot inject env vars; only os.environ is inherited."""
    popen = _mock_popen(mocker, stdout="{}", returncode=0)
    await github(operation="repo_view", ctx=_ctx())
    kwargs = popen.call_args.kwargs
    # env is os.environ (no agent-supplied additions).
    assert kwargs.get("env") is github_module.os.environ


class TestGithubConfigValidation:
  """GitHubToolConfig validates allowed_operations against the enum."""

  def test_unknown_operation_in_allowlist_raises(self) -> None:
    with pytest.raises(ValidationError):
      GitHubToolConfig(allowed_operations=("repo_view", "bogus_op"))

  def test_default_allowlist_has_twelve_ops(self) -> None:
    cfg = GitHubToolConfig()
    assert len(cfg.allowed_operations) == 12
    # Write ops are NOT in the default allowlist
    assert "pr_create" not in cfg.allowed_operations
    assert "pr_comment" not in cfg.allowed_operations
    assert "pr_ready" not in cfg.allowed_operations
    assert "pr_draft" not in cfg.allowed_operations
    assert "release_create" not in cfg.allowed_operations
    assert "issue_edit" not in cfg.allowed_operations
    assert "label_create" not in cfg.allowed_operations

  def test_write_ops_allowed_when_explicitly_configured(self) -> None:
    cfg = GitHubToolConfig(
      allowed_operations=(
        "repo_view",
        "pr_create",
        "pr_comment",
        "pr_ready",
        "pr_draft",
        "release_create",
      )
    )
    assert "pr_create" in cfg.allowed_operations
    assert "pr_comment" in cfg.allowed_operations
    assert "pr_ready" in cfg.allowed_operations
    assert "pr_draft" in cfg.allowed_operations
    assert "release_create" in cfg.allowed_operations

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
    # create_subprocess_exec must NOT be invoked on Windows.
    popen = mocker.patch.object(github_module.asyncio, "create_subprocess_exec")
    result = await github(operation="repo_view", ctx=_ctx())
    assert not result.success
    assert "not available on Windows" in result.error
    assert not popen.called


class TestPositionalRepoOps:
  """repo_view passes the repository as a positional operand (gh requirement)."""

  @pytest.mark.asyncio
  async def test_repo_view_with_repo_is_positional(self, mocker: MockerFixture) -> None:
    """gh repo view [<repository>] — repo goes after the subcommand, not as --repo."""
    popen = _mock_popen(mocker, stdout='{"name":"r"}')
    result = await github(operation="repo_view", ctx=_ctx(), repo="owner/repo")
    assert result.success
    cmd = popen.call_args.args[0]
    assert cmd[:4] == ["gh", "repo", "view", "owner/repo"]
    assert "--repo" not in cmd

  @pytest.mark.asyncio
  async def test_repo_view_without_repo_auto_detects(self, mocker: MockerFixture) -> None:
    """Without repo, no positional — gh auto-detects from the git remote."""
    popen = _mock_popen(mocker, stdout='{"name":"r"}')
    result = await github(operation="repo_view", ctx=_ctx())
    assert result.success
    cmd = popen.call_args.args[0]
    assert cmd[:3] == ["gh", "repo", "view"]
    assert "--repo" not in cmd
    # No stray operand: subcommand is directly followed by flags
    assert cmd[3] == "--json"

  @pytest.mark.asyncio
  async def test_other_ops_still_use_repo_flag(self, mocker: MockerFixture) -> None:
    """pr_list/issue_list still pass --repo as a flag (gh supports -R there)."""
    popen = _mock_popen(mocker, stdout="[]")
    await github(operation="pr_list", ctx=_ctx(), repo="owner/repo")
    cmd = popen.call_args.args[0]
    assert "--repo" in cmd and "owner/repo" in cmd
    # And the repo is NOT a positional right after the subcommand
    assert cmd[3] == "--repo"


class TestCiVerdict:
  """_ci_verdict compresses statusCheckRollup arrays into verdict strings."""

  def test_none_when_empty(self) -> None:
    assert github_module._ci_verdict(None) == "none"
    assert github_module._ci_verdict([]) == "none"
    assert github_module._ci_verdict("not-a-list") == "none"

  def test_all_ok(self) -> None:
    assert github_module._ci_verdict([{"conclusion": "SUCCESS"}] * 12) == "12 ok"

  def test_ok_counts_neutral_and_skipped(self) -> None:
    rollup = [
      {"conclusion": "SUCCESS"},
      {"conclusion": "NEUTRAL"},
      {"conclusion": "SKIPPED"},
    ]
    assert github_module._ci_verdict(rollup) == "3 ok"

  def test_failures(self) -> None:
    rollup = [{"conclusion": "SUCCESS"}] * 9 + [{"conclusion": "FAILURE"}] * 3
    assert github_module._ci_verdict(rollup) == "3 failing / 9 ok"

  def test_pending(self) -> None:
    rollup = [{"conclusion": "SUCCESS"}] * 9 + [{"status": "IN_PROGRESS"}] * 2
    assert github_module._ci_verdict(rollup) == "2 pending / 9 ok"

  def test_mixed(self) -> None:
    rollup = (
      [{"conclusion": "SUCCESS"}] * 9 + [{"conclusion": "FAILURE"}] * 3 + [{"status": "QUEUED"}]
    )
    assert github_module._ci_verdict(rollup) == "3 failing / 9 ok / 1 pending"

  def test_unknown_state_counts_pending(self) -> None:
    rollup = [{"conclusion": "WEIRD"}, {"conclusion": "SUCCESS"}]
    assert github_module._ci_verdict(rollup) == "1 pending / 1 ok"

  def test_non_dict_entries_count_pending(self) -> None:
    rollup = ["garbage", {"conclusion": "SUCCESS"}]
    assert github_module._ci_verdict(rollup) == "1 pending / 1 ok"

  def test_timed_out_counts_failing(self) -> None:
    rollup = [{"conclusion": "TIMED_OUT"}, {"conclusion": "SUCCESS"}]
    assert github_module._ci_verdict(rollup) == "1 failing / 1 ok"

  def test_status_context_state_field_counts(self) -> None:
    rollup = [{"conclusion": "SUCCESS"}] * 11 + [{"state": "SUCCESS"}]
    assert github_module._ci_verdict(rollup) == "12 ok"

  def test_status_context_states_map_to_verdicts(self) -> None:
    rollup = (
      [{"conclusion": "SUCCESS"}] * 10
      + [{"state": "FAILURE"}]
      + [{"state": "ERROR"}]
      + [{"state": "PENDING"}]
      + [{"state": "EXPECTED"}]
    )
    assert github_module._ci_verdict(rollup) == "2 failing / 10 ok / 2 pending"


class TestCompactDefaults:
  """Without explicit fields, pr_list/pr_view compress rollup and pr_list author."""

  def _rollup_pr(self, number: int = 10) -> dict[str, Any]:
    return {
      "number": number,
      "title": "T",
      "state": "MERGED",
      "reviewDecision": "APPROVED",
      "headRefName": "feature",
      "createdAt": "2026-01-01T00:00:00Z",
      "author": {"login": "alice"},
      "statusCheckRollup": [{"conclusion": "SUCCESS"}] * 12,
    }

  @pytest.mark.asyncio
  async def test_pr_list_compacts_by_default(self, mocker: MockerFixture) -> None:
    _mock_popen(mocker, stdout=json.dumps([self._rollup_pr()]))
    result = await github(operation="pr_list", ctx=_ctx(), repo="owner/repo", state="all")
    result = await github(operation="pr_list", ctx=_ctx(), repo="owner/repo", state="all")
    assert result.success
    items = json.loads(result.result)
    assert items[0]["ci"] == "12 ok"
    assert "statusCheckRollup" not in items[0]
    assert items[0]["author"] == "alice"

  @pytest.mark.asyncio
  async def test_pr_view_compacts_by_default(self, mocker: MockerFixture) -> None:
    _mock_popen(mocker, stdout=json.dumps(self._rollup_pr()))
    result = await github(operation="pr_view", ctx=_ctx(), repo="owner/repo", number=10)
    result = await github(operation="pr_view", ctx=_ctx(), repo="owner/repo", number=10)
    assert result.success
    item = json.loads(result.result)
    assert item["ci"] == "12 ok"
    assert "statusCheckRollup" not in item
    # pr_view keeps the full author object
    assert item["author"] == {"login": "alice"}

  @pytest.mark.asyncio
  async def test_explicit_fields_passthrough_raw(self, mocker: MockerFixture) -> None:
    """With explicit fields, gh output is passed through untouched."""
    popen = _mock_popen(mocker, stdout=json.dumps([self._rollup_pr()]))
    result = await github(
      operation="pr_list",
      ctx=_ctx(),
      repo="owner/repo",
      fields="number,statusCheckRollup",
    )
    assert result.success
    items = json.loads(result.result)
    assert items[0]["statusCheckRollup"] == [{"conclusion": "SUCCESS"}] * 12
    assert "ci" not in items[0]
    # And the command used the explicit fields, not the default set
    cmd = popen.call_args.args[0]
    json_idx = cmd.index("--json")
    assert cmd[json_idx + 1] == "number,statusCheckRollup"

  @pytest.mark.asyncio
  async def test_explicit_fields_pr_view_passthrough(self, mocker: MockerFixture) -> None:
    _mock_popen(mocker, stdout=json.dumps(self._rollup_pr()))
    result = await github(
      operation="pr_view",
      ctx=_ctx(),
      repo="owner/repo",
      number=10,
      fields="number,title,statusCheckRollup",
    )
    assert result.success
    item = json.loads(result.result)
    assert "ci" not in item  # no compression key added
    assert "statusCheckRollup" in item

  @pytest.mark.asyncio
  async def test_malformed_json_passthrough(self, mocker: MockerFixture) -> None:
    """Malformed gh output passes through unchanged — never raises."""
    _mock_popen(mocker, stdout="not json at all")
    result = await github(operation="pr_list", ctx=_ctx(), repo="owner/repo")
    assert result.success
    assert result.result == "not json at all"

  @pytest.mark.asyncio
  async def test_empty_pr_list_stays_empty(self, mocker: MockerFixture) -> None:
    _mock_popen(mocker, stdout="[]")
    result = await github(operation="pr_list", ctx=_ctx(), repo="owner/repo")
    assert result.success
    assert result.result == "[]"


class TestFieldsParameter:
  """Validation of the fields parameter and its dispatch."""

  @pytest.mark.asyncio
  async def test_invalid_field_rejected_with_allowed_set(self, mocker: MockerFixture) -> None:
    _mock_popen(mocker)
    result = await github(
      operation="pr_list", ctx=_ctx(), repo="owner/repo", fields="number,bogusField"
    )
    assert not result.success
    assert "bogusField" in result.error
    assert "statusCheckRollup" in result.error  # allowed set is listed

  @pytest.mark.asyncio
  async def test_fields_rejected_for_other_ops(self, mocker: MockerFixture) -> None:
    _mock_popen(mocker)
    result = await github(operation="repo_view", ctx=_ctx(), fields="number")
    assert not result.success
    assert "fields" in result.error

  @pytest.mark.asyncio
  async def test_fields_forbidden_chars_rejected(self, mocker: MockerFixture) -> None:
    _mock_popen(mocker)
    result = await github(operation="pr_list", ctx=_ctx(), repo="owner/repo", fields="number;ls")
    assert not result.success
    assert "forbidden" in result.error

  @pytest.mark.asyncio
  async def test_fields_only_field_names_dispatch(self, mocker: MockerFixture) -> None:
    """Explicit valid fields reach gh as --json <fields>."""
    popen = _mock_popen(mocker, stdout="[]")
    await github(operation="issue_list", ctx=_ctx(), repo="owner/repo", fields="number,title")
    cmd = popen.call_args.args[0]
    json_idx = cmd.index("--json")
    assert cmd[json_idx + 1] == "number,title"

  def test_default_pr_list_fields_unchanged(self) -> None:
    """The compact default still fetches the full default field set from gh."""
    cmd = github_module._build_command("pr_list", "owner/repo", None, "", 30, "open", "", None)
    json_idx = cmd.index("--json")
    fields = cmd[json_idx + 1]
    assert "reviewDecision" in fields
    assert "statusCheckRollup" in fields

  def test_dispatch_selects_explicit_fields(self) -> None:
    cmd = github_module._build_command(
      "pr_list", "owner/repo", None, "", 30, "open", "", "number,title"
    )
    json_idx = cmd.index("--json")
    assert cmd[json_idx + 1] == "number,title"
    assert "--repo" in cmd and "owner/repo" in cmd

  def test_dispatch_repo_view_positional(self) -> None:
    cmd = github_module._build_command("repo_view", "owner/repo", None, "", 30, "open", "", None)
    assert cmd[:4] == ["gh", "repo", "view", "owner/repo"]
    assert "--repo" not in cmd
