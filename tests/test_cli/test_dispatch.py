"""Tests for the CLI subcommand dispatch flow (MBI-004 task 4.10.1).

Covers ``main()`` routing to each subcommand handler and ``--with`` stripping
from arbitrary subcommand positions. The default-subcommand logic (bare
``yoker`` → ``chat``) is handled natively by Clevis via ``default_cmd=True``
on ``ChatConfig`` since Clevis 0.7.0.
"""

from __future__ import annotations

from importlib import reload
from unittest.mock import patch

import pytest
from clevis import _reset_factories

from yoker.__main__ import main


def _restore_subcommand_factories() -> None:
  """Re-register the @configclass(cmd=...) subcommand configs after _reset_factories."""
  import yoker.cli.commands

  reload(yoker.cli.commands)


class TestMainDispatch:
  """``main()`` routes to the correct subcommand handler via ``get_cmd()``."""

  @pytest.fixture
  def mock_plugin_parse(self):
    """Mock _parse_plugin_args to return no plugins and pass argv through."""
    with patch("yoker.__main__._parse_plugin_args") as m:
      m.return_value = ([], ["yoker"])
      yield m

  def _assert_routes(self, cmd_name, handler_name, mock_parse):
    with patch("yoker.__main__.get_cmd", return_value=cmd_name) as m_cmd:
      with patch(f"yoker.__main__.{handler_name}") as m_handler:
        main()
    m_cmd.assert_called_once()
    m_handler.assert_called_once()

  def test_main_routes_to_chat(self, mock_plugin_parse):
    self._assert_routes("chat", "run_chat", mock_plugin_parse)

  def test_main_routes_to_run(self, mock_plugin_parse):
    self._assert_routes("run", "run_run", mock_plugin_parse)

  def test_main_routes_to_loop(self, mock_plugin_parse):
    self._assert_routes("loop", "run_loop", mock_plugin_parse)

  def test_main_routes_to_inspect(self, mock_plugin_parse):
    self._assert_routes("inspect", "run_inspect", mock_plugin_parse)

  def test_main_routes_to_init(self, mock_plugin_parse):
    self._assert_routes("init", "run_init", mock_plugin_parse)

  def test_main_routes_to_config(self, mock_plugin_parse):
    self._assert_routes("config", "run_config_cmd", mock_plugin_parse)

  def test_main_routes_to_container(self, mock_plugin_parse):
    self._assert_routes("container", "run_container", mock_plugin_parse)

  def test_main_passes_plugin_packages_to_chat(self, mock_plugin_parse):
    """run_chat receives the plugin packages extracted by _parse_plugin_args."""
    packages = ["pkgq"]
    with patch("yoker.__main__._parse_plugin_args", return_value=(packages, ["yoker"])):
      with patch("yoker.__main__.get_cmd", return_value="chat"):
        with patch("yoker.__main__.run_chat") as m_chat:
          main()
    m_chat.assert_called_once_with(packages)

  def test_main_passes_plugin_packages_to_run(self, mock_plugin_parse):
    """run_run receives the plugin packages."""
    packages = ["pkgq"]
    with patch("yoker.__main__._parse_plugin_args", return_value=(packages, ["yoker"])):
      with patch("yoker.__main__.get_cmd", return_value="run"):
        with patch("yoker.__main__.run_run") as m_run:
          main()
    m_run.assert_called_once_with(packages)

  def test_main_unknown_cmd_aborts(self, mock_plugin_parse):
    """An unrecognised get_cmd result aborts with exit code 1."""
    with patch("yoker.__main__.get_cmd", return_value="bogus"):
      with patch("yoker.__main__.abort") as m_abort:
        main()
    m_abort.assert_called_once()
    assert m_abort.call_args.args[1] == 1


class TestMainDefaultChat:
  """When no subcommand is given, Clevis's default_cmd=True routes to chat."""

  def test_routes_to_chat_when_no_subcommand(self):
    """Bare ``yoker`` — get_cmd returns 'chat' via Clevis default_cmd=True."""
    with patch("yoker.__main__._parse_plugin_args", return_value=([], ["yoker"])):
      with patch("yoker.__main__.get_cmd", return_value="chat") as m_cmd:
        with patch("yoker.__main__.run_chat"):
          with patch("sys.argv", ["yoker"]):
            main()
    m_cmd.assert_called_once()

  def test_routes_to_run_when_subcommand_present(self):
    """Known subcommand: get_cmd returns 'run', no default routing."""
    argv = ["yoker", "run", "pkgq"]
    with patch("yoker.__main__._parse_plugin_args", return_value=([], argv)):
      with patch("yoker.__main__.get_cmd", return_value="run"):
        with patch("yoker.__main__.run_run"):
          with patch("sys.argv", argv):
            main()


class TestWithStrippingFromSubcommands:
  """``--with`` is stripped before dispatch from any subcommand position."""

  def test_with_stripped_before_run_dispatch(self):
    """``yoker run --with pkgq source`` strips --with before get_cmd."""
    argv = ["yoker", "run", "--with", "pkgq", "source"]
    cleaned = ["yoker", "run", "source"]
    with patch("yoker.__main__._parse_plugin_args", return_value=(["pkgq"], cleaned)) as m_parse:
      with patch("yoker.__main__.get_cmd", return_value="run"):
        with patch("yoker.__main__.run_run") as m_run:
          with patch("sys.argv", argv):
            main()
    m_parse.assert_called_once()
    m_run.assert_called_once_with(["pkgq"])

  def test_with_stripped_before_chat_dispatch(self):
    """``yoker --with pkgq chat`` strips --with and routes to chat."""
    argv = ["yoker", "--with", "pkgq", "chat"]
    cleaned = ["yoker", "chat"]
    with patch("yoker.__main__._parse_plugin_args", return_value=(["pkgq"], cleaned)):
      with patch("yoker.__main__.get_cmd", return_value="chat"):
        with patch("yoker.__main__.run_chat") as m_chat:
          with patch("sys.argv", argv):
            main()
    m_chat.assert_called_once_with(["pkgq"])

  def test_multiple_with_stripped_before_dispatch(self):
    """Multiple --with args are all stripped and passed to the handler."""
    argv = ["yoker", "loop", "--with", "a", "--with", "b", "source"]
    cleaned = ["yoker", "loop", "source"]
    with patch("yoker.__main__._parse_plugin_args", return_value=(["a", "b"], cleaned)):
      with patch("yoker.__main__.get_cmd", return_value="loop"):
        with patch("yoker.__main__.run_loop") as m_loop:
          with patch("sys.argv", argv):
            main()
    m_loop.assert_called_once_with(["a", "b"])


class TestDefaultCmdIntegration:
  """Integration tests exercising Clevis's real ``default_cmd=True`` routing.

  Unlike ``TestMainDefaultChat`` (which mocks ``get_cmd``), these tests let
  ``get_cmd()`` run against the real Clevis parser, verifying that
  ``default_cmd=True`` on ``ChatConfig`` natively routes bare ``yoker`` to
  ``chat``.
  """

  @pytest.fixture(autouse=True)
  def _ensure_clevis_state(self):
    """Ensure subcommand configs are registered with Clevis before each test.

    Other test modules (e.g. test_config_with_manifest) call
    ``_reset_factories()`` which wipes the @configclass registrations.
    This fixture restores them so ``get_cmd()`` finds the real subparser
    and default_cmd mapping.
    """
    _reset_factories()
    _restore_subcommand_factories()
    yield
    _reset_factories()
    _restore_subcommand_factories()

  def test_bare_yoker_routes_to_chat(self):
    """Bare ``yoker`` (no subcommand) → Clevis routes to chat via default_cmd=True."""
    with patch("yoker.__main__._parse_plugin_args", return_value=([], ["yoker"])):
      with patch("yoker.__main__.run_chat") as m_chat:
        main()
    m_chat.assert_called_once_with([])

  def test_help_shows_top_level_not_chat(self):
    """``yoker --help`` shows top-level help (SystemExit 0), does NOT route to chat."""
    with patch("yoker.__main__._parse_plugin_args", return_value=([], ["yoker", "--help"])):
      with patch("yoker.__main__.run_chat") as m_chat:
        with pytest.raises(SystemExit) as exc:
          main()
    assert exc.value.code == 0
    m_chat.assert_not_called()

  def test_run_subcommand_routes_to_run(self):
    """``yoker run`` routes to run, not chat."""
    with patch("yoker.__main__._parse_plugin_args", return_value=([], ["yoker", "run"])):
      with patch("yoker.__main__.run_run") as m_run:
        main()
    m_run.assert_called_once_with([])
