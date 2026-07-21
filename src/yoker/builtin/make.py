"""Make tool implementation for Yoker.

Executes ``make <target>`` in a working directory with security guardrails:
target name validation, per-target env_var allowlist + framework hard-denylist,
output truncation, and process-group kill on timeout (R4).

Security model
--------------
- Target validation (R2/R3): target must match GNU make target syntax
  (``_TARGET_RE``), reject leading dashes (flag injection), reject
  shell metacharacters (``_FORBIDDEN_TARGET_CHARS``), length <= 256.
- cwd (R1): resolved via ``Path.resolve()`` and validated by PathGuardrail
  against ``permissions.filesystem_paths``.
- env_vars (Q1/Q2/Q4): per-target allowlist (deny-by-default) +
  framework hard-denylist (``yoker.tools.guardrails.env``) + value rules
  (str, no NUL, no newlines, valid UTF-8, <= ``max_env_var_bytes``).
- Timeout (R4): subprocess spawned with ``start_new_session=True`` so the
  child leads its own process group; on timeout the whole group is killed
  via ``os.killpg(SIGKILL)`` to prevent orphaned children.
- Output: each stream truncated to ``max_output_kb`` on a UTF-8 boundary.

Residual risk (R5): the subprocess env is ``{**os.environ, **validated_env}``,
so Makefile recipes inherit the yoker process env. Any secret present in
yoker's env (API keys, tokens) is readable by recipes. The per-target
allowlist + hard denylist only govern agent-supplied ``env_vars`` — they do
not filter the inherited env. Operators should load sensitive API keys from
a secrets store (not plain env vars) when running untrusted agents.
"""

import os
import re
import signal
import subprocess
import sys
from pathlib import Path
from typing import Annotated

from structlog import get_logger

from yoker.config import MakeToolConfig
from yoker.tools.annotations import Path as PathArg
from yoker.tools.annotations import Text
from yoker.tools.context import ToolContext
from yoker.tools.guardrails.env import validate_env_vars
from yoker.tools.schema import ToolResult

logger = get_logger(__name__)

# GNU make target name syntax. The first char is restricted to alnum to
# reject leading dashes (flag injection: --eval, -C, -j).
_TARGET_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._%+\-]*$")

# Characters never permitted in a target name. Matches git's FORBIDDEN_CHARS
# plus owner's five.
_FORBIDDEN_TARGET_CHARS: frozenset[str] = frozenset({";", "|", "&", "$", "`", "\n", "\r", "\x00"})

_TRUNCATION_NOTICE = "\n... [truncated]\n"


async def make(
  target: Annotated[str, Text("Makefile target name (e.g., 'check', 'test')")],
  ctx: ToolContext,
  cwd: Annotated[str, PathArg("Working directory containing the Makefile")] = ".",
  timeout_ms: int = 300000,
  env_vars: dict[str, str] | None = None,
) -> ToolResult:
  """Execute a Makefile target via ``make <target>``.

  Args:
    target: Makefile target name (e.g., ``"check"``, ``"test"``). Validated
      against GNU make target syntax; leading dashes and shell
      metacharacters are rejected.
    ctx: Tool execution context carrying the ``MakeToolConfig``.
    cwd: Working directory containing the Makefile. Resolved and checked
      against ``permissions.filesystem_paths`` by PathGuardrail.
    timeout_ms: Per-call timeout in milliseconds. Clamped to
      ``[1000, make_config.timeout_ms]``.
    env_vars: Optional env vars to pass to make. Each name must be in the
      target's ``allowed_env_vars`` allowlist and not on the framework
      hard-denylist; values are length- and content-validated.

  Returns:
    A ``ToolResult`` whose ``result`` is ``{"exit_code": int, "stdout": str,
    "stderr": str, "truncated": bool}``. ``success`` is True iff
    ``exit_code == 0``. On failure ``error`` carries stderr (or a
    guardrail/validation message).

  See the module docstring for the full security model, including the
  R5 env-inheritance residual risk.
  """
  make_config = ctx.config
  if not isinstance(make_config, MakeToolConfig):
    logger.warning("make_invalid_config_type", config_type=type(make_config).__name__)
    return ToolResult(success=False, error="Invalid configuration for make tool")

  # --- Windows platform gate ---
  # R4 (kill the whole process group on timeout) relies on POSIX-only APIs
  # (os.killpg, signal.SIGKILL, start_new_session). Windows process-tree kill
  # requires Job Objects / taskkill /T, which is out of scope for 1.0. Refuse
  # the call with a clear error rather than silently regressing the invariant.
  if sys.platform == "win32":
    return ToolResult(
      success=False,
      error="make tool requires POSIX process-group support; not available on Windows",
    )

  # --- Target validation (R2, R3) ---
  if not isinstance(target, str):
    return ToolResult(success=False, error="Parameter 'target' must be a string")
  stripped = target.strip()
  if not stripped:
    return ToolResult(success=False, error="Parameter 'target' must not be empty")
  if stripped.startswith("-"):
    return ToolResult(success=False, error="Parameter 'target' must not start with '-'")
  if len(target) > 256:
    return ToolResult(success=False, error="Parameter 'target' exceeds 256 characters")
  if not _TARGET_RE.fullmatch(target):
    return ToolResult(success=False, error=f"Invalid make target name: {target!r}")
  for char in _FORBIDDEN_TARGET_CHARS:
    if char in target:
      return ToolResult(success=False, error="Parameter 'target' contains forbidden character")

  # --- Resolve cwd ---
  try:
    resolved_cwd = Path(cwd).resolve()
  except (OSError, ValueError):
    return ToolResult(success=False, error=f"Invalid working directory: {cwd}")

  # --- env_vars validation (per-target allowlist + hard denylist + value rules) ---
  validated_env: dict[str, str] = {}
  if env_vars:
    if not isinstance(env_vars, dict):
      return ToolResult(success=False, error="Parameter 'env_vars' must be an object")
    allowed_names = make_config.allowed_env_vars.get(target, ())
    failure = validate_env_vars(env_vars, allowed_names, make_config.max_env_var_bytes)
    if failure is not None:
      _name, error = failure
      return ToolResult(success=False, error=error)
    validated_env = dict(env_vars)

  # --- Timeout clamp ---
  effective_timeout_ms = max(min(timeout_ms, make_config.timeout_ms), 1000)
  effective_timeout_seconds = effective_timeout_ms / 1000

  logger.info("make_executing", target=target, cwd=str(resolved_cwd), env_keys=list(validated_env))

  # --- Subprocess execution (Popen so we can kill the process group on timeout) ---
  env = {**os.environ, **validated_env}
  try:
    proc = subprocess.Popen(
      ["make", target],
      cwd=str(resolved_cwd),
      env=env,
      stdout=subprocess.PIPE,
      stderr=subprocess.PIPE,
      text=True,
      start_new_session=True,  # R4: child leads its own process group
    )
  except FileNotFoundError:
    logger.error("make_not_found", target=target)
    return ToolResult(success=False, error="make is not installed or not found in PATH")
  except NotADirectoryError:
    return ToolResult(success=False, error=f"Working directory is not a directory: {cwd}")

  stdout = ""
  stderr = ""
  try:
    stdout, stderr = proc.communicate(timeout=effective_timeout_seconds)
  except subprocess.TimeoutExpired:
    # R4: kill the whole process group (start_new_session created one).
    _kill_process_group(proc.pid)
    # Reap to avoid zombie; collect any partial output the child produced.
    try:
      stdout, stderr = proc.communicate(timeout=5)
    except subprocess.TimeoutExpired:
      stdout, stderr = (stdout or "", stderr or "")
    logger.warning("make_timeout", target=target, timeout_ms=effective_timeout_ms)
    return ToolResult(
      success=False,
      error=f"make target '{target}' exceeded timeout ({effective_timeout_ms} ms)",
    )

  # --- Output truncation (per-stream, UTF-8-boundary) ---
  max_output_bytes = make_config.max_output_kb * 1024
  stdout_truncated, stdout_out = _truncate(stdout or "", max_output_bytes)
  stderr_truncated, stderr_out = _truncate(stderr or "", max_output_bytes)

  return ToolResult(
    success=(proc.returncode == 0),
    result={
      "exit_code": proc.returncode,
      "stdout": stdout_out,
      "stderr": stderr_out,
      "truncated": stdout_truncated or stderr_truncated,
    },
    error=stderr_out if proc.returncode != 0 else None,
  )


def _truncate(text: str, max_bytes: int) -> tuple[bool, str]:
  """Truncate text to max_bytes on a UTF-8 boundary.

  Returns ``(truncated, text)``. When truncated, appends a truncation notice.
  """
  encoded = text.encode("utf-8")
  if len(encoded) <= max_bytes:
    return False, text
  # Cut on a UTF-8 boundary: decode with errors='ignore' drops incomplete seq.
  cut = encoded[:max_bytes].decode("utf-8", errors="ignore")
  return True, cut + _TRUNCATION_NOTICE


def _kill_process_group(pid: int) -> None:
  """Kill the process group led by ``pid`` (R4). Best-effort; logs on failure."""
  try:
    os.killpg(pid, signal.SIGKILL)
  except (ProcessLookupError, PermissionError, OSError) as exc:
    logger.warning("make_killpg_failed", pid=pid, error=str(exc))


__all__ = ["make"]
