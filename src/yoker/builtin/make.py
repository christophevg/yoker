"""Make tool implementation for Yoker.

Executes ``make <target>`` in a working directory with security guardrails:
target name validation, per-target env_var allowlist + framework hard-denylist,
output size enforcement (centralized in _execute_tool after post_filter),
and process-group kill on timeout (R4).

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
- Output: full stdout/stderr returned; size limit enforced centrally in
  ``_execute_tool`` after ``post_filter`` is applied. If the (filtered)
  output exceeds ``max_output_kb``, an error is returned guiding the LLM
  to use ``post_filter`` to narrow the output.

Residual risk (R5): the subprocess env is ``{**os.environ, **validated_env}``,
so Makefile recipes inherit the yoker process env. Any secret present in
yoker's env (API keys, tokens) is readable by recipes. The per-target
allowlist + hard denylist only govern agent-supplied ``env_vars`` — they do
not filter the inherited env. Operators should load sensitive API keys from
a secrets store (not plain env vars) when running untrusted agents.
"""

import asyncio
import os
import re
import signal
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


async def make(
  target: Annotated[str, Text("Makefile target name (e.g., 'check', 'test')")],
  ctx: ToolContext,
  cwd: Annotated[str, PathArg("Working directory containing the Makefile")] = ".",
  timeout_ms: int = 300000,
  env_vars: dict[str, str] | None = None,
  verbose: bool = False,
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
    verbose: When True, always return full stdout and stderr regardless of
      exit code. When False (default), on success returns only stderr (usually
      empty or warnings) and on failure returns stdout + stderr combined
      (since tools like pytest, ruff, and mypy print errors to stdout, not
      stderr).

  Returns:
    A ``ToolResult`` whose ``result`` is ``{"exit_code": int, "stdout": str,
    "stderr": str}``. ``success`` is True iff ``exit_code == 0``. On failure
    ``error`` carries the relevant output (stdout + stderr when non-verbose,
    stderr only when verbose). Output size is enforced centrally in
    ``_execute_tool`` after ``post_filter`` is applied — if the (filtered)
    output exceeds ``max_output_kb``, an error is returned instead of
    silent truncation.

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

  # --- Subprocess execution (async so the event loop stays responsive) ---
  env = {**os.environ, **validated_env}
  try:
    proc = await asyncio.create_subprocess_exec(
      "make",
      target,
      cwd=str(resolved_cwd),
      env=env,
      stdout=asyncio.subprocess.PIPE,
      stderr=asyncio.subprocess.PIPE,
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
    stdout_b, stderr_b = await asyncio.wait_for(
      proc.communicate(), timeout=effective_timeout_seconds
    )
    stdout = stdout_b.decode("utf-8", errors="replace") if stdout_b else ""
    stderr = stderr_b.decode("utf-8", errors="replace") if stderr_b else ""
  except asyncio.TimeoutError:
    # R4: kill the whole process group (start_new_session created one).
    _kill_process_group(proc.pid)
    # Reap to avoid zombie; collect any partial output the child produced.
    try:
      stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=5)
      stdout = stdout_b.decode("utf-8", errors="replace") if stdout_b else ""
      stderr = stderr_b.decode("utf-8", errors="replace") if stderr_b else ""
    except asyncio.TimeoutError:
      pass
    logger.warning("make_timeout", target=target, timeout_ms=effective_timeout_ms)
    return ToolResult(
      success=False,
      error=f"make target '{target}' exceeded timeout ({effective_timeout_ms} ms)",
    )

  # Output size limit is enforced centrally in _execute_tool AFTER post_filter
  # is applied. The make tool returns full stdout/stderr so that post_filter
  # can grep through the complete output (failures are typically at the end).
  exit_code = proc.returncode
  success = exit_code == 0

  stdout_out = stdout or ""
  stderr_out = stderr or ""

  result = {
    "exit_code": exit_code,
    "stdout": stdout_out,
    "stderr": stderr_out,
  }

  # On failure, the error field is what the LLM sees (line 862 in
  # _processing.py: f"Error: {tool_result.error}"). Tools like pytest,
  # ruff, and mypy print their errors to stdout, not stderr — so returning
  # only stderr on failure hides the actual error messages.
  #
  # Strategy:
  # - verbose=True: error = stderr only (full output is in result dict)
  # - verbose=False, failure: error = stdout + stderr (so LLM sees errors)
  # - verbose=False, success: error = None (success, no error)
  if success:
    error_msg: str | None = None
  elif verbose:
    error_msg = stderr_out
  else:
    # Combine stdout and stderr for failure — stdout typically has the
    # actual error messages (test failures, lint errors, type errors).
    combined = ""
    if stdout_out.strip():
      combined = stdout_out
    if stderr_out.strip():
      if combined:
        combined += f"\n--- stderr ---\n{stderr_out}"
      else:
        combined = stderr_out
    error_msg = (
      combined if combined.strip() else f"make '{target}' failed with exit code {exit_code}"
    )

  return ToolResult(
    success=success,
    result=result,
    error=error_msg,
  )


def _kill_process_group(pid: int) -> None:
  """Kill the process group led by ``pid`` (R4). Best-effort; logs on failure."""
  try:
    os.killpg(pid, signal.SIGKILL)
  except (ProcessLookupError, PermissionError, OSError) as exc:
    logger.warning("make_killpg_failed", pid=pid, error=str(exc))


__all__ = ["make"]
