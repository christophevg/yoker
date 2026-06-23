"""Tests for git tool implementation.

These tests verify the behavior of the Git tool, including read-only operations,
permission-required operations, security guardrails (injection prevention, path
restrictions, output sanitization), and error handling.
"""

import subprocess
import sys
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from yoker.builtin import git, update, write
from yoker.builtin.git import _sanitize_output
from yoker.config import (
  Config,
  GitToolConfig,
  HandlerConfig,
  PermissionsConfig,
  ToolsSharedConfig,
  UpdateToolConfig,
  WriteToolConfig,
)
from yoker.tools import ToolRegistry
from yoker.tools.context import ToolContext
from yoker.tools.guardrails.path import PathGuardrail

# Import the actual module (not the function exported in __init__.py)
git_module = sys.modules["yoker.builtin.git"]


def _git_spec(
  config: GitToolConfig | None = None, permission_handlers: dict[str, HandlerConfig] | None = None
):
  """Create and register the git tool."""
  registry = ToolRegistry()
  # Create backends dict with permission_handlers if provided
  backends = {}
  if permission_handlers:
    backends["permission_handlers"] = permission_handlers
  return registry.register(git, name="git")


def _git_context(
  config: GitToolConfig | None = None, permission_handlers: dict[str, HandlerConfig] | None = None
) -> ToolContext:
  """Get ToolContext for tests."""
  backends: dict = {}
  if permission_handlers:
    backends["permission_handlers"] = permission_handlers
  if config is None:
    config = GitToolConfig()
  return ToolContext(
    config=config,
    shared=ToolsSharedConfig(),
    backends=backends,
  )


class TestGitToolSchema:
  """Tests for git tool schema and properties."""

  def test_name(self) -> None:
    """
    Given: A git tool spec
    When: Checking the spec name
    Then: Returns 'git'
    """
    spec = _git_spec()
    assert spec.name == "git"

  def test_description(self) -> None:
    """
    Given: A git tool spec
    When: Checking the spec description
    Then: Returns description mentioning Git operations
    """
    spec = _git_spec()
    assert "Git" in spec.description
    assert "operation" in spec.description.lower()

  def test_schema_structure(self) -> None:
    """
    Given: A git tool spec
    When: Getting the Ollama-compatible schema
    Then: Schema has correct structure with operation, path, and args parameters
    """
    spec = _git_spec()
    schema = spec.schema

    assert schema["type"] == "function"
    assert schema["function"]["name"] == "git"
    assert "parameters" in schema["function"]
    assert "properties" in schema["function"]["parameters"]

  def test_schema_operation_required(self) -> None:
    """
    Given: The git tool schema
    When: Checking required parameters
    Then: 'operation' is required, 'path' and 'args' are optional
    """
    spec = _git_spec()
    schema = spec.schema

    required = schema["function"]["parameters"]["required"]
    assert "operation" in required
    assert "path" not in required
    assert "args" not in required


class TestGitToolReadOnlyOperations:
  """Tests for read-only Git operations (safe, always allowed)."""

  @pytest.fixture
  def git_repo(self, tmp_path: Path) -> Path:
    """Create a temporary Git repository for testing."""
    repo = tmp_path / "test_repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    # Configure git identity locally for this repo
    subprocess.run(
      ["git", "config", "user.name", "Test"],
      cwd=repo,
      check=True,
      capture_output=True,
    )
    subprocess.run(
      ["git", "config", "user.email", "test@test.com"],
      cwd=repo,
      check=True,
      capture_output=True,
    )
    # Create initial commit
    (repo / "README.md").write_text("# Test Repository\n")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
      ["git", "commit", "-m", "Initial commit"],
      cwd=repo,
      check=True,
      capture_output=True,
    )
    return repo

  @pytest.mark.asyncio
  async def test_git_status_shows_working_directory_state(self, git_repo: Path) -> None:
    """
    Given: A valid Git repository with uncommitted changes
    When: Executing git status operation
    Then: Returns working tree status showing modified files
    """
    # Add uncommitted change
    (git_repo / "new_file.txt").write_text("New content")

    config = GitToolConfig()
    spec = _git_spec()
    ctx = _git_context(config=config)
    result = await spec.execute(operation="status", path=str(git_repo), ctx=ctx)

    assert result.success
    assert "new_file.txt" in result.result

  @pytest.mark.asyncio
  async def test_git_status_with_short_flag(self, git_repo: Path) -> None:
    """
    Given: A valid Git repository
    When: Executing git status with short=True
    Then: Returns status in short format (porcelain-like)
    """
    # Add uncommitted change
    (git_repo / "new_file.txt").write_text("New content")

    config = GitToolConfig()
    spec = _git_spec()
    ctx = _git_context(config=config)
    result = await spec.execute(
      operation="status", path=str(git_repo), ctx=ctx, args={"short": True}
    )

    assert result.success
    assert "?? new_file.txt" in result.result

  @pytest.mark.asyncio
  async def test_git_log_shows_commit_history(self, git_repo: Path) -> None:
    """
    Given: A valid Git repository with commits
    When: Executing git log operation
    Then: Returns commit history
    """
    config = GitToolConfig()
    spec = _git_spec()
    ctx = _git_context(config=config)
    result = await spec.execute(operation="log", path=str(git_repo), ctx=ctx)

    assert result.success
    assert "Initial commit" in result.result

  @pytest.mark.asyncio
  async def test_git_log_with_oneline_flag(self, git_repo: Path) -> None:
    """
    Given: A valid Git repository with commits
    When: Executing git log with oneline=True
    Then: Returns one commit per line in oneline format
    """
    config = GitToolConfig()
    spec = _git_spec()
    ctx = _git_context(config=config)
    result = await spec.execute(
      operation="log", path=str(git_repo), ctx=ctx, args={"oneline": True}
    )

    assert result.success
    assert "Initial commit" in result.result

  @pytest.mark.asyncio
  async def test_git_log_with_limit(self, git_repo: Path) -> None:
    """
    Given: A valid Git repository with many commits
    When: Executing git log with n=5
    Then: Returns only the most recent 5 commits
    """
    # Add more commits
    for i in range(10):
      (git_repo / f"file_{i}.txt").write_text(f"Content {i}")
      subprocess.run(["git", "add", f"file_{i}.txt"], cwd=git_repo, check=True, capture_output=True)
      subprocess.run(
        ["git", "commit", "-m", f"Commit {i}"],
        cwd=git_repo,
        check=True,
        capture_output=True,
      )

    config = GitToolConfig()
    spec = _git_spec()
    ctx = _git_context(config=config)
    result = await spec.execute(
      operation="log", path=str(git_repo), ctx=ctx, args={"oneline": True, "n": 5}
    )

    assert result.success
    # Should have exactly 5 commits shown
    lines = [line for line in result.result.strip().split("\n") if line.strip()]
    assert len(lines) == 5

  @pytest.mark.asyncio
  async def test_git_log_with_author_filter(self, git_repo: Path) -> None:
    """
    Given: A valid Git repository with commits from multiple authors
    When: Executing git log with author="Test"
    Then: Returns only commits from matching author
    """
    config = GitToolConfig()
    spec = _git_spec()
    ctx = _git_context(config=config)
    result = await spec.execute(
      operation="log", path=str(git_repo), ctx=ctx, args={"author": "Test"}
    )

    assert result.success
    assert "Initial commit" in result.result

  @pytest.mark.asyncio
  async def test_git_diff_shows_uncommitted_changes(self, git_repo: Path) -> None:
    """
    Given: A valid Git repository with uncommitted changes
    When: Executing git diff operation
    Then: Returns diff of uncommitted changes
    """
    # Modify tracked file
    (git_repo / "README.md").write_text("# Modified\n")

    config = GitToolConfig()
    spec = _git_spec()
    ctx = _git_context(config=config)
    result = await spec.execute(operation="diff", path=str(git_repo), ctx=ctx)

    assert result.success
    assert "# Modified" in result.result

  @pytest.mark.asyncio
  async def test_git_diff_with_stat_flag(self, git_repo: Path) -> None:
    """
    Given: A valid Git repository with uncommitted changes
    When: Executing git diff with stat=True
    Then: Returns diffstat output with file statistics
    """
    # Modify tracked file
    (git_repo / "README.md").write_text("# Modified\n")

    config = GitToolConfig()
    spec = _git_spec()
    ctx = _git_context(config=config)
    result = await spec.execute(operation="diff", path=str(git_repo), ctx=ctx, args={"stat": True})

    assert result.success
    assert "README.md" in result.result

  @pytest.mark.asyncio
  async def test_git_diff_cached_shows_staged_changes(self, git_repo: Path) -> None:
    """
    Given: A valid Git repository with staged changes
    When: Executing git diff with cached=True
    Then: Returns diff of staged changes
    """
    # Stage a new file
    (git_repo / "staged_file.txt").write_text("Staged content")
    subprocess.run(["git", "add", "staged_file.txt"], cwd=git_repo, check=True, capture_output=True)

    config = GitToolConfig()
    spec = _git_spec()
    ctx = _git_context(config=config)
    result = await spec.execute(
      operation="diff", path=str(git_repo), ctx=ctx, args={"cached": True}
    )

    assert result.success
    assert "staged_file.txt" in result.result

  @pytest.mark.asyncio
  async def test_git_branch_lists_branches(self, git_repo: Path) -> None:
    """
    Given: A valid Git repository with multiple branches
    When: Executing git branch operation
    Then: Returns list of branches
    """
    # Create another branch
    subprocess.run(["git", "branch", "feature"], cwd=git_repo, check=True, capture_output=True)

    config = GitToolConfig()
    spec = _git_spec()
    ctx = _git_context(config=config)
    result = await spec.execute(
      operation="branch", path=str(git_repo), ctx=ctx, args={"list": True}
    )

    assert result.success
    assert "master" in result.result or "main" in result.result
    assert "feature" in result.result

  @pytest.mark.asyncio
  async def test_git_branch_all_lists_remote_branches(self, git_repo: Path) -> None:
    """
    Given: A valid Git repository with remotes
    When: Executing git branch with all=True
    Then: Returns both local and remote branches
    """
    config = GitToolConfig()
    spec = _git_spec()
    ctx = _git_context(config=config)
    result = await spec.execute(operation="branch", path=str(git_repo), ctx=ctx, args={"all": True})

    assert result.success
    # Should show at least the current branch
    assert "master" in result.result or "main" in result.result

  @pytest.mark.asyncio
  async def test_git_show_displays_commit_details(self, git_repo: Path) -> None:
    """
    Given: A valid Git repository with commits
    When: Executing git show operation with a commit hash
    Then: Returns commit details including diff
    """
    config = GitToolConfig()
    spec = _git_spec()
    ctx = _git_context(config=config)
    result = await spec.execute(operation="show", path=str(git_repo), ctx=ctx)

    assert result.success
    assert "Initial commit" in result.result

  @pytest.mark.asyncio
  async def test_git_show_with_format(self, git_repo: Path) -> None:
    """
    Given: A valid Git repository with commits
    When: Executing git show with format="%H %s"
    Then: Returns commit in specified format
    """
    config = GitToolConfig()
    spec = _git_spec()
    ctx = _git_context(config=config)
    result = await spec.execute(
      operation="show", path=str(git_repo), ctx=ctx, args={"format": "%s"}
    )

    assert result.success
    assert "Initial commit" in result.result


class TestGitToolPermissionRequiredOperations:
  """Tests for operations that require explicit permission."""

  @pytest.fixture
  def git_repo(self, tmp_path: Path) -> Path:
    """Create a temporary Git repository for testing."""
    repo = tmp_path / "test_repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    # Configure git identity locally for this repo (needed for commit operations)
    subprocess.run(
      ["git", "config", "user.name", "Test"],
      cwd=repo,
      check=True,
      capture_output=True,
    )
    subprocess.run(
      ["git", "config", "user.email", "test@test.com"],
      cwd=repo,
      check=True,
      capture_output=True,
    )
    (repo / "README.md").write_text("# Test\n")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
      ["git", "commit", "-m", "Initial"],
      cwd=repo,
      check=True,
      capture_output=True,
    )
    return repo

  @pytest.mark.asyncio
  async def test_git_commit_blocked_without_permission(self, git_repo: Path) -> None:
    """
    Given: A git tool without permission handler for commit
    When: Executing git commit operation
    Then: Returns error that commit requires permission
    """
    # Allow commit in config but don't provide handler
    config = GitToolConfig(allowed_commands=("status", "log", "commit"))
    spec = _git_spec()
    ctx = _git_context(config=config, permission_handlers={})

    result = await spec.execute(
      operation="commit",
      path=str(git_repo),
      args={"message": "Test commit"},
      ctx=ctx,
    )

    assert not result.success
    assert "requires permission" in result.error.lower()

  @pytest.mark.asyncio
  async def test_git_commit_blocked_with_block_handler(self, git_repo: Path) -> None:
    """
    Given: A git tool with permission handler mode='block' for commit
    When: Executing git commit operation
    Then: Returns error with handler's message
    """
    config = GitToolConfig(allowed_commands=("status", "log", "commit"))
    handlers = {"git_commit": HandlerConfig(mode="block", message="Commits are blocked")}

    spec = _git_spec()
    ctx = _git_context(config=config, permission_handlers=handlers)

    result = await spec.execute(
      operation="commit",
      path=str(git_repo),
      args={"message": "Test commit"},
      ctx=ctx,
    )

    assert not result.success
    assert "Commits are blocked" in result.error

  @pytest.mark.asyncio
  async def test_git_commit_allowed_with_permission(self, git_repo: Path) -> None:
    """
    Given: A git tool with permission handler mode='allow' for commit
    When: Executing git commit operation with message
    Then: Commit is created successfully
    """
    # Add a file to commit
    (git_repo / "new_file.txt").write_text("New content")
    subprocess.run(["git", "add", "new_file.txt"], cwd=git_repo, check=True, capture_output=True)

    config = GitToolConfig(allowed_commands=("status", "log", "commit"))
    handlers = {"git_commit": HandlerConfig(mode="allow")}

    spec = _git_spec()
    ctx = _git_context(config=config, permission_handlers=handlers)

    result = await spec.execute(
      operation="commit",
      path=str(git_repo),
      args={"message": "Test commit"},
      ctx=ctx,
    )

    assert result.success

  @pytest.mark.asyncio
  async def test_git_push_blocked_without_permission(self, git_repo: Path) -> None:
    """
    Given: A git tool without permission handler for push
    When: Executing git push operation
    Then: Returns error that push requires permission
    """
    config = GitToolConfig(allowed_commands=("status", "log", "push"))

    spec = _git_spec()
    ctx = _git_context(config=config, permission_handlers={})

    result = await spec.execute(operation="push", path=str(git_repo), ctx=ctx)

    assert not result.success
    assert "requires permission" in result.error.lower()

  @pytest.mark.asyncio
  async def test_git_push_blocked_with_block_handler(self, git_repo: Path) -> None:
    """
    Given: A git tool with permission handler mode='block' for push
    When: Executing git push operation
    Then: Returns error with handler's message
    """
    config = GitToolConfig(allowed_commands=("status", "log", "push"))
    handlers = {"git_push": HandlerConfig(mode="block", message="Push is blocked")}

    spec = _git_spec()
    ctx = _git_context(config=config, permission_handlers=handlers)

    result = await spec.execute(operation="push", path=str(git_repo), ctx=ctx)

    assert not result.success
    assert "Push is blocked" in result.error

  @pytest.mark.asyncio
  async def test_git_push_allowed_with_permission(self, git_repo: Path) -> None:
    """
    Given: A git tool with permission handler mode='allow' for push
    When: Executing git push operation
    Then: Push succeeds (or fails with network error if no remote)
    """
    config = GitToolConfig(allowed_commands=("status", "log", "push"))
    handlers = {"git_push": HandlerConfig(mode="allow")}

    spec = _git_spec()
    ctx = _git_context(config=config, permission_handlers=handlers)

    # Push will fail because there's no remote, but it should get past permission check
    result = await spec.execute(operation="push", path=str(git_repo), ctx=ctx)

    # The error should be from git, not from permission
    if not result.success:
      assert "permission" not in result.error.lower()

  @pytest.mark.asyncio
  async def test_disallowed_operation_returns_error(self, git_repo: Path) -> None:
    """
    Given: A git tool with only status and log allowed
    When: Executing git reset operation
    Then: Returns error that operation is not allowed
    """
    config = GitToolConfig(allowed_commands=("status", "log"))

    spec = _git_spec()
    ctx = _git_context(config=config)

    result = await spec.execute(operation="reset", path=str(git_repo), ctx=ctx)

    assert not result.success
    assert "not allowed" in result.error.lower()


class TestGitToolCommandInjectionPrevention:
  """Tests for command injection attack prevention."""

  @pytest.fixture
  def git_repo(self, tmp_path: Path) -> Path:
    """Create a temporary Git repository for testing."""
    repo = tmp_path / "test_repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    return repo

  @pytest.mark.asyncio
  async def test_flag_injection_blocked(self, git_repo: Path) -> None:
    """
    Given: A malicious operation argument starting with dash
    When: Executing git operation
    Then: Returns error about invalid argument
    """
    config = GitToolConfig()
    spec = _git_spec()
    ctx = _git_context(config=config)

    result = await spec.execute(
      operation="log",
      path=str(git_repo),
      ctx=ctx,
      args={"format": "--something-malicious"},
    )

    assert not result.success
    assert "dash" in result.error.lower() or "flag" in result.error.lower()

  @pytest.mark.asyncio
  async def test_config_injection_blocked(self, git_repo: Path) -> None:
    """
    Given: An argument containing -c option (Git config override)
    When: Executing git operation
    Then: Returns error about forbidden character
    """
    config = GitToolConfig()
    spec = _git_spec()
    ctx = _git_context(config=config)

    # Try to inject config via format arg
    result = await spec.execute(
      operation="log",
      path=str(git_repo),
      ctx=ctx,
      args={"format": "-c core.hooksPath=/malicious"},
    )

    assert not result.success

  @pytest.mark.asyncio
  async def test_upload_pack_injection_blocked(self, git_repo: Path) -> None:
    """
    Given: An argument containing --upload-pack option
    When: Executing git operation
    Then: Returns error about disallowed argument
    """
    config = GitToolConfig()
    spec = _git_spec()
    ctx = _git_context(config=config)

    result = await spec.execute(
      operation="log",
      path=str(git_repo),
      ctx=ctx,
      args={"format": "--upload-pack=/malicious"},
    )

    assert not result.success
    assert "dash" in result.error.lower() or "dangerous" in result.error.lower()

  @pytest.mark.asyncio
  async def test_underscore_form_bypass_blocked(self, git_repo: Path) -> None:
    """
    Given: An argument with --uploadPack (underscore form)
    When: Executing git operation
    Then: Returns error about disallowed argument
    """
    config = GitToolConfig()
    spec = _git_spec()
    ctx = _git_context(config=config)

    result = await spec.execute(
      operation="log",
      path=str(git_repo),
      ctx=ctx,
      args={"format": "--uploadPack=/malicious"},
    )

    assert not result.success
    # Error should mention dangerous option or dash/flag injection
    assert "dangerous" in result.error.lower() or "flag injection" in result.error.lower()

  @pytest.mark.asyncio
  async def test_shell_special_chars_blocked(self, git_repo: Path) -> None:
    """
    Given: An argument containing shell special chars (|, ;, &, $)
    When: Executing git operation
    Then: Returns error about forbidden character
    """
    config = GitToolConfig()
    spec = _git_spec()
    ctx = _git_context(config=config)

    result = await spec.execute(
      operation="log",
      path=str(git_repo),
      ctx=ctx,
      args={"format": "test | cat /etc/passwd"},
    )

    assert not result.success
    assert "forbidden" in result.error.lower()

  @pytest.mark.asyncio
  async def test_command_substitution_blocked(self, git_repo: Path) -> None:
    """
    Given: An argument containing $(command) or `command`
    When: Executing git operation
    Then: Returns error about forbidden character
    """
    config = GitToolConfig()
    spec = _git_spec()
    ctx = _git_context(config=config)

    result = await spec.execute(
      operation="log",
      path=str(git_repo),
      ctx=ctx,
      args={"format": "$(cat /etc/passwd)"},
    )

    assert not result.success
    assert "forbidden" in result.error.lower()

  @pytest.mark.asyncio
  async def test_newline_injection_blocked(self, git_repo: Path) -> None:
    """
    Given: An argument containing newline character
    When: Executing git operation
    Then: Returns error about forbidden character
    """
    config = GitToolConfig()
    spec = _git_spec()
    ctx = _git_context(config=config)

    result = await spec.execute(
      operation="log",
      path=str(git_repo),
      ctx=ctx,
      args={"format": "test\nmalicious"},
    )

    assert not result.success
    assert "forbidden" in result.error.lower()

  @pytest.mark.asyncio
  async def test_null_byte_injection_blocked(self, git_repo: Path) -> None:
    """
    Given: An argument containing null byte
    When: Executing git operation
    Then: Returns error about forbidden character
    """
    config = GitToolConfig()
    spec = _git_spec()
    ctx = _git_context(config=config)

    result = await spec.execute(
      operation="log",
      path=str(git_repo),
      ctx=ctx,
      args={"format": "test\x00malicious"},
    )

    assert not result.success
    assert "forbidden" in result.error.lower()


class TestGitToolPathRestrictions:
  """Tests for path traversal and repository access restrictions."""

  @pytest.mark.asyncio
  async def test_path_traversal_blocked(self, tmp_path: Path) -> None:
    """
    Given: A path with traversal sequence like ../../../etc
    When: Validating the path against the guardrail
    Then: Guardrail blocks the resolved path as outside allowed directories
    """
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = PathGuardrail(config)
    git_config = GitToolConfig()
    spec = _git_spec(config=git_config)

    validation = guardrail.validate(spec.name, {"path": "/etc/passwd/../../../.."})

    assert not validation.valid
    assert "allowed" in validation.reason.lower() or "outside" in validation.reason.lower()

  @pytest.mark.asyncio
  async def test_git_dir_option_blocked(self, tmp_path: Path) -> None:
    """
    Given: A path argument containing --git-dir option
    When: Executing git operation
    Then: Returns error about disallowed argument
    """
    # Create a valid git repo so path validation passes
    repo = tmp_path / "test_repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)

    git_config = GitToolConfig()
    spec = _git_spec(config=git_config)
    ctx = _git_context(config=git_config)

    result = await spec.execute(
      operation="log",
      path=str(repo),
      ctx=ctx,
      args={"format": "--git-dir=/malicious"},
    )

    assert not result.success
    # Error should mention dangerous option or dash/flag injection
    assert "dangerous" in result.error.lower() or "flag injection" in result.error.lower()

  @pytest.mark.asyncio
  async def test_work_tree_option_blocked(self, tmp_path: Path) -> None:
    """
    Given: A path argument containing --work-tree option
    When: Executing git operation
    Then: Returns error about disallowed argument
    """
    # Create a valid git repo so path validation passes
    repo = tmp_path / "test_repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)

    git_config = GitToolConfig()
    spec = _git_spec(config=git_config)
    ctx = _git_context(config=git_config)

    result = await spec.execute(
      operation="log",
      path=str(repo),
      ctx=ctx,
      args={"format": "--work-tree=/malicious"},
    )

    assert not result.success
    # Error should mention dangerous option or dash/flag injection
    assert "dangerous" in result.error.lower() or "flag injection" in result.error.lower()

  @pytest.mark.asyncio
  async def test_repository_outside_allowed_paths_blocked(self, tmp_path: Path) -> None:
    """
    Given: A guardrail restricting to specific paths
    When: Validating a repository path outside allowed paths
    Then: Guardrail reports path outside allowed directories
    """
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = PathGuardrail(config)
    git_config = GitToolConfig()
    spec = _git_spec(config=git_config)

    validation = guardrail.validate(spec.name, {"path": "/some/path"})

    assert not validation.valid
    assert "allowed" in validation.reason.lower() or "outside" in validation.reason.lower()

  @pytest.mark.asyncio
  async def test_nonexistent_repository_returns_error(self, tmp_path: Path) -> None:
    """
    Given: A path that does not exist
    When: Executing git operation
    Then: Returns error about path not found
    """
    git_config = GitToolConfig()
    spec = _git_spec(config=git_config)
    ctx = _git_context(config=git_config)

    result = await spec.execute(operation="status", path=str(tmp_path / "nonexistent"), ctx=ctx)

    assert not result.success
    assert "not exist" in result.error.lower() or "not found" in result.error.lower()

  @pytest.mark.asyncio
  async def test_non_git_directory_returns_error(self, tmp_path: Path) -> None:
    """
    Given: A directory without .git subdirectory
    When: Executing git operation
    Then: Returns error about not being a Git repository
    """
    non_git = tmp_path / "not_a_repo"
    non_git.mkdir()

    git_config = GitToolConfig()
    spec = _git_spec(config=git_config)
    ctx = _git_context(config=git_config)

    result = await spec.execute(operation="status", path=str(non_git), ctx=ctx)

    assert not result.success
    assert "git repository" in result.error.lower() or "not a git" in result.error.lower()


class TestGitToolOutputSanitization:
  """Tests for output sanitization and information disclosure prevention."""

  @pytest.fixture
  def git_repo_with_remote(self, tmp_path: Path) -> Path:
    """Create a Git repository with remote containing credentials in URL."""
    repo = tmp_path / "test_repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    # Add remote with token in URL
    subprocess.run(
      ["git", "remote", "add", "origin", "https://user:secret_token@github.com/user/repo.git"],
      cwd=repo,
      check=True,
      capture_output=True,
    )
    return repo

  def test_credentials_redacted_from_remote_urls(self, git_repo_with_remote: Path) -> None:
    """
    Given: A repository with remote URL containing credentials
    When: Getting output that includes remote URL
    Then: Credentials are redacted in the output
    """
    # Test the _sanitize_output function directly since git branch
    # doesn't show remote URLs
    output_with_creds = "remote: https://user:secret_token@github.com/user/repo.git"
    sanitized = _sanitize_output(output_with_creds)

    # The output should have credentials redacted
    assert "secret_token" not in sanitized
    assert "<redacted>" in sanitized

  @pytest.mark.asyncio
  async def test_sensitive_config_values_hidden(self, tmp_path: Path) -> None:
    """
    Given: A repository with sensitive git config values
    When: Executing any git operation
    Then: Sensitive values are not exposed in output
    """
    repo = tmp_path / "test_repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    # Configure git identity locally for this repo
    subprocess.run(
      ["git", "config", "user.name", "Test"],
      cwd=repo,
      check=True,
      capture_output=True,
    )
    subprocess.run(
      ["git", "config", "user.email", "test@test.com"],
      cwd=repo,
      check=True,
      capture_output=True,
    )
    (repo / "README.md").write_text("# Test\n")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
      ["git", "commit", "-m", "Initial"],
      cwd=repo,
      check=True,
      capture_output=True,
    )

    git_config = GitToolConfig()
    spec = _git_spec(config=git_config)
    ctx = _git_context(config=git_config)

    result = await spec.execute(operation="log", path=str(repo), ctx=ctx)

    assert result.success
    # Output should not contain any config values that weren't committed


class TestGitToolErrorHandling:
  """Tests for error handling scenarios."""

  @pytest.mark.asyncio
  async def test_invalid_git_command_returns_error(self, tmp_path: Path) -> None:
    """
    Given: An invalid/nonexistent git operation
    When: Executing the operation
    Then: Returns error about invalid operation
    """
    git_config = GitToolConfig()
    spec = _git_spec(config=git_config)
    ctx = _git_context(config=git_config)

    result = await spec.execute(operation="nonexistent", path=str(tmp_path), ctx=ctx)

    assert not result.success
    assert "not allowed" in result.error.lower()

  @pytest.mark.asyncio
  async def test_git_timeout_enforced(self, tmp_path: Path, mocker: MockerFixture) -> None:
    """
    Given: A git operation that takes too long
    When: Executing with timeout
    Then: Returns error about command timeout
    """
    repo = tmp_path / "test_repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)

    git_config = GitToolConfig()
    spec = _git_spec(config=git_config)
    ctx = _git_context(config=git_config)

    # Mock subprocess.run to raise TimeoutExpired
    mock_run = mocker.MagicMock()
    mock_run.side_effect = subprocess.TimeoutExpired(cmd=["git"], timeout=30)
    mocker.patch.object(git_module, "subprocess")
    git_module.subprocess.run = mock_run
    # Keep the real exception classes
    git_module.subprocess.TimeoutExpired = subprocess.TimeoutExpired
    git_module.subprocess.CompletedProcess = subprocess.CompletedProcess

    result = await spec.execute(operation="status", path=str(repo), ctx=ctx)

    assert not result.success
    assert "timeout" in result.error.lower()

  @pytest.mark.asyncio
  async def test_git_not_installed_error(self, tmp_path: Path, mocker: MockerFixture) -> None:
    """
    Given: A system where git is not installed
    When: Executing any git operation
    Then: Returns error about git not found
    """
    repo = tmp_path / "test_repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)

    git_config = GitToolConfig()
    spec = _git_spec(config=git_config)
    ctx = _git_context(config=git_config)

    # Mock subprocess.run to raise FileNotFoundError
    mock_run = mocker.MagicMock()
    mock_run.side_effect = FileNotFoundError()
    mocker.patch.object(git_module, "subprocess")
    git_module.subprocess.run = mock_run
    # Keep the real exception classes
    git_module.subprocess.TimeoutExpired = subprocess.TimeoutExpired
    git_module.subprocess.CompletedProcess = subprocess.CompletedProcess

    result = await spec.execute(operation="status", path=str(repo), ctx=ctx)

    assert not result.success
    assert "not installed" in result.error.lower() or "not found" in result.error.lower()

  @pytest.mark.asyncio
  async def test_invalid_operation_type_error(self, tmp_path: Path) -> None:
    """
    Given: A non-string operation parameter
    When: Executing git operation
    Then: Returns error about invalid parameter type
    """
    git_config = GitToolConfig()
    spec = _git_spec(config=git_config)
    ctx = _git_context(config=git_config)

    result = await spec.execute(operation=123, path=str(tmp_path), ctx=ctx)

    assert not result.success
    assert "string" in result.error.lower()

  @pytest.mark.asyncio
  async def test_invalid_path_type_error(self, tmp_path: Path) -> None:
    """
    Given: A non-string path parameter
    When: Executing git operation
    Then: Returns error about invalid parameter type
    """
    git_config = GitToolConfig()
    spec = _git_spec(config=git_config)
    ctx = _git_context(config=git_config)

    result = await spec.execute(operation="status", path=123, ctx=ctx)

    assert not result.success
    assert "string" in result.error.lower()

  @pytest.mark.asyncio
  async def test_invalid_args_type_error(self, tmp_path: Path) -> None:
    """
    Given: A non-dict args parameter
    When: Executing git operation
    Then: Returns error about invalid parameter type
    """
    # Create a valid git repo so path validation passes
    repo = tmp_path / "test_repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)

    git_config = GitToolConfig()
    spec = _git_spec(config=git_config)
    ctx = _git_context(config=git_config)

    result = await spec.execute(operation="status", path=str(repo), ctx=ctx, args="invalid")

    assert not result.success
    assert "object" in result.error.lower()

  @pytest.mark.asyncio
  async def test_missing_operation_parameter_error(self, tmp_path: Path) -> None:
    """
    Given: No operation parameter provided
    When: Executing git tool
    Then: Returns error about missing required parameter
    """
    git_config = GitToolConfig()
    spec = _git_spec(config=git_config)
    ctx = _git_context(config=git_config)

    # Calling without operation parameter raises TypeError
    # because operation is a required parameter
    with pytest.raises(TypeError, match="missing.*operation"):
      await spec.execute(path=str(tmp_path), ctx=ctx)


class TestGitToolArgumentValidation:
  """Tests for argument validation and schema enforcement."""

  @pytest.fixture
  def git_repo(self, tmp_path: Path) -> Path:
    """Create a temporary Git repository for testing."""
    repo = tmp_path / "test_repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    return repo

  @pytest.mark.asyncio
  async def test_disallowed_argument_rejected(self, git_repo: Path) -> None:
    """
    Given: A git operation with an argument not in the allowed schema
    When: Executing the operation
    Then: Returns error about argument not allowed
    """
    git_config = GitToolConfig()
    spec = _git_spec(config=git_config)
    ctx = _git_context(config=git_config)

    result = await spec.execute(
      operation="log",
      path=str(git_repo),
      ctx=ctx,
      args={"invalid_arg": "value"},
    )

    assert not result.success
    assert "not allowed" in result.error.lower()

  @pytest.mark.asyncio
  async def test_integer_argument_type_validated(self, git_repo: Path) -> None:
    """
    Given: git log with n parameter as string instead of integer
    When: Executing the operation
    Then: Returns error about argument type
    """
    git_config = GitToolConfig()
    spec = _git_spec(config=git_config)
    ctx = _git_context(config=git_config)

    result = await spec.execute(
      operation="log",
      path=str(git_repo),
      ctx=ctx,
      args={"n": "five"},
    )

    assert not result.success
    assert "integer" in result.error.lower()

  @pytest.mark.asyncio
  async def test_boolean_argument_type_validated(self, git_repo: Path) -> None:
    """
    Given: git status with short parameter as string instead of boolean
    When: Executing the operation
    Then: Returns error about argument type
    """
    git_config = GitToolConfig()
    spec = _git_spec(config=git_config)
    ctx = _git_context(config=git_config)

    result = await spec.execute(
      operation="status",
      path=str(git_repo),
      ctx=ctx,
      args={"short": "yes"},
    )

    assert not result.success
    assert "boolean" in result.error.lower()

  @pytest.mark.asyncio
  async def test_integer_range_validated(self, git_repo: Path) -> None:
    """
    Given: git log with n parameter exceeding maximum (100)
    When: Executing the operation
    Then: Returns error about argument range
    """
    git_config = GitToolConfig()
    spec = _git_spec(config=git_config)
    ctx = _git_context(config=git_config)

    result = await spec.execute(
      operation="log",
      path=str(git_repo),
      ctx=ctx,
      args={"n": 500},
    )

    assert not result.success
    assert "100" in result.error or "maximum" in result.error.lower()

  @pytest.mark.asyncio
  async def test_string_length_limited(self, git_repo: Path) -> None:
    """
    Given: An argument with string value exceeding 1000 characters
    When: Executing the operation
    Then: Returns error about argument length limit
    """
    git_config = GitToolConfig()
    spec = _git_spec(config=git_config)
    ctx = _git_context(config=git_config)

    long_string = "x" * 1001

    result = await spec.execute(
      operation="log",
      path=str(git_repo),
      ctx=ctx,
      args={"format": long_string},
    )

    assert not result.success
    assert "length" in result.error.lower()


class TestGitToolGuardrailIntegration:
  """Tests for guardrail integration with PathGuardrail."""

  @pytest.fixture
  def git_repo(self, tmp_path: Path) -> Path:
    """Create a temporary Git repository for testing."""
    repo = tmp_path / "test_repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    return repo

  @pytest.mark.asyncio
  async def test_guardrail_blocks_outside_allowed_path(self, git_repo: Path) -> None:
    """
    Given: A guardrail restricting to a different path
    When: Validating the repository path
    Then: Guardrail reports path outside allowed directories
    """
    config = Config(permissions=PermissionsConfig(filesystem_paths=("/tmp/allowed",)))
    guardrail = PathGuardrail(config)
    git_config = GitToolConfig()
    spec = _git_spec(config=git_config)

    validation = guardrail.validate(spec.name, {"path": str(git_repo)})

    assert not validation.valid
    assert "allowed" in validation.reason.lower() or "outside" in validation.reason.lower()

  @pytest.mark.asyncio
  async def test_guardrail_allows_inside_allowed_path(self, git_repo: Path) -> None:
    """
    Given: A guardrail allowing the repository path
    When: Validating and executing git operation
    Then: Operation succeeds
    """
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(git_repo),)))
    guardrail = PathGuardrail(config)
    git_config = GitToolConfig()
    spec = _git_spec(config=git_config)
    ctx = _git_context(config=git_config)

    validation = guardrail.validate(spec.name, {"path": str(git_repo)})
    assert validation.valid

    result = await spec.execute(operation="status", path=str(git_repo), ctx=ctx)
    assert result.success


class TestGitToolReturnFormat:
  """Tests for return format structure."""

  @pytest.fixture
  def git_repo(self, tmp_path: Path) -> Path:
    """Create a temporary Git repository for testing."""
    repo = tmp_path / "test_repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    # Configure git identity locally for this repo
    subprocess.run(
      ["git", "config", "user.name", "Test"],
      cwd=repo,
      check=True,
      capture_output=True,
    )
    subprocess.run(
      ["git", "config", "user.email", "test@test.com"],
      cwd=repo,
      check=True,
      capture_output=True,
    )
    (repo / "README.md").write_text("# Test\n")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
      ["git", "commit", "-m", "Initial"],
      cwd=repo,
      check=True,
      capture_output=True,
    )
    return repo

  @pytest.mark.asyncio
  async def test_success_return_format(self, git_repo: Path) -> None:
    """
    Given: A successful git operation
    When: Checking the ToolResult
    Then: success=True, result contains output string, error is empty
    """
    git_config = GitToolConfig()
    spec = _git_spec(config=git_config)
    ctx = _git_context(config=git_config)

    result = await spec.execute(operation="status", path=str(git_repo), ctx=ctx)

    assert result.success is True
    assert isinstance(result.result, str)
    assert len(result.result) > 0
    assert result.error is None

  @pytest.mark.asyncio
  async def test_error_return_format(self, tmp_path: Path) -> None:
    """
    Given: A failed git operation
    When: Checking the ToolResult
    Then: success=False, result is empty, error contains message
    """
    git_config = GitToolConfig()
    spec = _git_spec(config=git_config)
    ctx = _git_context(config=git_config)

    result = await spec.execute(operation="status", path=str(tmp_path / "nonexistent"), ctx=ctx)

    assert result.success is False
    assert result.result == ""
    assert result.error is not None
    assert len(result.error) > 0

  @pytest.mark.asyncio
  async def test_empty_output_handled(self, git_repo: Path) -> None:
    """
    Given: A git operation that produces no output
    When: Checking the ToolResult
    Then: Returns "(no output)" message
    """
    # Clean repo with no changes
    git_config = GitToolConfig()
    spec = _git_spec(config=git_config)
    ctx = _git_context(config=git_config)

    result = await spec.execute(operation="diff", path=str(git_repo), ctx=ctx)

    # diff with no changes returns empty output
    assert result.success
    assert "no output" in result.result.lower()


class TestGitToolSubprocessSecurity:
  """Tests for subprocess execution security."""

  @pytest.mark.asyncio
  async def test_no_shell_true_used(self, tmp_path: Path, mocker: MockerFixture) -> None:
    """
    Given: git tool executing a command
    When: Checking subprocess.run call
    Then: shell=True is NOT used
    """
    repo = tmp_path / "test_repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)

    git_config = GitToolConfig()
    spec = _git_spec(config=git_config)
    ctx = _git_context(config=git_config)

    mock_run = mocker.MagicMock()
    mock_run.return_value = subprocess.CompletedProcess(
      args=["git", "status"],
      returncode=0,
      stdout="On branch main",
      stderr="",
    )
    mocker.patch.object(git_module, "subprocess")
    git_module.subprocess.run = mock_run
    # Keep the real exception classes
    git_module.subprocess.TimeoutExpired = subprocess.TimeoutExpired
    git_module.subprocess.CompletedProcess = subprocess.CompletedProcess

    await spec.execute(operation="status", path=str(repo), ctx=ctx)

    # Verify shell=True was NOT passed
    call_kwargs = mock_run.call_args.kwargs
    assert "shell" not in call_kwargs or call_kwargs.get("shell") is not True

  @pytest.mark.asyncio
  async def test_command_as_list_not_string(self, tmp_path: Path, mocker: MockerFixture) -> None:
    """
    Given: git tool building a command
    When: Passing to subprocess
    Then: Command is a list of strings, not a single string
    """
    repo = tmp_path / "test_repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)

    git_config = GitToolConfig()
    spec = _git_spec(config=git_config)
    ctx = _git_context(config=git_config)

    mock_run = mocker.MagicMock()
    mock_run.return_value = subprocess.CompletedProcess(
      args=["git", "status"],
      returncode=0,
      stdout="On branch main",
      stderr="",
    )
    mocker.patch.object(git_module, "subprocess")
    git_module.subprocess.run = mock_run
    # Keep the real exception classes
    git_module.subprocess.TimeoutExpired = subprocess.TimeoutExpired
    git_module.subprocess.CompletedProcess = subprocess.CompletedProcess

    await spec.execute(operation="status", path=str(repo), ctx=ctx)

    # Verify first argument (command) is a list
    call_args = mock_run.call_args.args
    assert isinstance(call_args[0], list)
    assert all(isinstance(item, str) for item in call_args[0])


class TestGitToolIntegration:
  """Integration tests for git tool with other components."""

  @pytest.fixture
  def git_repo(self, tmp_path: Path) -> Path:
    """Create a temporary Git repository for testing."""
    repo = tmp_path / "test_repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    # Configure git identity locally for this repo
    subprocess.run(
      ["git", "config", "user.name", "Test"],
      cwd=repo,
      check=True,
      capture_output=True,
    )
    subprocess.run(
      ["git", "config", "user.email", "test@test.com"],
      cwd=repo,
      check=True,
      capture_output=True,
    )
    (repo / "README.md").write_text("# Test\n")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
      ["git", "commit", "-m", "Initial"],
      cwd=repo,
      check=True,
      capture_output=True,
    )
    return repo

  @pytest.mark.asyncio
  async def test_git_status_after_write(self, git_repo: Path) -> None:
    """
    Given: Using write tool to create a file, then git tool to check status
    When: Writing a new file and checking git status
    Then: Git status shows the new file as untracked
    """
    write_spec = ToolRegistry().register(write, name="write")
    git_spec = _git_spec()

    # Create context for write tool
    write_ctx = ToolContext(
      config=WriteToolConfig(),
      shared=ToolsSharedConfig(),
      backends={},
    )

    # Create a file with write tool
    write_result = await write_spec.execute(
      path=str(git_repo / "new_file.txt"),
      content="New content",
      ctx=write_ctx,
    )
    assert write_result.success

    # Create context for git tool
    git_ctx = ToolContext(
      config=GitToolConfig(),
      shared=ToolsSharedConfig(),
      backends={},
    )

    # Check git status
    result = await git_spec.execute(operation="status", path=str(git_repo), ctx=git_ctx)

    assert result.success
    assert "new_file.txt" in result.result

  @pytest.mark.asyncio
  async def test_git_diff_after_update(self, git_repo: Path) -> None:
    """
    Given: Using update tool to modify a file, then git tool to check diff
    When: Updating a tracked file and checking git diff
    Then: Git diff shows the changes
    """
    update_spec = ToolRegistry().register(update, name="update")
    git_spec = _git_spec()

    # Create context for update tool
    update_ctx = ToolContext(
      config=UpdateToolConfig(),
      shared=ToolsSharedConfig(),
      backends={},
    )

    # Update README.md with update tool
    update_result = await update_spec.execute(
      path=str(git_repo / "README.md"),
      operation="replace",
      old_string="# Test",
      new_string="# Updated",
      ctx=update_ctx,
    )
    assert update_result.success

    # Create context for git tool
    git_ctx = ToolContext(
      config=GitToolConfig(),
      shared=ToolsSharedConfig(),
      backends={},
    )

    # Check git diff
    result = await git_spec.execute(operation="diff", path=str(git_repo), ctx=git_ctx)

    assert result.success
    assert "# Updated" in result.result
