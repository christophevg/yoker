# Component Resolution Strategy

**Date**: 2026-05-14
**Question**: How are components combined when they exist at multiple levels?

## Resolution Strategy

### Key Concept: Sets vs. Additional Directories

There are two mechanisms for loading components:

1. **Sets** — One active set at a time (override behavior)
2. **Additional Directories** — Merged with active set (union behavior)

```toml
# Example configuration
[prompts]
set = "default"                    # Use this set (override)
additional_dirs = ["./prompts"]    # Merge these (union)

[skills]
set = "default"
additional_dirs = ["./skills"]

[agents]
set = "default"
additional_dirs = ["./agents"]
```

## Set Resolution (Override)

When you specify a set, **only that set is used**:

```toml
[prompts]
set = "default"
```

**Behavior**: Load from `prompts/sets/default/` — built-in, user, or project level (first match wins)

**Resolution Order**:
1. `./yoker/prompts/sets/default/` (project)
2. `~/.yoker/prompts/sets/default/` (user)
3. `src/yoker/prompts/sets/default/` (built-in)

**Result**: First existing set wins, others are ignored.

### Example

```
# Directory structure
src/yoker/prompts/sets/default/main.md     # Built-in
~/.yoker/prompts/sets/default/main.md      # User override
./yoker/prompts/sets/default/main.md       # Project override

# With set = "default"
# Result: Uses ./yoker/prompts/sets/default/main.md (project)
```

## Additional Directories (Merge/Union)

Additional directories are **merged** with the active set:

```toml
[skills]
set = "default"
additional_dirs = ["./skills"]
```

**Behavior**: Load from `skills/sets/default/` **AND** `./skills/` (union)

### Example

```
# Directory structure
src/yoker/skills/sets/default/
├── git-commit.md      # Built-in skill
└── project-status.md  # Built-in skill

./skills/
├── my-custom-skill.md  # Custom skill
└── git-commit.md       # Override built-in

# With set = "default" and additional_dirs = ["./skills"]
# Result:
# - git-commit.md → from ./skills/ (override)
# - project-status.md → from built-in default set
# - my-custom-skill.md → from ./skills/ (addition)
```

## Resolution Summary

| Component Type | Set Resolution | Additional Dirs |
|---------------|----------------|-----------------|
| **Prompts** | Override (first match) | Merge (union) |
| **Skills** | Override (first match) | Merge (union) |
| **Agents** | Override (first match) | Merge (union) |

## Detailed Examples

### Example 1: Using Only Built-in Set

```toml
# yoker.toml
[prompts]
set = "default"
```

**Resolution**:
1. Check `./yoker/prompts/sets/default/` → not found
2. Check `~/.yoker/prompts/sets/default/` → not found
3. Check `src/yoker/prompts/sets/default/` → found!
4. Load all prompts from built-in default set

**Result**: Uses built-in prompts only.

---

### Example 2: Project Override

```toml
# yoker.toml
[prompts]
set = "default"
```

```
# Directory structure
src/yoker/prompts/sets/default/main.md      # Built-in
./yoker/prompts/sets/default/main.md        # Project override
```

**Resolution**:
1. Check `./yoker/prompts/sets/default/` → found!
2. Load all prompts from project default set
3. Built-in set is ignored

**Result**: Uses project prompts only (built-in is shadowed).

---

### Example 3: Additional Directory (Merge)

```toml
# yoker.toml
[skills]
set = "default"
additional_dirs = ["./skills"]
```

```
# Directory structure
src/yoker/skills/sets/default/
├── git-commit.md
├── project-status.md
└── bug-fixing.md

./skills/
├── my-custom-skill.md      # New skill
└── git-commit.md           # Override
```

**Resolution**:
1. Load `default` set: `{git-commit, project-status, bug-fixing}`
2. Load from `./skills/`: `{my-custom-skill, git-commit}`
3. **Merge**: Union of both
4. **Override**: `git-commit` from `./skills/` wins

**Result**:
- `git-commit` → from `./skills/`
- `project-status` → from built-in default
- `bug-fixing` → from built-in default
- `my-custom-skill` → from `./skills/`

---

### Example 4: Custom Set

```toml
# yoker.toml
[prompts]
set_path = "~/.yoker/prompts/my-custom-prompts"
```

```
# Directory structure
~/.yoker/prompts/my-custom-prompts/
├── metadata.toml
└── main.md
```

**Resolution**:
1. Load from specified path directly
2. No fallback to built-in

**Result**: Uses custom prompts only.

---

### Example 5: Multiple Additional Directories

```toml
# yoker.toml
[skills]
set = "default"
additional_dirs = ["./skills", "./team-skills"]
```

```
# Directory structure
src/yoker/skills/sets/default/
├── git-commit.md
└── project-status.md

./skills/
├── my-skill.md
└── git-commit.md      # Override

./team-skills/
├── team-skill.md
└── my-skill.md        # Override
```

**Resolution**:
1. Load default set: `{git-commit, project-status}`
2. Load from `./skills/`: `{my-skill, git-commit}`
3. Load from `./team-skills/`: `{team-skill, my-skill}`
4. **Merge**: Union of all
5. **Override**: Later dirs win (`./team-skills/` > `./skills/` > set)

**Result**:
- `project-status` → from default set
- `git-commit` → from `./skills/` (first additional dir)
- `my-skill` → from `./team-skills/` (second additional dir wins)
- `team-skill` → from `./team-skills/`

**Priority Order**: additional_dirs listed later have higher priority.

---

## Override Priority (Highest to Lowest)

1. **Additional directories** (listed later = higher priority)
2. **Set** (from project/user/built-in)

### Within Additional Directories

```toml
additional_dirs = ["./skills", "./team-skills"]
```

- `./team-skills/` has **higher** priority than `./skills/`
- If same skill exists in both, `./team-skills/` version wins

### Within Set

```toml
set = "default"
```

- `./yoker/prompts/sets/default/` has **higher** priority
- Then `~/.yoker/prompts/sets/default/`
- Then `src/yoker/prompts/sets/default/`

---

## Code Implementation

```python
# src/yoker/prompts/loader.py

class PromptLoader:
    """Load prompts with merge/override resolution."""
    
    def load_set(self, name: str) -> PromptSet:
        """Load a set by name (override behavior)."""
        # Search order: project → user → built-in
        for search_path in [
            *self.project_dirs,
            *self.user_dirs,
            self.builtin_dir,
        ]:
            set_path = search_path / name
            if set_path.exists():
                return self._load_from_path(set_path)
        
        raise ValueError(f"Set '{name}' not found")
    
    def load_with_additional(
        self, 
        set_name: str, 
        additional_dirs: list[Path]
    ) -> dict[str, PromptTemplate]:
        """Load set and merge with additional directories."""
        # 1. Load base set
        base_set = self.load_set(set_name)
        prompts = dict(base_set.prompts)
        
        # 2. Merge additional directories (later = higher priority)
        for additional_dir in additional_dirs:
            if additional_dir.exists():
                for prompt_file in additional_dir.glob("*.md"):
                    name = prompt_file.stem
                    prompts[name] = self._load_prompt(prompt_file)
        
        return prompts
```

---

## Configuration Examples

### Minimal Configuration

```toml
# Use all built-ins
[prompts]
set = "default"

[skills]
set = "default"

[agents]
set = "default"
```

### Project Customization

```toml
# Override prompts, extend skills and agents
[prompts]
set = "default"
additional_dirs = ["./prompts"]  # Override specific prompts

[skills]
set = "default"
additional_dirs = ["./skills"]   # Add project-specific skills

[agents]
set = "default"
additional_dirs = ["./agents"]   # Add project-specific agents
```

### Full Customization

```toml
# Use completely custom sets
[prompts]
set_path = "./yoker/prompts/my-prompts"

[skills]
set_path = "./yoker/skills/my-skills"

[agents]
set_path = "./yoker/agents/my-agents"
```

### Team Configuration

```toml
# Team skills override individual skills
[skills]
set = "default"
additional_dirs = [
    "~/.yoker/skills",        # Individual skills (lowest priority)
    "./skills",               # Project skills
    "./team-skills",          # Team skills (highest priority)
]
```

---

## Summary

| Mechanism | Behavior | Use Case |
|-----------|----------|-----------|
| **Set** | Override (first match) | Choose one complete set |
| **Additional dirs** | Merge (union, later wins) | Extend/override specific components |
| **set_path** | Direct path | Use completely custom set |

**Best Practice**:
- Use **set** for choosing a baseline (default, minimal, detailed)
- Use **additional_dirs** for project-specific customizations
- Use **set_path** for completely custom configurations