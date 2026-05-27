"""Skill loader for Yoker.

Parses Markdown files with YAML frontmatter into Skill objects.
"""

import os
from pathlib import Path

import yaml

from yoker.exceptions import ConfigurationError, FileNotFoundError
from yoker.skills.schema import Skill

# Security constants
MAX_SKILL_SIZE_KB = 100  # Maximum skill file size in KB
ALLOWED_SKILL_PATHS: list[str] = []  # Empty means all paths allowed (will be configured)


def _validate_skill_path(path: Path, allowed_paths: list[str] | None = None) -> None:
  """Validate that the skill path is within allowed directories.

  Security (SEC-2): Resolve symlinks and validate against allowed paths.

  Args:
    path: Path to validate.
    allowed_paths: List of allowed directory paths. None means use defaults.

  Raises:
    ConfigurationError: If path is outside allowed directories.
  """
  if allowed_paths is None:
    allowed_paths = ALLOWED_SKILL_PATHS

  # No restrictions if not configured
  if not allowed_paths:
    return

  # Resolve symlinks (SEC-4)
  resolved_path = path.resolve()

  for allowed in allowed_paths:
    allowed_resolved = Path(allowed).resolve()
    try:
      # Check if resolved path is within allowed directory
      resolved_path.relative_to(allowed_resolved)
      return  # Path is allowed
    except ValueError:
      continue

  raise ConfigurationError(
    setting="skill_path",
    message=f"Skill path '{path}' is outside allowed directories: {allowed_paths}",
  )


def _validate_skill_size(content: str, path: Path) -> None:
  """Validate that skill content is within size limits.

  Security (SEC-3): Enforce maximum content size.

  Args:
    content: Skill content to validate.
    path: Path to skill file (for error messages).

  Raises:
    ConfigurationError: If content exceeds size limit.
  """
  size_kb = len(content.encode("utf-8")) / 1024
  if size_kb > MAX_SKILL_SIZE_KB:
    raise ConfigurationError(
      setting="skill_size",
      message=f"Skill file '{path}' exceeds maximum size ({size_kb:.1f}KB > {MAX_SKILL_SIZE_KB}KB)",
    )


def parse_skill_frontmatter(content: str) -> tuple[dict[str, object], str]:
  """Parse YAML frontmatter from skill Markdown content.

  Uses the same pattern as agent frontmatter parsing.

  Args:
    content: Raw file content (may contain frontmatter).

  Returns:
    Tuple of (frontmatter dict, body content).
    If no frontmatter, returns ({}, content).

  Raises:
    ConfigurationError: If frontmatter exists but is invalid YAML.
  """
  lines = content.strip().split("\n")

  # Check for frontmatter delimiter
  if not lines or lines[0] != "---":
    return {}, content

  # Find closing delimiter
  try:
    end_index = lines.index("---", 1)
  except ValueError:
    # No closing delimiter - not valid frontmatter
    return {}, content

  # Extract frontmatter and body
  frontmatter_lines = lines[1:end_index]
  body_lines = lines[end_index + 1 :]

  if not frontmatter_lines:
    # Empty frontmatter
    return {}, "\n".join(body_lines)

  # Parse YAML (SEC-1: use safe_load)
  try:
    frontmatter = yaml.safe_load("\n".join(frontmatter_lines))
    if frontmatter is None:
      frontmatter = {}
    if not isinstance(frontmatter, dict):
      raise ConfigurationError(
        setting="frontmatter",
        message=f"Frontmatter must be a YAML dictionary, got {type(frontmatter).__name__}",
      )
    return frontmatter, "\n".join(body_lines)
  except yaml.YAMLError as e:
    raise ConfigurationError(
      setting="frontmatter",
      message=f"Invalid YAML in frontmatter: {e}",
    ) from None


def load_skill(
  path: Path | str,
  allowed_paths: list[str] | None = None,
  namespace: str | None = None,
) -> Skill:
  """Load a skill definition from a Markdown file.

  Args:
    path: Path to the Markdown file.
    allowed_paths: List of allowed directory paths for security.
    namespace: Optional namespace prefix (e.g., 'pkg' for package skills).

  Returns:
    Skill object with parsed frontmatter and body.

  Raises:
    FileNotFoundError: If the file doesn't exist.
    ConfigurationError: If frontmatter is invalid or missing required fields.

  Security:
    - SEC-1: Uses yaml.safe_load() for YAML parsing
    - SEC-2: Validates path against allowed directories
    - SEC-3: Enforces maximum content size
    - SEC-4: Resolves symlinks before validation
    - SEC-5: Namespaces package skills with 'pkg:skill' format
  """
  file_path = Path(path)

  # Resolve symlinks (SEC-4)
  if file_path.is_symlink():
    file_path = file_path.resolve()

  if not file_path.exists():
    raise FileNotFoundError(str(file_path), "skill definition")

  # Validate path (SEC-2)
  _validate_skill_path(file_path, allowed_paths)

  # Expand user home directory
  if "~" in str(file_path):
    file_path = file_path.expanduser()

  try:
    content = file_path.read_text(encoding="utf-8")
  except OSError as e:
    raise ConfigurationError(
      setting=str(file_path),
      message=f"Failed to read file: {e}",
    ) from None

  # Validate size (SEC-3)
  _validate_skill_size(content, file_path)

  frontmatter, body = parse_skill_frontmatter(content)

  # Extract required fields
  name = frontmatter.get("name")
  if not name:
    raise ConfigurationError(
      setting="name",
      message="Required field 'name' is missing or empty",
    )

  description = frontmatter.get("description")
  if not description:
    raise ConfigurationError(
      setting="description",
      message="Required field 'description' is missing or empty",
    )

  # Extract optional triggers
  triggers: tuple[str, ...] = ()
  triggers_raw = frontmatter.get("triggers")
  if triggers_raw is None:
    # Single trigger field fallback
    trigger = frontmatter.get("trigger")
    if trigger:
      triggers = (str(trigger),)
  elif isinstance(triggers_raw, str):
    triggers = (triggers_raw,)
  elif isinstance(triggers_raw, list):
    triggers = tuple(str(t).strip() for t in triggers_raw if t)

  # Extract optional tools
  tools: tuple[str, ...] = ()
  tools_raw = frontmatter.get("tools")
  if tools_raw is None:
    pass  # tools already empty tuple
  elif isinstance(tools_raw, str):
    tools = tuple(t.strip() for t in tools_raw.split(",") if t.strip())
  elif isinstance(tools_raw, list):
    tools = tuple(str(t).strip() for t in tools_raw if t)

  return Skill(
    name=str(name),
    description=str(description),
    content=body.strip(),
    triggers=triggers,
    tools=tools,
    source_path=str(file_path),
    namespace=namespace,
  )


def load_skills(
  directory: Path | str,
  allowed_paths: list[str] | None = None,
  namespace: str | None = None,
) -> dict[str, Skill]:
  """Load all skill definitions from a directory.

  Args:
    directory: Path to the skills directory.
    allowed_paths: List of allowed directory paths for security.
    namespace: Optional namespace prefix for all skills in this directory.

  Returns:
    Dictionary mapping skill names (or 'namespace:name') to Skill objects.

  Raises:
    FileNotFoundError: If the directory doesn't exist.
    ConfigurationError: If any skill definition is invalid.

  Security:
    - Validates directory path against allowed_paths
    - Resolves symlinks before validation
    - Enforces size limits on all skill files
  """
  dir_path = Path(directory)

  # Expand user home directory
  if "~" in str(dir_path):
    dir_path = dir_path.expanduser()

  # Resolve symlinks (SEC-4)
  if dir_path.is_symlink():
    dir_path = dir_path.resolve()

  if not dir_path.exists():
    raise FileNotFoundError(str(dir_path), "skills directory")

  if not dir_path.is_dir():
    raise ConfigurationError(
      setting=str(dir_path),
      message="Skills path is not a directory",
    )

  # Validate directory path (SEC-2)
  _validate_skill_path(dir_path, allowed_paths)

  skills: dict[str, Skill] = {}

  for md_file in sorted(dir_path.glob("*.md")):
    try:
      skill = load_skill(md_file, allowed_paths, namespace)
      skill_key = skill.full_name
      if skill_key in skills:
        raise ConfigurationError(
          setting=f"skill.{skill_key}",
          message=f"Duplicate skill name '{skill_key}' in {md_file}",
        )
      skills[skill_key] = skill
    except ConfigurationError:
      raise
    except Exception as e:
      raise ConfigurationError(
        setting=str(md_file),
        message=f"Failed to load skill definition: {e}",
      ) from None

  return skills


def load_skills_from_env(env_var: str = "YOKER_SKILLS_PATH") -> dict[str, Skill]:
  """Load skills from directories specified in environment variable.

  Environment variable should contain colon-separated list of directories.
  Each directory is searched for skill definition files.

  Args:
    env_var: Environment variable name (default: YOKER_SKILLS_PATH).

  Returns:
    Dictionary mapping skill names to Skill objects.

  Security:
    - Validates all paths against allowed directories
    - Resolves symlinks before validation
  """
  skills: dict[str, Skill] = {}

  path_str = os.environ.get(env_var, "")
  if not path_str:
    return skills

  for directory in path_str.split(":"):
    if not directory:
      continue

    try:
      dir_skills = load_skills(directory)
      skills.update(dir_skills)
    except (FileNotFoundError, ConfigurationError):
      # Log warning but continue loading other directories
      continue

  return skills


__all__ = [
  "parse_skill_frontmatter",
  "load_skill",
  "load_skills",
  "load_skills_from_env",
  "MAX_SKILL_SIZE_KB",
]
