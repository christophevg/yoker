# Prompt Sets Design

**Date**: 2026-05-14
**Feature**: Swappable prompt sets for experimentation

## Concept

Prompts are organized in folders (prompt sets), allowing:
- Easy experimentation with different prompt strategies
- A/B testing prompt effectiveness
- Project-specific prompt customizations
- Version control of prompts

## Directory Structure

```
src/yoker/
├── prompts/
│   ├── __init__.py           # Prompt loader and registry
│   ├── base.py               # Base classes (SystemPrompt, PromptSet)
│   └── sets/                 # Prompt sets go here
│       ├── default/          # Default prompt set
│       │   ├── main.md       # Main agent prompt
│       │   ├── general-purpose.md  # Sub-agent prompt
│       │   ├── explore.md    # Read-only search agent
│       │   ├── plan.md       # Planning agent
│       │   └── metadata.toml # Set metadata (name, version, description)
│       ├── minimal/          # Minimal prompt set (for testing)
│       │   ├── main.md
│       │   └── metadata.toml
│       ├── detailed/         # Verbose prompt set (for complex tasks)
│       │   ├── main.md
│       │   ├── general-purpose.md
│       │   ├── explore.md
│       │   └── metadata.toml
│       └── experimental/     # Experimental prompts
│           ├── main.md
│           └── metadata.toml
```

## Prompt Set Format

Each prompt set is a directory containing:

### 1. `metadata.toml` (Required)

```toml
name = "default"
version = "1.0.0"
description = "Default prompt set for Yoker"
author = "Christophe VG"

# Which prompts are included
prompts = ["main", "general-purpose", "explore", "plan"]

# Compatibility
min_yoker_version = "0.1.0"

# Tags for discovery
tags = ["stable", "production"]

# Optional: prompt variants
[variants]
concise = { file = "main-concise.md", description = "Shorter main prompt" }
verbose = { file = "main-verbose.md", description = "Detailed main prompt" }
```

### 2. `main.md` (Required)

```markdown
# Main Agent Prompt

You are Yoker, an agent harness with configurable tools and guardrails.

## Role

You help users with software engineering tasks using the tools available to you.

## Strengths

- Reading and analyzing code across large codebases
- Implementing features and fixing bugs
- Managing git operations safely
- Coordinating sub-agents for complex tasks

## Guidelines

- Complete tasks fully without gold-plating
- Use tools systematically: search → read → edit → test
- Report progress clearly to the user
- Ask for clarification when requirements are ambiguous

## Constraints

- Never modify files outside allowed paths
- Always validate tool parameters before use
- Respect recursion limits for sub-agents

## Tool Usage

Use the tools available to complete the task. When you don't know something,
use the search tools to find it.

{# This is a template variable #}
{% if tools_available %}
Available tools: {{ tools_available | join(", ") }}
{% endif %}
```

### 3. Sub-Agent Prompts (Optional)

```
general-purpose.md   # For general tasks
explore.md          # For read-only search
plan.md             # For planning
```

## Configuration

```toml
# yoker.toml

[prompts]
# Active prompt set
set = "default"  # Can be: default, minimal, detailed, experimental, or custom path

# Custom prompt set location (overrides built-in)
# set_path = "/path/to/custom/prompts"

# Prompt variants
[prompts.variants]
main = "default"  # or "concise", "verbose"
```

## Implementation

### Base Classes

```python
# src/yoker/prompts/base.py

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal
import tomllib


@dataclass(frozen=True)
class PromptMetadata:
    """Metadata for a prompt set."""
    name: str
    version: str
    description: str = ""
    author: str = ""
    prompts: list[str] = field(default_factory=list)
    min_yoker_version: str = "0.1.0"
    tags: list[str] = field(default_factory=list)
    variants: dict[str, dict] = field(default_factory=dict)


@dataclass(frozen=True)
class PromptTemplate:
    """A loaded prompt template."""
    name: str
    content: str
    variables: list[str] = field(default_factory=list)
    
    def render(self, **kwargs) -> str:
        """Render the template with variables."""
        # Simple template rendering (can use Jinja2 later)
        result = self.content
        for key, value in kwargs.items():
            placeholder = f"{{{{{key}}}}}"
            if placeholder in result:
                result = result.replace(placeholder, str(value))
        return result


@dataclass
class PromptSet:
    """A complete prompt set."""
    metadata: PromptMetadata
    prompts: dict[str, PromptTemplate]
    path: Path
    
    def get_prompt(self, name: str, variant: str | None = None) -> PromptTemplate:
        """Get a prompt by name, optionally with variant."""
        if variant and variant in self.metadata.variants:
            # Use variant file
            variant_file = self.metadata.variants[variant]["file"]
            variant_name = variant_file.replace(".md", "")
            return self.prompts.get(variant_name, self.prompts[name])
        
        return self.prompts[name]
    
    def list_prompts(self) -> list[str]:
        """List available prompts."""
        return list(self.prompts.keys())
    
    def list_variants(self, prompt_name: str) -> list[str]:
        """List variants for a prompt."""
        if prompt_name in self.metadata.variants:
            return list(self.metadata.variants.keys())
        return []
```

### Loader

```python
# src/yoker/prompts/loader.py

from pathlib import Path
from typing import Protocol
import tomllib


class PromptLoader:
    """Load and manage prompt sets."""
    
    BUILTIN_SETS = Path(__file__).parent / "sets"
    
    def __init__(self, prompt_sets_dir: Path | None = None):
        self.prompt_sets_dir = prompt_sets_dir or self.BUILTIN_SETS
        self._loaded_sets: dict[str, PromptSet] = {}
    
    def list_sets(self) -> list[str]:
        """List available prompt sets."""
        sets = []
        for path in self.prompt_sets_dir.iterdir():
            if path.is_dir() and (path / "metadata.toml").exists():
                sets.append(path.name)
        return sorted(sets)
    
    def load_set(self, name: str) -> PromptSet:
        """Load a prompt set by name."""
        if name in self._loaded_sets:
            return self._loaded_sets[name]
        
        set_path = self.prompt_sets_dir / name
        if not set_path.exists():
            raise ValueError(f"Prompt set '{name}' not found")
        
        # Load metadata
        metadata_path = set_path / "metadata.toml"
        if not metadata_path.exists():
            raise ValueError(f"Prompt set '{name}' missing metadata.toml")
        
        with open(metadata_path, "rb") as f:
            metadata_dict = tomllib.load(f)
        
        metadata = PromptMetadata(
            name=metadata_dict.get("name", name),
            version=metadata_dict.get("version", "0.0.0"),
            description=metadata_dict.get("description", ""),
            author=metadata_dict.get("author", ""),
            prompts=metadata_dict.get("prompts", []),
            min_yoker_version=metadata_dict.get("min_yoker_version", "0.1.0"),
            tags=metadata_dict.get("tags", []),
            variants=metadata_dict.get("variants", {}),
        )
        
        # Load prompts
        prompts = {}
        for prompt_name in metadata.prompts:
            prompt_file = set_path / f"{prompt_name}.md"
            if prompt_file.exists():
                content = prompt_file.read_text()
                prompts[prompt_name] = PromptTemplate(
                    name=prompt_name,
                    content=content,
                    variables=self._extract_variables(content),
                )
        
        prompt_set = PromptSet(
            metadata=metadata,
            prompts=prompts,
            path=set_path,
        )
        
        self._loaded_sets[name] = prompt_set
        return prompt_set
    
    def _extract_variables(self, content: str) -> list[str]:
        """Extract template variables from content."""
        import re
        # Find {{variable}} patterns
        pattern = r'\{\{(\w+)\}\}'
        return list(set(re.findall(pattern, content)))
    
    def get_prompt(
        self, 
        set_name: str, 
        prompt_name: str, 
        variant: str | None = None,
        **kwargs
    ) -> str:
        """Get a rendered prompt."""
        prompt_set = self.load_set(set_name)
        template = prompt_set.get_prompt(prompt_name, variant)
        return template.render(**kwargs)


# Convenience function
_loader: PromptLoader | None = None

def get_prompt_loader() -> PromptLoader:
    """Get the global prompt loader."""
    global _loader
    if _loader is None:
        _loader = PromptLoader()
    return _loader
```

### Integration with Agent

```python
# src/yoker/agent.py

from yoker.prompts.loader import get_prompt_loader

class Agent:
    def __init__(self, config: Config):
        self.config = config
        self.prompt_loader = get_prompt_loader()
        self.prompt_set = self.prompt_loader.load_set(config.prompts.set)
    
    def _get_system_prompt(self, agent_type: str = "main") -> str:
        """Get system prompt for agent type."""
        variant = self.config.prompts.variants.get(agent_type)
        return self.prompt_loader.get_prompt(
            set_name=self.config.prompts.set,
            prompt_name=agent_type,
            variant=variant,
            tools_available=self._get_tool_names(),
        )
```

## Example Prompt Sets

### Default Set (`sets/default/`)

```markdown
<!-- main.md -->
# Main Agent Prompt

You are Yoker, an agent harness with configurable tools and guardrails.

## Role
You help users with software engineering tasks...

## Strengths
- Reading and analyzing code
- Implementing features
- Managing git operations
- Coordinating sub-agents

## Guidelines
- Complete tasks fully
- Use tools systematically
- Report progress clearly

## Constraints
- Never modify files outside allowed paths
- Always validate parameters
- Respect recursion limits

{% if tools_available %}
Available tools: {{tools_available}}
{% endif %}
```

### Minimal Set (`sets/minimal/`)

```markdown
<!-- main.md -->
You are Yoker. Help users with software engineering tasks.

Use available tools to complete tasks. Report findings concisely.

{% if tools_available %}
Tools: {{tools_available}}
{% endif %}
```

### Detailed Set (`sets/detailed/`)

```markdown
<!-- main.md -->
# Yoker Agent - Detailed Prompt

## Identity

You are Yoker, an agent harness with configurable tools and guardrails.
Your name means "one who yokes" - you join tools together to accomplish tasks.

## Role

You are a software engineering assistant that:
- Analyzes codebases to understand structure and patterns
- Implements features following best practices
- Debugs issues systematically
- Manages git operations with safety checks
- Coordinates sub-agents for complex, multi-step tasks

## Capabilities

### Code Analysis
- Read and understand code in multiple languages
- Identify patterns and anti-patterns
- Trace execution flow through codebases
- Analyze dependencies and relationships

### Feature Implementation
- Plan implementation before coding
- Write clean, maintainable code
- Follow existing code conventions
- Add appropriate tests

### Git Operations
- Create atomic commits with clear messages
- Review changes before committing
- Handle merge conflicts
- Manage branches safely

### Sub-Agent Coordination
- Spawn sub-agents for parallel tasks
- Aggregate results efficiently
- Maintain context isolation
- Respect recursion depth limits

## Workflow

1. **Understand**: Clarify requirements, identify constraints
2. **Plan**: Break down into steps, identify dependencies
3. **Execute**: Use tools systematically, verify results
4. **Report**: Summarize findings, explain decisions

## Constraints

CRITICAL RULES - NEVER VIOLATE:
- Only modify files within allowed paths
- Validate all tool parameters before use
- Never expose sensitive information
- Respect recursion limits (max {{max_depth}} levels)
- Always backup before destructive operations

{% if tools_available %}

## Available Tools

{{tools_available}}

Each tool has specific capabilities and constraints. Use the most appropriate
tool for each task. When in doubt, use Search to locate relevant code first.

{% endif %}

## Output Format

- Be concise but thorough
- Use markdown formatting
- Include code examples when helpful
- Explain reasoning for significant decisions
- Report errors clearly with context
```

## Usage Examples

### Switching Prompt Sets

```python
from yoker import Agent, Config

# Use default prompts
config = Config(prompts={"set": "default"})
agent = Agent(config)

# Use minimal prompts
config = Config(prompts={"set": "minimal"})
agent = Agent(config)

# Use custom prompts
config = Config(prompts={"set_path": "/path/to/my/prompts"})
agent = Agent(config)
```

### Using Variants

```toml
# yoker.toml

[prompts]
set = "default"

[prompts.variants]
main = "verbose"  # Use main-verbose.md instead of main.md
```

### Creating a Custom Prompt Set

```bash
# Create custom prompt set
mkdir -p my_prompts
cat > my_prompts/metadata.toml << EOF
name = "custom"
version = "1.0.0"
description = "Custom prompt set for my project"
prompts = ["main"]
EOF

cat > my_prompts/main.md << EOF
You are Yoker. Be helpful and efficient.
EOF

# Use custom prompts
# In yoker.toml:
[prompts]
set_path = "./my_prompts"
```

## Benefits

1. **Experimentation**: Try different prompt strategies easily
2. **Version Control**: Track prompt changes over time
3. **A/B Testing**: Compare prompt effectiveness
4. **Customization**: Project-specific prompts
5. **Iterative Improvement**: Refine prompts based on results

## Testing

```python
# tests/test_prompts/test_loader.py

def test_list_sets():
    loader = PromptLoader()
    sets = loader.list_sets()
    assert "default" in sets
    assert "minimal" in sets

def test_load_set():
    loader = PromptLoader()
    prompt_set = loader.load_set("default")
    assert prompt_set.metadata.name == "default"
    assert "main" in prompt_set.prompts

def test_get_prompt():
    loader = PromptLoader()
    prompt = loader.get_prompt("default", "main", tools_available=["Read", "Write"])
    assert "You are Yoker" in prompt
    assert "Read, Write" in prompt

def test_custom_set(tmp_path):
    # Create custom set
    set_dir = tmp_path / "custom"
    set_dir.mkdir()
    
    (set_dir / "metadata.toml").write_text("""
name = "custom"
version = "1.0.0"
prompts = ["main"]
""")
    
    (set_dir / "main.md").write_text("Custom prompt: {{tools_available}}")
    
    loader = PromptLoader(prompt_sets_dir=tmp_path)
    prompt = loader.get_prompt("custom", "main", tools_available="Read")
    assert "Custom prompt" in prompt
    assert "Read" in prompt
```

## Migration Path

1. Create `prompts/sets/default/` with current prompts
2. Create `prompts/sets/minimal/` for testing
3. Update Agent to use PromptLoader
4. Add configuration support
5. Document prompt set creation

## Future Enhancements

- Prompt versioning within sets
- Prompt A/B testing framework
- Prompt effectiveness metrics
- Community prompt sets repository
- Prompt linting and validation
- Template inheritance (base prompts)
- Conditional prompt sections based on config