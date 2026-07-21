"""Tests for the env var guardrail (yoker.tools.guardrails.env).

Covers: hard-denylist enforcement (each denied pattern), per-target allowlist
enforcement, and value validation (oversize, NUL, newline, non-UTF-8).
"""

import sys

import pytest

from yoker.tools.guardrails.env import is_denied_env_var, validate_env_vars


class TestIsDeniedEnvVar:
  """Hard-denylist membership tests."""

  @pytest.mark.parametrize(
    "name",
    [
      # Framework trust gates
      "YOKER_TRUST_SOURCE",
      "YOKER_ALLOW_CUSTOM_BASE_URL",
      "YOKER_DEV_MODE",
      "YOKER_FOO",
      # Shared-library / interpreter injection
      "LD_PRELOAD",
      "LD_LIBRARY_PATH",
      "LD_AUDIT",
      "DYLD_INSERT_LIBRARIES",
      "DYLD_LIBRARY_PATH",
      "DYLD_FALLBACK_LIBRARY_PATH",
      # Shell-flag / make-flag injection
      "MAKEFLAGS",
      "MFLAGS",
      # Git config / workspace redirect
      "GIT_DIR",
      "GIT_WORK_TREE",
      "GIT_CONFIG_PARAMETERS",
      "GIT_CONFIG_COUNT",
      "GIT_CONFIG_KEY_0",
      "GIT_CONFIG_VALUE_1",
      # Shell startup injection
      "BASH_ENV",
      "ENV",
      "BASH_FUNC_foo%%",
      "BASH_FUNC_environment%%",
      # Interpreter injection (exact)
      "PYTHONSTARTUP",
      "PYTHONPATH",
      "PYTHONHOME",
      "PERL5OPT",
      "RUBYOPT",
      "NODE_OPTIONS",
      "NODE_PATH",
      # Shell parsing
      "IFS",
      # Network / TLS redirect
      "HTTP_PROXY",
      "HTTPS_PROXY",
      "ALL_PROXY",
      "NO_PROXY",
      "SSL_CERT_FILE",
      "REQUESTS_CA_BUNDLE",
      "CURL_CA_BUNDLE",
      # Identity
      "HOME",
      "USER",
      "LOGNAME",
      # API-key substitution
      "ANTHROPIC_API_KEY",
      "OPENAI_API_KEY",
      "GEMINI_API_KEY",
      "OLLAMA_API_KEY",
      "GITHUB_TOKEN",
      # Inherited
      "PATH",
    ],
  )
  def test_denied_names(self, name: str) -> None:
    """Names on the hard-denylist are denied."""
    assert is_denied_env_var(name) is True

  @pytest.mark.parametrize(
    "name",
    [
      "TEST",
      "BUILD",
      "LINT_FLAGS",
      "VARIANT",
      "DEBUG",
      "PROFILE",
      "COVERAGE",
      "PYTEST_ADDOPTS",
      "_TEST",
      "MY_VAR",
    ],
  )
  def test_allowed_names(self, name: str) -> None:
    """Names not on the denylist pass the denylist check."""
    assert is_denied_env_var(name) is False


class TestValidateEnvVars:
  """validate_env_vars: allowlist + denylist + value rules."""

  def test_empty_env_vars_passes(self) -> None:
    """Empty env_vars returns None (no failure)."""
    assert validate_env_vars({}, ("TEST",), 4096) is None

  def test_allowed_var_passes(self) -> None:
    """A var in the allowlist and not denied, with a valid value, passes."""
    assert validate_env_vars({"TEST": "foo.py"}, ("TEST",), 4096) is None

  def test_var_not_in_allowlist_rejected(self) -> None:
    """A var not in the per-target allowlist is rejected (deny-by-default)."""
    result = validate_env_vars({"OTHER": "x"}, ("TEST",), 4096)
    assert result is not None
    name, error = result
    assert name == "OTHER"
    assert "allowlist" in error

  def test_empty_allowlist_rejects_all(self) -> None:
    """Empty allowlist rejects every var (deny-by-default)."""
    result = validate_env_vars({"TEST": "foo"}, (), 4096)
    assert result is not None
    assert result[0] == "TEST"

  def test_denied_var_rejected_even_if_allowlisted(self) -> None:
    """A hard-denied var is rejected even if present in the allowlist."""
    result = validate_env_vars({"MAKEFLAGS": "--eval=pwn"}, ("MAKEFLAGS",), 4096)
    assert result is not None
    name, error = result
    assert name == "MAKEFLAGS"
    assert "hard-denylist" in error

  def test_denied_yoker_prefix_rejected_even_if_allowlisted(self) -> None:
    """YOKER_* prefix is denied even if allowlisted."""
    result = validate_env_vars({"YOKER_TRUST_SOURCE": "1"}, ("YOKER_TRUST_SOURCE",), 4096)
    assert result is not None
    assert "hard-denylist" in result[1]

  def test_non_string_value_rejected(self) -> None:
    """Non-string value is rejected."""
    result = validate_env_vars({"TEST": 123}, ("TEST",), 4096)  # type: ignore[dict-item]
    assert result is not None
    assert result[0] == "TEST"
    assert "string" in result[1]

  def test_oversize_value_rejected(self) -> None:
    """Value exceeding max_bytes is rejected."""
    big = "x" * 4097
    result = validate_env_vars({"TEST": big}, ("TEST",), 4096)
    assert result is not None
    assert result[0] == "TEST"
    assert "exceeds" in result[1]

  def test_value_at_limit_passes(self) -> None:
    """Value exactly at max_bytes passes."""
    ok = "x" * 4096
    assert validate_env_vars({"TEST": ok}, ("TEST",), 4096) is None

  def test_nul_byte_in_value_rejected(self) -> None:
    """NUL byte in value is rejected."""
    result = validate_env_vars({"TEST": "foo\x00bar"}, ("TEST",), 4096)
    assert result is not None
    assert result[0] == "TEST"
    assert "NUL" in result[1]

  def test_newline_in_value_rejected(self) -> None:
    """Newline in value is rejected."""
    result = validate_env_vars({"TEST": "foo\nbar"}, ("TEST",), 4096)
    assert result is not None
    assert result[0] == "TEST"
    assert "newline" in result[1]

  def test_carriage_return_in_value_rejected(self) -> None:
    """Carriage return in value is rejected."""
    result = validate_env_vars({"TEST": "foo\rbar"}, ("TEST",), 4096)
    assert result is not None
    assert "newline" in result[1]

  def test_returns_first_failure(self) -> None:
    """validate_env_vars returns the first failing entry, not later ones."""
    # FIRST is allowed and valid; SECOND is not in allowlist — fails there.
    env_vars = {"FIRST": "ok", "SECOND": "x"}
    result = validate_env_vars(env_vars, ("FIRST",), 4096)
    assert result is not None
    assert result[0] == "SECOND"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows env vars are case-insensitive")
class TestIsDeniedEnvVarWindowsCaseSensitivity:
  """On Windows the denylist must match case-insensitively.

  Windows env var names are case-insensitive (``PATH`` == ``Path`` == ``path``),
  so an agent setting ``Path``, ``MakeFlags``, or ``Yoker_Trust_Source`` must
  not bypass the exact-match denylist.
  """

  def test_path_denied_case_insensitive_on_windows(self) -> None:
    assert is_denied_env_var("Path") is True

  def test_makeflags_denied_case_insensitive_on_windows(self) -> None:
    assert is_denied_env_var("MakeFlags") is True

  def test_yoker_prefix_denied_case_insensitive_on_windows(self) -> None:
    assert is_denied_env_var("Yoker_Trust_Source") is True

  def test_userprofile_denied_on_windows(self) -> None:
    assert is_denied_env_var("USERPROFILE") is True

  def test_systemroot_denied_on_windows(self) -> None:
    assert is_denied_env_var("SystemRoot") is True

  def test_comspec_denied_case_insensitive_on_windows(self) -> None:
    assert is_denied_env_var("comspec") is True


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX env vars are case-sensitive")
class TestIsDeniedEnvVarPosixCaseSensitivity:
  """POSIX env vars are case-sensitive — the denylist stays exact-match.

  Regression: the Windows case-insensitive branch must not leak to POSIX.
  ``Path`` is a different variable from ``PATH`` on POSIX and is not denied.
  """

  def test_path_denied_exact_on_posix(self) -> None:
    assert is_denied_env_var("PATH") is True

  def test_path_variant_not_denied_on_posix(self) -> None:
    assert is_denied_env_var("Path") is False
