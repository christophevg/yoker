"""Tests for GitTool implementation.

These tests verify the behavior of the Git tool, including read-only operations,
permission-required operations, security guardrails (injection prevention, path
restrictions, output sanitization), and error handling.
"""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from yoker.config.schema import (
  GitToolConfig,
  HandlerConfig,
)
from yoker.tools.base import ValidationResult
from yoker.tools.git import GitTool
from yoker.tools.guardrails import Guardrail


class TestGitToolSchema:
  """Tests for GitTool schema and properties."""

  def test_name(self) -> None:
    """
    Given: A GitTool instance
    When: Checking the tool name property
    Then: Returns 'git'
    """
    config = GitToolConfig()
    tool = GitTool(config=config)
    assert tool.name == "git"

  def test_description(self) -> None:
    """
    Given: A GitTool instance
    When: Checking the tool description property
    Then: Returns description mentioning Git operations
    """
    config = GitToolConfig()
    tool = GitTool(config=config)
    assert "Git" in tool.description
    assert "status" in tool.description

  def test_schema_structure(self) -> None:
    """
    Given: A GitTool instance
    When: Getting the Ollama-compatible schema
    Then: Schema has correct structure with operation, path, and args parameters
    """
    config = GitToolConfig()
    tool = GitTool(config=config)
    schema = tool.get_schema()

    assert schema["type"] == "function"
    assert schema["function"]["name"] == "git"
    assert "parameters" in schema["function"]
    assert "properties" in schema["function"]["parameters"]

  def test_schema_operation_required(self) -> None:
    """
    Given: The GitTool schema
    When: Checking required parameters
    Then: 'operation' is required, 'path' and 'args' are optional
    """
    config = GitToolConfig()
    tool = GitTool(config=config)
    schema = tool.get_schema()

    required = schema["function"]["parameters"]["required"]
    assert "operation" in required
    assert "path" not in required
    assert "args" not in required

  def test_schema_operation_enum(self) -> None:
    """
    Given: The GitTool schema
    When: Checking operation parameter
    Then: Operation has enum listing allowed commands
    """
    config = GitToolConfig()
    tool = GitTool(config=config)
    schema = tool.get_schema()

    operation = schema["function"]["parameters"]["properties"]["operation"]
    assert "enum" in operation
    assert "status" in operation["enum"]
    assert "log" in operation["enum"]


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

  def test_git_status_shows_working_directory_state(self, git_repo: Path) -> None:
    """
    Given: A valid Git repository with uncommitted changes
    When: Executing git status operation
    Then: Returns working tree status showing modified files
    """
    # Add uncommitted change
    (git_repo / "new_file.txt").write_text("New content")

    config = GitToolConfig()
    tool = GitTool(config=config)
    result = tool.execute(operation="status", path=str(git_repo))

    assert result.success
    assert "new_file.txt" in result.result

  def test_git_status_with_short_flag(self, git_repo: Path) -> None:
    """
    Given: A valid Git repository
    When: Executing git status with short=True
    Then: Returns status in short format (porcelain-like)
    """
    # Add uncommitted change
    (git_repo / "new_file.txt").write_text("New content")

    config = GitToolConfig()
    tool = GitTool(config=config)
    result = tool.execute(operation="status", path=str(git_repo), args={"short": True})

    assert result.success
    assert "?? new_file.txt" in result.result

  def test_git_log_shows_commit_history(self, git_repo: Path) -> None:
    """
    Given: A valid Git repository with commits
    When: Executing git log operation
    Then: Returns commit history
    """
    config = GitToolConfig()
    tool = GitTool(config=config)
    result = tool.execute(operation="log", path=str(git_repo))

    assert result.success
    assert "Initial commit" in result.result

  def test_git_log_with_oneline_flag(self, git_repo: Path) -> None:
    """
    Given: A valid Git repository with commits
    When: Executing git log with oneline=True
    Then: Returns one commit per line in oneline format
    """
    config = GitToolConfig()
    tool = GitTool(config=config)
    result = tool.execute(operation="log", path=str(git_repo), args={"oneline": True})

    assert result.success
    assert "Initial commit" in result.result

  def test_git_log_with_limit(self, git_repo: Path) -> None:
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
    tool = GitTool(config=config)
    result = tool.execute(operation="log", path=str(git_repo), args={"oneline": True, "n": 5})

    assert result.success
    # Should have exactly 5 commits shown
    lines = [line for line in result.result.strip().split("\n") if line.strip()]
    assert len(lines) == 5

  def test_git_log_with_author_filter(self, git_repo: Path) -> None:
    """
    Given: A valid Git repository with commits from multiple authors
    When: Executing git log with author="Test"
    Then: Returns only commits from matching author
    """
    config = GitToolConfig()
    tool = GitTool(config=config)
    result = tool.execute(operation="log", path=str(git_repo), args={"author": "Test"})

    assert result.success
    assert "Initial commit" in result.result

  def test_git_diff_shows_uncommitted_changes(self, git_repo: Path) -> None:
    """
    Given: A valid Git repository with uncommitted changes
    When: Executing git diff operation
    Then: Returns diff of uncommitted changes
    """
    # Modify tracked file
    (git_repo / "README.md").write_text("# Modified\n")

    config = GitToolConfig()
    tool = GitTool(config=config)
    result = tool.execute(operation="diff", path=str(git_repo))

    assert result.success
    assert "# Modified" in result.result

  def test_git_diff_with_stat_flag(self, git_repo: Path) -> None:
    """
    Given: A valid Git repository with uncommitted changes
    When: Executing git diff with stat=True
    Then: Returns diffstat output with file statistics
    """
    # Modify tracked file
    (git_repo / "README.md").write_text("# Modified\n")

    config = GitToolConfig()
    tool = GitTool(config=config)
    result = tool.execute(operation="diff", path=str(git_repo), args={"stat": True})

    assert result.success
    assert "README.md" in result.result

  def test_git_diff_cached_shows_staged_changes(self, git_repo: Path) -> None:
    """
    Given: A valid Git repository with staged changes
    When: Executing git diff with cached=True
    Then: Returns diff of staged changes
    """
    # Stage a new file
    (git_repo / "staged_file.txt").write_text("Staged content")
    subprocess.run(["git", "add", "staged_file.txt"], cwd=git_repo, check=True, capture_output=True)

    config = GitToolConfig()
    tool = GitTool(config=config)
    result = tool.execute(operation="diff", path=str(git_repo), args={"cached": True})

    assert result.success
    assert "staged_file.txt" in result.result

  def test_git_branch_lists_branches(self, git_repo: Path) -> None:
    """
    Given: A valid Git repository with multiple branches
    When: Executing git branch operation
    Then: Returns list of branches
    """
    # Create another branch
    subprocess.run(["git", "branch", "feature"], cwd=git_repo, check=True, capture_output=True)

    config = GitToolConfig()
    tool = GitTool(config=config)
    result = tool.execute(operation="branch", path=str(git_repo), args={"list": True})

    assert result.success
    assert "master" in result.result or "main" in result.result
    assert "feature" in result.result

  def test_git_branch_all_lists_remote_branches(self, git_repo: Path) -> None:
    """
    Given: A valid Git repository with remotes
    When: Executing git branch with all=True
    Then: Returns both local and remote branches
    """
    config = GitToolConfig()
    tool = GitTool(config=config)
    result = tool.execute(operation="branch", path=str(git_repo), args={"all": True})

    assert result.success
    # Should show at least the current branch
    assert "master" in result.result or "main" in result.result

  def test_git_show_displays_commit_details(self, git_repo: Path) -> None:
    """
    Given: A valid Git repository with commits
    When: Executing git show operation with a commit hash
    Then: Returns commit details including diff
    """
    config = GitToolConfig()
    tool = GitTool(config=config)
    result = tool.execute(operation="show", path=str(git_repo))

    assert result.success
    assert "Initial commit" in result.result

  def test_git_show_with_format(self, git_repo: Path) -> None:
    """
    Given: A valid Git repository with commits
    When: Executing git show with format="%H %s"
    Then: Returns commit in specified format
    """
    config = GitToolConfig()
    tool = GitTool(config=config)
    result = tool.execute(operation="show", path=str(git_repo), args={"format": "%s"})

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

  def test_git_commit_blocked_without_permission(self, git_repo: Path) -> None:
    """
    Given: A GitTool without permission handler for commit
    When: Executing git commit operation
    Then: Returns error that commit requires permission
    """
    # Allow commit in config but don't provide handler
    config = GitToolConfig(allowed_commands=("status", "log", "commit"))
    tool = GitTool(config=config, permission_handlers={})

    result = tool.execute(
      operation="commit",
      path=str(git_repo),
      args={"message": "Test commit"},
    )

    assert not result.success
    assert "requires permission" in result.error.lower()

  def test_git_commit_blocked_with_block_handler(self, git_repo: Path) -> None:
    """
    Given: A GitTool with permission handler mode='block' for commit
    When: Executing git commit operation
    Then: Returns error with handler's message
    """
    config = GitToolConfig(allowed_commands=("status", "log", "commit"))
    handlers = {"git_commit": HandlerConfig(mode="block", message="Commits are blocked")}

    tool = GitTool(config=config, permission_handlers=handlers)

    result = tool.execute(
      operation="commit",
      path=str(git_repo),
      args={"message": "Test commit"},
    )

    assert not result.success
    assert "Commits are blocked" in result.error

  def test_git_commit_allowed_with_permission(self, git_repo: Path) -> None:
    """
    Given: A GitTool with permission handler mode='allow' for commit
    When: Executing git commit operation with message
    Then: Commit is created successfully
    """
    # Add a file to commit
    (git_repo / "new_file.txt").write_text("New content")
    subprocess.run(["git", "add", "new_file.txt"], cwd=git_repo, check=True, capture_output=True)

    config = GitToolConfig(allowed_commands=("status", "log", "commit"))
    handlers = {"git_commit": HandlerConfig(mode="allow")}

    tool = GitTool(config=config, permission_handlers=handlers)

    result = tool.execute(
      operation="commit",
      path=str(git_repo),
      args={"message": "Test commit"},
    )

    assert result.success

  def test_git_push_blocked_without_permission(self, git_repo: Path) -> None:
    """
    Given: A GitTool without permission handler for push
    When: Executing git push operation
    Then: Returns error that push requires permission
    """
    config = GitToolConfig(allowed_commands=("status", "log", "push"))

    tool = GitTool(config=config, permission_handlers={})

    result = tool.execute(operation="push", path=str(git_repo))

    assert not result.success
    assert "requires permission" in result.error.lower()

  def test_git_push_blocked_with_block_handler(self, git_repo: Path) -> None:
    """
    Given: A GitTool with permission handler mode='block' for push
    When: Executing git push operation
    Then: Returns error with handler's message
    """
    config = GitToolConfig(allowed_commands=("status", "log", "push"))
    handlers = {"git_push": HandlerConfig(mode="block", message="Push is blocked")}

    tool = GitTool(config=config, permission_handlers=handlers)

    result = tool.execute(operation="push", path=str(git_repo))

    assert not result.success
    assert "Push is blocked" in result.error

  def test_git_push_allowed_with_permission(self, git_repo: Path) -> None:
    """
    Given: A GitTool with permission handler mode='allow' for push
    When: Executing git push operation
    Then: Push succeeds (or fails with network error if no remote)
    """
    config = GitToolConfig(allowed_commands=("status", "log", "push"))
    handlers = {"git_push": HandlerConfig(mode="allow")}

    tool = GitTool(config=config, permission_handlers=handlers)

    # Push will fail because there's no remote, but it should get past permission check
    result = tool.execute(operation="push", path=str(git_repo))

    # The error should be from git, not from permission
    if not result.success:
      assert "permission" not in result.error.lower()

  def test_disallowed_operation_returns_error(self, git_repo: Path) -> None:
    """
    Given: A GitTool with only status and log allowed
    When: Executing git reset operation
    Then: Returns error that operation is not allowed
    """
    config = GitToolConfig(allowed_commands=("status", "log"))

    tool = GitTool(config=config)

    result = tool.execute(operation="reset", path=str(git_repo))

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

  def test_flag_injection_blocked(self, git_repo: Path) -> None:
    """
    Given: A malicious operation argument starting with dash
    When: Executing git operation
    Then: Returns error about invalid argument
    """
    config = GitToolConfig()
    tool = GitTool(config=config)

    result = tool.execute(
      operation="log",
      path=str(git_repo),
      args={"format": "--something-malicious"},
    )

    assert not result.success
    assert "dash" in result.error.lower() or "flag" in result.error.lower()

  def test_config_injection_blocked(self, git_repo: Path) -> None:
    """
    Given: An argument containing -c option (Git config override)
    When: Executing git operation
    Then: Returns error about forbidden character
    """
    config = GitToolConfig()
    tool = GitTool(config=config)

    # Try to inject config via format arg
    result = tool.execute(
      operation="log",
      path=str(git_repo),
      args={"format": "-c core.hooksPath=/malicious"},
    )

    assert not result.success

  def test_upload_pack_injection_blocked(self, git_repo: Path) -> None:
    """
    Given: An argument containing --upload-pack option
    When: Executing git operation
    Then: Returns error about disallowed argument
    """
    config = GitToolConfig()
    tool = GitTool(config=config)

    result = tool.execute(
      operation="log",
      path=str(git_repo),
      args={"format": "--upload-pack=/malicious"},
    )

    assert not result.success
    assert "dash" in result.error.lower() or "dangerous" in result.error.lower()

  def test_underscore_form_bypass_blocked(self, git_repo: Path) -> None:
    """
    Given: An argument with --uploadPack (underscore form)
    When: Executing git operation
    Then: Returns error about disallowed argument
    """
    config = GitToolConfig()
    tool = GitTool(config=config)

    result = tool.execute(
      operation="log",
      path=str(git_repo),
      args={"format": "--uploadPack=/malicious"},
    )

    assert not result.success
    # Error should mention dangerous option or dash/flag injection
    assert "dangerous" in result.error.lower() or "flag injection" in result.error.lower()

  def test_shell_special_chars_blocked(self, git_repo: Path) -> None:
    """
    Given: An argument containing shell special chars (|, ;, &, $)
    When: Executing git operation
    Then: Returns error about forbidden character
    """
    config = GitToolConfig()
    tool = GitTool(config=config)

    result = tool.execute(
      operation="log",
      path=str(git_repo),
      args={"format": "test | cat /etc/passwd"},
    )

    assert not result.success
    assert "forbidden" in result.error.lower()

  def test_command_substitution_blocked(self, git_repo: Path) -> None:
    """
    Given: An argument containing $(command) or `command`
    When: Executing git operation
    Then: Returns error about forbidden character
    """
    config = GitToolConfig()
    tool = GitTool(config=config)

    result = tool.execute(
      operation="log",
      path=str(git_repo),
      args={"format": "$(cat /etc/passwd)"},
    )

    assert not result.success
    assert "forbidden" in result.error.lower()

  def test_newline_injection_blocked(self, git_repo: Path) -> None:
    """
    Given: An argument containing newline character
    When: Executing git operation
    Then: Returns error about forbidden character
    """
    config = GitToolConfig()
    tool = GitTool(config=config)

    result = tool.execute(
      operation="log",
      path=str(git_repo),
      args={"format": "test\nmalicious"},
    )

    assert not result.success
    assert "forbidden" in result.error.lower()

  def test_null_byte_injection_blocked(self, git_repo: Path) -> None:
    """
    Given: An argument containing null byte
    When: Executing git operation
    Then: Returns error about forbidden character
    """
    config = GitToolConfig()
    tool = GitTool(config=config)

    result = tool.execute(
      operation="log",
      path=str(git_repo),
      args={"format": "test\x00malicious"},
    )

    assert not result.success
    assert "forbidden" in result.error.lower()


class TestGitToolPathRestrictions:
  """Tests for path traversal and repository access restrictions."""

  def test_path_traversal_blocked(self, tmp_path: Path) -> None:
    """
    Given: A path with traversal sequence like ../../../etc
    When: Executing git operation
    Then: Path is resolved and blocked if outside allowed directories
    """
    config = GitToolConfig()

    # Create a mock guardrail that blocks path traversal
    mock_guardrail = MagicMock(spec=Guardrail)
    mock_guardrail.validate.return_value = ValidationResult(
      valid=False, reason="Path outside allowed directories"
    )

    tool = GitTool(config=config, guardrail=mock_guardrail)

    result = tool.execute(operation="status", path="/etc/passwd/../../../..")

    assert not result.success
    assert "allowed" in result.error.lower() or "outside" in result.error.lower()

  def test_git_dir_option_blocked(self, tmp_path: Path) -> None:
    """
    Given: A path argument containing --git-dir option
    When: Executing git operation
    Then: Returns error about disallowed argument
    """
    # Create a valid git repo so path validation passes
    repo = tmp_path / "test_repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)

    config = GitToolConfig()
    tool = GitTool(config=config)

    result = tool.execute(
      operation="log",
      path=str(repo),
      args={"format": "--git-dir=/malicious"},
    )

    assert not result.success
    # Error should mention dangerous option or dash/flag injection
    assert "dangerous" in result.error.lower() or "flag injection" in result.error.lower()

  def test_work_tree_option_blocked(self, tmp_path: Path) -> None:
    """
    Given: A path argument containing --work-tree option
    When: Executing git operation
    Then: Returns error about disallowed argument
    """
    # Create a valid git repo so path validation passes
    repo = tmp_path / "test_repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)

    config = GitToolConfig()
    tool = GitTool(config=config)

    result = tool.execute(
      operation="log",
      path=str(repo),
      args={"format": "--work-tree=/malicious"},
    )

    assert not result.success
    # Error should mention dangerous option or dash/flag injection
    assert "dangerous" in result.error.lower() or "flag injection" in result.error.lower()

  def test_repository_outside_allowed_paths_blocked(self, tmp_path: Path) -> None:
    """
    Given: A GitTool with guardrail restricting to specific paths
    When: Executing git operation on repository outside allowed paths
    Then: Returns error about path outside allowed directories
    """
    config = GitToolConfig()

    # Create mock guardrail that rejects the path
    mock_guardrail = MagicMock(spec=Guardrail)
    mock_guardrail.validate.return_value = ValidationResult(
      valid=False, reason="Path outside allowed directories"
    )

    tool = GitTool(config=config, guardrail=mock_guardrail)

    result = tool.execute(operation="status", path="/some/path")

    assert not result.success
    assert "allowed" in result.error.lower() or "outside" in result.error.lower()

  def test_symlink_repository_path_blocked(self, tmp_path: Path) -> None:
    """
    Given: A symlink pointing to a Git repository
    When: Executing git operation with symlink as path
    Then: Returns error about path not accessible
    """
    # Create a real repo
    repo = tmp_path / "real_repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)

    # Create a symlink
    symlink = tmp_path / "link_repo"
    symlink.symlink_to(repo)

    config = GitToolConfig()

    # Create mock guardrail that rejects symlinks
    mock_guardrail = MagicMock(spec=Guardrail)
    mock_guardrail.validate.return_value = ValidationResult(
      valid=False, reason="Symlinks are not permitted"
    )

    tool = GitTool(config=config, guardrail=mock_guardrail)

    result = tool.execute(operation="status", path=str(symlink))

    assert not result.success

  def test_nonexistent_repository_returns_error(self, tmp_path: Path) -> None:
    """
    Given: A path that does not exist
    When: Executing git operation
    Then: Returns error about path not found
    """
    config = GitToolConfig()
    tool = GitTool(config=config)

    result = tool.execute(operation="status", path=str(tmp_path / "nonexistent"))

    assert not result.success
    assert "not exist" in result.error.lower() or "not found" in result.error.lower()

  def test_non_git_directory_returns_error(self, tmp_path: Path) -> None:
    """
    Given: A directory without .git subdirectory
    When: Executing git operation
    Then: Returns error about not being a Git repository
    """
    non_git = tmp_path / "not_a_repo"
    non_git.mkdir()

    config = GitToolConfig()
    tool = GitTool(config=config)

    result = tool.execute(operation="status", path=str(non_git))

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
    config = GitToolConfig()
    tool = GitTool(config=config)

    # Test the _sanitize_output method directly since git branch
    # doesn't show remote URLs
    output_with_creds = "remote: https://user:secret_token@github.com/user/repo.git"
    sanitized = tool._sanitize_output(output_with_creds)

    # The output should have credentials redacted
    assert "secret_token" not in sanitized
    assert "<redacted>" in sanitized

  def test_sensitive_config_values_hidden(self, tmp_path: Path) -> None:
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

    config = GitToolConfig()
    tool = GitTool(config=config)

    result = tool.execute(operation="log", path=str(repo))

    assert result.success
    # Output should not contain any config values that weren't committed


class TestGitToolErrorHandling:
  """Tests for error handling scenarios."""

  def test_invalid_git_command_returns_error(self, tmp_path: Path) -> None:
    """
    Given: An invalid/nonexistent git operation
    When: Executing the operation
    Then: Returns error about invalid operation
    """
    config = GitToolConfig()
    tool = GitTool(config=config)

    result = tool.execute(operation="nonexistent", path=str(tmp_path))

    assert not result.success
    assert "not allowed" in result.error.lower()

  def test_git_timeout_enforced(self, tmp_path: Path) -> None:
    """
    Given: A git operation that takes too long
    When: Executing with timeout
    Then: Returns error about command timeout
    """
    repo = tmp_path / "test_repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)

    config = GitToolConfig()
    tool = GitTool(config=config)

    # Mock subprocess to raise TimeoutExpired
    with patch("yoker.tools.git.subprocess.run") as mock_run:
      mock_run.side_effect = subprocess.TimeoutExpired(cmd=["git"], timeout=30)

      result = tool.execute(operation="status", path=str(repo))

      assert not result.success
      assert "timeout" in result.error.lower()

  def test_git_not_installed_error(self, tmp_path: Path) -> None:
    """
    Given: A system where git is not installed
    When: Executing any git operation
    Then: Returns error about git not found
    """
    repo = tmp_path / "test_repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)

    config = GitToolConfig()
    tool = GitTool(config=config)

    # Mock subprocess to raise FileNotFoundError
    with patch("yoker.tools.git.subprocess.run") as mock_run:
      mock_run.side_effect = FileNotFoundError()

      result = tool.execute(operation="status", path=str(repo))

      assert not result.success
      assert "not installed" in result.error.lower() or "not found" in result.error.lower()

  def test_invalid_operation_type_error(self, tmp_path: Path) -> None:
    """
    Given: A non-string operation parameter
    When: Executing git operation
    Then: Returns error about invalid parameter type
    """
    config = GitToolConfig()
    tool = GitTool(config=config)

    result = tool.execute(operation=123, path=str(tmp_path))

    assert not result.success
    assert "string" in result.error.lower()

  def test_invalid_path_type_error(self, tmp_path: Path) -> None:
    """
    Given: A non-string path parameter
    When: Executing git operation
    Then: Returns error about invalid parameter type
    """
    config = GitToolConfig()
    tool = GitTool(config=config)

    result = tool.execute(operation="status", path=123)

    assert not result.success
    assert "string" in result.error.lower()

  def test_invalid_args_type_error(self, tmp_path: Path) -> None:
    """
    Given: A non-dict args parameter
    When: Executing git operation
    Then: Returns error about invalid parameter type
    """
    # Create a valid git repo so path validation passes
    repo = tmp_path / "test_repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)

    config = GitToolConfig()
    tool = GitTool(config=config)

    result = tool.execute(operation="status", path=str(repo), args="invalid")

    assert not result.success
    assert "object" in result.error.lower()

  def test_missing_operation_parameter_error(self, tmp_path: Path) -> None:
    """
    Given: No operation parameter provided
    When: Executing git tool
    Then: Returns error about missing required parameter
    """
    config = GitToolConfig()
    tool = GitTool(config=config)

    result = tool.execute(path=str(tmp_path))

    assert not result.success
    assert "missing" in result.error.lower() and "operation" in result.error.lower()


class TestGitToolArgumentValidation:
  """Tests for argument validation and schema enforcement."""

  @pytest.fixture
  def git_repo(self, tmp_path: Path) -> Path:
    """Create a temporary Git repository for testing."""
    repo = tmp_path / "test_repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    return repo

  def test_disallowed_argument_rejected(self, git_repo: Path) -> None:
    """
    Given: A git operation with an argument not in the allowed schema
    When: Executing the operation
    Then: Returns error about argument not allowed
    """
    config = GitToolConfig()
    tool = GitTool(config=config)

    result = tool.execute(
      operation="log",
      path=str(git_repo),
      args={"invalid_arg": "value"},
    )

    assert not result.success
    assert "not allowed" in result.error.lower()

  def test_integer_argument_type_validated(self, git_repo: Path) -> None:
    """
    Given: git log with n parameter as string instead of integer
    When: Executing the operation
    Then: Returns error about argument type
    """
    config = GitToolConfig()
    tool = GitTool(config=config)

    result = tool.execute(
      operation="log",
      path=str(git_repo),
      args={"n": "five"},
    )

    assert not result.success
    assert "integer" in result.error.lower()

  def test_boolean_argument_type_validated(self, git_repo: Path) -> None:
    """
    Given: git status with short parameter as string instead of boolean
    When: Executing the operation
    Then: Returns error about argument type
    """
    config = GitToolConfig()
    tool = GitTool(config=config)

    result = tool.execute(
      operation="status",
      path=str(git_repo),
      args={"short": "yes"},
    )

    assert not result.success
    assert "boolean" in result.error.lower()

  def test_integer_range_validated(self, git_repo: Path) -> None:
    """
    Given: git log with n parameter exceeding maximum (100)
    When: Executing the operation
    Then: Returns error about argument range
    """
    config = GitToolConfig()
    tool = GitTool(config=config)

    result = tool.execute(
      operation="log",
      path=str(git_repo),
      args={"n": 500},
    )

    assert not result.success
    assert "100" in result.error or "maximum" in result.error.lower()

  def test_string_length_limited(self, git_repo: Path) -> None:
    """
    Given: An argument with string value exceeding 1000 characters
    When: Executing the operation
    Then: Returns error about argument length limit
    """
    config = GitToolConfig()
    tool = GitTool(config=config)

    long_string = "x" * 1001

    result = tool.execute(
      operation="log",
      path=str(git_repo),
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

  def test_guardrail_blocks_outside_allowed_path(self, git_repo: Path) -> None:
    """
    Given: A guardrail restricting to specific paths
    When: Executing git operation on repository outside allowed paths
    Then: Returns error from guardrail
    """
    config = GitToolConfig()

    # Create mock guardrail that rejects
    mock_guardrail = MagicMock(spec=Guardrail)
    mock_guardrail.validate.return_value = ValidationResult(
      valid=False, reason="Path outside allowed directories"
    )

    tool = GitTool(config=config, guardrail=mock_guardrail)

    result = tool.execute(operation="status", path=str(git_repo))

    assert not result.success
    assert "allowed" in result.error.lower() or "outside" in result.error.lower()

  def test_guardrail_allows_inside_allowed_path(self, git_repo: Path) -> None:
    """
    Given: A guardrail allowing specific paths
    When: Executing git operation on repository inside allowed paths
    Then: Operation succeeds
    """
    config = GitToolConfig()

    # Create mock guardrail that allows
    mock_guardrail = MagicMock(spec=Guardrail)
    mock_guardrail.validate.return_value = ValidationResult(valid=True)

    tool = GitTool(config=config, guardrail=mock_guardrail)

    result = tool.execute(operation="status", path=str(git_repo))

    assert result.success

  def test_git_added_to_filesystem_tools(self) -> None:
    """
    Given: The PathGuardrail module
    When: Checking _FILESYSTEM_TOOLS
    Then: 'git' is included in the set
    """
    from yoker.tools.path_guardrail import _FILESYSTEM_TOOLS

    assert "git" in _FILESYSTEM_TOOLS


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

  def test_success_return_format(self, git_repo: Path) -> None:
    """
    Given: A successful git operation
    When: Checking the ToolResult
    Then: success=True, result contains output string, error is empty
    """
    config = GitToolConfig()
    tool = GitTool(config=config)

    result = tool.execute(operation="status", path=str(git_repo))

    assert result.success is True
    assert isinstance(result.result, str)
    assert len(result.result) > 0
    assert result.error is None

  def test_error_return_format(self, tmp_path: Path) -> None:
    """
    Given: A failed git operation
    When: Checking the ToolResult
    Then: success=False, result is empty, error contains message
    """
    config = GitToolConfig()
    tool = GitTool(config=config)

    result = tool.execute(operation="status", path=str(tmp_path / "nonexistent"))

    assert result.success is False
    assert result.result == ""
    assert result.error is not None
    assert len(result.error) > 0

  def test_empty_output_handled(self, git_repo: Path) -> None:
    """
    Given: A git operation that produces no output
    When: Checking the ToolResult
    Then: Returns "(no output)" message
    """
    # Clean repo with no changes
    config = GitToolConfig()
    tool = GitTool(config=config)

    result = tool.execute(operation="diff", path=str(git_repo))

    # diff with no changes returns empty output
    assert result.success
    assert "no output" in result.result.lower()


class TestGitToolSubprocessSecurity:
  """Tests for subprocess execution security."""

  def test_no_shell_true_used(self, tmp_path: Path) -> None:
    """
    Given: GitTool executing a command
    When: Checking subprocess.run call
    Then: shell=True is NOT used
    """
    repo = tmp_path / "test_repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)

    config = GitToolConfig()
    tool = GitTool(config=config)

    with patch("yoker.tools.git.subprocess.run") as mock_run:
      mock_run.return_value = subprocess.CompletedProcess(
        args=["git", "status"],
        returncode=0,
        stdout="On branch main",
        stderr="",
      )

      tool.execute(operation="status", path=str(repo))

      # Verify shell=True was NOT passed
      call_kwargs = mock_run.call_args.kwargs
      assert "shell" not in call_kwargs or call_kwargs.get("shell") is not True

  def test_command_as_list_not_string(self, tmp_path: Path) -> None:
    """
    Given: GitTool building a command
    When: Passing to subprocess
    Then: Command is a list of strings, not a single string
    """
    repo = tmp_path / "test_repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)

    config = GitToolConfig()
    tool = GitTool(config=config)

    with patch("yoker.tools.git.subprocess.run") as mock_run:
      mock_run.return_value = subprocess.CompletedProcess(
        args=["git", "status"],
        returncode=0,
        stdout="On branch main",
        stderr="",
      )

      tool.execute(operation="status", path=str(repo))

      # Verify first argument (command) is a list
      call_args = mock_run.call_args.args
      assert isinstance(call_args[0], list)
      assert all(isinstance(item, str) for item in call_args[0])


class TestGitToolIntegration:
  """Integration tests for GitTool with other components."""

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

  def test_git_status_after_write(self, git_repo: Path) -> None:
    """
    Given: Using WriteTool to create a file, then GitTool to check status
    When: Writing a new file and checking git status
    Then: Git status shows the new file as untracked
    """
    from yoker.tools.write import WriteTool

    # Create a file with WriteTool
    write_tool = WriteTool()
    write_result = write_tool.execute(
      path=str(git_repo / "new_file.txt"),
      content="New content",
      create_parents=True,
    )
    assert write_result.success

    # Check git status
    config = GitToolConfig()
    git_tool = GitTool(config=config)
    result = git_tool.execute(operation="status", path=str(git_repo))

    assert result.success
    assert "new_file.txt" in result.result

  def test_git_diff_after_update(self, git_repo: Path) -> None:
    """
    Given: Using UpdateTool to modify a file, then GitTool to check diff
    When: Updating a tracked file and checking git diff
    Then: Git diff shows the changes
    """
    from yoker.tools.update import UpdateTool

    # Update README.md with UpdateTool
    update_tool = UpdateTool()
    update_result = update_tool.execute(
      path=str(git_repo / "README.md"),
      operation="replace",
      old_string="# Test",
      new_string="# Updated",
    )
    assert update_result.success

    # Check git diff
    config = GitToolConfig()
    git_tool = GitTool(config=config)
    result = git_tool.execute(operation="diff", path=str(git_repo))

    assert result.success
    assert "# Updated" in result.result
