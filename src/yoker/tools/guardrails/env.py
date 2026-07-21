"""Environment variable guardrail for subprocess-spawning tools.

Provides a non-configurable hard denylist of env var names the framework
refuses to let an agent set, regardless of the operator's per-tool allowlist.
These bypass framework trust gates, enable code injection in subprocesses,
or redirect network/credentials. Mirrors the ``path.py`` guardrail pattern
(module-level frozenset + functions, no class).
"""

import re
import sys

# Exact-match denials: name must be in this set verbatim.
_DENIED_EXACT: frozenset[str] = frozenset(
  {
    # Framework trust gates
    "YOKER_TRUST_SOURCE",
    "YOKER_ALLOW_CUSTOM_BASE_URL",
    # Shell-flag / make-flag injection (reopens --eval)
    "MAKEFLAGS",
    "MFLAGS",
    # Git config / workspace redirect
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_CONFIG_PARAMETERS",
    "GIT_CONFIG_COUNT",
    # Shell startup injection
    "BASH_ENV",
    "ENV",
    # Interpreter injection
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
    # Identity / sandbox escape
    "HOME",
    "USER",
    "LOGNAME",
    # API-key substitution
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "GEMINI_API_KEY",
    "OLLAMA_API_KEY",
    "GITHUB_TOKEN",
    # Inherited, not settable
    "PATH",
  }
)

# Prefix-match denials: name matching any prefix is denied.
_DENIED_PREFIXES: tuple[str, ...] = (
  "YOKER_",
  "LD_",
  "DYLD_",
  "BASH_FUNC_",
  "GIT_CONFIG_KEY_",
  "GIT_CONFIG_VALUE_",
)

_DENIED_PREFIX_RE = re.compile(
  r"^(?:YOKER_|LD_|DYLD_|BASH_FUNC_|GIT_CONFIG_KEY_|GIT_CONFIG_VALUE_)"
)

# Windows env vars are case-insensitive (PATH == Path == path). The POSIX
# denylist above uses exact-string match, so on Windows we additionally check
# an uppercased view of the name against uppercased denylist entries plus a
# Windows-only extension set (identity/config vectors that have no POSIX
# equivalent: USERPROFILE, SystemRoot, COMSPEC, PATHEXT, ...).
_WIN_DENIED_EXTRA: frozenset[str] = frozenset(
  {
    "USERPROFILE",
    "USERNAME",
    "USERDOMAIN",
    "APPDATA",
    "LOCALAPPDATA",
    "PROGRAMDATA",
    "PROGRAMFILES",
    "PROGRAMFILES(X86)",
    "SystemRoot",
    "WINDIR",
    "COMSPEC",
    "PATHEXT",
    "SYSTEMDRIVE",
    "HOMEDRIVE",
    "HOMEPATH",
    "TEMP",
    "TMP",
  }
)

_DENIED_EXACT_UPPER = frozenset(n.upper() for n in _DENIED_EXACT)
_WIN_DENIED_EXTRA_UPPER = frozenset(n.upper() for n in _WIN_DENIED_EXTRA)
_WIN_PREFIXES_UPPER = tuple(p.upper() for p in _DENIED_PREFIXES)


def is_denied_env_var(name: str) -> bool:
  """True if ``name`` is on the framework hard-denylist.

  Checked after the per-tool allowlist and enforced regardless of operator
  configuration. The operator cannot waive framework invariants.

  On Windows, env var names are case-insensitive, so the denylist is matched
  case-insensitively (``Path``, ``MakeFlags``, ``Yoker_Trust_Source`` must not
  bypass it). POSIX stays case-sensitive (env vars are case-sensitive there).
  """
  if name in _DENIED_EXACT:
    return True
  if _DENIED_PREFIX_RE.match(name) is not None:
    return True
  if sys.platform == "win32":
    upper = name.upper()
    if upper in _DENIED_EXACT_UPPER:
      return True
    if upper in _WIN_DENIED_EXTRA_UPPER:
      return True
    if upper.startswith(_WIN_PREFIXES_UPPER):
      return True
  return False


def validate_env_vars(
  env_vars: dict[str, str],
  allowed_names: tuple[str, ...],
  max_bytes: int,
) -> tuple[str, str] | None:
  """Validate agent-supplied env_vars against allowlist + denylist + value rules.

  Returns ``(name, error)`` for the first failing entry, or ``None`` if all
  pass. On any failure the caller MUST return ``ToolResult(success=False)``
  without spawning a subprocess.

  Checks per entry:
    - ``name`` must be in ``allowed_names`` (deny-by-default).
    - ``name`` must not match the hard denylist.
    - ``value`` must be a ``str``.
    - ``value`` byte length (UTF-8) <= ``max_bytes``.
    - ``value`` must contain no NUL byte.
    - ``value`` must contain no newlines.
    - ``value`` must be valid UTF-8.
  """
  for name, value in env_vars.items():
    if name not in allowed_names:
      return name, f"env var {name!r} not in per-target allowlist"
    if is_denied_env_var(name):
      return name, f"env var {name!r} on framework hard-denylist"
    if not isinstance(value, str):
      return name, f"env var {name!r} value must be a string"
    if "\x00" in value:
      return name, f"env var {name!r} value contains NUL byte"
    if "\n" in value or "\r" in value:
      return name, f"env var {name!r} value contains newline"
    try:
      vbytes = value.encode("utf-8")
    except UnicodeError:
      return name, f"env var {name!r} value is not valid UTF-8"
    if len(vbytes) > max_bytes:
      return name, f"env var {name!r} value exceeds {max_bytes} bytes"
  return None


__all__ = ["is_denied_env_var", "validate_env_vars"]
