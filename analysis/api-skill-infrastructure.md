# API Design: Skill Infrastructure

**Date**: 2026-05-27
**Task**: 2.1 Skill Infrastructure
**Priority**: P1 (MVP Phase 2)
**Context**: Package Plugin System (Issue #14)

## Executive Summary

This document defines the API for the skill infrastructure in yoker, following the established patterns from the agent definition system. Skills are reusable capability modules that inject context into conversations, similar to Claude Code's skill system.

**Key Design Decision**: Skills are NOT tools or agents. They are context injection modules that provide guidance and workflows to the LLM. They're invoked via slash commands (e.g., `/git-commit`) and inject their content as user-level messages.

## Overview

### What is a Skill?

A **skill** is a reusable capability module that:
1. Provides structured guidance for specific tasks
2. Defines workflows and best practices
3. Specifies required tools
4. Injects context into the conversation when invoked

### Skills vs. Tools vs. Agents

| Component | Purpose | Invocation | Output |
|-----------|---------|------------|--------|
| **Tool** | Execute an action | LLM tool call | Structured result |
| **Agent** | Autonomous task completion | Agent tool spawn | Task result |
| **Skill** | Provide guidance | Slash command | Context injection |

**Example**:
- **Tool**: `git status` → Returns repository status
- **Agent**: Developer agent → Autonomously implements a feature
- **Skill**: `git-commit` → Injects commit workflow guidance

## API Design

### 1. Skill Dataclass

**File**: `src/yoker/skills/schema.py`

```python
"""Skill definition schema for Yoker.

Provides frozen dataclass for skill definitions loaded from Markdown files.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Skill:
  """Skill definition loaded from a Markdown file.

  Skills are reusable capability modules that inject context into conversations.
  They provide structured guidance, workflows, and best practices.

  Attributes:
    name: Skill identifier (unique, used in slash commands).
    description: Short description for skill listing.
    triggers: Tuple of trigger phrases or commands that invoke this skill.
    tools: Tuple of tool names required by this skill.
    content: The Markdown body content (skill instructions).
    source_path: Path to the source Markdown file.
  """

  name: str
  description: str
  triggers: tuple[str, ...] = ()
  tools: tuple[str, ...] = ()
  content: str = ""
  source_path: str = ""


__all__ = [
  "Skill",
]
```

**Rationale**:
- Follows `AgentDefinition` pattern for consistency
- Frozen dataclass for immutability
- `triggers` enables natural language invocation (future feature)
- `tools` documents dependencies but doesn't enforce (tool availability is agent-level)
- `content` is the skill instructions (Markdown body)
- `source_path` for debugging and error messages

### 2. SkillLoader Class

**File**: `src/yoker/skills/loader.py`

```python
"""Skill definition loader for Yoker.

Parses Markdown files with YAML frontmatter into Skill objects.
"""

from pathlib import Path

import yaml

from yoker.skills.schema import Skill
from yoker.exceptions import ConfigurationError, FileNotFoundError


def parse_frontmatter(content: str) -> tuple[dict[str, object], str]:
  """Parse YAML frontmatter from Markdown content.

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

  # Parse YAML
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


def load_skill(path: Path | str) -> Skill:
  """Load a skill definition from a Markdown file.

  Args:
    path: Path to the Markdown file.

  Returns:
    Skill object with parsed frontmatter and body.

  Raises:
    FileNotFoundError: If the file doesn't exist.
    ConfigurationError: If frontmatter is invalid or missing required fields.
  """
  file_path = Path(path)

  if not file_path.exists():
    raise FileNotFoundError(str(file_path), "skill definition")

  try:
    content = file_path.read_text(encoding="utf-8")
  except OSError as e:
    raise ConfigurationError(
      setting=str(file_path),
      message=f"Failed to read file: {e}",
    ) from None

  frontmatter, body = parse_frontmatter(content)

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
  triggers_raw = frontmatter.get("triggers", [])
  if isinstance(triggers_raw, str):
    triggers = tuple(t.strip() for t in triggers_raw.split(",") if t.strip())
  elif isinstance(triggers_raw, list):
    triggers = tuple(str(t).strip() for t in triggers_raw if t)
  else:
    triggers = ()

  # Extract optional tools
  tools_raw = frontmatter.get("tools", [])
  if isinstance(tools_raw, str):
    tools = tuple(t.strip() for t in tools_raw.split(",") if t.strip())
  elif isinstance(tools_raw, list):
    tools = tuple(str(t).strip() for t in tools_raw if t)
  else:
    tools = ()

  return Skill(
    name=str(name),
    description=str(description),
    triggers=triggers,
    tools=tools,
    content=body.strip(),
    source_path=str(file_path),
  )


def load_skills(directory: Path | str) -> dict[str, Skill]:
  """Load all skill definitions from a directory.

  Args:
    directory: Path to the skills directory.

  Returns:
    Dictionary mapping skill names to definitions.

  Raises:
    FileNotFoundError: If the directory doesn't exist.
    ConfigurationError: If any skill definition is invalid.
  """
  dir_path = Path(directory)

  if not dir_path.exists():
    raise FileNotFoundError(str(dir_path), "skills directory")

  if not dir_path.is_dir():
    raise ConfigurationError(
      setting=str(dir_path),
      message="Skills path is not a directory",
    )

  skills: dict[str, Skill] = {}

  for md_file in sorted(dir_path.glob("*.md")):
    try:
      skill = load_skill(md_file)
      if skill.name in skills:
        raise ConfigurationError(
          setting=f"skill.{skill.name}",
          message=f"Duplicate skill name '{skill.name}' in {md_file}",
        )
      skills[skill.name] = skill
    except ConfigurationError:
      raise
    except Exception as e:
      raise ConfigurationError(
        setting=str(md_file),
        message=f"Failed to load skill definition: {e}",
      ) from None

  return skills


__all__ = [
  "parse_frontmatter",
  "load_skill",
  "load_skills",
]
```

**Rationale**:
- Reuses `parse_frontmatter()` pattern from `agents/loader.py`
- Could refactor to shared utility in future (DRY)
- `load_skills()` returns dict for O(1) lookup by name
- Duplicate skill names raise error (fail fast)
- Sorted glob for deterministic loading order

### 3. Skill Registry

**File**: `src/yoker/skills/registry.py`

```python
"""Skill registry for managing loaded skills.

Provides SkillRegistry for registering, listing, and looking up skills.
"""

from typing import Any

from .schema import Skill


class SkillRegistry:
  """Registry for managing available skills.

  Skills are registered by name and can be retrieved for context injection.
  Supports namespaced skills from packages (e.g., "pkgq:find").

  Attributes:
    _skills: Internal dictionary mapping skill names to Skill instances.

  Example:
    registry = SkillRegistry()
    registry.register(skill)
    skill = registry.get("git-commit")
    context = skill.content
  """

  def __init__(self) -> None:
    """Initialize an empty skill registry."""
    self._skills: dict[str, Skill] = {}

  def register(self, skill: Skill) -> None:
    """Register a skill.

    Args:
      skill: The Skill instance to register.

    Raises:
      ValueError: If a skill with the same name is already registered.
    """
    if skill.name in self._skills:
      raise ValueError(f"Skill '{skill.name}' is already registered")
    self._skills[skill.name] = skill

  def get(self, name: str) -> Skill | None:
    """Get a skill by name.

    Args:
      name: Skill name (case-sensitive, may include namespace prefix).

    Returns:
      The Skill instance if found, None otherwise.
    """
    return self._skills.get(name)

  def list_skills(self) -> list[Skill]:
    """Get all registered skills.

    Returns:
      List of Skill instances sorted by name.
    """
    return sorted(self._skills.values(), key=lambda s: s.name)

  def names(self) -> list[str]:
    """Get all registered skill names.

    Returns:
      List of skill names sorted alphabetically.
    """
    return sorted(self._skills.keys())

  def get_skills_listing(self) -> str:
    """Get formatted skills listing for context injection.

    Returns:
      Markdown-formatted string listing all skills with descriptions.

    Example:
      >>> registry.get_skills_listing()
      'Available skills:\\n\\n- git-commit: Guide git commit operations\\n- research: Research topics comprehensively'
    """
    lines = ["Available skills:", ""]
    for skill in self.list_skills():
      lines.append(f"- {skill.name}: {skill.description}")
    return "\n".join(lines)


__all__ = [
  "SkillRegistry",
]
```

**Rationale**:
- Mirrors `ToolRegistry` pattern for consistency
- `get_skills_listing()` provides formatted output for context injection
- Supports namespaced skills (e.g., "pkgq:find") via simple string keys
- Empty registry is valid (no required skills)

### 4. Skill Context Injection

**File**: `src/yoker/skills/injection.py`

```python
"""Skill context injection for Yoker.

Injects skill content into user messages as system reminders.
"""

from yoker.skills.schema import Skill


def inject_skill_context(skill: Skill) -> str:
  """Inject skill content as a user-level message.

  Creates a formatted message that provides the skill's guidance
  to the LLM without modifying system prompts.

  Args:
    skill: The skill to inject.

  Returns:
    Formatted string for injection into user message.

  Example:
    >>> skill = Skill(name="git-commit", content="## Workflow\\n1. Stage changes...")
    >>> inject_skill_context(skill)
    '<skill>\\n# git-commit\\n\\n## Workflow\\n1. Stage changes...\\n</skill>'
  """
  return f"<skill>\n# {skill.name}\n\n{skill.content}\n</skill>"


def inject_skills_listing(skills: list[Skill]) -> str:
  """Inject skills listing as a system reminder.

  Lists available skills with descriptions, similar to Claude Code's
  skills reminder.

  Args:
    skills: List of skills to list.

  Returns:
    Formatted string for injection into user message.

  Example:
    >>> inject_skills_listing([skill1, skill2])
    '<system-reminder>\\nThe following skills are available for use with the /skill command:\\n\\n- git-commit: Guide git commit operations\\n- research: Research topics comprehensively\\n</system-reminder>'
  """
  if not skills:
    return ""

  lines = [
    "<system-reminder>",
    "The following skills are available for use with the /skill command:",
    "",
  ]

  for skill in skills:
    lines.append(f"- {skill.name}: {skill.description}")

  lines.append("</system-reminder>")
  return "\n".join(lines)


__all__ = [
  "inject_skill_context",
  "inject_skills_listing",
]
```

**Rationale**:
- Follows Claude Code's `<system-reminder>` pattern from context-injection-analysis.md
- `<skill>` tags distinguish skill content from regular user messages
- Skills listing is separate from skill invocation (listing is always injected, invocation is on-demand)
- Non-intrusive injection (doesn't modify system prompt)

### 5. Skill Command Integration

**File**: `src/yoker/commands/skill.py`

```python
"""Skill command for Yoker.

Invokes skills via slash commands (e.g., /git-commit).
"""

from yoker.commands.base import Command
from yoker.skills.registry import SkillRegistry


class SkillCommand(Command):
  """Invoke a skill by name.

  Usage: /{skill_name}

  Example:
    /git-commit
    /research
    /pkgq:find
  """

  name = "skill"
  description = "Invoke a skill by name"

  def __init__(self, skill_registry: SkillRegistry):
    """Initialize with skill registry.

    Args:
      skill_registry: Registry containing available skills.
    """
    self.skill_registry = skill_registry

  def execute(self, args: str) -> str | None:
    """Execute the skill command.

    Args:
      args: Skill name (e.g., "git-commit" or "pkgq:find").

    Returns:
      Skill content for context injection, or None if skill not found.
    """
    skill_name = args.strip()

    if not skill_name:
      # List available skills
      skills = self.skill_registry.list_skills()
      if not skills:
        return "No skills available."
      lines = ["Available skills:", ""]
      for skill in skills:
        lines.append(f"  {skill.name}: {skill.description}")
      return "\n".join(lines)

    # Look up skill
    skill = self.skill_registry.get(skill_name)
    if skill is None:
      return f"Skill '{skill_name}' not found. Use /skill to list available skills."

    # Return skill content for injection
    from yoker.skills.injection import inject_skill_context
    return inject_skill_context(skill)

  def get_completions(self, partial: str) -> list[str]:
    """Get skill name completions.

    Args:
      partial: Partial skill name.

    Returns:
      List of matching skill names.
    """
    all_skills = self.skill_registry.names()
    if not partial:
      return all_skills
    return [s for s in all_skills if s.startswith(partial)]


__all__ = [
  "SkillCommand",
]
```

**Rationale**:
- Integrates with existing command system (follows `/help`, `/think` pattern)
- Tab completion for skill names
- Listing skills when invoked without arguments
- Returns skill content for context injection (handled by CLI/TUI layer)

### 6. Integration with Agent Class

**File**: `src/yoker/agent.py` (modifications)

```python
# Add to imports
from yoker.skills import SkillRegistry

# Add to __init__
def __init__(
  self,
  ...,
  skill_registry: SkillRegistry | None = None,
  ...,
):
  # ... existing initialization ...
  
  # Initialize skill registry
  self.skill_registry = skill_registry or SkillRegistry()
  
  # Load built-in skills
  self._load_builtin_skills()
  
  # ... rest of initialization ...

def _load_builtin_skills(self) -> None:
  """Load built-in skills from default directory."""
  from pathlib import Path
  from yoker.skills.loader import load_skills
  
  builtin_skills_dir = Path(__file__).parent / "skills" / "builtin"
  if builtin_skills_dir.exists():
    try:
      skills = load_skills(builtin_skills_dir)
      for skill in skills.values():
        self.skill_registry.register(skill)
    except Exception as e:
      log.warning("failed_to_load_builtin_skills", error=str(e))

def _build_user_message(self, user_input: str) -> str:
  """Build user message with context injection.

  Injects skills listing as a system reminder before user input.
  """
  from yoker.skills.injection import inject_skills_listing
  
  parts = []
  
  # Inject skills listing (if skills available)
  skills = self.skill_registry.list_skills()
  if skills:
    parts.append(inject_skills_listing(skills))
  
  # Add actual user input
  parts.append(user_input)
  
  return "\n\n".join(parts)
```

**Rationale**:
- Skills are per-agent (not global), allowing different agents to have different skills
- Built-in skills loaded automatically
- Skills listing injected on every turn (lightweight, ~100 bytes per skill)
- Skill invocation handled by command system
- No modification to existing message structure

### 7. Package Plugin Integration

**File**: `src/yoker/skills/__init__.py`

```python
"""Skills module for Yoker.

Provides skill loading, registration, and context injection.
"""

from .schema import Skill
from .loader import load_skill, load_skills
from .registry import SkillRegistry
from .injection import inject_skill_context, inject_skills_listing

__all__ = [
  "Skill",
  "load_skill",
  "load_skills",
  "SkillRegistry",
  "inject_skill_context",
  "inject_skills_listing",
]
```

**For Package Plugin System (Task 2.2)**:

```python
# In package's __init__.py or yoker.py
from yoker.skills import Skill

# Define skills
SKILLS = [
  Skill(
    name="pkgq:find",
    description="Find package documentation",
    content="...",
  ),
]

# Yoker will discover and register these
```

**Rationale**:
- Packages can provide skills via `SKILLS` list
- Namespace format: `{package}:{skill}` (e.g., `pkgq:find`)
- Registration happens during package loading (Task 2.2)
- Skill objects can be created programmatically or loaded from files

## Skill File Format

### Example: git-commit.md

```markdown
---
name: git-commit
description: Guide git commit operations with atomic commits
triggers:
  - "commit changes"
  - "create a commit"
  - "/commit"
tools:
  - Bash
  - Read
---

## Purpose

Create well-structured git commits with clear messages.

## Workflow

1. **Stage changes**: Review what changed
2. **Group related changes**: One commit per logical change
3. **Write message**: Conventional commit format
4. **Verify**: Check staged changes
5. **Commit**: Create atomic commit

## Guidelines

- Use conventional commit format: `type(scope): description`
- One logical change per commit
- Write clear, descriptive messages
- Reference issues when applicable

## Example

```bash
# Review changes
git status
git diff

# Stage related changes
git add src/yoker/agent.py
git add tests/test_agent.py

# Commit
git commit -m "feat(agent): add lazy tool loading

- Load tools on first use
- Cache loaded tools in registry
- Reduce initial context size by 70%"
```
```

### Example: research.md (from package)

```markdown
---
name: c3:research
description: Research topics comprehensively with full provenance tracking
tools:
  - WebSearch
  - WebFetch
  - Read
---

## Purpose

Research topics and gather information with full source tracking.

## Workflow

1. **Define scope**: What information is needed?
2. **Search**: Use WebSearch for current information
3. **Fetch**: Retrieve detailed content with WebFetch
4. **Analyze**: Extract relevant information
5. **Cite**: Track all sources for provenance
6. **Report**: Synthesize findings with citations

## Guidelines

- Always cite sources
- Track provenance (where information came from)
- Cross-reference multiple sources
- Note uncertainties and conflicts
- Provide URLs for all claims

## Output Format

```markdown
# Research: {topic}

## Summary
{brief summary}

## Findings
{detailed findings with citations}

## Sources
1. [Title](URL) - Retrieved {date}
2. ...
```
```

## Directory Structure

```
src/yoker/
  skills/
    __init__.py          # Public API exports
    schema.py            # Skill dataclass
    loader.py            # Skill loading from files
    registry.py          # Skill registry
    injection.py         # Context injection
    builtin/             # Built-in skills (optional)
      git-commit.md
      research.md
```

## Usage Examples

### Loading Skills from Directory

```python
from yoker.skills import load_skills, SkillRegistry

# Load skills from directory
skills = load_skills("./skills")

# Register in registry
registry = SkillRegistry()
for skill in skills.values():
  registry.register(skill)

# Get skill
skill = registry.get("git-commit")
print(skill.content)
```

### Injecting Skill Context

```python
from yoker.skills import inject_skill_context, inject_skills_listing

# Inject specific skill
skill = registry.get("git-commit")
context = inject_skill_context(skill)
# Result: "<skill>\n# git-commit\n\n## Purpose\n...\n</skill>"

# Inject skills listing
listing = inject_skills_listing(registry.list_skills())
# Result: "<system-reminder>\nThe following skills are available...\n</system-reminder>"
```

### Invoking Skill from CLI

```
User: /git-commit
[Skill git-commit injected into context]
LLM: I'll help you create a git commit. Let me first check the current status...
```

### Using Skill from Package

```python
# In package's yoker.py
from yoker.skills import Skill

SKILLS = [
  Skill(
    name="pkgq:find",
    description="Find package documentation",
    tools=("WebSearch", "WebFetch"),
    content="""
## Purpose
Find documentation for Python packages.

## Workflow
1. Search PyPI for package
2. Fetch documentation
3. Extract relevant sections
...
""",
  ),
]
```

```
User: /pkgq:find
[Skill pkgq:find injected into context]
LLM: I'll help you find package documentation. What package are you looking for?
```

## Configuration

### TOML Configuration

```toml
[skills]
# Built-in set (future: configurable sets)
set = "default"

# Additional skill directories
additional_dirs = ["./skills"]

# Disable built-in skills
load_builtin = true
```

### Programmatic Configuration

```python
from yoker import Agent
from yoker.skills import SkillRegistry, load_skills

# Create registry with custom skills
registry = SkillRegistry()
custom_skills = load_skills("./my-skills")
for skill in custom_skills.values():
  registry.register(skill)

# Pass to agent
agent = Agent(skill_registry=registry)
```

## Testing Strategy

### Unit Tests

**File**: `tests/test_skills/test_loader.py`

```python
import pytest
from pathlib import Path
from yoker.skills import load_skill, load_skills
from yoker.exceptions import ConfigurationError


def test_load_skill_basic(tmp_path):
  """Test loading a valid skill file."""
  skill_file = tmp_path / "test.md"
  skill_file.write_text("""---
name: test-skill
description: A test skill
---
# Test Skill
Content here.
""")
  
  skill = load_skill(skill_file)
  assert skill.name == "test-skill"
  assert skill.description == "A test skill"
  assert "# Test Skill" in skill.content


def test_load_skill_missing_name(tmp_path):
  """Test that missing name raises error."""
  skill_file = tmp_path / "invalid.md"
  skill_file.write_text("""---
description: No name
---
Content
""")
  
  with pytest.raises(ConfigurationError, match="name"):
    load_skill(skill_file)


def test_load_skill_with_triggers(tmp_path):
  """Test loading skill with triggers."""
  skill_file = tmp_path / "triggers.md"
  skill_file.write_text("""---
name: trigger-skill
description: Has triggers
triggers:
  - "do something"
  - "/trigger"
---
Content
""")
  
  skill = load_skill(skill_file)
  assert skill.triggers == ("do something", "/trigger")


def test_load_skills_directory(tmp_path):
  """Test loading multiple skills from directory."""
  (tmp_path / "skill1.md").write_text("""---
name: skill1
description: First skill
---
Content 1
""")
  (tmp_path / "skill2.md").write_text("""---
name: skill2
description: Second skill
---
Content 2
""")
  
  skills = load_skills(tmp_path)
  assert len(skills) == 2
  assert "skill1" in skills
  assert "skill2" in skills


def test_load_skills_duplicate_name(tmp_path):
  """Test that duplicate skill names raise error."""
  (tmp_path / "a.md").write_text("""---
name: duplicate
description: First
---
Content
""")
  (tmp_path / "b.md").write_text("""---
name: duplicate
description: Second
---
Content
""")
  
  with pytest.raises(ConfigurationError, match="Duplicate"):
    load_skills(tmp_path)
```

**File**: `tests/test_skills/test_registry.py`

```python
import pytest
from yoker.skills import Skill, SkillRegistry


def test_register_skill():
  """Test registering a skill."""
  registry = SkillRegistry()
  skill = Skill(name="test", description="Test skill")
  registry.register(skill)
  
  assert registry.get("test") == skill


def test_register_duplicate():
  """Test that duplicate registration raises error."""
  registry = SkillRegistry()
  skill1 = Skill(name="test", description="First")
  skill2 = Skill(name="test", description="Second")
  
  registry.register(skill1)
  with pytest.raises(ValueError, match="already registered"):
    registry.register(skill2)


def test_list_skills():
  """Test listing skills."""
  registry = SkillRegistry()
  registry.register(Skill(name="b", description="B"))
  registry.register(Skill(name="a", description="A"))
  
  skills = registry.list_skills()
  assert len(skills) == 2
  assert skills[0].name == "a"
  assert skills[1].name == "b"


def test_get_skills_listing():
  """Test formatted skills listing."""
  registry = SkillRegistry()
  registry.register(Skill(name="git-commit", description="Guide git commits"))
  registry.register(Skill(name="research", description="Research topics"))
  
  listing = registry.get_skills_listing()
  assert "git-commit: Guide git commits" in listing
  assert "research: Research topics" in listing
```

**File**: `tests/test_skills/test_injection.py`

```python
from yoker.skills import Skill, inject_skill_context, inject_skills_listing


def test_inject_skill_context():
  """Test skill context injection."""
  skill = Skill(
    name="test",
    description="Test skill",
    content="## Workflow\n1. Step one\n2. Step two",
  )
  
  result = inject_skill_context(skill)
  assert "<skill>" in result
  assert "# test" in result
  assert "## Workflow" in result
  assert "</skill>" in result


def test_inject_skills_listing():
  """Test skills listing injection."""
  skills = [
    Skill(name="git-commit", description="Guide git commits"),
    Skill(name="research", description="Research topics"),
  ]
  
  result = inject_skills_listing(skills)
  assert "<system-reminder>" in result
  assert "git-commit: Guide git commits" in result
  assert "research: Research topics" in result
  assert "</system-reminder>" in result


def test_inject_skills_listing_empty():
  """Test empty skills listing returns empty string."""
  result = inject_skills_listing([])
  assert result == ""
```

## Error Handling

### Error Types

| Error | When Raised | Message |
|-------|-------------|---------|
| `FileNotFoundError` | Skill file doesn't exist | "Skill file '{path}' not found" |
| `ConfigurationError` | Invalid frontmatter | "Invalid YAML in frontmatter: {details}" |
| `ConfigurationError` | Missing required field | "Required field 'name' is missing or empty" |
| `ConfigurationError` | Duplicate skill name | "Duplicate skill name '{name}' in {file}" |
| `ValueError` | Duplicate registration | "Skill '{name}' is already registered" |

### Error Recovery

```python
# Graceful handling in agent initialization
def _load_builtin_skills(self) -> None:
  try:
    skills = load_skills(builtin_dir)
    for skill in skills.values():
      self.skill_registry.register(skill)
  except Exception as e:
    log.warning("failed_to_load_builtin_skills", error=str(e))
    # Continue without built-in skills (not fatal)
```

## Performance Considerations

### Context Size Impact

| Component | Size | Notes |
|-----------|------|-------|
| Skills listing (10 skills) | ~500 bytes | Injected on every turn |
| Single skill invocation | 1-3KB | Injected on `/skill-name` |
| Total with 10 skills | ~3.5KB | Per invocation |

**Optimization**: Skills listing is lightweight (~50 bytes per skill). Only invoked skills inject full content.

### Loading Performance

- Skills loaded once at agent initialization
- Registry provides O(1) lookup by name
- No runtime file I/O after loading

### Memory Footprint

- Each skill: ~1-3KB (content + metadata)
- 50 skills: ~50-150KB
- Negligible compared to LLM context window

## Migration Path

### Phase 1: Core Implementation

1. Create `src/yoker/skills/` module
2. Implement `Skill` dataclass
3. Implement `SkillLoader`
4. Implement `SkillRegistry`
5. Write unit tests

### Phase 2: Integration

1. Add `skill_registry` to `Agent.__init__`
2. Implement `_load_builtin_skills()`
3. Implement `_build_user_message()` with context injection
4. Create `SkillCommand` for slash commands
5. Update `CommandRegistry` to include skill commands

### Phase 3: Built-in Skills

1. Create `src/yoker/skills/builtin/` directory
2. Add `git-commit.md`
3. Add `research.md`
4. Add `bug-fixing.md`
5. Add `project-status.md`

### Phase 4: Package Plugin Support (Task 2.2)

1. Update plugin discovery to check for `SKILLS` list
2. Register package skills with namespace prefix
3. Handle skill name conflicts
4. Document package skill format

## Future Enhancements

### Skill Dependencies

```yaml
---
name: complex-skill
description: Skill with dependencies
requires:
  - git-commit
  - research
---
```

### Skill Triggers

Natural language skill invocation:
```python
# Detect trigger phrases in user input
user_input = "commit these changes"
matching_skill = find_skill_by_trigger(user_input)
if matching_skill:
  inject_skill_context(matching_skill)
```

### Skill Sets

Swappable skill collections (like prompt sets):
```toml
[skills]
set = "development"  # git-commit, testing, debugging
```

### Skill Validation

Validate tool availability:
```python
def validate_skill_tools(skill: Skill, tool_registry: ToolRegistry) -> list[str]:
  warnings = []
  for tool_name in skill.tools:
    if not tool_registry.get(tool_name):
      warnings.append(f"Skill '{skill.name}' requires tool '{tool_name}' which is not available")
  return warnings
```

## Dependencies

### Required (already in project)

- `pyyaml>=6.0` - YAML frontmatter parsing
- `structlog>=23.0.0` - Logging

### New (none required)

No new dependencies needed. Skill system uses existing infrastructure.

## Documentation Updates

### Files to Update

1. **README.md**
   - Add "Skills" section to features
   - Add usage examples for skills

2. **docs/quickstart.md**
   - Add skill invocation examples
   - Document `/skill` command

3. **docs/skills.md** (new)
   - Skill file format reference
   - Creating custom skills
   - Package skill integration

4. **CLAUDE.md**
   - Update package structure
   - Add skill development notes

## Checklist

- [ ] Create `src/yoker/skills/` module structure
- [ ] Implement `Skill` dataclass
- [ ] Implement `load_skill()` and `load_skills()`
- [ ] Implement `SkillRegistry`
- [ ] Implement context injection functions
- [ ] Implement `SkillCommand`
- [ ] Add skill registry to `Agent` class
- [ ] Create built-in skills directory
- [ ] Write unit tests (loader, registry, injection)
- [ ] Update documentation (README, docs)
- [ ] Test with existing agents
- [ ] Test with package plugins (Task 2.2)

## Related Tasks

- **Task 2.2**: Package Plugin System - Uses skill infrastructure for package skills
- **Task 3.4**: Configurable Components Infrastructure - Future skill sets
- **Task 3.6**: Skills Sets Implementation - Swappable skill collections

## References

- `src/yoker/agents/` - Agent definition pattern (schema, loader, validator)
- `src/yoker/tools/registry.py` - Tool registry pattern
- `analysis/configurable-components-design.md` - Future skill sets design
- `analysis/context-injection-analysis.md` - Context injection patterns from Claude Code
- `analysis/context-implementation-plan.md` - Implementation priorities