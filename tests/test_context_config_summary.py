"""Tests for the effective-configuration summary renderer.

The summary is embedded in the environment reminder. Security-critical
property: credential fields must never appear in the output, regardless
of how they are populated.
"""

from dataclasses import dataclass

from yoker.context.config_summary import render_config_summary


def _make_config(**overrides):
  """Build a minimal stand-in Config with only the fields the renderer reads."""
  from yoker.config import (
    BackendConfig,
    ContextConfig,
    GitHubToolConfig,
    GitToolConfig,
    MakeToolConfig,
    PermissionsConfig,
    PluginsConfig,
    ToolsConfig,
  )

  @dataclass
  class _StubConfig:
    tools: ToolsConfig
    permissions: object
    backend: BackendConfig
    plugins: PluginsConfig
    context: ContextConfig

  github = overrides.get("github", GitHubToolConfig())
  make = overrides.get("make", MakeToolConfig())
  git = overrides.get("git", GitToolConfig())
  tools = ToolsConfig(github=github, make=make, git=git)
  permissions = overrides.get("permissions", PermissionsConfig())
  backend = overrides.get("backend", BackendConfig())
  plugins = overrides.get("plugins", PluginsConfig())
  context = overrides.get("context", ContextConfig())
  return _StubConfig(
    tools=tools, permissions=permissions, backend=backend, plugins=plugins, context=context
  )


class TestContextCompactionRendering:
  def test_default_ratio_shows_half_cap_target(self) -> None:
    from yoker.config import ContextConfig

    config = _make_config(context=ContextConfig(max_tokens=200_000))
    summary = render_config_summary(config)
    assert "context compaction: cap 200,000 tokens; trim target ≈100,000" in summary

  def test_ratio_one_shows_cap_as_target(self) -> None:
    from yoker.config import ContextConfig

    config = _make_config(context=ContextConfig(max_tokens=80_000, compact_ratio=1.0))
    summary = render_config_summary(config)
    assert "context compaction: cap 80,000 tokens; trim target ≈80,000" in summary

  def test_default_stage_order_shown(self) -> None:
    """Without a compaction config attribute (old/stub configs), the
    framework default stage order is shown."""
    config = _make_config()
    summary = render_config_summary(config)
    assert "stages: prune_tool_results, prune_thinking, force_stub_tool_results, cutoff" in summary

  def test_configured_stage_order_shown(self) -> None:
    """A configured compaction strategies list is rendered in order."""
    from yoker.config import CompactionConfig, ContextConfig

    compaction = CompactionConfig(strategies=("cutoff", "prune_tool_results"))
    config = _make_config(context=ContextConfig(compaction=compaction))
    summary = render_config_summary(config)
    assert "stages: cutoff, prune_tool_results" in summary

  def test_empty_strategies_shows_disabled(self) -> None:
    """An empty strategies list (compaction disabled) is rendered as such."""
    from yoker.config import CompactionConfig, ContextConfig

    compaction = CompactionConfig(strategies=())
    config = _make_config(context=ContextConfig(compaction=compaction))
    summary = render_config_summary(config)
    assert "stages: disabled" in summary


class TestGithubOperationsRendering:
  def test_read_only_set_mentions_write_ops_not_enabled(self) -> None:
    config = _make_config()
    summary = render_config_summary(config)
    assert "read-only set" in summary
    assert "NOT enabled" in summary

  def test_granted_write_ops_shown(self) -> None:
    from yoker.config import GitHubToolConfig

    config = _make_config(
      github=GitHubToolConfig(
        allowed_operations=(
          "repo_view",
          "issue_list",
          "issue_create",
          "issue_comment",
        )
      )
    )
    summary = render_config_summary(config)
    assert "issue_create" in summary
    assert "issue_comment" in summary
    assert "explicitly granted" in summary

  def test_no_leak_of_denied_write_op_names_when_none_granted(self) -> None:
    config = _make_config()
    summary = render_config_summary(config)
    # The denial note may mention examples, but must not render a full
    # grantable list as if it were active.
    assert "write ops explicitly granted" not in summary


class TestMakeEnvVarsRendering:
  def test_empty_allowlist_renders_deny_by_default(self) -> None:
    from yoker.config import MakeToolConfig

    config = _make_config(make=MakeToolConfig())
    summary = render_config_summary(config)
    assert "deny-by-default" in summary

  def test_populated_allowlist_renders_targets(self) -> None:
    from yoker.config import MakeToolConfig

    config = _make_config(
      make=MakeToolConfig(
        allowed_env_vars={"test": ("TEST",), "lint": ("LINT_FLAGS", "LINT_CONFIG")}
      )
    )
    summary = render_config_summary(config)
    assert "test: [TEST]" in summary
    assert "lint: [LINT_FLAGS, LINT_CONFIG]" in summary


class TestGitPermissionsRendering:
  def test_default_config_shows_approval_required(self) -> None:
    from yoker.config import GitToolConfig

    config = _make_config(git=GitToolConfig())
    summary = render_config_summary(config)
    assert "approval required" in summary
    assert "commit" in summary

  def test_all_auto_approved_when_no_approval_ops(self) -> None:
    from yoker.config import GitToolConfig

    git = GitToolConfig(auto_permission=GitToolConfig.allowed_commands)
    config = _make_config(git=git)
    summary = render_config_summary(config)
    assert "all configured commands auto-approved" in summary


class TestRedactionGuarantee:
  def test_api_key_never_appears(self) -> None:
    from yoker.config import OllamaConfig

    backend = _make_config().backend  # same stub shape, fresh instance
    backend.provider = "ollama"
    backend.ollama = OllamaConfig(api_key="sk-super-secret-key-123", model="test-model")
    config = _make_config(backend=backend)
    summary = render_config_summary(config)
    assert "sk-super-secret-key-123" not in summary
    assert "api_key" not in summary

  def test_backend_line_contains_only_names(self) -> None:
    config = _make_config()
    summary = render_config_summary(config)
    assert "backend: ollama (model:" in summary


class TestTruncationCaps:
  def test_long_lists_truncate_with_overflow_notice(self) -> None:
    from yoker.config import GitHubToolConfig

    many_ops = (
      "repo_view",
      "issue_list",
      "issue_view",
      "pr_list",
      "pr_view",
      "pr_reviews",
      "pr_comments",
      "workflow_list",
      "workflow_view",
      "workflow_logs",
      "release_list",
      "release_view",
      "pr_create",
      "pr_comment",
      "issue_create",
      "issue_comment",
    )
    config = _make_config(github=GitHubToolConfig(allowed_operations=many_ops))
    summary = render_config_summary(config)
    assert "…" in summary
    assert "(+" in summary


class TestEmptyConfig:
  def test_summary_always_has_content_for_real_config(self) -> None:
    # The renderer intentionally always shows backend + permissions lines;
    # an empty return only happens for degenerate configs.
    config = _make_config()
    summary = render_config_summary(config)
    assert "Effective Configuration" in summary
    assert "filesystem_paths" in summary
