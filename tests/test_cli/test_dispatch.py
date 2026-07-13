"""Tests for the CLI subcommand dispatch flow (MBI-004 task 4.10.1).

Covers ``_needs_default_chat`` (the backward-compat default-subcommand logic),
``main()`` routing to each subcommand handler, and ``--with`` stripping from
arbitrary subcommand positions.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from yoker.__main__ import KNOWN_COMMANDS, _needs_default_chat, main


class TestNeedsDefaultChat:
  """``_needs_default_chat`` decides whether to insert "chat" as default."""

  def test_no_args_inserts_chat(self):
    """Bare ``yoker`` (only program name) defaults to chat."""
    assert _needs_default_chat(["yoker"]) is True

  def test_empty_argv_inserts_chat(self):
    """Completely empty argv defaults to chat."""
    assert _needs_default_chat([]) is True

  def test_help_flag_does_not_insert(self):
    """``yoker --help`` must NOT insert chat (let top-level parser show help)."""
    assert _needs_default_chat(["yoker", "--help"]) is False

  def test_short_help_flag_does_not_insert(self):
    """``yoker -h`` must NOT insert chat."""
    assert _needs_default_chat(["yoker", "-h"]) is False

  def test_flag_first_inserts_chat(self):
    """``yoker --backend-ollama-model X`` defaults to chat (backward compat)."""
    assert _needs_default_chat(["yoker", "--backend-ollama-model", "X"]) is True

  def test_known_subcommand_does_not_insert(self):
    """Each known subcommand must route directly (no chat insertion)."""
    for cmd in KNOWN_COMMANDS:
      assert _needs_default_chat(["yoker", cmd]) is False

  def test_unknown_positional_does_not_insert(self):
    """Unknown positional lets argparse error with the valid-choice list."""
    assert _needs_default_chat(["yoker", "bogus-cmd"]) is False

  def test_flag_after_subcommand_does_not_insert(self):
    """When a known subcommand is first, flags after it don't trigger default."""
    assert _needs_default_chat(["yoker", "run", "--persist"]) is False

  def test_dash_flag_after_unknown_does_not_insert(self):
    """Unknown positional first — let argparse handle the error."""
    assert _needs_default_chat(["yoker", "bogus", "--flag"]) is False


class TestMainDispatch:
  """``main()`` routes to the correct subcommand handler via ``get_cmd()``."""

  @pytest.fixture
  def mock_plugin_parse(self):
    """Mock _parse_plugin_args to return no plugins and pass argv through."""
    with patch("yoker.__main__._parse_plugin_args") as m:
      m.return_value = ([], ["yoker"])
      yield m

  @pytest.fixture
  def mock_needs_default(self):
    """Mock _needs_default_chat to return False (subcommand already present)."""
    with patch("yoker.__main__._needs_default_chat", return_value=False) as m:
      yield m

  def _assert_routes(self, cmd_name, handler_name, mock_parse, mock_needs):
    with patch("yoker.__main__.get_cmd", return_value=cmd_name) as m_cmd:
      with patch(f"yoker.__main__.{handler_name}") as m_handler:
        main()
    m_cmd.assert_called_once()
    m_handler.assert_called_once()

  def test_main_routes_to_chat(self, mock_plugin_parse, mock_needs_default):
    self._assert_routes("chat", "run_chat", mock_plugin_parse, mock_needs_default)

  def test_main_routes_to_run(self, mock_plugin_parse, mock_needs_default):
    self._assert_routes("run", "run_run", mock_plugin_parse, mock_needs_default)

  def test_main_routes_to_loop(self, mock_plugin_parse, mock_needs_default):
    self._assert_routes("loop", "run_loop", mock_plugin_parse, mock_needs_default)

  def test_main_routes_to_inspect(self, mock_plugin_parse, mock_needs_default):
    self._assert_routes("inspect", "run_inspect", mock_plugin_parse, mock_needs_default)

  def test_main_routes_to_init(self, mock_plugin_parse, mock_needs_default):
    self._assert_routes("init", "run_init", mock_plugin_parse, mock_needs_default)

  def test_main_routes_to_config(self, mock_plugin_parse, mock_needs_default):
    self._assert_routes("config", "run_config_cmd", mock_plugin_parse, mock_needs_default)

  def test_main_routes_to_container(self, mock_plugin_parse, mock_needs_default):
    self._assert_routes("container", "run_container", mock_plugin_parse, mock_needs_default)

  def test_main_passes_plugin_packages_to_chat(self, mock_needs_default):
    """run_chat receives the plugin packages extracted by _parse_plugin_args."""
    packages = ["pkgq"]
    with patch("yoker.__main__._parse_plugin_args", return_value=(packages, ["yoker"])):
      with patch("yoker.__main__.get_cmd", return_value="chat"):
        with patch("yoker.__main__.run_chat") as m_chat:
          main()
    m_chat.assert_called_once_with(packages)

  def test_main_passes_plugin_packages_to_run(self, mock_needs_default):
    """run_run receives the plugin packages."""
    packages = ["pkgq"]
    with patch("yoker.__main__._parse_plugin_args", return_value=(packages, ["yoker"])):
      with patch("yoker.__main__.get_cmd", return_value="run"):
        with patch("yoker.__main__.run_run") as m_run:
          main()
    m_run.assert_called_once_with(packages)

  def test_main_unknown_cmd_aborts(self, mock_plugin_parse, mock_needs_default):
    """An unrecognised get_cmd result aborts with exit code 1."""
    with patch("yoker.__main__.get_cmd", return_value="bogus"):
      with patch("yoker.__main__.abort") as m_abort:
        main()
    m_abort.assert_called_once()
    assert m_abort.call_args.args[1] == 1


class TestMainDefaultChat:
  """When no subcommand is given, main inserts 'chat' into argv (backward compat)."""

  def test_inserts_chat_when_no_subcommand(self):
    """Bare ``yoker`` triggers _needs_default_chat and inserts 'chat' into argv."""
    with patch("yoker.__main__._parse_plugin_args", return_value=([], ["yoker"])):
      with patch("yoker.__main__._needs_default_chat", return_value=True):
        with patch("yoker.__main__.get_cmd", return_value="chat") as m_cmd:
          with patch("yoker.__main__.run_chat"):
            with patch("sys.argv", ["yoker"]):
              main()
    m_cmd.assert_called_once()

  def test_does_not_insert_chat_when_subcommand_present(self):
    """Known subcommand: _needs_default_chat returns False, no insertion."""
    argv = ["yoker", "run", "pkgq"]
    with patch("yoker.__main__._parse_plugin_args", return_value=([], argv)):
      with patch("yoker.__main__._needs_default_chat", return_value=False) as m_needs:
        with patch("yoker.__main__.get_cmd", return_value="run"):
          with patch("yoker.__main__.run_run"):
            with patch("sys.argv", argv):
              main()
    m_needs.assert_called_once_with(argv)


class TestWithStrippingFromSubcommands:
  """``--with`` is stripped before dispatch from any subcommand position."""

  def test_with_stripped_before_run_dispatch(self):
    """``yoker run --with pkgq source`` strips --with before get_cmd."""
    argv = ["yoker", "run", "--with", "pkgq", "source"]
    cleaned = ["yoker", "run", "source"]
    with patch("yoker.__main__._parse_plugin_args", return_value=(["pkgq"], cleaned)) as m_parse:
      with patch("yoker.__main__._needs_default_chat", return_value=False):
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
      with patch("yoker.__main__._needs_default_chat", return_value=False):
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
      with patch("yoker.__main__._needs_default_chat", return_value=False):
        with patch("yoker.__main__.get_cmd", return_value="loop"):
          with patch("yoker.__main__.run_loop") as m_loop:
            with patch("sys.argv", argv):
              main()
    m_loop.assert_called_once_with(["a", "b"])
