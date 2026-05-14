# Context Implementation Plan

**Date**: 2026-05-14
**Priority**: Core prompts, Context reminders, Lazy loading
**Note**: Tool definitions handled by Ollama SDK (not Yoker's responsibility)

## Implementation Priorities

### 1. Core Prompts (P1)

Yoker needs system prompts for:
- Main agent (comprehensive)
- Sub-agents (specialized)

#### Main Agent Prompt

**Source**: Based on `agent-prompt-general-purpose.md` from Claude Code repo

**Structure**:
```
Identity: Who you are
Role: What you do
Strengths: Your capabilities
Guidelines: How to work
Constraints: What NOT to do
Tool Usage: How to use tools
```

**Estimated Size**: ~6KB (~1,500 tokens)

#### Sub-Agent Prompts

| Agent Type | Purpose | Size |
|------------|---------|------|
| `general-purpose` | Search, analyze, edit code | ~3KB |
| `explore` | Fast read-only search | ~3KB |
| `plan` | Design implementation plans | ~4KB |

**Key Differences from Main Agent**:
- Shorter (3-4KB vs 27KB)
- Task-specific role definition
- Constrained tool set
- Read-only mode enforcement (when applicable)

#### Implementation

```python
# src/yoker/prompts/__init__.py

from dataclasses import dataclass
from typing import Literal

@dataclass(frozen=True)
class SystemPrompt:
    """System prompt configuration."""
    identity: str
    role: str
    strengths: list[str]
    guidelines: list[str]
    constraints: list[str]
    tool_usage: str | None = None
    
    def to_text(self) -> str:
        """Generate full prompt text."""
        parts = [
            f"You are {self.identity}.",
            "",
            f"{self.role}",
            "",
            "Your strengths:",
        ]
        for s in self.strengths:
            parts.append(f"- {s}")
        
        parts.extend([
            "",
            "Guidelines:",
        ])
        for g in self.guidelines:
            parts.append(f"- {g}")
        
        if self.constraints:
            parts.extend([
                "",
                "IMPORTANT: " + " ".join(self.constraints),
            ])
        
        if self.tool_usage:
            parts.extend([
                "",
                self.tool_usage,
            ])
        
        return "\n".join(parts)


@dataclass(frozen=True)
class AgentType:
    """Available agent types."""
    MAIN: Literal["main"] = "main"
    GENERAL_PURPOSE: Literal["general-purpose"] = "general-purpose"
    EXPLORE: Literal["explore"] = "explore"
    PLAN: Literal["plan"] = "plan"


def get_system_prompt(agent_type: str) -> SystemPrompt:
    """Get system prompt for agent type."""
    prompts = {
        "main": SystemPrompt(
            identity="Yoker, an agent harness with configurable tools",
            role="You help users with software engineering tasks...",
            strengths=[
                "Reading and analyzing code across large codebases",
                "Implementing features and fixing bugs",
                "Managing git operations safely",
                "Coordinating sub-agents for complex tasks",
            ],
            guidelines=[
                "Complete tasks fully without gold-plating",
                "Use tools systematically: search → read → edit → test",
                "Report progress clearly to the user",
                "Ask for clarification when requirements are ambiguous",
            ],
            constraints=[
                "Never modify files outside allowed paths",
                "Always validate tool parameters before use",
                "Respect recursion limits for sub-agents",
            ],
            tool_usage="Use the tools available to complete the task...",
        ),
        
        "general-purpose": SystemPrompt(
            identity="a Yoker sub-agent for general tasks",
            role="Given a task, use available tools to complete it.",
            strengths=[
                "Searching for code and configurations",
                "Analyzing multiple files",
                "Investigating complex questions",
            ],
            guidelines=[
                "Complete the task fully and report findings concisely",
                "Start broad, then narrow down",
                "Check multiple locations and naming conventions",
            ],
            constraints=[
                "Never create files unless absolutely necessary",
                "Never create documentation files unless requested",
            ],
        ),
        
        "explore": SystemPrompt(
            identity="a fast read-only search agent for Yoker",
            role="Locate code by searching, reading, and analyzing.",
            strengths=[
                "Fast file system navigation",
                "Pattern matching and searching",
                "Code location and analysis",
            ],
            guidelines=[
                "Use search tools when location is unknown",
                "Use Read when path is known",
                "Report findings concisely",
            ],
            constraints=[
                "READ-ONLY: Never modify, create, or delete files",
                "Never use Write, Edit, or Mkdir tools",
            ],
        ),
    }
    
    return prompts.get(agent_type, prompts["general-purpose"])
```

### 2. Context Reminders (P1)

Context reminders are injected into user messages.

#### Reminder Types

| Type | When to Inject | Size |
|------|----------------|------|
| `skills` | Skills are configured | Variable |
| `claude_md` | CLAUDE.md exists | Variable |
| `current_date` | Always | ~50 chars |
| `working_directory` | Always | ~100 chars |
| `git_context` | Git repository detected | ~200 chars |

#### Implementation

```python
# src/yoker/context/reminders.py

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

class ContextReminder(Protocol):
    """Protocol for context reminders."""
    
    def generate(self) -> str:
        """Generate the reminder text."""
        ...

@dataclass
class SkillsReminder:
    """Reminder about available skills."""
    skills: list[str]  # Skill names
    
    def generate(self) -> str:
        if not self.skills:
            return ""
        
        lines = [
            "<system-reminder>",
            "The following skills are available for use with the Skill tool:",
            "",
        ]
        for skill in self.skills:
            lines.append(f"- {skill}")
        lines.append("</system-reminder>")
        
        return "\n".join(lines)


@dataclass
class ClaudeMdReminder:
    """Reminder with CLAUDE.md content."""
    global_content: str | None = None
    project_content: str | None = None
    
    def generate(self) -> str:
        if not self.global_content and not self.project_content:
            return ""
        
        lines = [
            "<system-reminder>",
            "As you answer the user's questions, you can use the following context:",
            "# claudeMd",
        ]
        
        if self.global_content:
            lines.extend([
                "Contents of ~/.claude/CLAUDE.md (user's private global instructions):",
                "",
                self.global_content,
            ])
        
        if self.project_content:
            lines.extend([
                f"Contents of {Path.cwd()}/CLAUDE.md (project instructions):",
                "",
                self.project_content,
            ])
        
        lines.append("</system-reminder>")
        
        return "\n".join(lines)


@dataclass
class CurrentDateReminder:
    """Reminder with current date."""
    
    def generate(self) -> str:
        date = datetime.now().strftime("%Y-%m-%d")
        return f"<system-reminder>\n# currentDate\nToday's date is {date}.\n</system-reminder>"


@dataclass
class WorkingDirectoryReminder:
    """Reminder with current working directory."""
    
    def generate(self) -> str:
        cwd = Path.cwd()
        return f"<system-reminder>\n# cwd\nCurrent working directory: {cwd}\n</system-reminder>"


@dataclass
class GitContextReminder:
    """Reminder with git context (branch, status)."""
    branch: str | None = None
    status: str | None = None  # clean, dirty
    
    def generate(self) -> str:
        lines = ["<system-reminder>", "# gitContext"]
        if self.branch:
            lines.append(f"Current branch: {self.branch}")
        if self.status:
            lines.append(f"Status: {self.status}")
        lines.append("</system-reminder>")
        
        return "\n".join(lines)


class ReminderComposer:
    """Compose multiple reminders into a single message."""
    
    def __init__(self):
        self.reminders: list[ContextReminder] = []
    
    def add(self, reminder: ContextReminder) -> "ReminderComposer":
        """Add a reminder."""
        self.reminders.append(reminder)
        return self
    
    def compose(self) -> str:
        """Compose all reminders into message."""
        parts = [r.generate() for r in self.reminders if r.generate()]
        return "\n\n".join(parts)
    
    def inject_into_message(self, user_message: str) -> str:
        """Inject reminders before user message."""
        reminders = self.compose()
        if not reminders:
            return user_message
        return f"{reminders}\n\n{user_message}"
```

#### Usage in Agent

```python
# src/yoker/agent.py

class Agent:
    def _build_message(self, user_input: str) -> list[dict]:
        """Build message with context reminders."""
        composer = ReminderComposer()
        
        # Always include date
        composer.add(CurrentDateReminder())
        
        # Add working directory
        composer.add(WorkingDirectoryReminder())
        
        # Add skills if configured
        if self.config.skills:
            composer.add(SkillsReminder(skills=self.config.skills))
        
        # Add CLAUDE.md if exists
        global_md = self._load_global_claude_md()
        project_md = self._load_project_claude_md()
        if global_md or project_md:
            composer.add(ClaudeMdReminder(global_content=global_md, project_content=project_md))
        
        # Inject into message
        return [
            {
                "role": "user",
                "content": composer.inject_into_message(user_input)
            }
        ]
```

### 3. Lazy Loading (P1)

Reduce context size by loading tools/skills on-demand.

#### Tool Lazy Loading

```python
# src/yoker/tools/lazy.py

from dataclasses import dataclass
from typing import Callable

@dataclass
class LazyTool:
    """A tool that is loaded on first use."""
    name: str
    loader: Callable[[], Tool]
    _tool: Tool | None = None
    
    def get(self) -> Tool:
        """Get the tool, loading if necessary."""
        if self._tool is None:
            self._tool = self.loader()
        return self._tool


class LazyToolRegistry:
    """Registry that lazily loads tools."""
    
    def __init__(self, available_tools: list[str]):
        self.available_tools = available_tools
        self.loaded_tools: dict[str, Tool] = {}
        self.loaders: dict[str, Callable[[], Tool]] = {}
    
    def register_loader(self, name: str, loader: Callable[[], Tool]) -> None:
        """Register a tool loader."""
        self.loaders[name] = loader
    
    def get_tool(self, name: str) -> Tool | None:
        """Get a tool, loading if necessary."""
        if name in self.loaded_tools:
            return self.loaded_tools[name]
        
        if name in self.loaders:
            tool = self.loaders[name]()
            self.loaded_tools[name] = tool
            return tool
        
        return None
    
    def get_loaded_tools(self) -> list[Tool]:
        """Get all loaded tools."""
        return list(self.loaded_tools.values())
    
    def get_tools_for_request(self) -> list[Tool]:
        """Get tools to include in API request.
        
        Options:
        1. All tools (eager)
        2. Only loaded tools (lazy)
        3. Core + loaded (hybrid)
        """
        # Hybrid approach: always include core tools + loaded tools
        core_tools = ["Read", "List", "Search", "Existence"]
        
        tools = []
        for name in core_tools:
            tool = self.get_tool(name)
            if tool:
                tools.append(tool)
        
        tools.extend(self.get_loaded_tools())
        return tools
```

#### Skill Lazy Loading

```python
# src/yoker/skills/lazy.py

class LazySkillLoader:
    """Load skills on-demand from skill directories."""
    
    def __init__(self, skill_dirs: list[Path]):
        self.skill_dirs = skill_dirs
        self.available_skills: dict[str, Path] = {}
        self.loaded_skills: dict[str, Skill] = {}
        
        # Discover available skills
        self._discover_skills()
    
    def _discover_skills(self) -> None:
        """Discover available skills without loading them."""
        for skill_dir in self.skill_dirs:
            for skill_file in skill_dir.glob("*.md"):
                skill_name = skill_file.stem
                self.available_skills[skill_name] = skill_file
    
    def list_skills(self) -> list[str]:
        """List available skill names."""
        return list(self.available_skills.keys())
    
    def load_skill(self, name: str) -> Skill | None:
        """Load a skill on-demand."""
        if name in self.loaded_skills:
            return self.loaded_skills[name]
        
        if name not in self.available_skills:
            return None
        
        # Load skill from file
        skill_path = self.available_skills[name]
        skill = self._parse_skill(skill_path)
        self.loaded_skills[name] = skill
        return skill
    
    def get_skills_for_reminder(self) -> list[str]:
        """Get skills to include in reminder.
        
        Only list skills, don't load them.
        """
        return self.list_skills()
```

#### Integration with Context Management

```python
# src/yoker/context/manager.py

class ContextManager:
    """Manage context with lazy loading."""
    
    def __init__(self, config: Config):
        self.config = config
        self.tool_registry = LazyToolRegistry(available_tools=config.tools.available)
        self.skill_loader = LazySkillLoader(skill_dirs=config.skills.directories)
        self.reminder_composer = ReminderComposer()
    
    def build_initial_context(self) -> tuple[list[dict], list[Tool]]:
        """Build initial context for first request.
        
        Returns:
            - System prompts
            - Initial tools (core only for lazy loading)
        """
        # System prompts (always full)
        system_prompt = get_system_prompt("main").to_text()
        
        # Initial tools (core only)
        initial_tools = [
            self.tool_registry.get_tool(name)
            for name in ["Read", "List", "Search", "Existence"]
            if self.tool_registry.get_tool(name)
        ]
        
        return [{"type": "text", "text": system_prompt}], initial_tools
    
    def load_tool_for_use(self, tool_name: str) -> Tool:
        """Load a tool when it's first used."""
        return self.tool_registry.get_tool(tool_name)
    
    def build_reminders(self) -> str:
        """Build context reminders."""
        self.reminder_composer = ReminderComposer()
        
        # Always include
        self.reminder_composer.add(CurrentDateReminder())
        self.reminder_composer.add(WorkingDirectoryReminder())
        
        # Add skills (just list, don't load)
        if self.config.skills.enabled:
            self.reminder_composer.add(SkillsReminder(
                skills=self.skill_loader.list_skills()
            ))
        
        # Add CLAUDE.md
        # ...
        
        return self.reminder_composer.compose()
```

## File Structure

```
src/yoker/
├── prompts/
│   ├── __init__.py          # Prompt classes and get_system_prompt()
│   ├── main.py              # Main agent prompt
│   ├── subagents.py         # Sub-agent prompts
│   └── templates/           # Prompt template files (future)
├── context/
│   ├── __init__.py
│   ├── reminders.py         # Context reminder classes
│   ├── manager.py           # Context building and management
│   └── lazy.py             # Lazy loading utilities
├── skills/
│   ├── __init__.py
│   ├── loader.py            # Lazy skill loading
│   └── registry.py          # Skill registry
└── tools/
    ├── lazy.py              # Lazy tool loading
    └── registry.py          # Tool registry
```

## Implementation Order

1. **Core Prompts** (Week 1)
   - Create `prompts/` module
   - Implement `SystemPrompt` dataclass
   - Add main agent prompt
   - Add sub-agent prompts (general-purpose, explore)

2. **Context Reminders** (Week 2)
   - Create `context/reminders.py`
   - Implement reminder classes
   - Add to agent message building
   - Test with CLAUDE.md

3. **Lazy Loading** (Week 3)
   - Create `tools/lazy.py`
   - Create `skills/loader.py`
   - Update context manager
   - Test lazy vs eager loading

## Testing Strategy

```python
# tests/test_context/test_reminders.py

def test_skills_reminder():
    reminder = SkillsReminder(skills=["skill1", "skill2"])
    text = reminder.generate()
    assert "<system-reminder>" in text
    assert "- skill1" in text
    assert "- skill2" in text

def test_reminder_injection():
    composer = ReminderComposer()
    composer.add(CurrentDateReminder())
    message = composer.inject_into_message("Hello")
    assert "<system-reminder>" in message
    assert "Hello" in message

def test_lazy_tool_loading():
    registry = LazyToolRegistry(available_tools=["Read", "Write"])
    registry.register_loader("Read", lambda: ReadTool())
    
    # Not loaded yet
    assert len(registry.loaded_tools) == 0
    
    # Load on use
    tool = registry.get_tool("Read")
    assert tool is not None
    assert len(registry.loaded_tools) == 1
```

## Configuration

```toml
# yoker.toml

[harness]
name = "my-yoke"

[context]
# Lazy loading
lazy_tools = true
lazy_skills = true

# Reminders
include_date = true
include_cwd = true
include_git_context = true

[skills]
enabled = true
directories = ["~/.claude/skills", "./skills"]

[tools]
# Core tools (always loaded)
core = ["Read", "List", "Search", "Existence"]

# Available tools (lazy loaded)
available = ["Read", "Write", "Edit", "Bash", "Agent", "WebSearch", "WebFetch"]
```

## Success Metrics

| Metric | Target |
|--------|--------|
| Main agent context size | <50KB (vs 170KB current) |
| Sub-agent context size | <20KB (vs 69KB current) |
| Initial tool definitions | 4-6 core tools |
| Skills in reminder | List only, not loaded |
| Load time for tool | <100ms |

## Next Steps

1. Review and approve implementation plan
2. Create TODO tasks for each component
3. Implement Core Prompts first (P1)
4. Add Context Reminders (P1)
5. Implement Lazy Loading (P1)