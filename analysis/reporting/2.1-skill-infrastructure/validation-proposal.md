# Validation Proposal: Skill Infrastructure Approach

**Task**: 2.1 Skill Infrastructure
**Context**: Package Plugin System (Issue #14)
**Date**: 2026-05-27
**Status**: Validation Request

## Executive Summary

This proposal validates the skill infrastructure approach through:
1. A realistic scenario using a "commit changes" skill
2. A concrete skill example in Markdown format
3. Detailed explanation of context injection mechanisms
4. Expected LLM behavior before and after skill invocation

The goal is to confirm that:
- Skills are introduced correctly via system context listings
- Skill body is inserted as user-level message instructions
- The LLM can use skill content to guide its actions

## 1. Scenario Description

### Use Case: Commit Changes Skill

**Scenario**: A developer has made changes to the codebase and wants to create a well-structured git commit following best practices.

**User Request**: "commit these changes"

**Expected Behavior**:
1. LLM checks current changes (`git status`, `git diff`)
2. LLM stages related changes together
3. LLM writes conventional commit message
4. LLM creates atomic commit
5. LLM verifies commit was successful

**Why a Skill?**:
- Commit workflow requires multiple steps
- Best practices should be followed (atomic commits, conventional messages)
- Workflow guidance helps LLM produce better commits
- Not a simple command - requires judgment

**Without Skill**: LLM might:
- Stage all changes without grouping
- Write vague commit messages
- Skip verification step
- Mix unrelated changes in one commit

**With Skill**: LLM follows structured workflow with guidance on:
- Staging strategy (group related changes)
- Message format (conventional commits)
- Verification steps (review staged changes)
- Atomic commit principle

### When Skill Would Be Invoked

The skill is invoked when:
1. **User explicitly requests**: User types `/commit` or "commit changes"
2. **Natural language trigger**: LLM detects "commit" intent (future enhancement)
3. **Agent definition includes it**: Agent pre-loaded with commit skill

For validation, we'll use **explicit invocation**: User types `/commit`

## 2. Skill Example

### Skill File: `skills/git-commit.md`

```markdown
---
name: git-commit
description: Guide git commit operations with atomic commits and conventional messages
triggers:
  - "commit changes"
  - "create a commit"
  - "make a commit"
  - "/commit"
tools:
  - Bash
  - Read
---

## Purpose

Create well-structured git commits following best practices: atomic commits, conventional format, and clear messages.

## Workflow

1. **Review Changes**: Understand what changed
   - Run `git status` to see modified files
   - Run `git diff` to see actual changes
   - Identify logical groupings of changes

2. **Stage Changes**: Group related changes
   - Stage files that belong together (e.g., test + implementation)
   - Avoid staging unrelated changes in same commit
   - Use `git add <files>` for specific files

3. **Write Message**: Follow conventional commit format
   - Format: `type(scope): description`
   - Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`
   - Scope: optional component/module name
   - Description: imperative mood, lowercase, no period

4. **Verify**: Review staged changes
   - Run `git status` to confirm staged files
   - Run `git diff --staged` to see what will be committed

5. **Commit**: Create atomic commit
   - Run `git commit -m "..."`
   - Keep message concise but descriptive
   - Add body if more context needed

## Guidelines

- **Atomic**: One logical change per commit
- **Descriptive**: Message explains *why*, not just *what*
- **Conventional**: Follow conventional commit format
- **References**: Include issue/PR numbers when applicable
- **No secrets**: Never commit credentials or .env files

## Examples

### Feature Addition
```bash
git add src/yoker/agent.py
git add tests/test_agent.py
git commit -m "feat(agent): add lazy tool loading

- Load tools on first use
- Cache loaded tools in registry
- Reduce initial context size by 70%"
```

### Bug Fix
```bash
git add src/yoker/config/loader.py
git commit -m "fix(config): handle missing config file gracefully

- Return empty config instead of raising error
- Log warning when config file not found
- Fixes #123"
```

### Refactoring
```bash
git add src/yoker/tools/
git commit -m "refactor(tools): extract common tool patterns

- Move shared validation to base class
- Reduce code duplication by 40%"
```

## Common Mistakes to Avoid

- Staging all changes at once: `git add .` (lazy, mixes changes)
- Vague messages: "update code", "fix bug", "changes"
- Missing scope: "feat: add feature" (should be "feat(module): add feature")
- Too large commits: 500+ lines in single commit
- Forgetting to stage: committing without `git add`
- Ignoring untracked files: not using `git status` first

## Verification Checklist

Before committing, verify:
- [ ] Changes are logically grouped
- [ ] Message follows conventional format
- [ ] Message starts with lowercase
- [ ] No sensitive files staged (.env, credentials)
- [ ] Tests pass (if applicable)
- [ ] Commit is atomic (one logical change)
```

### Skill File Analysis

| Field | Value | Purpose |
|-------|-------|---------|
| `name` | `git-commit` | Unique identifier for skill invocation |
| `description` | "Guide git commit operations..." | Shown in skills listing |
| `triggers` | ["commit changes", "create a commit", ...] | Natural language invocation (future) |
| `tools` | ["Bash", "Read"] | Documents required tools (informational) |
| `content` | (Markdown body) | The actual skill instructions |

**Key Points**:
- Frontmatter contains metadata (name, description, triggers, tools)
- Body contains workflow guidance
- Format matches `AgentDefinition` pattern
- File location: `./skills/git-commit.md` or `~/.yoker/skills/git-commit.md`

## 3. Context Injection Explanation

### How Skills Are Introduced (System Context)

Skills are introduced to the LLM via a **skills listing** in the system context:

**Before any skill is invoked**, the agent injects:

```
<system-reminder>
The following skills are available for use with the /skill command:

- git-commit: Guide git commit operations with atomic commits and conventional messages
- research: Research topics comprehensively with full provenance tracking
- bug-fixing: Systematic bug fixing with TDD approach
</system-reminder>
```

**Where this appears**:
- Injected at the **beginning of the conversation** (first turn)
- Re-injected on **every turn** (lightweight, ~500 bytes for 10 skills)
- Part of the **user-level message** (not system prompt)

**Why system-reminder tag?**:
- Follows Claude Code's pattern for context injection
- Distinguishes skill listings from regular user content
- Lightweight and doesn't consume system prompt tokens
- Visible to LLM but not intrusive

**Implementation**:

```python
# In agent.py: _build_user_message()
from yoker.skills import inject_skills_listing

def _build_user_message(self, user_input: str) -> str:
    """Build user message with skills listing."""
    parts = []

    # Inject skills listing (if skills available)
    skills = self.skill_registry.list_skills()
    if skills:
        parts.append(inject_skills_listing(skills))

    # Add actual user input
    parts.append(user_input)

    return "\n\n".join(parts)
```

### How Skill Body Is Inserted (Full Content)

When a user invokes a skill via `/git-commit`, the skill's **full content** is injected:

**Invocation**: User types `/git-commit`

**Injected Content**:

```
<skill>
# git-commit

## Purpose

Create well-structured git commits following best practices: atomic commits, conventional format, and clear messages.

## Workflow

1. **Review Changes**: Understand what changed
   - Run `git status` to see modified files
   - Run `git diff` to see actual changes
   - Identify logical groupings of changes

2. **Stage Changes**: Group related changes
   - Stage files that belong together (e.g., test + implementation)
   - Avoid staging unrelated changes in same commit
   - Use `git add <files>` for specific files

[... rest of skill content ...]

## Verification Checklist

Before committing, verify:
- [ ] Changes are logically grouped
- [ ] Message follows conventional format
- [ ] Message starts with lowercase
- [ ] No sensitive files staged (.env, credentials)
- [ ] Tests pass (if applicable)
- [ ] Commit is atomic (one logical change)
</skill>
```

**Where this appears**:
- Injected in the **user message** after the skills listing
- **Replaces** the `/git-commit` command in the user input
- Persists for **that conversation turn only**
- Not cached or remembered across turns (unless re-invoked)

**Why skill tag?**:
- Distinguishes skill content from user content
- Clear marker for LLM to parse
- Follows HTML/XML-like pattern familiar to LLMs
- Can be parsed/stripped if needed

**Implementation**:

```python
# In commands/skill.py: SkillCommand.execute()
from yoker.skills import inject_skill_context

def execute(self, args: str) -> str | None:
    """Execute skill command."""
    skill_name = args.strip()

    # Look up skill
    skill = self.skill_registry.get(skill_name)
    if skill is None:
        return f"Skill '{skill_name}' not found."

    # Return skill content for injection
    return inject_skill_context(skill)
```

### Context Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    LLM Conversation Context                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Turn 1 (User starts conversation):                             │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │ <system-reminder>                                        │ │
│  │ The following skills are available...                     │ │
│  │ - git-commit: Guide git commit operations...              │ │
│  │ - research: Research topics comprehensively...            │ │
│  │ - bug-fixing: Systematic bug fixing...                    │ │
│  │ </system-reminder>                                        │ │
│  │                                                           │ │
│  │ Hello, I want to commit my changes.                      │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                 │
│  LLM Response: "I see you want to commit. I'll help you..."   │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Turn 2 (User invokes skill):                                   │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │ <system-reminder>                                        │ │
│  │ The following skills are available...                     │ │
│  │ </system-reminder>                                        │ │
│  │                                                           │ │
│  │ <skill>                                                   │ │
│  │ # git-commit                                              │ │
│  │                                                           │ │
│  │ ## Purpose                                                │ │
│  │ Create well-structured git commits...                    │ │
│  │                                                           │ │
│  │ ## Workflow                                                │ │
│  │ 1. Review Changes: ...                                    │ │
│  │ 2. Stage Changes: ...                                     │ │
│  │ ...                                                        │ │
│  │ </skill>                                                   │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                 │
│  LLM Response: Follows workflow steps...                        │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Turn 3 (User continues conversation):                          │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │ <system-reminder>                                        │ │
│  │ The following skills are available...                     │ │
│  │ </system-reminder>                                        │ │
│  │                                                           │ │
│  │ Great, commit those changes.                              │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                 │
│  LLM Response: Executes git commands...                         │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Key Points**:
- Skills listing appears in **every turn** (lightweight reminder)
- Skill content appears **only when invoked** (1-3KB)
- Skill content is **ephemeral** - not persisted across turns
- LLM must follow the workflow in that turn

## 4. Expected Agent Behavior

### Before Skill Invocation

**What the LLM sees** (Turn 1):

```
User: <system-reminder>
The following skills are available for use with the /skill command:

- git-commit: Guide git commit operations with atomic commits and conventional messages
- research: Research topics comprehensively with full provenance tracking
- bug-fixing: Systematic bug fixing with TDD approach
</system-reminder>

Hello, I want to commit my changes.
```

**LLM Response**:

The LLM sees the available skills but doesn't know their content yet. It can:
1. Acknowledge the request
2. Ask for clarification
3. Suggest invoking a skill: "I can help you commit changes. Would you like me to use the git-commit skill?"

**Expected LLM behavior**:
- Recognizes "commit changes" matches a skill trigger
- May suggest using the skill
- May ask for permission to invoke
- Cannot execute skill workflow yet (doesn't have instructions)

### After Skill Invocation

**What the LLM sees** (Turn 2, after `/git-commit`):

```
User: <system-reminder>
The following skills are available for use with the /skill command:

- git-commit: Guide git commit operations with atomic commits and conventional messages
- research: Research topics comprehensively with full provenance tracking
- bug-fixing: Systematic bug fixing with TDD approach
</system-reminder>

<skill>
# git-commit

## Purpose

Create well-structured git commits following best practices: atomic commits, conventional format, and clear messages.

## Workflow

1. **Review Changes**: Understand what changed
   - Run `git status` to see modified files
   - Run `git diff` to see actual changes
   - Identify logical groupings of changes

2. **Stage Changes**: Group related changes
   - Stage files that belong together (e.g., test + implementation)
   - Avoid staging unrelated changes in same commit
   - Use `git add <files>` for specific files

3. **Write Message**: Follow conventional commit format
   - Format: `type(scope): description`
   - Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`
   - Scope: optional component/module name
   - Description: imperative mood, lowercase, no period

4. **Verify**: Review staged changes
   - Run `git status` to confirm staged files
   - Run `git diff --staged` to see what will be committed

5. **Commit**: Create atomic commit
   - Run `git commit -m "..."`
   - Keep message concise but descriptive
   - Add body if more context needed

## Guidelines

- **Atomic**: One logical change per commit
- **Descriptive**: Message explains *why*, not just *what*
- **Conventional**: Follow conventional commit format
- **References**: Include issue/PR numbers when applicable
- **No secrets**: Never commit credentials or .env files

[... examples and verification checklist ...]

</skill>
```

**LLM Response**:

Now the LLM has the full workflow. It will:
1. Follow step 1: Review changes (`git status`, `git diff`)
2. Follow step 2: Stage related changes
3. Follow step 3: Write conventional commit message
4. Follow step 4: Verify staged changes
5. Follow step 5: Create commit

**Example LLM response**:

```
I'll help you commit these changes following the git-commit workflow.

Let me start by reviewing the changes:

**Step 1: Review Changes**

[Bash] git status
[Bash] git diff

I can see we have:
- Modified: src/yoker/agent.py (added skill_registry parameter)
- Modified: src/yoker/skills/loader.py (implemented skill loading)
- New file: src/yoker/skills/schema.py (Skill dataclass)

These changes are related (skill infrastructure implementation), so I'll stage them together.

**Step 2: Stage Changes**

[Bash] git add src/yoker/agent.py src/yoker/skills/loader.py src/yoker/skills/schema.py

**Step 3: Write Message**

Following conventional commit format: `feat(skills): implement skill infrastructure`

The commit message should be:
```
feat(skills): implement skill infrastructure

- Add Skill dataclass for skill definitions
- Implement SkillLoader with YAML parsing
- Add SkillRegistry for skill management
- Integrate skill loading with Agent class
```

**Step 4: Verify**

[Bash] git status
[Bash] git diff --staged

Confirmed: 3 files staged, changes look correct.

**Step 5: Commit**

[Bash] git commit -m "feat(skills): implement skill infrastructure

- Add Skill dataclass for skill definitions
- Implement SkillLoader with YAML parsing
- Add SkillRegistry for skill management
- Integrate skill loading with Agent class"

Commit created successfully: abc123def
```

### How LLM Uses Skill Content

The LLM uses the skill content as **structured guidance**:

1. **Workflow Order**: Follows steps 1-5 in sequence
2. **Best Practices**: Applies guidelines (atomic, conventional format)
3. **Examples**: References examples for message format
4. **Verification**: Uses checklist to validate commit

**Without skill**: LLM might do:
```bash
git add .
git commit -m "update code"
```

**With skill**: LLM follows:
```bash
git status
git diff
git add src/yoker/agent.py src/yoker/skills/loader.py src/yoker/skills/schema.py
git diff --staged
git commit -m "feat(skills): implement skill infrastructure

- Add Skill dataclass for skill definitions
- Implement SkillLoader with YAML parsing
- Add SkillRegistry for skill management
- Integrate skill loading with Agent class"
```

### Key Differences

| Aspect | Without Skill | With Skill |
|--------|---------------|------------|
| **Workflow** | Ad-hoc, unstructured | Follows defined steps |
| **Message** | Generic, vague | Conventional format |
| **Staging** | All files at once | Logical groupings |
| **Verification** | Skipped | Explicit check |
| **Quality** | Inconsistent | Follows best practices |

## 5. Validation Approach

### Step 1: Create Demo Script

Create a skill file in `examples/skills/git-commit.md`:

```markdown
---
name: git-commit
description: Guide git commit operations
tools:
  - Bash
  - Read
---

## Workflow
1. Review changes
2. Stage related files
3. Write conventional commit
4. Verify and commit
```

### Step 2: Run Session with Skill

Run an interactive session:
1. Start agent: `python -m yoker`
2. Show skills listing is injected
3. Invoke skill: `/git-commit`
4. Show skill content is injected
5. Verify LLM follows workflow

### Step 3: Capture Transcript

Capture the conversation transcript showing:
1. Initial context with skills listing
2. Skill invocation
3. Skill content injection
4. LLM following workflow

### Step 4: Analyze Behavior

Verify that:
1. Skills listing appears in system context
2. Skill content is injected as user-level message
3. LLM follows the workflow steps
4. LLM produces better commits

## 6. Implementation Verification

### What to Verify

| Component | Verification Method |
|-----------|---------------------|
| **Skills listing injection** | Check initial turn context contains `<system-reminder>` with skill names |
| **Skill invocation** | Check `/git-commit` triggers skill lookup |
| **Skill content injection** | Check user message contains `<skill>` tag with full content |
| **LLM follows workflow** | Check LLM response follows skill steps 1-5 |
| **Better output quality** | Compare commits with/without skill |

### Expected Transcript Excerpts

**Turn 1 (Initial context)**:

```json
{
  "role": "user",
  "content": "<system-reminder>\nThe following skills are available for use with the /skill command:\n\n- git-commit: Guide git commit operations with atomic commits and conventional messages\n- research: Research topics comprehensively with full provenance tracking\n</system-reminder>\n\nHello, I want to commit my changes."
}
```

**Turn 2 (Skill invocation)**:

```json
{
  "role": "user",
  "content": "<system-reminder>\nThe following skills are available for use with the /skill command:\n\n- git-commit: Guide git commit operations with atomic commits and conventional messages\n- research: Research topics comprehensively with full provenance tracking\n</system-reminder>\n\n<skill>\n# git-commit\n\n## Purpose\nCreate well-structured git commits following best practices...\n\n## Workflow\n1. **Review Changes**: ...\n2. **Stage Changes**: ...\n[...]\n</skill>"
}
```

**Turn 3 (LLM response)**:

```json
{
  "role": "assistant",
  "content": "I'll help you commit these changes following the git-commit workflow.\n\n**Step 1: Review Changes**\n\n[Bash] git status\n[Bash] git diff\n\nI can see we have...\n\n**Step 2: Stage Changes**\n\n[Bash] git add ...\n\n**Step 3: Write Message**\n\nFollowing conventional commit format...\n\n**Step 4: Verify**\n\n[Bash] git diff --staged\n\n**Step 5: Commit**\n\n[Bash] git commit -m \"...\""
}
```

### Success Criteria

- [ ] Skills listing appears in initial context
- [ ] Skill invocation triggers content injection
- [ ] Skill content is properly formatted (`<skill>` tag)
- [ ] LLM follows workflow steps in order
- [ ] LLM applies best practices from skill
- [ ] Commit quality improves with skill

## 7. Next Steps

### For Owner

1. **Provide transcript**: Run a session with the example skill and provide the transcript
2. **Validate behavior**: Confirm LLM follows the workflow
3. **Approve approach**: If behavior matches expectations, approve implementation

### For Implementation

1. **Create skill infrastructure** (Task 2.1)
2. **Implement git-commit skill** (built-in skill)
3. **Write tests** (loader, registry, injection)
4. **Validate integration** (CLI commands, agent integration)

## Appendix: Technical Details

### Context Injection Code

```python
# src/yoker/skills/injection.py

def inject_skills_listing(skills: list[Skill]) -> str:
    """Inject skills listing as system reminder."""
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


def inject_skill_context(skill: Skill) -> str:
    """Inject skill content as user-level message."""
    return f"<skill>\n# {skill.name}\n\n{skill.content}\n</skill>"
```

### Agent Integration Code

```python
# src/yoker/agent.py

def _build_user_message(self, user_input: str) -> str:
    """Build user message with context injection."""
    from yoker.skills import inject_skills_listing

    parts = []

    # Inject skills listing
    skills = self.skill_registry.list_skills()
    if skills:
        parts.append(inject_skills_listing(skills))

    # Add user input
    parts.append(user_input)

    return "\n\n".join(parts)
```

### Command Integration Code

```python
# src/yoker/commands/skill.py

class SkillCommand(Command):
    """Invoke a skill by name."""

    name = "skill"
    description = "Invoke a skill by name"

    def __init__(self, skill_registry: SkillRegistry):
        self.skill_registry = skill_registry

    def execute(self, args: str) -> str | None:
        """Execute skill command."""
        skill_name = args.strip()

        if not skill_name:
            # List available skills
            skills = self.skill_registry.list_skills()
            lines = ["Available skills:", ""]
            for skill in skills:
                lines.append(f"  {skill.name}: {skill.description}")
            return "\n".join(lines)

        # Look up and inject skill
        skill = self.skill_registry.get(skill_name)
        if skill is None:
            return f"Skill '{skill_name}' not found."

        from yoker.skills import inject_skill_context
        return inject_skill_context(skill)
```

## Conclusion

This validation proposal demonstrates:

1. **Scenario**: Realistic use case (commit changes)
2. **Skill**: Concrete example with workflow guidance
3. **Context Injection**: Clear mechanism (system-reminder for listing, skill tag for content)
4. **Expected Behavior**: LLM follows structured workflow

The approach is:
- **Lightweight**: ~500 bytes for listings, 1-3KB per invocation
- **Non-intrusive**: Doesn't modify system prompt
- **Ephemeral**: Skill content not persisted across turns
- **Followable**: LLM can parse and execute workflow steps

**Ready for validation**: Provide a transcript from a session using the example skill to confirm the approach works as expected.