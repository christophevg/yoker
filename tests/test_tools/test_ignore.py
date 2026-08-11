"""Tests for the IgnoreMatcher gitignore-style pattern matching."""

from pathlib import Path

from yoker.tools.ignore import IgnoreMatcher, parse_ignore_file


class TestParseIgnoreFile:
  def test_basic_patterns(self, tmp_path: Path) -> None:
    """Parsing a .gitignore file produces correct patterns."""
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text(
      "# Comment\n\ncontext/\n*.jsonl\n/yoker.toml\nlogs\n!important.log\nbuild/\n"
    )
    result = parse_ignore_file(gitignore)
    assert result is not None
    assert result.root_dir == tmp_path
    assert len(result.patterns) == 6  # comment and blank line skipped

  def test_nonexistent_file(self, tmp_path: Path) -> None:
    """Parsing a nonexistent file returns None."""
    result = parse_ignore_file(tmp_path / ".gitignore")
    assert result is None

  def test_empty_file(self, tmp_path: Path) -> None:
    """Parsing an empty file returns None."""
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text("")
    result = parse_ignore_file(gitignore)
    assert result is None

  def test_only_comments(self, tmp_path: Path) -> None:
    """Parsing a file with only comments returns None."""
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text("# comment 1\n# comment 2\n")
    result = parse_ignore_file(gitignore)
    assert result is None

  def test_negation_pattern(self, tmp_path: Path) -> None:
    """Negation patterns are parsed correctly."""
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text("*.log\n!important.log\n")
    result = parse_ignore_file(gitignore)
    assert result is not None
    assert result.patterns[0].negation is False
    assert result.patterns[1].negation is True
    assert result.patterns[1].raw == "!important.log"


class TestIgnoreMatcherBasic:
  def test_skip_dirs(self, tmp_path: Path) -> None:
    """Hardcoded skip_dirs are pruned."""
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("x")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("x")

    matcher = IgnoreMatcher(
      tmp_path, skip_dirs=(".git",), skip_dotfiles=False, respect_ignore_files=False
    )
    assert matcher.should_skip_dir(".git") is True
    assert matcher.should_skip_dir("src") is False

  def test_skip_dotfiles(self, tmp_path: Path) -> None:
    """Dotfiles are skipped when skip_dotfiles is True."""
    matcher = IgnoreMatcher(tmp_path, skip_dirs=(), skip_dotfiles=True, respect_ignore_files=False)
    assert matcher.should_skip_dir(".env") is True
    assert matcher.should_skip_dir(".venv") is True
    assert matcher.should_skip_dir("src") is False

  def test_no_skip_dotfiles(self, tmp_path: Path) -> None:
    """Dotfiles are not skipped when skip_dotfiles is False."""
    matcher = IgnoreMatcher(tmp_path, skip_dirs=(), skip_dotfiles=False, respect_ignore_files=False)
    assert matcher.should_skip_dir(".env") is False


class TestIgnoreMatcherGitignore:
  def test_gitignore_excludes_directory(self, tmp_path: Path) -> None:
    """A directory listed in .gitignore is excluded."""
    (tmp_path / ".gitignore").write_text("context/\n")
    (tmp_path / "context").mkdir()
    (tmp_path / "context" / "session.jsonl").write_text("x")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("x")

    matcher = IgnoreMatcher(tmp_path, skip_dirs=(), skip_dotfiles=False, respect_ignore_files=True)
    context_dir = tmp_path / "context"
    assert matcher.should_ignore_path(context_dir, is_dir=True) is True
    src_dir = tmp_path / "src"
    assert matcher.should_ignore_path(src_dir, is_dir=True) is False

  def test_gitignore_excludes_files_by_pattern(self, tmp_path: Path) -> None:
    """Wildcard patterns in .gitignore exclude matching files."""
    (tmp_path / ".gitignore").write_text("*.jsonl\n")
    (tmp_path / "session.jsonl").write_text("x")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "data.jsonl").write_text("x")
    (tmp_path / "src" / "main.py").write_text("x")

    matcher = IgnoreMatcher(tmp_path, skip_dirs=(), skip_dotfiles=False, respect_ignore_files=True)
    assert matcher.should_ignore_path(tmp_path / "session.jsonl") is True
    assert matcher.should_ignore_path(tmp_path / "src" / "data.jsonl") is True
    assert matcher.should_ignore_path(tmp_path / "src" / "main.py") is False

  def test_gitignore_anchored_pattern(self, tmp_path: Path) -> None:
    """Anchored patterns only match from the root."""
    (tmp_path / ".gitignore").write_text("/yoker.toml\n")
    (tmp_path / "yoker.toml").write_text("x")
    (tmp_path / "subdir").mkdir()
    (tmp_path / "subdir" / "yoker.toml").write_text("x")

    matcher = IgnoreMatcher(tmp_path, skip_dirs=(), skip_dotfiles=False, respect_ignore_files=True)
    assert matcher.should_ignore_path(tmp_path / "yoker.toml") is True
    assert matcher.should_ignore_path(tmp_path / "subdir" / "yoker.toml") is False

  def test_gitignore_negation(self, tmp_path: Path) -> None:
    """Negation patterns un-ignore previously ignored paths."""
    (tmp_path / ".gitignore").write_text("*.log\n!important.log\n")
    (tmp_path / "debug.log").write_text("x")
    (tmp_path / "important.log").write_text("x")

    matcher = IgnoreMatcher(tmp_path, skip_dirs=(), skip_dotfiles=False, respect_ignore_files=True)
    assert matcher.should_ignore_path(tmp_path / "debug.log") is True
    assert matcher.should_ignore_path(tmp_path / "important.log") is False

  def test_gitignore_dir_only_pattern(self, tmp_path: Path) -> None:
    """Trailing slash means directory-only matching."""
    (tmp_path / ".gitignore").write_text("build/\n")
    (tmp_path / "build").mkdir()
    (tmp_path / "build" / "output.py").write_text("x")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "build.py").write_text("x")

    matcher = IgnoreMatcher(tmp_path, skip_dirs=(), skip_dotfiles=False, respect_ignore_files=True)
    # "build" as a directory is ignored
    assert matcher.should_ignore_path(tmp_path / "build", is_dir=True) is True
    # "build.py" as a file is NOT ignored (dir_only pattern)
    assert matcher.should_ignore_path(tmp_path / "src" / "build.py") is False
    # Files inside an ignored directory are also ignored
    assert matcher.should_ignore_path(tmp_path / "build" / "output.py") is True

  def test_gitignore_plain_name_matches_anywhere(self, tmp_path: Path) -> None:
    """A plain name pattern matches at any directory level."""
    (tmp_path / ".gitignore").write_text("logs\n")
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "run.log").write_text("x")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "logs").mkdir()
    (tmp_path / "src" / "logs" / "debug.log").write_text("x")

    matcher = IgnoreMatcher(tmp_path, skip_dirs=(), skip_dotfiles=False, respect_ignore_files=True)
    assert matcher.should_ignore_path(tmp_path / "logs", is_dir=True) is True
    assert matcher.should_ignore_path(tmp_path / "src" / "logs", is_dir=True) is True
    assert matcher.should_ignore_path(tmp_path / "src" / "logs" / "debug.log") is True

  def test_nested_gitignore(self, tmp_path: Path) -> None:
    """Nested .gitignore files are respected within their scope."""
    (tmp_path / ".gitignore").write_text("*.tmp\n")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / ".gitignore").write_text("*.local\n")
    (tmp_path / "src" / "main.py").write_text("x")
    (tmp_path / "src" / "cache.tmp").write_text("x")
    (tmp_path / "src" / "config.local").write_text("x")
    (tmp_path / "config.tmp").write_text("x")

    matcher = IgnoreMatcher(tmp_path, skip_dirs=(), skip_dotfiles=False, respect_ignore_files=True)
    # Root .gitignore applies
    assert matcher.should_ignore_path(tmp_path / "config.tmp") is True
    assert matcher.should_ignore_path(tmp_path / "src" / "cache.tmp") is True
    # Nested .gitignore applies
    assert matcher.should_ignore_path(tmp_path / "src" / "config.local") is True
    # Non-ignored files
    assert matcher.should_ignore_path(tmp_path / "src" / "main.py") is False

  def test_respect_ignore_files_false(self, tmp_path: Path) -> None:
    """When respect_ignore_files=False, .gitignore is not parsed."""
    (tmp_path / ".gitignore").write_text("*.jsonl\n")
    (tmp_path / "data.jsonl").write_text("x")

    matcher = IgnoreMatcher(tmp_path, skip_dirs=(), skip_dotfiles=False, respect_ignore_files=False)
    assert matcher.should_ignore_path(tmp_path / "data.jsonl") is False

  def test_no_ignore_file(self, tmp_path: Path) -> None:
    """No .gitignore means only skip_dirs/dotfiles apply."""
    (tmp_path / "data.jsonl").write_text("x")

    matcher = IgnoreMatcher(tmp_path, skip_dirs=(), skip_dotfiles=False, respect_ignore_files=True)
    assert matcher.should_ignore_path(tmp_path / "data.jsonl") is False

  def test_double_star_pattern(self, tmp_path: Path) -> None:
    """** patterns match across directory boundaries."""
    (tmp_path / ".gitignore").write_text("node_modules/**/cache\n")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "pkg").mkdir()
    (tmp_path / "node_modules" / "pkg" / "cache").write_text("x")

    matcher = IgnoreMatcher(tmp_path, skip_dirs=(), skip_dotfiles=False, respect_ignore_files=True)
    cache_path = tmp_path / "node_modules" / "pkg" / "cache"
    assert matcher.should_ignore_path(cache_path) is True


class TestIgnoreMatcherRealWorld:
  def test_yoker_gitignore(self, tmp_path: Path) -> None:
    """Simulates the actual Yoker .gitignore."""
    (tmp_path / ".gitignore").write_text(
      "build/\n"
      "dist/\n"
      "*.egg-info/\n"
      "__pycache__/\n"
      ".venv/\n"
      "/context/\n"
      "logs/\n"
      "*.jsonl\n"
      "/yoker.toml\n"
      ".env\n"
      "local/\n"
    )
    # Create structure
    (tmp_path / "context").mkdir()
    (tmp_path / "context" / "session.jsonl").write_text("x")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("x")
    (tmp_path / "src" / "__pycache__").mkdir()
    (tmp_path / "session.jsonl").write_text("x")
    (tmp_path / "yoker.toml").write_text("x")
    (tmp_path / "local").mkdir()
    (tmp_path / "local" / "temp.txt").write_text("x")

    matcher = IgnoreMatcher(tmp_path, skip_dirs=(), skip_dotfiles=False, respect_ignore_files=True)

    # context/ directory should be ignored (anchored)
    assert matcher.should_ignore_path(tmp_path / "context", is_dir=True) is True
    assert matcher.should_ignore_path(tmp_path / "context" / "session.jsonl") is True
    # src/ should not be ignored
    assert matcher.should_ignore_path(tmp_path / "src", is_dir=True) is False
    assert matcher.should_ignore_path(tmp_path / "src" / "main.py") is False
    # *.jsonl should be ignored anywhere
    assert matcher.should_ignore_path(tmp_path / "session.jsonl") is True
    # /yoker.toml should be ignored at root only
    assert matcher.should_ignore_path(tmp_path / "yoker.toml") is True
    # local/ directory should be ignored
    assert matcher.should_ignore_path(tmp_path / "local", is_dir=True) is True
    assert matcher.should_ignore_path(tmp_path / "local" / "temp.txt") is True
