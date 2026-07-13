"""``yoker container <source>`` subcommand handler — container setup generation.

Generates a Dockerfile (or Containerfile for podman) for running a yoker
agentic package in a container. Resolves the source via
:func:`yoker.cli.sources.resolve_source` (phase 1 only — metadata) to determine
the source type and, for GitHub sources, the resolved commit SHA for pinning.

Security (H3 remediation):
  - Dockerfile uses JSON-array form exclusively for ``RUN``/``ENTRYPOINT`` —
    no shell-form with string interpolation.
  - The source string is validated against shell metacharacters.
  - ``base_image`` is validated against whitespace/newlines (L3) to prevent
    Dockerfile directive injection.
  - No ``~/.yoker.toml`` or API keys are copied into the image — secret
    management is documented in comments instead.
  - A non-root ``USER`` directive (``USER 1000``) is included.
  - A ``.dockerignore``/``.containerignore`` is generated excluding secrets,
    ``.git``, ``__pycache__``, etc.
  - The yoker version is pinned (``pip install yoker==<version>``).
  - For GitHub sources, the Dockerfile pins to the resolved commit SHA.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from structlog import get_logger

from yoker.cli.commands import ContainerConfig
from yoker.cli.shared import abort, load_subcommand_config, safe_cleanup
from yoker.cli.sources import ResolvedSource, resolve_source
from yoker.exceptions import YokerError

logger = get_logger(__name__)

# Shell metacharacters that indicate injection attempts in the source string.
# JSON-array form prevents shell interpretation, but we validate anyway as
# defense-in-depth (H3).
_SHELL_METACHARS = re.compile(r"[;&|`$()<>{}\n\r!*#~]")

# Files/dirs excluded from the container build context.
_IGNORE_PATTERNS = [
  ".git",
  "__pycache__",
  "*.pyc",
  "*.pyo",
  ".env",
  ".yoker.toml",
  ".ssh",
  "credentials",
  "*.pem",
  "*.key",
  ".venv",
  "venv",
  ".eggs",
  "*.egg-info",
  "dist",
  "build",
]


def run_container() -> None:
  """Run the ``yoker container <source>`` subcommand.

  Loads :class:`ContainerConfig` via Clevis, resolves the source (phase 1),
  validates the source string, generates container files, and exits.
  """
  try:
    config = load_subcommand_config(ContainerConfig)
  except ValueError as e:
    abort(f"Error: {e}\n", 1)

  if not config.source:
    abort(
      "Error: yoker container requires a source. Usage: yoker container <source>\n",
      1,
    )

  _validate_source_string(config.source)
  _validate_base_image(config.base_image)

  # Phase 1: resolve source to determine type and (for GitHub) commit SHA.
  try:
    resolved = resolve_source(config.source)
  except YokerError as e:
    abort(f"Error: {e}\n", 1)

  # Validate engine.
  engine = config.engine
  if engine not in ("docker", "podman"):
    abort(f"Error: --engine must be 'docker' or 'podman', got '{engine}'\n", 1)

  output_dir = Path(config.output_dir).resolve()
  try:
    output_dir.mkdir(parents=True, exist_ok=True)
  except OSError as e:
    safe_cleanup(resolved)
    abort(f"Error: cannot create output directory {output_dir}: {e}\n", 1)

  try:
    yoker_version = _read_yoker_version()
    _generate_files(
      output_dir,
      engine,
      config.base_image,
      yoker_version,
      resolved,
      config.source,
      compose=config.compose,
    )
  finally:
    safe_cleanup(resolved)

  file_name = "Containerfile" if engine == "podman" else "Dockerfile"
  sys.stdout.write(
    f"Container files written to {output_dir} ({file_name}, "
    f".{'container' if engine == 'podman' else 'docker'}ignore"
    + (", docker-compose.yml" if config.compose else "")
    + ")\n"
  )


def _validate_source_string(source: str) -> None:
  """Reject source strings containing shell metacharacters (H3 defense)."""
  if _SHELL_METACHARS.search(source):
    abort(
      f"Error: source contains shell metacharacters (rejected for safety): {source!r}\n",
      1,
    )


def _validate_base_image(base_image: str) -> None:
  """Reject base_image values containing whitespace or newlines (L3).

  A ``base_image`` with a newline could inject Dockerfile directives after
  the ``FROM`` line. Only a single token (no spaces, tabs, newlines) is allowed.
  """
  if re.search(r"\s", base_image):
    abort(
      f"Error: --base-image must not contain whitespace or newlines (rejected for safety): {base_image!r}\n",
      1,
    )


def _read_yoker_version() -> str:
  """Read the yoker version from ``yoker.__version__``."""
  from yoker import __version__

  return __version__


def _generate_files(
  output_dir: Path,
  engine: str,
  base_image: str,
  yoker_version: str,
  resolved: ResolvedSource,
  source: str,
  *,
  compose: bool,
) -> None:
  """Generate the Dockerfile/Containerfile, ignore file, and optional compose."""
  is_podman = engine == "podman"
  file_name = "Containerfile" if is_podman else "Dockerfile"
  ignore_name = ".containerignore" if is_podman else ".dockerignore"

  dockerfile = _build_dockerfile(base_image, yoker_version, resolved, source)
  ignore_content = _build_ignore_file()

  (output_dir / file_name).write_text(dockerfile)
  (output_dir / ignore_name).write_text(ignore_content)

  if compose:
    compose_content = _build_compose_file(file_name, resolved, source)
    (output_dir / "docker-compose.yml").write_text(compose_content)


def _build_dockerfile(
  base_image: str,
  yoker_version: str,
  resolved: ResolvedSource,
  source: str,
) -> str:
  """Build the Dockerfile/Containerfile content (JSON-array form exclusively)."""
  lines: list[str] = []
  lines.append(f"FROM {base_image}")
  lines.append("")
  lines.append("WORKDIR /app")
  lines.append("")
  # Install yoker with pinned version.
  lines.append(f'RUN ["pip", "install", "yoker=={yoker_version}"]')
  lines.append("")

  # Source-specific build steps.
  source_steps, entrypoint_source = _source_build_steps(resolved, source)
  lines.extend(source_steps)

  # Non-root user (H3).
  lines.append("USER 1000")
  lines.append("")

  # Secret management note (H3 — no ~/.yoker.toml copied).
  lines.append("# Secret management: mount your config at runtime:")
  lines.append("#   docker run -v ~/.yoker.toml:/home/yoker/.yoker.toml:ro ...")
  lines.append("# Do NOT bake API keys into the image.")
  lines.append("")

  # Entrypoint in JSON-array form.
  lines.append(f'ENTRYPOINT ["yoker", "run", "{entrypoint_source}"]')
  lines.append("")

  return "\n".join(lines)


def _source_build_steps(
  resolved: ResolvedSource,
  source: str,
) -> tuple[list[str], str]:
  """Return (build-step lines, entrypoint source arg) for the source type.

  Module: ``pip install <module>``; entrypoint uses the module name.
  GitHub: ``git clone`` + ``git checkout <sha>``; entrypoint uses the clone dir.
  Folder: ``COPY`` the folder (using its actual basename); entrypoint uses the
  in-image path.
  Zip: ``COPY`` + extract (using the actual zip filename); entrypoint uses the
  extraction dir.
  """
  if resolved.kind == "module":
    return (
      [f'RUN ["pip", "install", "{source}"]', ""],
      source,
    )

  if resolved.kind == "github":
    # Pin to the resolved commit SHA (C3 remediation).
    sha = _extract_sha_from_trust_key(resolved.trust_key)
    url = _ensure_git_url(source)
    steps = [
      f'RUN ["git", "clone", "{url}", "/app/source"]',
    ]
    if sha is not None:
      steps.append(f'RUN ["git", "-C", "/app/source", "checkout", "{sha}"]')
    steps.append("")
    return steps, "/app/source"

  if resolved.kind == "zip":
    # Use the actual zip filename (Path(source).name) for the COPY source —
    # the build context has the user's file, not a hardcoded "source.zip".
    zip_name = Path(source).name
    return (
      [
        f"COPY {zip_name} /app/source.zip",
        'RUN ["python", "-m", "zipfile", "-e", "/app/source.zip", "/app/source"]',
        "",
      ],
      "/app/source",
    )

  # folder — use the actual folder basename for the COPY source.
  folder_name = Path(source).name
  return (
    [
      f"COPY {folder_name}/ /app/source/",
      "",
    ],
    "/app/source",
  )


def _extract_sha_from_trust_key(trust_key: str) -> str | None:
  """Extract the commit SHA from a GitHub trust key (``github:owner/repo@sha``)."""
  if "@" not in trust_key:
    return None
  sha = trust_key.rsplit("@", 1)[-1]
  # Validate: short SHAs are hex strings of 7-40 chars.
  if re.fullmatch(r"[0-9a-f]{7,40}", sha):
    return sha
  return None


def _ensure_git_url(url: str) -> str:
  """Ensure the URL ends with ``.git`` for the Dockerfile clone step."""
  if url.endswith(".git"):
    return url
  return url + ".git"


def _build_ignore_file() -> str:
  """Build the .dockerignore/.containerignore content (H3)."""
  return "\n".join(_IGNORE_PATTERNS) + "\n"


def _build_compose_file(dockerfile_name: str, resolved: ResolvedSource, source: str) -> str:
  """Build a minimal docker-compose.yml for the generated image."""
  service_name = "yoker-agent"
  return (
    f"services:\n"
    f"  {service_name}:\n"
    f"    build:\n"
    f"      context: .\n"
    f"      dockerfile: {dockerfile_name}\n"
    f"    volumes:\n"
    f"      - ~/.yoker.toml:/home/yoker/.yoker.toml:ro\n"
  )


__all__ = ["run_container"]
