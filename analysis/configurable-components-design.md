# Configurable Components Design

**Date**: 2026-05-14
**Feature**: Swappable folders for prompts, skills, and agents

## Overview

All three major components follow the same pattern:
- **Prompts** — System prompts for different agent types
- **Skills** — Reusable capability modules
- **Agents** — Agent definitions with behaviors

Each is a **configurable folder** that can be swapped, extended, and versioned.

## Directory Structure

```
src/yoker/
├── prompts/
│   ├── __init__.py           # Prompt loader
│   ├── base.py               # Base classes
│   └── sets/                 # Prompt sets
│       ├── default/
│       ├── minimal/
│       ├── detailed/
│       └── experimental/
│
├── skills/                    # Skills (built-in)
│   ├── __init__.py           # Skill loader
│   ├── base.py               # Base classes
│   └── sets/                 # Skill sets
│       ├── default/
│       ├── minimal/
│       └── development/
│
├── agents/                    # Agents (built-in)
│   ├── __init__.py           # Agent loader
│   ├── base.py               # Base classes
│   └── sets/                 # Agent sets
│       ├── default/
│       ├── research/
│       └── development/
│
# User-defined (outside src/yoker)
~/.yoker/
├── prompts/
│   └── my-prompts/
├── skills/
│   └── my-skills/
└── agents/
    └── my-agents/

# Project-defined
./yoker/
├── prompts/
│   └── project-prompts/
├── skills/
│   └── project-skills/
└── agents/
    └── project-agents/
```

## Configuration

```toml
# yoker.toml

# Prompt configuration
[prompts]
set = "default"                          # Built-in set name
# OR custom path:
# set_path = "~/.yoker/prompts/my-prompts"

[prompts.variants]
main = "default"  # or "concise", "verbose"

# Skill configuration
[skills]
set = "default"                          # Built-in set name
# OR custom path:
# set_path = "./yoker/skills/project-skills"

# Additional skill directories (merged with set)
additional_dirs = ["./skills"]

# Agent configuration
[agents]
set = "default"                          # Built-in set name
# OR custom path:
# set_path = "~/.yoker/agents/my-agents"

# Additional agent directories (merged with set)
additional_dirs = ["./agents"]
```

## Component Formats

### 1. Prompts

Each prompt set is a directory:

```
prompts/sets/default/
├── metadata.toml      # Set metadata
├── main.md            # Main agent prompt
├── general-purpose.md # Sub-agent prompt
├── explore.md         # Explore agent prompt
└── plan.md            # Plan agent prompt
```

**metadata.toml:**
```toml
name = "default"
version = "1.0.0"
description = "Default prompt set for Yoker"
prompts = ["main", "general-purpose", "explore", "plan"]

[variants]
concise = { file = "main-concise.md" }
verbose = { file = "main-verbose.md" }
```

**main.md:**
```markdown
# Main Agent Prompt

You are Yoker, an agent harness with configurable tools.

## Role
You help users with software engineering tasks.

## Strengths
- Reading and analyzing code
- Implementing features
- Managing git operations

## Guidelines
- Complete tasks fully
- Use tools systematically
- Report progress clearly

{% if tools_available %}
Available tools: {{tools_available}}
{% endif %}
```

### 2. Skills

Each skill set is a directory:

```
skills/sets/default/
├── metadata.toml           # Set metadata
├── git-commit.md          # Skill definition
├── project-status.md
├── bug-fixing.md
└── research.md
```

**metadata.toml:**
```toml
name = "default"
version = "1.0.0"
description = "Default skill set for Yoker"
skills = ["git-commit", "project-status", "bug-fixing", "research"]

# Skill dependencies
requires = []

# Conflicting skills (cannot be loaded together)
conflicts = []
```

**git-commit.md:**
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

## Error Handling

- **No changes**: Report nothing to commit
- **Merge conflicts**: Ask user to resolve first
- **Large diff**: Suggest splitting into multiple commits
```

### 3. Agents

Each agent set is a directory:

```
agents/sets/default/
├── metadata.toml           # Set metadata
├── main.md                # Main agent definition
├── researcher.md          # Research agent
├── developer.md           # Developer agent
└── reviewer.md            # Code reviewer agent
```

**metadata.toml:**
```toml
name = "default"
version = "1.0.0"
description = "Default agent set for Yoker"
agents = ["main", "researcher", "developer", "reviewer"]
```

**researcher.md:**
```markdown
---
name: researcher
description: Research topics and gather information
type: subagent
tools:
  - Read
  - WebSearch
  - WebFetch
  - Search
  - Bash
model: llama3.2:latest
max_depth: 3
timeout: 300
---

## Role

You are a research agent. Your job is to gather information
on topics and return findings to the parent agent.

## Capabilities

- Search the web for information
- Read and analyze documents
- Follow citations and references
- Summarize findings concisely

## Workflow

1. **Understand query**: What information is needed?
2. **Search**: Use appropriate search tools
3. **Analyze**: Read and extract relevant information
4. **Synthesize**: Combine findings into coherent summary
5. **Report**: Return findings to parent agent

## Constraints

- READ-ONLY: Never modify files
- Stay focused on the query
- Cite sources when possible
- Report findings concisely
```

## Loader Pattern

All three loaders follow the same pattern:

```python
# src/yoker/prompts/loader.py
# src/yoker/skills/loader.py
# src/yoker/agents/loader.py

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
import tomllib


@dataclass(frozen=True)
class SetMetadata:
    """Metadata for a component set."""
    name: str
    version: str
    description: str = ""
    components: list[str] = field(default_factory=list)


@dataclass
class ComponentSet:
    """A set of components (prompts/skills/agents)."""
    metadata: SetMetadata
    components: dict[str, Any]  # PromptTemplate, Skill, Agent
    path: Path
    
    def get(self, name: str) -> Any:
        """Get a component by name."""
        return self.components.get(name)
    
    def list(self) -> list[str]:
        """List available components."""
        return list(self.components.keys())


class ComponentLoader:
    """Load component sets from directories."""
    
    def __init__(
        self,
        builtin_dir: Path,
        user_dirs: list[Path] | None = None,
        project_dirs: list[Path] | None = None,
    ):
        self.builtin_dir = builtin_dir
        self.user_dirs = user_dirs or []
        self.project_dirs = project_dirs or []
        self._loaded_sets: dict[str, ComponentSet] = {}
    
    def list_sets(self) -> list[str]:
        """List all available sets."""
        sets = set()
        
        # Builtin sets
        for path in self.builtin_dir.iterdir():
            if path.is_dir() and self._has_metadata(path):
                sets.add(path.name)
        
        # User sets
        for user_dir in self.user_dirs:
            for path in user_dir.iterdir():
                if path.is_dir() and self._has_metadata(path):
                    sets.add(path.name)
        
        # Project sets
        for project_dir in self.project_dirs:
            for path in project_dir.iterdir():
                if path.is_dir() and self._has_metadata(path):
                    sets.add(path.name)
        
        return sorted(sets)
    
    def load_set(self, name: str) -> ComponentSet:
        """Load a set by name."""
        if name in self._loaded_sets:
            return self._loaded_sets[name]
        
        # Search order: project -> user -> builtin
        for search_path in [
            *self.project_dirs,
            *self.user_dirs,
            self.builtin_dir,
        ]:
            set_path = search_path / name
            if set_path.exists() and self._has_metadata(set_path):
                component_set = self._load_from_path(set_path)
                self._loaded_sets[name] = component_set
                return component_set
        
        raise ValueError(f"Component set '{name}' not found")
    
    def _has_metadata(self, path: Path) -> bool:
        """Check if path has metadata file."""
        return (path / "metadata.toml").exists()
    
    def _load_from_path(self, path: Path) -> ComponentSet:
        """Load component set from directory."""
        # Load metadata
        metadata = self._load_metadata(path)
        
        # Load components
        components = {}
        for component_name in metadata.components:
            component_path = path / f"{component_name}.md"
            if component_path.exists():
                components[component_name] = self._load_component(component_path)
        
        return ComponentSet(
            metadata=metadata,
            components=components,
            path=path,
        )
    
    def _load_metadata(self, path: Path) -> SetMetadata:
        """Load metadata.toml."""
        metadata_path = path / "metadata.toml"
        with open(metadata_path, "rb") as f:
            data = tomllib.load(f)
        
        return SetMetadata(
            name=data.get("name", path.name),
            version=data.get("version", "0.0.0"),
            description=data.get("description", ""),
            components=data.get("prompts", data.get("skills", data.get("agents", []))),
        )
    
    def _load_component(self, path: Path) -> Any:
        """Load a component from file."""
        # Override in subclasses
        raise NotImplementedError


# Specific loaders inherit from ComponentLoader

class PromptLoader(ComponentLoader):
    """Load prompt sets."""
    
    def _load_component(self, path: Path) -> PromptTemplate:
        """Load a prompt template from file."""
        content = path.read_text()
        variables = self._extract_variables(content)
        return PromptTemplate(
            name=path.stem,
            content=content,
            variables=variables,
        )


class SkillLoader(ComponentLoader):
    """Load skill sets."""
    
    def _load_component(self, path: Path) -> Skill:
        """Load a skill from file."""
        content = path.read_text()
        frontmatter, body = self._parse_frontmatter(content)
        
        return Skill(
            name=frontmatter.get("name", path.stem),
            description=frontmatter.get("description", ""),
            triggers=frontmatter.get("triggers", []),
            tools=frontmatter.get("tools", []),
            content=body,
            path=path,
        )


class AgentLoader(ComponentLoader):
    """Load agent sets."""
    
    def _load_component(self, path: Path) -> AgentDefinition:
        """Load an agent definition from file."""
        content = path.read_text()
        frontmatter, body = self._parse_frontmatter(content)
        
        return AgentDefinition(
            name=frontmatter.get("name", path.stem),
            description=frontmatter.get("description", ""),
            type=frontmatter.get("type", "main"),
            tools=frontmatter.get("tools", []),
            model=frontmatter.get("model"),
            max_depth=frontmatter.get("max_depth", 3),
            timeout=frontmatter.get("timeout", 300),
            system_prompt=body,
            path=path,
        )
```

## Configuration Integration

```python
# src/yoker/config/schema.py

@dataclass(frozen=True)
class ComponentSetConfig:
    """Configuration for a component set."""
    set: str = "default"
    set_path: str | None = None
    additional_dirs: tuple[str, ...] = ()
    variants: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class PromptsConfig(ComponentSetConfig):
    """Prompt set configuration."""
    pass


@dataclass(frozen=True)
class SkillsConfig(ComponentSetConfig):
    """Skill set configuration."""
    pass


@dataclass(frozen=True)
class AgentsConfig(ComponentSetConfig):
    """Agent set configuration."""
    pass


@dataclass(frozen=True)
class Config:
    """Root configuration."""
    prompts: PromptsConfig = field(default_factory=PromptsConfig)
    skills: SkillsConfig = field(default_factory=SkillsConfig)
    agents: AgentsConfig = field(default_factory=AgentsConfig)
    # ... other config
```

## Usage Examples

### Using Built-in Sets

```python
from yoker import Yoker

# Default sets
yoker = Yoker()  # Uses prompts/default, skills/default, agents/default

# Minimal sets
yoker = Yoker(config={
    "prompts": {"set": "minimal"},
    "skills": {"set": "minimal"},
    "agents": {"set": "default"},
})
```

### Using Custom Sets

```python
# Custom prompt set
yoker = Yoker(config={
    "prompts": {"set_path": "~/.yoker/prompts/my-prompts"},
})

# Custom skill set
yoker = Yoker(config={
    "skills": {"set_path": "./yoker/skills/project-skills"},
})

# Custom agent
yoker = Yoker(config={
    "agents": {"set_path": "~/.yoker/agents/my-agents"},
})
```

### Merging Additional Directories

```python
# Add project-specific skills to default set
yoker = Yoker(config={
    "skills": {
        "set": "default",
        "additional_dirs": ["./skills"],
    },
})

# Skills from: default + ./skills (merged)
```

## Component Resolution Order

When loading components, search in order:

1. **Project directories** — `./yoker/prompts/`, `./yoker/skills/`, `./yoker/agents/`
2. **User directories** — `~/.yoker/prompts/`, `~/.yoker/skills/`, `~/.yoker/agents/`
3. **Built-in directories** — `src/yoker/prompts/sets/`, `src/yoker/skills/sets/`, `src/yoker/agents/sets/`

This allows:
- Override built-in components with project/user versions
- Extend built-in sets with additional components
- Create completely custom sets

## Built-in Sets

### Prompts

| Set | Description | Size |
|-----|-------------|------|
| `default` | Standard prompts | ~3KB |
| `minimal` | Short prompts | ~0.5KB |
| `detailed` | Verbose prompts | ~10KB |
| `experimental` | Work in progress | Variable |

### Skills

| Set | Description | Skills |
|-----|-------------|--------|
| `default` | Standard skills | git-commit, project-status, bug-fixing, research |
| `minimal` | Core skills only | git-commit |
| `development` | Development focused | git-commit, bug-fixing, testing |

### Agents

| Set | Description | Agents |
|-----|-------------|--------|
| `default` | Standard agents | main, researcher, developer, reviewer |
| `research` | Research focused | main, researcher |
| `development` | Development focused | main, developer, tester |

## File Format Details

### Prompt File (`.md`)

```markdown
# Optional frontmatter (YAML)
---
variant: verbose
description: Longer version of main prompt
---

# Main Agent Prompt

You are Yoker...

{% if tools_available %}
Tools: {{tools_available}}
{% endif %}
```

### Skill File (`.md`)

```markdown
---
name: skill-name
description: What this skill does
triggers:
  - "trigger phrase"
  - "/command"
tools:
  - Read
  - Bash
---

## Purpose
...

## Workflow
...

## Examples
...
```

### Agent File (`.md`)

```markdown
---
name: agent-name
description: Agent purpose
type: main | subagent
tools:
  - Read
  - Write
model: llama3.2:latest
max_depth: 3
timeout: 300
---

## Role
...

## Capabilities
...

## Constraints
...
```

## Testing

```python
# tests/test_loaders.py

def test_prompt_loader_lists_sets():
    loader = PromptLoader()
    sets = loader.list_sets()
    assert "default" in sets
    assert "minimal" in sets

def test_skill_loader_loads_skill():
    loader = SkillLoader()
    skill_set = loader.load_set("default")
    skill = skill_set.get("git-commit")
    assert skill.name == "git-commit"
    assert "Bash" in skill.tools

def test_agent_loader_loads_agent():
    loader = AgentLoader()
    agent_set = loader.load_set("default")
    agent = agent_set.get("researcher")
    assert agent.type == "subagent"
    assert agent.max_depth == 3

def test_custom_set_override(tmp_path):
    # Create custom prompt set
    custom = tmp_path / "custom"
    custom.mkdir()
    (custom / "metadata.toml").write_text("name = 'custom'\nversion = '1.0'\nprompts = ['main']")
    (custom / "main.md").write_text("Custom prompt")
    
    loader = PromptLoader(builtin_dir=tmp_path)
    prompt_set = loader.load_set("custom")
    assert prompt_set.metadata.name == "custom"
```

## Benefits

| Benefit | Description |
|---------|-------------|
| **Consistency** | Same pattern for all three components |
| **Swappable** | Change sets via config |
| **Extensible** | Add directories to merge |
| **Versionable** | Git-track custom sets |
| **Testable** | Easy to test different sets |
| **Shareable** | Share sets across projects |

## Migration Path

1. Create `prompts/sets/default/` with current prompts
2. Create `skills/sets/default/` with current skills  
3. Create `agents/sets/default/` with current agents
4. Update loaders to use ComponentLoader pattern
5. Add configuration support
6. Document set creation

## Future Enhancements

- Set inheritance (extend another set)
- Set composition (merge multiple sets)
- Set versioning (require specific version)
- Set validation (check required components)
- Set marketplace (download community sets)