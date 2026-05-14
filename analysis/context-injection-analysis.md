# Context Injection Analysis

**Date**: 2026-05-14
**Sources**: 
1. Recorded session (../incubator/ideas/http-proxy-logger/recording.jsonl)
2. Claude Code system prompts repo (../local/claude-code-system-prompts)

## Overview

Claude Code injects significant context beyond user input. This analysis maps what's injected, where, and recommends what Yoker should include.

## Injection Points

### 1. System Prompts (Array)

Injected as `system` array in the API request. Contains:
- Billing header
- Identity prompt ("You are Claude Code...")
- Main system prompt (26KB+ for main agent)

### 2. Context Reminders (Injected into User Messages)

Injected as `<system-reminder>` tags in user messages. Contains:
- Available skills list
- CLAUDE.md content (global + project)
- Current date
- Project context

### 3. Tool Definitions (Array)

Injected as `tools` array in the API request. Each tool includes:
- Name
- Description (often detailed, multi-line)
- Input schema (JSON Schema)

## Recorded Session Analysis

### What Was Injected (Beyond User Input)

| Component | Size | Location | Purpose |
|-----------|------|----------|---------|
| **System Prompts** | ~27KB | `system[]` array | Core behavior instructions |
| **Tool Definitions** | ~143KB | `tools[]` array | Available capabilities |
| **Skills List** | ~10KB | User message `<system-reminder>` | Available skills with descriptions |
| **CLAUDE.md Content** | Variable | User message `<system-reminder>` | Project-specific instructions |
| **Current Date** | ~50 chars | User message `<system-reminder>` | Temporal context |

### Skills List Injection

The recorded session showed 50+ skills injected:

```
<system-reminder>
The following skills are available for use with the Skill tool:

- c3:start-baseweb-project: Use this skill to start...
- c3:analysis-integration: Use this skill after...
- c3:pyenv: Manage Python versions...
[... 47 more skills ...]
</system-reminder>
```

**Size Impact**: ~10KB for 50 skills with descriptions.

### CLAUDE.md Injection

Global and project CLAUDE.md files are injected:

```
<system-reminder>
As you answer the user's questions, you can use the following context:
# claudeMd
Codebase and user instructions are shown below...
Contents of /Users/xtof/.claude/CLAUDE.md (user's private global instructions)...
Contents of /Users/xtof/Workspace/agentic/yoker/CLAUDE.md (project instructions)...
</system-reminder>
```

## System Prompts Repository Structure

The `claude-code-system-prompts` repo contains 296 prompts organized as:

### Categories

| Category | Count | Purpose |
|----------|-------|---------|
| **Agent Prompts** | ~50 | Sub-agent and utility prompts |
| **Data Files** | ~30 | Reference documentation (API refs, catalogs) |
| **Skills** | ~20 | Skill-specific instructions |
| **Slash Commands** | ~10 | Command implementations |
| **Utilities** | ~15 | Helper functions |
| **System Reminders** | ~40 | Context injection templates |
| **Tool Prompts** | ~130 | Tool descriptions and schemas |

### Key Prompts for Yoker

#### Tier 1: Essential (Must Implement)

| Prompt | Tokens | Why |
|--------|--------|-----|
| **Main System Prompt** | ~6,000 | Core behavior, tool usage, constraints |
| **Tool Schemas** | ~140,000 | All tool definitions |
| **Error Handling** | ~500 | Error codes, recovery patterns |

#### Tier 2: Important (Should Implement)

| Prompt | Tokens | Why |
|--------|--------|-----|
| **Sub-agent Prompts** | ~300-700 each | General-purpose, Explore, Plan |
| **Context Reminders** | ~10,000 | Skills, CLAUDE.md, date |
| **Memory Prompts** | ~400-800 | Context synthesis, memory management |

#### Tier 3: Nice to Have (Future)

| Prompt | Tokens | Why |
|--------|--------|-----|
| **Conversation Compaction** | ~1,200 | Summarization for long sessions |
| **Security Monitoring** | ~7,500 | Block/allow rules for autonomous actions |
| **Session Title Generation** | ~300 | Auto-naming sessions |

## Prompt Injection Pattern

### Main Agent Request Structure

```json
{
  "model": "claude-...",
  "system": [
    { "type": "text", "text": "x-anthropic-billing-header: ..." },
    { "type": "text", "text": "You are Claude Code, Anthropic's official CLI for Claude." },
    { "type": "text", "text": "[6KB+ system prompt...]" }
  ],
  "messages": [
    {
      "role": "user",
      "content": [
        { 
          "type": "text", 
          "text": "<system-reminder>\nThe following skills are available...\n</system-reminder>\n\n<system-reminder>\nAs you answer...\n</system-reminder>\n\n[actual user message]"
        }
      ]
    }
  ],
  "tools": [
    { "name": "Agent", "description": "...", "input_schema": {...} },
    { "name": "AskUserQuestion", ... },
    ...
  ]
}
```

### Sub-Agent Request Structure

```json
{
  "model": "claude-...",
  "system": [
    { "type": "text", "text": "x-anthropic-billing-header: ..." },
    { "type": "text", "text": "You are Claude Code, Anthropic's official CLI for Claude." },
    { "type": "text", "text": "[specialized prompt for task, ~3KB]" }
  ],
  "messages": [
    {
      "role": "user",
      "content": "[task from parent agent + context reminders]"
    }
  ],
  "tools": [
    // Filtered subset (28 tools vs 37 in main)
  ]
}
```

## System Reminders from Repository

The repo contains ~40 system reminder templates:

| Reminder | Purpose |
|----------|---------|
| `skill-available` | List available skills |
| `claude-md-context` | CLAUDE.md content |
| `current-date` | Today's date |
| `cwd-context` | Current working directory |
| `git-context` | Git status, branch info |
| `project-context` | Project metadata |
| `mcp-servers` | Available MCP servers |
| `memory-context` | Memory file synthesis |
| ... | ... |

## Recommendations for Yoker

### 1. Implement Core System Prompt

Based on the repository, Yoker should have:

```
Identity: "You are [agent name], [agent description]."
Role: What the agent does, its strengths
Guidelines: How to approach tasks
Constraints: What NOT to do
Tools: How to use available tools
```

**Size**: ~3KB for specialized agents, ~27KB for main agent

### 2. Implement Context Reminders

Yoker should inject these reminders:

```python
class ContextReminder:
    """Inject context into user messages."""
    
    def inject_skills(self, skills: list[Skill]) -> str:
        return f"<system-reminder>\nThe following skills are available for use with the Skill tool:\n\n{self.format_skills(skills)}\n</system-reminder>"
    
    def inject_claude_md(self, content: str) -> str:
        return f"<system-reminder>\nAs you answer the user's questions, you can use the following context:\n# claudeMd\n{content}\n</system-reminder>"
    
    def inject_date(self) -> str:
        return f"<system-reminder>\n# currentDate\nToday's date is {datetime.now().strftime('%Y-%m-%d')}.\n</system-reminder>"
```

### 3. Implement Tool Definitions

Tool definitions are ~3-4KB each on average. Yoker should:

```python
# Core tools (always include)
CORE_TOOLS = ["Read", "Write", "Edit", "Bash", "Agent", "Skill"]

# Specialized tools (include based on agent type)
FILE_TOOLS = ["Read", "Write", "Edit", "List", "Search", "Existence", "Mkdir"]
WEB_TOOLS = ["WebSearch", "WebFetch"]
DEV_TOOLS = ["Git", "Pytest", "Ruff"]

# Generate tool definitions
def generate_tool_schema(tool: Tool) -> dict:
    return {
        "name": tool.name,
        "description": tool.description,  # Detailed, multi-line
        "input_schema": tool.input_schema  # JSON Schema
    }
```

### 4. Sub-Agent Prompts

Yoker should implement specialized prompts for sub-agents:

```python
SUB_AGENT_PROMPTS = {
    "general-purpose": """
You are an agent for Yoker. Given the task, you should use the tools 
available to complete it. Complete the task fully—don't gold-plate, 
but don't leave it half-done.

Your strengths:
- Searching for code, configurations, and patterns across codebases
- Analyzing multiple files to understand system architecture
- Investigating complex questions that require exploring many files
- Performing multi-step research tasks

Guidelines:
- For file searches: search broadly when you don't know where something lives
- For analysis: Start broad and narrow down
- Be thorough: Check multiple locations, consider different naming conventions
- NEVER create files unless absolutely necessary
- NEVER proactively create documentation files
""",
    
    "explore": """
You are a fast read-only search agent for Yoker. Your job is to locate 
code by searching, reading files, and using grep/ Glob/ Bash. 

You search for a living—never guess. When you don't know where something 
lives, use the search tools to find it.
""",
    
    # Add more specialized prompts...
}
```

### 5. Context Size Management

From the recording:
- System prompts: ~27KB (main agent)
- Tool definitions: ~143KB (37 tools)
- Context reminders: ~10KB (skills + CLAUDE.md)
- Per-turn growth: ~2KB (user + assistant messages)

**Recommendations**:
1. Lazy-load tools (only include when first used)
2. Cache tool definitions client-side
3. Summarize old conversation turns
4. Use specialized prompts for sub-agents (smaller context)

## System Reminder Templates from Repo

Based on the repository, these system reminder templates exist:

| Template File | Purpose | Size |
|---------------|---------|------|
| `skill-available.md` | List available skills | Variable |
| `claude-md-context.md` | CLAUDE.md content | Variable |
| `current-date.md` | Today's date | ~50 chars |
| `cwd-context.md` | Working directory | Variable |
| `git-context.md` | Git status | Variable |
| `project-context.md` | Project metadata | Variable |
| `mcp-servers.md` | MCP server configs | Variable |
| `memory-context.md` | Memory synthesis | Variable |
| `env-context.md` | Environment variables | Variable |

**Implementation Priority**:
1. `skill-available` (skills list)
2. `claude-md-context` (project instructions)
3. `current-date` (temporal context)
4. `cwd-context` (working directory)
5. Others as needed

## Tool Definition Analysis

From the recorded session, tool definitions average ~3.8KB each. Example structure:

```json
{
  "name": "Read",
  "description": "Reads a file from the local filesystem...",
  "input_schema": {
    "type": "object",
    "properties": {
      "file_path": {
        "type": "string",
        "description": "The absolute path to the file..."
      },
      "offset": {...},
      "limit": {...}
    },
    "required": ["file_path"]
  }
}
```

**Key Insight**: Tool descriptions are detailed and prescriptive, often including:
1. What the tool does
2. When to use it
3. How to use it
4. Safety/security notes
5. Examples

## Token Budget Analysis

| Component | Tokens | Percentage |
|-----------|--------|------------|
| System prompt | ~6,000 | 4% |
| Tool definitions | ~35,000 | 23% |
| Context reminders | ~2,500 | 2% |
| **Total fixed** | ~43,500 | 29% |
| Conversation | Variable | 71% |

**Claude Sonnet context window**: 200,000 tokens
**Available for conversation**: ~156,500 tokens

## Appendix: Key Prompt Files from Repository

### Main Agent Prompts
- No single "main" prompt file - it's constructed from multiple pieces
- Key components: identity, behavior, tool usage, constraints

### Sub-Agent Prompts
- `agent-prompt-general-purpose.md` (285 tokens)
- `agent-prompt-explore.md` (575 tokens)
- `agent-prompt-plan-mode-enhanced.md` (715 tokens)

### Utility Prompts
- `agent-prompt-conversation-summarization.md` (1,201 tokens)
- `agent-prompt-memory-synthesis.md` (443 tokens)
- `agent-prompt-coding-session-title-generator.md` (181 tokens)

### Security/Monitoring
- `agent-prompt-security-monitor-for-autonomous-agent-actions-first-part.md` (3,332 tokens)
- `agent-prompt-security-monitor-for-autonomous-agent-actions-second-part.md` (4,136 tokens)
- `agent-prompt-bash-command-prefix-detection.md` (823 tokens)

### Reference Data
- `data-claude-api-reference-python.md` (4,499 tokens)
- `data-claude-model-catalog.md` (2,315 tokens)
- `data-anthropic-cli.md` (2,878 tokens)