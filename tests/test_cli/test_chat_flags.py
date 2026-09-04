"""Tests for the Clevis-generated CLI flags of the chat subcommand.

Regression guard for the examples/README.md and examples/plugins/demo/README.md
invocation snippets: chat accepts ``--agent-name <name>`` (the Clevis-generated
flag for the nested ``Config.agent.name`` field) and does NOT accept ``--agent``
(that flag exists only for run/loop via ``parse_run_overrides``).
"""

from __future__ import annotations

import sys
from importlib import reload
from pathlib import Path

import pytest
from clevis import _reset_factories

import yoker.cli.commands
from yoker.cli.shared import load_subcommand_config


def _restore_subcommand_factories() -> None:
  """Re-register the @configclass(cmd=...) subcommand configs after _reset_factories."""
  reload(yoker.cli.commands)


class TestChatCliFlags:
  """Chat accepts ``--agent-name``; ``--agent`` is rejected (run/loop-only)."""

  @pytest.fixture(autouse=True)
  def _isolate_clevis(self, tmp_path: Path, monkeypatch):
    """Reset Clevis global state and re-register subcommand configs per test.

    ``load_subcommand_config(ChatConfig)`` needs the ``cmd="chat"`` attribute
    set by ``@configclass(cmd="chat")``. After ``_reset_factories()``, the
    factory is gone, so reload ``yoker.cli.commands`` to re-run the decorators
    (same pattern as test_shared_manifest.py).

    Isolates from real TOML files (HOME/chdir → tmp_path) and dev-bypasses
    the config security checks.
    """
    _reset_factories()
    _restore_subcommand_factories()
    monkeypatch.setenv("YOKER_DEV_MODE", "1")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    yield
    _reset_factories()
    _restore_subcommand_factories()

  def test_agent_name_flag_reaches_config(self, monkeypatch) -> None:
    """A chat parse with ``--agent-name demo`` populates ``config.agent.name``.

    Drives the real Clevis CLI parse through the same public entry point
    (``load_subcommand_config``) that ``run_chat`` uses — behavioral proof
    that the flag exists, is accepted, and lands on the nested field.
    """
    monkeypatch.setattr(sys, "argv", ["yoker", "chat", "--agent-name", "demo"], raising=False)
    config = load_subcommand_config(yoker.cli.commands.ChatConfig)
    assert config.agent.name == "demo"

  def test_bare_agent_flag_rejected(self, monkeypatch) -> None:
    """``--agent demo`` is rejected for chat (SystemExit from argparse).

    Guards against the examples ever regressing to ``--agent``, which only
    exists for run/loop via ``parse_run_overrides``.
    """
    monkeypatch.setattr(sys, "argv", ["yoker", "chat", "--agent", "demo"], raising=False)
    with pytest.raises(SystemExit):
      load_subcommand_config(yoker.cli.commands.ChatConfig)

  def test_agent_name_toml_alternative(self, monkeypatch, tmp_path: Path) -> None:
    """TOML alternative: ``[agent] name = "demo"`` reaches the same field.

    Documents the config-file route for selecting the chat agent, since the
    nested ``agent.name`` is equally settable without a CLI flag.
    """
    project_toml = tmp_path / "yoker.toml"
    project_toml.write_text('[agent]\nname = "demo"\n', encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["yoker", "chat"], raising=False)

    config = load_subcommand_config(yoker.cli.commands.ChatConfig)

    assert config.agent.name == "demo"
