"""Source resolution for ``yoker run`` (MBI-004 task 4.6).

Resolves four source types — module, GitHub URL, folder, zip — into loadable
sources through a **two-phase** design that is a security invariant:

**Phase 1 —** :func:`resolve_source` returns a :class:`ResolvedSource` carrying
metadata ONLY (source type, paths, parsed ``agent.toml`` manifest, trust key,
cleanup hook). It MUST NOT import ``tools_module``, run ``pip install``, or
execute ANY code. It is safe to call without trust confirmation (used by
``yoker inspect``).

**Phase 2 —** :func:`load_source` performs the actual imports
(``tools_module``), loads skills/agents/tools, and returns
:class:`~yoker.plugins.loader.PluginComponents`. It MUST be called ONLY after
:func:`yoker.plugins.security.check_plugin_allowed` returns ``True``.

Security measures per source type:

* **folder**: ``skills_dir``/``agents_dir``/``tools_module`` paths are
  validated with :func:`yoker.context.validator.is_safe_path` — reject ``..``
  and absolute paths that escape the folder root.
* **github**: HTTPS only; reject ``git://``, ``ssh://``, ``file://``, and
  embedded credentials; run SSRF check
  (:meth:`UrlWebGuardrail._check_ssrf_for_host`) before cloning; record the
  resolved commit SHA; clone to a ``0o700`` temp dir; no auto-``pip install``.
* **zip**: reject symlink entries, absolute paths, ``..`` entries; enforce
  max total uncompressed size (100 MB), max entries (10,000), max compression
  ratio (100:1); extract to a ``0o700`` temp dir; use
  :func:`is_safe_path` per entry.
* **module**: uses the existing :func:`~yoker.plugins.loader.load_plugin`
  ``importlib.import_module`` path (deferred to phase 2).
"""

from __future__ import annotations

import hashlib
import importlib
import shutil
import subprocess
import tempfile
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import urlparse

from structlog import get_logger

from yoker.context.validator import is_safe_path
from yoker.exceptions import PluginError
from yoker.plugins.file_manifest import FileManifestResult, load_file_manifest

if TYPE_CHECKING:
  from yoker.plugins.manifest import PluginManifest

logger = get_logger(__name__)

# Zip-bomb defenses (H1).
_MAX_ZIP_UNCOMPRESSED_BYTES = 100 * 1024 * 1024  # 100 MB
_MAX_ZIP_ENTRIES = 10_000
_MAX_ZIP_COMPRESSION_RATIO = 100

# Unix file mode mask for symlink detection: S_IFMT = 0o170000, S_IFLNK = 0o120000
_S_IFMT = 0o170000
_S_IFLNK = 0o120000


@dataclass
class ResolvedSource:
  """Phase-1 result: metadata about a resolved source (no code execution).

  Attributes:
    kind: Source kind — ``"module"``, ``"github"``, ``"folder"``, or ``"zip"``.
    source_string: The original input string (e.g. ``"pkgq"`` or a URL).
    path: Resolved local path. For folders this is the absolute folder path;
      for github/zip it is the temp extraction dir; for modules it is the
      package directory (resolved in phase 2, so this is the package name as
      a path placeholder until then).
    manifest: Parsed ``agent.toml`` file manifest if found, else ``None``.
    plugin_manifest: Python ``__YOKER_MANIFEST__`` if discoverable without
      imports. Always ``None`` in phase 1 (populated by phase 2 if needed);
      kept as a field for forward compatibility.
    trust_key: Stable identifier for the trust gate
      (e.g. ``"github:owner/repo@abc123"``, ``"folder:/abs/path"``,
      ``"zip:<sha256>"``, ``"module:pkgname"``).
    cleanup: Optional callable to release temp resources (github clone / zip
      extraction). ``None`` for module and folder sources.
  """

  kind: Literal["module", "github", "folder", "zip"]
  source_string: str
  path: Path
  manifest: FileManifestResult | None = None
  plugin_manifest: PluginManifest | None = None
  trust_key: str = ""
  cleanup: Callable[[], None] | None = None


@dataclass
class LoadedSource:
  """Phase-2 result: fully loaded plugin components plus run config.

  Attributes:
    components: Loaded plugin components (tools, skills, agents).
    agent: Agent definition name from the manifest (``[run].agent`` or the
      Python manifest's ``agent`` field), or ``None``.
    prompt: Initial prompt from the manifest, or ``None``.
    tools_module: The ``tools_module`` name declared in the manifest, or
      ``None``. Phase 2 imports it when set.
    cleanup: Optional callable carried through from phase 1.
  """

  components: Any
  agent: str | None = None
  prompt: str | None = None
  tools_module: str | None = None
  cleanup: Callable[[], None] | None = field(default=None)


# ---------------------------------------------------------------------------
# Phase 1: resolve_source (metadata only — no imports, no code execution)
# ---------------------------------------------------------------------------


def resolve_source(source_string: str) -> ResolvedSource:
  """Resolve a source string into metadata (phase 1 — no code execution).

  Detection order: URL (has scheme) → zip (``.zip`` extension, not a dir) →
  folder (``is_dir()``) → module (fallback).

  Args:
    source_string: A module name, GitHub URL, folder path, or zip file path.

  Returns:
    A :class:`ResolvedSource` with metadata only.

  Raises:
    PluginError: If the source cannot be resolved (bad URL, missing zip file,
      unsafe paths, zip-bomb detected, clone failure, etc.).

  Security:
    This function MUST NOT import ``tools_module`` or run ``pip install``. It
    only parses ``agent.toml`` (TOML parsing is not code execution) and
    performs filesystem/network operations (clone, extract) that do not
    execute source-controlled code.
  """
  kind = _detect_kind(source_string)
  logger.info("source_detected", source=source_string, kind=kind)

  if kind == "github":
    return _resolve_github(source_string)
  if kind == "zip":
    return _resolve_zip(source_string)
  if kind == "folder":
    return _resolve_folder(source_string)
  return _resolve_module(source_string)


def _detect_kind(source: str) -> Literal["github", "zip", "folder", "module"]:
  """Detect the source kind from the source string.

  Order matters: a URL is never a local path; a ``.zip`` that is a directory
  is vanishingly unlikely (guarded by ``not is_dir()``).

  Any URL with a scheme (``http``, ``https``, ``git``, ``ssh``, ``file``, ...)
  is classified as ``"github"`` so that :func:`_validate_github_url` can reject
  non-HTTPS schemes — this prevents ``git://``/``ssh://``/``file://`` URLs from
  silently falling through to the module path.
  """
  parsed = urlparse(source)
  if parsed.scheme and "://" in source:
    return "github"
  if source.endswith(".zip") and not Path(source).is_dir():
    return "zip"
  if Path(source).is_dir():
    return "folder"
  return "module"


# --- module ---------------------------------------------------------------


def _resolve_module(source_string: str) -> ResolvedSource:
  """Resolve a module-name source (metadata only — no import in phase 1).

  The package directory and Python manifest are discovered in phase 2
  (:func:`load_source`); phase 1 only records the trust key.
  """
  trust_key = f"module:{source_string}"
  logger.info("source_resolved_module", source=source_string, trust_key=trust_key)
  return ResolvedSource(
    kind="module",
    source_string=source_string,
    path=Path(source_string),
    trust_key=trust_key,
  )


# --- folder ---------------------------------------------------------------


def _resolve_folder(source_string: str) -> ResolvedSource:
  """Resolve a folder source: load ``agent.toml`` and validate paths.

  Security: ``skills_dir``/``agents_dir``/``tools_module`` paths are
  validated with :func:`is_safe_path` to reject ``..`` and absolute paths
  that escape the folder root. Does NOT import ``tools_module``.
  """
  folder = Path(source_string).resolve()
  if not folder.is_dir():
    raise PluginError(
      package=str(folder),
      message=f"Folder source does not exist or is not a directory: {folder}",
    )

  manifest = load_file_manifest(folder / "agent.toml")
  if manifest is not None:
    _validate_folder_subpaths(folder, manifest.plugin_config)

  trust_key = f"folder:{folder}"
  logger.info("source_resolved_folder", source=source_string, trust_key=trust_key)
  return ResolvedSource(
    kind="folder",
    source_string=source_string,
    path=folder,
    manifest=manifest,
    trust_key=trust_key,
  )


def _validate_folder_subpaths(folder: Path, plugin_config: Any) -> None:
  """Validate that skills_dir/agents_dir/tools_module stay under the folder.

  Rejects ``..`` and absolute paths that escape the folder root (H4).
  """
  for name in ("skills_dir", "agents_dir"):
    sub = getattr(plugin_config, name, None)
    if sub is None:
      continue
    _assert_contained(folder, sub, name)

  tools_module = getattr(plugin_config, "tools_module", None)
  if tools_module is not None:
    # tools_module is a dotted Python module path, not a filesystem path.
    # Reject any filesystem-traversal characters — it must be a pure module
    # name resolvable via importlib relative to the folder (loaded in phase 2).
    if "/" in tools_module or "\\" in tools_module or ".." in tools_module:
      raise PluginError(
        package=str(folder),
        message=(
          f"[plugin].tools_module must be a dotted module name, not a path (got: {tools_module!r})"
        ),
      )


def _assert_contained(folder: Path, sub: str, field_name: str) -> None:
  """Assert that ``folder/sub`` resolves inside ``folder``."""
  if Path(sub).is_absolute():
    raise PluginError(
      package=str(folder),
      message=f"[plugin].{field_name} must be a relative path, not absolute (got: {sub!r})",
    )
  if ".." in Path(sub).parts:
    raise PluginError(
      package=str(folder),
      message=f"[plugin].{field_name} must not contain '..' (got: {sub!r})",
    )
  target = (folder / sub).resolve()
  if not is_safe_path(folder, target):
    raise PluginError(
      package=str(folder),
      message=f"[plugin].{field_name} escapes the folder root (got: {sub!r})",
    )


# --- github ---------------------------------------------------------------


def _resolve_github(source_string: str) -> ResolvedSource:
  """Resolve a GitHub URL source: validate, clone, and read ``agent.toml``.

  Security: HTTPS only; reject embedded credentials; run SSRF check before
  cloning; clone to a ``0o700`` temp dir; record the resolved commit SHA;
  no auto-``pip install``.
  """
  _validate_github_url(source_string)

  host = urlparse(source_string).hostname or ""
  _check_ssrf(host)

  tmpdir = _make_secure_tempdir(prefix="yoker-github-")
  try:
    folder = Path(tmpdir.name)
    short_sha = _git_clone(source_string, folder)
    manifest = load_file_manifest(folder / "agent.toml")
    if manifest is not None:
      _validate_folder_subpaths(folder, manifest.plugin_config)

    owner_repo = _github_owner_repo(source_string)
    trust_key = f"github:{owner_repo}@{short_sha}"
    logger.info(
      "source_resolved_github",
      source=source_string,
      trust_key=trust_key,
      sha=short_sha,
    )
    return ResolvedSource(
      kind="github",
      source_string=source_string,
      path=folder,
      manifest=manifest,
      trust_key=trust_key,
      cleanup=tmpdir.cleanup,
    )
  except Exception:
    tmpdir.cleanup()
    raise


def _validate_github_url(url: str) -> None:
  """Validate a GitHub URL: HTTPS only, no embedded credentials, no bad schemes."""
  parsed = urlparse(url)
  if parsed.scheme != "https":
    raise PluginError(
      package=url,
      message=(
        f"GitHub URL must use HTTPS (got scheme {parsed.scheme!r}). "
        "git://, ssh://, and file:// are rejected."
      ),
    )
  if parsed.username or parsed.password:
    raise PluginError(
      package=url,
      message="GitHub URL must not contain embedded credentials (user:pass@host).",
    )
  if parsed.hostname is None:
    raise PluginError(package=url, message=f"GitHub URL has no host: {url}")


def _check_ssrf(host: str) -> None:
  """Run the SSRF check from UrlWebGuardrail against the clone host (C3)."""
  from yoker.tools.web.guardrail import UrlWebGuardrail, WebGuardrailConfig

  guardrail = UrlWebGuardrail(WebGuardrailConfig(block_private_cidrs=True, require_https=True))
  err = guardrail._check_ssrf_for_host(host)
  if err is not None:
    raise PluginError(package=host, message=err)


def _git_clone(url: str, dest: Path) -> str:
  """Shallow-clone ``url`` into ``dest`` and return the short commit SHA."""
  try:
    subprocess.run(
      ["git", "clone", "--depth", "1", url, str(dest)],
      check=True,
      capture_output=True,
      text=True,
    )
  except FileNotFoundError as e:
    raise PluginError(package=url, message="git is not installed or not on PATH.") from e
  except subprocess.CalledProcessError as e:
    stderr = e.stderr.strip() if e.stderr else ""
    raise PluginError(
      package=url,
      message=f"git clone failed: {stderr or e}",
    ) from e

  return _read_commit_sha(dest)


def _read_commit_sha(repo: Path) -> str:
  """Read the resolved commit SHA from a cloned repo (short form)."""
  try:
    result = subprocess.run(
      ["git", "-C", str(repo), "rev-parse", "--short", "HEAD"],
      check=True,
      capture_output=True,
      text=True,
    )
    return result.stdout.strip()
  except (subprocess.CalledProcessError, FileNotFoundError) as e:
    raise PluginError(package=str(repo), message=f"Could not read commit SHA: {e}") from e


def _github_owner_repo(url: str) -> str:
  """Extract ``owner/repo`` from a GitHub URL (best effort)."""
  parsed = urlparse(url)
  parts = [p for p in parsed.path.split("/") if p]
  if len(parts) >= 2:
    repo = parts[1]
    if repo.endswith(".git"):
      repo = repo[:-4]
    return f"{parts[0]}/{repo}"
  return parsed.hostname or "unknown/unknown"


# --- zip ------------------------------------------------------------------


def _resolve_zip(source_string: str) -> ResolvedSource:
  """Resolve a zip source: validate, extract safely, and read ``agent.toml``.

  Security: reject symlink entries, absolute paths, ``..`` entries; enforce
  max total uncompressed size, max entries, max compression ratio; extract
  to a ``0o700`` temp dir; use :func:`is_safe_path` per entry.
  """
  zip_path = Path(source_string)
  if not zip_path.is_file():
    raise PluginError(
      package=source_string,
      message=f"Zip source does not exist or is not a file: {zip_path}",
    )
  if not zipfile.is_zipfile(zip_path):
    raise PluginError(
      package=source_string,
      message=f"Source is not a valid zip file: {zip_path}",
    )

  file_hash = _sha256_of_file(zip_path)
  tmpdir = _make_secure_tempdir(prefix="yoker-zip-")
  try:
    folder = Path(tmpdir.name)
    _safe_extract(zip_path, folder)
    manifest = load_file_manifest(folder / "agent.toml")
    if manifest is not None:
      _validate_folder_subpaths(folder, manifest.plugin_config)

    trust_key = f"zip:{file_hash}"
    logger.info("source_resolved_zip", source=source_string, trust_key=trust_key)
    return ResolvedSource(
      kind="zip",
      source_string=source_string,
      path=folder,
      manifest=manifest,
      trust_key=trust_key,
      cleanup=tmpdir.cleanup,
    )
  except Exception:
    tmpdir.cleanup()
    raise


def _sha256_of_file(path: Path) -> str:
  """Compute the SHA-256 hex digest of a file."""
  h = hashlib.sha256()
  with path.open("rb") as fh:
    for chunk in iter(lambda: fh.read(65536), b""):
      h.update(chunk)
  return h.hexdigest()


def _safe_extract(zip_path: Path, extract_root: Path) -> None:
  """Extract a zip archive with path-traversal, symlink, and zip-bomb defenses.

  Defenses (H1):
    - Reject entries with ``..`` in name or absolute paths.
    - Reject symlink entries (``S_IFLNK`` in ``external_attr``).
    - Enforce max entries, max total uncompressed size, max compression ratio.
    - Validate each target with :func:`is_safe_path`.
  """
  total_uncompressed = 0
  with zipfile.ZipFile(zip_path, "r") as zf:
    infos = zf.infolist()
    if len(infos) > _MAX_ZIP_ENTRIES:
      raise PluginError(
        package=str(zip_path),
        message=(
          f"Zip has too many entries: {len(infos)} > {_MAX_ZIP_ENTRIES}. Possible zip bomb."
        ),
      )
    for zi in infos:
      name = zi.filename
      if zi.is_dir():
        # Still validate the directory path is safe.
        _assert_safe_zip_entry(name, extract_root, zi)
        continue

      _assert_safe_zip_entry(name, extract_root, zi)

      # Zip-bomb size checks.
      uncompressed = zi.file_size
      if uncompressed > 0:
        ratio = uncompressed / zi.compress_size if zi.compress_size > 0 else 1
        if ratio > _MAX_ZIP_COMPRESSION_RATIO:
          raise PluginError(
            package=str(zip_path),
            message=(
              f"Zip entry {name!r} compression ratio {ratio:.0f}:1 exceeds "
              f"max {_MAX_ZIP_COMPRESSION_RATIO}:1. Possible zip bomb."
            ),
          )
      total_uncompressed += uncompressed
      if total_uncompressed > _MAX_ZIP_UNCOMPRESSED_BYTES:
        raise PluginError(
          package=str(zip_path),
          message=(
            f"Zip total uncompressed size exceeds "
            f"{_MAX_ZIP_UNCOMPRESSED_BYTES // (1024 * 1024)} MB. Possible zip bomb."
          ),
        )

      target = (extract_root / name).resolve()
      if not is_safe_path(extract_root, target):
        raise PluginError(
          package=str(zip_path),
          message=f"Zip entry {name!r} escapes the extraction root.",
        )
      target.parent.mkdir(parents=True, exist_ok=True)
      with zf.open(zi, "r") as src, target.open("wb") as dst:
        shutil.copyfileobj(src, dst)


def _assert_safe_zip_entry(name: str, extract_root: Path, zi: zipfile.ZipInfo) -> None:
  """Validate a single zip entry name and type against traversal/symlink rules."""
  # Reject absolute paths.
  if Path(name).is_absolute():
    raise PluginError(
      package=str(extract_root),
      message=f"Zip entry has an absolute path (rejected): {name!r}",
    )
  # Reject '..' components.
  if ".." in Path(name).parts:
    raise PluginError(
      package=str(extract_root),
      message=f"Zip entry contains '..' (rejected): {name!r}",
    )
  # Reject symlink entries (H1).
  mode = (zi.external_attr >> 16) & _S_IFMT
  if mode == _S_IFLNK:
    raise PluginError(
      package=str(extract_root),
      message=f"Zip entry is a symlink (rejected): {name!r}",
    )


# --- shared helpers -------------------------------------------------------


def _make_secure_tempdir(prefix: str) -> tempfile.TemporaryDirectory:
  """Create a temp directory with ``0o700`` permissions."""
  tmpdir = tempfile.TemporaryDirectory(prefix=prefix)
  Path(tmpdir.name).chmod(0o700)
  return tmpdir


# ---------------------------------------------------------------------------
# Phase 2: load_source (imports, code execution — trust gate required)
# ---------------------------------------------------------------------------


def load_source(resolved: ResolvedSource) -> LoadedSource:
  """Load a resolved source into plugin components (phase 2 — requires trust).

  This performs the actual imports (``tools_module`` / ``importlib.import_module``)
  and loads skills/agents. It MUST be called ONLY after
  :func:`yoker.plugins.security.check_plugin_allowed` returns ``True``.

  Args:
    resolved: The phase-1 :class:`ResolvedSource` from :func:`resolve_source`.

  Returns:
    A :class:`LoadedSource` with plugin components and run config.

  Raises:
    PluginError: On import or loading failures.
  """
  if resolved.kind == "module":
    return _load_module_source(resolved)
  return _load_folder_source(resolved)


def _load_module_source(resolved: ResolvedSource) -> LoadedSource:
  """Load a module source via the existing ``load_plugin`` path."""
  from yoker.plugins.loader import load_plugin

  components = load_plugin(resolved.source_string)
  # Read agent/prompt from the Python manifest (fallback for packages without
  # agent.toml).
  agent: str | None = None
  prompt: str | None = None
  tools_module: str | None = None
  try:
    package = importlib.import_module(resolved.source_string)
    manifest = getattr(package, "__YOKER_MANIFEST__", None)
    if manifest is not None:
      agent = getattr(manifest, "agent", None)
      prompt = getattr(manifest, "prompt", None)
  except ImportError as e:
    raise PluginError(
      package=resolved.source_string,
      message=f"Could not import module source: {e}",
    ) from e

  # File manifest (agent.toml) overrides Python manifest for agent/prompt.
  if resolved.manifest is not None:
    agent = resolved.manifest.run_config.agent or agent
    prompt = resolved.manifest.run_config.prompt or prompt
    tools_module = resolved.manifest.plugin_config.tools_module

  return LoadedSource(
    components=components,
    agent=agent,
    prompt=prompt,
    tools_module=tools_module,
    cleanup=resolved.cleanup,
  )


def _load_folder_source(resolved: ResolvedSource) -> LoadedSource:
  """Load a folder/github/zip source: import tools_module, load skills/agents."""
  from yoker.agents.loader import load_agent_definitions
  from yoker.plugins.loader import PluginComponents
  from yoker.skills import load_skills
  from yoker.tools.schema import build_tool_spec

  folder = resolved.path
  plugin_config = resolved.manifest.plugin_config if resolved.manifest is not None else None
  skills_dir = getattr(plugin_config, "skills_dir", "skills") or "skills"
  agents_dir = getattr(plugin_config, "agents_dir", "agents") or "agents"
  tools_module = getattr(plugin_config, "tools_module", None)

  namespace = folder.name

  # Load skills.
  skills: list[Any] = []
  skills_path = folder / skills_dir
  if skills_path.is_dir():
    skills = list(load_skills(skills_path, namespace=namespace).values())

  # Load agent definitions.
  agents: list[Any] = []
  agents_path = folder / agents_dir
  if agents_path.is_dir():
    agents = list(load_agent_definitions(agents_path, namespace=namespace))

  # Import tools_module (phase 2 — only after trust gate).
  tools: list[Any] = []
  if tools_module is not None:
    tools = _import_tools_module(tools_module, folder)

  components = PluginComponents(
    tools=[build_tool_spec(t, namespace=namespace) for t in tools],
    skills=skills,
    agents=agents,
    source=str(folder),
  )

  agent = resolved.manifest.run_config.agent if resolved.manifest else None
  prompt = resolved.manifest.run_config.prompt if resolved.manifest else None

  return LoadedSource(
    components=components,
    agent=agent,
    prompt=prompt,
    tools_module=tools_module,
    cleanup=resolved.cleanup,
  )


def _import_tools_module(tools_module: str, folder: Path) -> list[Any]:
  """Import a tools module from a folder source and return its tool callables.

  The module name may be a dotted path. It is resolved relative to the folder
  root by adding the folder to ``sys.path`` for the duration of the import.
  """
  import sys

  path_str = str(folder)
  added = False
  if path_str not in sys.path:
    sys.path.insert(0, path_str)
    added = True
  try:
    module = importlib.import_module(tools_module)
  except ImportError as e:
    raise PluginError(
      package=str(folder),
      message=f"Could not import tools_module {tools_module!r}: {e}",
    ) from e
  finally:
    if added:
      try:
        sys.path.remove(path_str)
      except ValueError:
        pass

  # Collect callables declared via __YOKER_TOOLS__ or a `tools` list attribute;
  # fall back to all public callables in the module.
  tools = list(getattr(module, "__YOKER_TOOLS__", []) or [])
  if not tools:
    tools_attr = getattr(module, "tools", None)
    if isinstance(tools_attr, list):
      tools = list(tools_attr)
  return tools


__all__ = [
  "LoadedSource",
  "ResolvedSource",
  "load_source",
  "resolve_source",
]
