# Agent Definition Loader Design

**Document Version**: 1.0
**Date**: 2026-04-21
**Status**: Design Analysis
**Task**: 1.3 Agent Definition Loader

## Summary

This document defines the API design for the Agent Definition Loader, which parses Markdown files with YAML frontmatter to create agent definitions. The design follows existing project patterns established in `src/yoker/config/` and integrates with the configuration system.

## 1. Agent Definition Format

Agent definitions are Markdown files with YAML frontmatter:

```markdown
---
name: researcher
description: Research assistant that searches and reads files
tools: List, Read, Search
color: blue
---

# Researcher Agent

You are a research assistant specialized in finding and analyzing information.
```

### Frontmatter Fields

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `name` | Yes | `str` | Agent identifier (used in Agent tool calls) |
| `description` | Yes | `str` | Short description for LLM tool definition |
| `tools` | Yes | `str` | Comma-separated list of available tools |
| `color` | No | `str | None` | Display color for UI integrations |

### Markdown Body

The body after the frontmatter delimiter (`---`) contains the agent's system prompt. This content is passed to the LLM as the system message.

---

## 2. Schema Design

### 2.1 AgentDefinition Dataclass

**File**: `src/yoker/agents/schema.py`

```python
"""Agent definition schema for Yoker.

Provides frozen dataclasses for agent definitions loaded from Markdown files.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AgentDefinition:
  """Agent definition loaded from a Markdown file.

  Attributes:
    name: Agent identifier (unique within a configuration).
    description: Short description for LLM tool definition.
    tools: Tuple of tool names available to this agent.
    color: Optional display color for UI integrations.
    system_prompt: The Markdown body content (agent's system prompt).
    source_path: Path to the source Markdown file.
  """

  name: str
  description: str
  tools: tuple[str, ...]
  color: str | None = None
  system_prompt: str = ""
  source_path: str = ""


__all__ = [
  "AgentDefinition",
]
```

### 2.2 Design Rationale

1. **Frozen dataclass**: Matches `config/schema.py` pattern for immutability
2. **Tuple for tools**: Immutable sequence, hashable, efficient for membership tests
3. **Optional color**: UI integration hook without being required
4. **system_prompt field**: Extracted from Markdown body during parsing
5. **source_path field**: Traceability for error messages and debugging

### 2.3 Integration with Config Schema

The existing `AgentsConfig` in `config/schema.py` already defines:

```python
@dataclass(frozen=True)
class AgentsConfig:
  """Agent definition settings."""
  directory: str = "./agents"
  default_type: str = "main"
```

No changes needed to `AgentsConfig`. The `AgentDefinition` is loaded separately and validated against `ToolsConfig` (tool names must be subset of enabled tools).

---

## 3. Loader Design

### 3.1 Module Structure

**File**: `src/yoker/agents/loader.py`

```python
"""Agent definition loader for Yoker.

Parses Markdown files with YAML frontmatter into AgentDefinition objects.
"""

from pathlib import Path

import yaml

from yoker.agents.schema import AgentDefinition
from yoker.exceptions import FileNotFoundError, ConfigurationError


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
  # Implementation details...
  pass


def load_agent_definition(path: Path | str) -> AgentDefinition:
  """Load an agent definition from a Markdown file.

  Args:
    path: Path to the Markdown file.

  Returns:
    AgentDefinition object with parsed frontmatter and body.

  Raises:
    FileNotFoundError: If the file doesn't exist.
    ConfigurationError: If frontmatter is invalid or missing required fields.
  """
  # Implementation details...
  pass


def load_agent_definitions(directory: Path | str) -> dict[str, AgentDefinition]:
  """Load all agent definitions from a directory.

  Args:
    directory: Path to the agents directory.

  Returns:
    Dictionary mapping agent names to definitions.

  Raises:
    FileNotFoundError: If the directory doesn't exist.
    ConfigurationError: If any agent definition is invalid.
  """
  # Implementation details...
  pass


__all__ = [
  "parse_frontmatter",
  "load_agent_definition",
  "load_agent_definitions",
]
```

### 3.2 Frontmatter Parsing

The `parse_frontmatter` function handles:

1. **No frontmatter**: Returns empty dict and full content
2. **Valid frontmatter**: Returns parsed YAML dict and body
3. **Invalid YAML**: Raises `ConfigurationError` with E005 code context

```python
def parse_frontmatter(content: str) -> tuple[dict[str, object], str]:
  """Parse YAML frontmatter from Markdown content."""
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
    return frontmatter, "\n".join(body_lines)
  except yaml.YAMLError as e:
    raise ConfigurationError(
      setting="frontmatter",
      message=f"Invalid YAML in frontmatter: {e}",
    ) from None
```

### 3.3 Agent Definition Loading

```python
def load_agent_definition(path: Path | str) -> AgentDefinition:
  """Load an agent definition from a Markdown file."""
  file_path = Path(path)

  if not file_path.exists():
    raise FileNotFoundError(str(file_path), "agent definition")

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

  tools_raw = frontmatter.get("tools")
  if not tools_raw:
    raise ConfigurationError(
      setting="tools",
      message="Required field 'tools' is missing or empty",
    )

  # Parse tools (comma-separated string or list)
  if isinstance(tools_raw, str):
    tools = tuple(t.strip() for t in tools_raw.split(",") if t.strip())
  elif isinstance(tools_raw, list):
    tools = tuple(str(t).strip() for t in tools_raw if t)
  else:
    raise ConfigurationError(
      setting="tools",
      message=f"Field 'tools' must be a comma-separated string or list, got {type(tools_raw).__name__}",
    )

  return AgentDefinition(
    name=str(name),
    description=str(description),
    tools=tools,
    color=frontmatter.get("color"),
    system_prompt=body.strip(),
    source_path=str(file_path),
  )
```

### 3.4 Directory Loading

```python
def load_agent_definitions(directory: Path | str) -> dict[str, AgentDefinition]:
  """Load all agent definitions from a directory."""
  dir_path = Path(directory)

  if not dir_path.exists():
    raise FileNotFoundError(str(dir_path), "agents directory")

  if not dir_path.is_dir():
    raise ConfigurationError(
      setting=str(dir_path),
      message="Agents path is not a directory",
    )

  definitions: dict[str, AgentDefinition] = {}

  for md_file in sorted(dir_path.glob("*.md")):
    try:
      definition = load_agent_definition(md_file)
      if definition.name in definitions:
        raise ConfigurationError(
          setting=f"agent.{definition.name}",
          message=f"Duplicate agent name '{definition.name}' in {md_file}",
        )
      definitions[definition.name] = definition
    except ConfigurationError:
      raise
    except Exception as e:
      raise ConfigurationError(
        setting=str(md_file),
        message=f"Failed to load agent definition: {e}",
      ) from None

  return definitions
```

---

## 4. Validator Design

### 4.1 Module Structure

**File**: `src/yoker/agents/validator.py`

```python
"""Agent definition validation for Yoker.

Validates agent definitions against configuration constraints.
"""

from yoker.agents.schema import AgentDefinition
from yoker.config.schema import ToolsConfig
from yoker.exceptions import ValidationError


def validate_non_empty_string(value: str, path: str) -> None:
  """Validate that a value is a non-empty string."""
  if not value or not value.strip():
    raise ValidationError(path, value, "must be a non-empty string")


def validate_tools(
  tools: tuple[str, ...],
  tools_config: ToolsConfig,
  path: str,
) -> list[str]:
  """Validate tools against enabled tools configuration.

  Args:
    tools: Tools specified in agent definition.
    tools_config: Global tools configuration.
    path: Configuration path for error messages.

  Returns:
    List of validation warnings (tool not enabled but specified).

  Raises:
    ValidationError: If any specified tool is not recognized.
  """
  # Map of tool names to their config attributes
  known_tools = {
    "list": tools_config.list,
    "read": tools_config.read,
    "write": tools_config.write,
    "update": tools_config.update,
    "search": tools_config.search,
    "agent": tools_config.agent,
    "git": tools_config.git,
  }

  warnings: list[str] = []
  enabled_tools = {name for name, config in known_tools.items() if config.enabled}

  for tool in tools:
    if tool.lower() not in known_tools:
      raise ValidationError(path, tool, f"unknown tool '{tool}'")

    if tool.lower() not in enabled_tools:
      warnings.append(f"Tool '{tool}' is specified but not enabled in configuration")

  return warnings


def validate_agent_definition(
  definition: AgentDefinition,
  tools_config: ToolsConfig,
  existing_names: set[str] | None = None,
) -> list[str]:
  """Validate an agent definition.

  Args:
    definition: Agent definition to validate.
    tools_config: Global tools configuration.
    existing_names: Set of already-used agent names (for uniqueness check).

  Returns:
    List of validation warnings.

  Raises:
    ValidationError: If validation fails.
  """
  warnings: list[str] = []

  # Validate required fields
  validate_non_empty_string(definition.name, "agent.name")
  validate_non_empty_string(definition.description, "agent.description")

  # Validate tools
  if not definition.tools:
    raise ValidationError("agent.tools", definition.tools, "must specify at least one tool")

  warnings.extend(
    validate_tools(definition.tools, tools_config, "agent.tools")
  )

  # Check uniqueness
  if existing_names and definition.name in existing_names:
    raise ValidationError(
      "agent.name",
      definition.name,
      f"agent name must be unique, '{definition.name}' already defined",
    )

  # Warn if no system prompt
  if not definition.system_prompt.strip():
    warnings.append("Agent has no system prompt (empty Markdown body)")

  return warnings


__all__ = [
  "validate_agent_definition",
  "validate_tools",
  "validate_non_empty_string",
]
```

### 4.2 Error Code Integration

Error E005 (Invalid agent frontmatter) is raised as `ConfigurationError` when:
- YAML parsing fails
- Required fields are missing
- Field types are incorrect

Error E004 (Agent definition not found) is raised as `FileNotFoundError`.

ValidationError is raised for:
- Unknown tool names
- Duplicate agent names
- Empty required fields

---

## 5. Error Handling Approach

### 5.1 Exception Mapping

| Condition | Exception Type | Error Code |
|-----------|---------------|------------|
| File not found | `FileNotFoundError` | E004 |
| Invalid YAML | `ConfigurationError` | E005 |
| Missing required field | `ConfigurationError` | E005 |
| Invalid field type | `ConfigurationError` | E005 |
| Unknown tool name | `ValidationError` | - |
| Duplicate agent name | `ValidationError` | - |

### 5.2 Error Messages

Following the existing pattern from `config/validator.py`:

```python
# ConfigurationError for structural issues
raise ConfigurationError(
  setting="agent.tools",
  message="Required field 'tools' is missing or empty",
)

# ValidationError for semantic issues
raise ValidationError(
  "agent.tools",
  "unknown_tool",
  "unknown tool 'unknown_tool'",
)
```

### 5.3 Graceful Degradation

The loader does not perform validation by default. Validation is a separate step:

```python
# Load (may have warnings)
definition = load_agent_definition("agents/main.md")

# Validate (raises on critical errors)
warnings = validate_agent_definition(definition, tools_config)
for warning in warnings:
  logger.warning(warning)
```

This separation allows:
- Loading definitions without validation (for inspection)
- Validating multiple definitions together (for cross-agent uniqueness)
- Custom validation rules (for future extensions)

---

## 6. Module Public API

### 6.1 `__init__.py`

**File**: `src/yoker/agents/__init__.py`

```python
"""Agent definition module for Yoker.

Provides schema, loader, and validator for agent definitions.
"""

from yoker.agents.schema import AgentDefinition
from yoker.agents.loader import (
  load_agent_definition,
  load_agent_definitions,
  parse_frontmatter,
)
from yoker.agents.validator import (
  validate_agent_definition,
  validate_tools,
)

__all__ = [
  # Schema
  "AgentDefinition",
  # Loader
  "load_agent_definition",
  "load_agent_definitions",
  "parse_frontmatter",
  # Validator
  "validate_agent_definition",
  "validate_tools",
]
```

### 6.2 Usage Examples

#### Load Single Agent

```python
from yoker.agents import load_agent_definition, validate_agent_definition
from yoker.config import load_config

config = load_config("yoker.toml")
definition = load_agent_definition("agents/researcher.md")
warnings = validate_agent_definition(definition, config.tools)
```

#### Load All Agents

```python
from yoker.agents import load_agent_definitions, validate_agent_definition
from yoker.config import load_config

config = load_config("yoker.toml")
definitions = load_agent_definitions(config.agents.directory)

# Validate all definitions
for name, definition in definitions.items():
  warnings = validate_agent_definition(
    definition,
    config.tools,
    existing_names=set(definitions.keys()),
  )
```

#### Parse Frontmatter Only

```python
from yoker.agents import parse_frontmatter

content = """---
name: test
description: Test agent
tools: Read
---
# System Prompt
You are a test agent.
"""

frontmatter, body = parse_frontmatter(content)
# frontmatter = {"name": "test", "description": "Test agent", "tools": "Read"}
# body = "# System Prompt\nYou are a test agent."
```

---

## 7. Integration Points

### 7.1 With Configuration System

The Agent Definition Loader integrates with the existing configuration system:

```
yoker.toml                    → load_config() → Config
                                          ↓
agents/*.md                   → load_agent_definitions() → dict[str, AgentDefinition]
                                          ↓
validate_agent_definition(definition, config.tools)
```

### 7.2 With Agent Runner (Future)

The `AgentDefinition` will be used by the Agent Runner (task 1.4 and Phase 4):

```python
# Future: Agent Runner integration
class Agent:
  def __init__(self, definition: AgentDefinition, config: Config):
    self.definition = definition
    self.config = config
    # Tool filtering based on definition.tools
    # System prompt from definition.system_prompt
```

### 7.3 With Context Manager (Future)

Agent definitions determine available tools, which affects context structure:

```python
# Future: Context includes agent metadata
{
  "type": "metadata",
  "session_id": "uuid",
  "agent_name": "researcher",
  "agent_tools": ["List", "Read", "Search"],
  ...
}
```

---

## 8. Test Strategy

### 8.1 Unit Tests

| Test Category | Tests |
|---------------|-------|
| `parse_frontmatter` | Valid frontmatter, no frontmatter, invalid YAML, empty frontmatter |
| `load_agent_definition` | Valid file, missing file, missing fields, invalid tools format |
| `load_agent_definitions` | Multiple files, duplicate names, empty directory |
| `validate_agent_definition` | Valid definition, unknown tool, disabled tool, duplicate name |

### 8.2 Test Fixtures

```python
# tests/conftest.py or tests/agents/conftest.py
@pytest.fixture
def valid_agent_content() -> str:
  return """---
name: test-agent
description: Test agent for unit tests
tools: Read, Search
color: green
---

# Test Agent

You are a test agent.
"""

@pytest.fixture
def tools_config() -> ToolsConfig:
  return ToolsConfig(
    read=ReadToolConfig(enabled=True),
    search=SearchToolConfig(enabled=True),
  )
```

### 8.3 Edge Cases

- Frontmatter with Windows line endings (`\r\n`)
- Frontmatter with trailing whitespace
- Markdown body with multiple `---` delimiters
- Tool names with different cases (`read`, `Read`, `READ`)
- Empty Markdown body (system prompt required?)
- Very long tool lists
- Special characters in agent names

---

## 9. Future Considerations

### 9.1 Additional Frontmatter Fields

Future versions may support:
- `model: str` — Override default model for this agent
- `temperature: float` — Agent-specific temperature
- `max_tokens: int` — Agent-specific token limit
- `extends: str` — Inherit from another agent definition

### 9.2 Agent Inheritance

```markdown
---
name: senior-researcher
extends: researcher
tools: +Write  # Add to inherited tools
---

Additional instructions for senior researchers.
```

### 9.3 Conditional Tool Availability

Future validation may check:
- Tool combinations (e.g., `Write` requires `Read`)
- Tool prerequisites (e.g., `Agent` tool requires other tools)

---

## 10. Action Items

### 10.1 Implementation Tasks

1. Create `src/yoker/agents/` directory structure
2. Implement `schema.py` with `AgentDefinition` dataclass
3. Implement `loader.py` with parsing and loading functions
4. Implement `validator.py` with validation functions
5. Create `__init__.py` with public API exports
6. Write unit tests in `tests/agents/`
7. Create example agent definitions in `examples/`
8. Update documentation

### 10.2 Review Checkpoints

1. Schema review: Verify frozen dataclass matches patterns
2. Loader review: Ensure error handling matches existing code
3. Validator review: Confirm integration with `ToolsConfig`
4. Integration review: Test with actual configuration files

### 10.3 Documentation Updates

- Update `analysis/functional.md` with implementation notes
- Add API documentation in `docs/api/agents.md`
- Create example configurations in `examples/`

---

## Appendix: Error Code Reference

From `analysis/functional.md` Appendix A:

| Code | Category | Description |
|------|----------|-------------|
| E004 | Config | Agent definition not found |
| E005 | Config | Invalid agent frontmatter |

This design addresses both error codes:
- **E004**: `FileNotFoundError` when agent file or directory doesn't exist
- **E005**: `ConfigurationError` when frontmatter is missing or invalid