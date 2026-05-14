# Context Management Research

**Date**: 2026-05-14
**Source**: Recorded Claude Code session (37 turns, ~7MB JSONL)
**Purpose**: Understand how context is managed across agent invocations, sub-agent spawning, and skill integration.

## Executive Summary

This research analyzes a recorded Claude Code session to understand context management patterns. Key findings:

| Aspect | Main Agent | Sub-Agent |
|--------|-----------|-----------|
| **Tools** | 37 tools | 28 tools (9 removed) |
| **System Prompt** | 26,827 chars | 3,152 chars |
| **Context Growth** | Accumulates | Fresh start |
| **Can Spawn Agents** | Yes | No |
| **Can Edit Files** | Yes | No (read-only) |

## Session Overview

The recorded session had 6 user turns but generated 37 HTTP requests due to:
- Title generation turn (special initial request)
- Tool loading (separate request)
- Sub-agent spawning (separate context)
- Message accumulation (each conversation turn)

### Context Growth Pattern

| Turn | Messages | Tools | Body Size | Notes |
|------|----------|-------|-----------|-------|
| 1 | 1 | 0 | 1.5 KB | Title generation (no tools) |
| 2 | 1 | 37 | 145 KB | Tools loaded |
| 3-5 | 3,5,7 | 37 | 147-152 KB | Conversation turns |
| 6 | 1 | 0 | 1.5 KB | Sub-agent spawn (fresh context) |
| 7-8 | 9,11 | 37 | 159-162 KB | Back to main agent |
| 9 | 1 | 0 | 1.6 KB | Another sub-agent spawn |
| 10-11 | 1,1 | 28 | 68-69 KB | Sub-agent with filtered tools |
| 12+ | 13+ | 37 | 162+ KB | Main agent continues |

**Key Observations**:
1. Tools add ~143KB to request body (37 tools × ~3.8KB average)
2. Each conversation turn adds ~2KB (user message + assistant response)
3. Context grew from 145KB to 268KB over the session
4. Sub-agents start fresh with smaller context (~69KB vs ~150KB+)

## Sub-Agent Spawning

### Discovery Method

Sub-agent spawns were identified by:
1. Request body size drops to < 2KB (fresh context)
2. Followed by request with fewer tools (28 vs 37)
3. Single message (the task prompt from parent)

### Tools Removed from Sub-Agent

The main agent has 37 tools, but sub-agents only get 28:

| Removed Tool | Reason |
|-------------|--------|
| Agent | Cannot spawn sub-sub-agents |
| AskUserQuestion | Cannot interact with user |
| Edit | Read-only mode enforcement |
| EnterPlanMode | No planning capability |
| ExitPlanMode | No planning capability |
| NotebookEdit | No notebook editing |
| ScheduleWakeup | No scheduling |
| TaskOutput | No task management |
| Write | Read-only mode enforcement |

**Pattern**: Sub-agents get tools appropriate to their task constraints.

### System Prompt Differences

**Main Agent System Prompt** (26,827 chars):
```
You are an interactive agent that helps users with software 
engineering tasks. Use the instructions below and the tools 
available to you to assist the user.

[Comprehensive instructions about capabilities, constraints,
best practices, tool usage patterns, etc.]
```

**Sub-Agent System Prompt** (3,152 chars):
```
You are a file search specialist for Claude Code, Anthropic's 
official CLI for Claude. You excel at thoroughly navigating and 
exploring codebases.

=== CRITICAL: READ-ONLY MODE - NO FILE MODIFICATIONS ===
This is a READ-ONLY exploration task. You are STRICTLY PROHIBITED 
from:
- Creating new files (no Write, touch, or file creation of any kind)
- Modifying existing files (no Edit operations)
[... specific constraints for this task ...]

Your strengths...
```

**Key Differences**:
1. **Length**: Main agent has 8.5× longer system prompt
2. **Scope**: Sub-agent prompt is task-specific
3. **Constraints**: Sub-agent has explicit restrictions
4. **Role**: Sub-agent has specialized role definition

### Context Passing to Sub-Agent

Sub-agent receives:
1. **System prompts**: Billing header + identity + specialized instructions
2. **First message**: The task (from parent agent)
3. **Context reminders**: Current date, available skills

Example task passed to sub-agent:
```
Search across all files in src/yoker/tools/ to find which tool 
implementations use PathGuardrail. For each tool that uses it, 
identify:
1. The tool name and file
2. How it instantiates or receives PathGuardrail  
3. What paths/operations it validates

Be thorough - check all .py files in the tools directory.
```

**No conversation history is passed to sub-agent** - it starts fresh.

## Skill Integration

### Observation

Skills are mentioned in the context reminders:
```
The following skills are available for use with the Skill tool:

- c3:start-baseweb-project: Use this skill to start...
- c3:analysis-integration: Use this skill after multiple domain...
- c3:pa-session: Manage session state for personal assistant...
```

### Pattern

1. Skills are NOT loaded as tools
2. Skills are referenced by name in system reminders
3. Skills are invoked through the `Skill` tool (one of the 37 tools)
4. The agent decides when to call a skill based on context

**Implication**: Skills are loaded on-demand via the Skill tool, not pre-loaded into context.

## Token Optimization

### Current Approach

The session showed **full context accumulation**:
- All messages retained (no summarization)
- Tool definitions loaded once and remain
- Context grew from 145KB to 268KB (85% increase)

### Potential Optimizations

Based on the analysis:

| Technique | Estimated Savings | Implementation |
|-----------|------------------|----------------|
| **Lazy tool loading** | ~140KB | Only load tools when first used |
| **Tool caching** | ~140KB per request | Cache tool definitions client-side |
| **Message summarization** | Variable | Summarize older turns |
| **Context compression** | 20-50% | Remove redundant system prompt elements |

### Tool Definition Size

Tool definitions are significant:
- 37 tools = ~143KB
- Average: ~3.8KB per tool
- Largest tools likely have extensive schemas

**Recommendation**: For Yoker, consider:
1. Load core tools always (Read, Write, Edit, Bash, Agent)
2. Load specialized tools on-demand
3. Cache tool definitions on client side

## Context Inheritance Rules

Based on observed patterns:

### Main Agent Context
1. **System prompts**: Full system prompt (26KB+)
2. **Tools**: All available tools (37)
3. **Messages**: Accumulating history
4. **Context reminders**: Current date, available skills

### Sub-Agent Context
1. **System prompts**: Specialized prompt for task (~3KB)
2. **Tools**: Filtered subset (28, no Write/Edit/Agent)
3. **Messages**: Single task message (fresh start)
4. **Context reminders**: Current date, available skills

### Key Rules

1. **Fresh Start**: Sub-agents do NOT inherit conversation history
2. **Tool Filtering**: Tools are filtered based on task constraints
3. **System Prompt Replacement**: Sub-agent gets specialized prompt
4. **Context Reminders Preserved**: Date and skill availability passed through

## Implications for Yoker

### Sub-Agent Implementation

```python
class AgentTool(Tool):
    def execute(self, task: str, agent_type: str) -> ToolResult:
        # 1. Create fresh context
        sub_context = Context()
        
        # 2. Generate specialized system prompt
        system_prompt = self._get_specialized_prompt(agent_type)
        
        # 3. Filter tools based on agent type
        available_tools = self._filter_tools(agent_type)
        
        # 4. Pass task as first message
        sub_context.add_message(role="user", content=task)
        
        # 5. Invoke sub-agent
        result = Agent(
            context=sub_context,
            system_prompt=system_prompt,
            tools=available_tools
        ).run()
        
        return ToolResult(content=result)
```

### Tool Filtering

```python
# Tools to remove for sub-agents
RESTRICTED_TOOLS = {
    "Agent",           # No sub-sub-agents
    "AskUserQuestion", # No user interaction
    "Edit",            # Read-only
    "Write",           # Read-only
    "EnterPlanMode",   # No planning
    "ExitPlanMode",    # No planning
    "NotebookEdit",    # No notebooks
    "ScheduleWakeup",  # No scheduling
    "TaskOutput",      # No task management
}
```

### Skill Integration

```python
class SkillTool(Tool):
    def execute(self, skill_name: str, args: dict) -> ToolResult:
        # Skills are NOT pre-loaded
        # They are loaded on-demand from skill directories
        
        skill = self._load_skill(skill_name)
        return skill.execute(args)
```

### Context Size Management

```python
class Context:
    def get_context_for_request(self) -> list[Message]:
        messages = self.messages
        
        # Option 1: Summarize old turns
        if self.should_summarize(messages):
            messages = self._summarize_old_turns(messages)
        
        # Option 2: Lazy load tools
        if self.lazy_tool_loading:
            # Only include tools that have been used
            tools = self._get_used_tools()
        else:
            tools = self._get_all_tools()
        
        return messages, tools
```

## Recommendations for Yoker

### 1. Implement Context Isolation for Sub-Agents

Sub-agents should start with:
- Fresh message history (no parent conversation)
- Filtered tool set (no Write/Edit/Agent)
- Specialized system prompt for task
- Context reminders (date, config)

### 2. Implement Tool Filtering

Create tool categories:
```python
CORE_TOOLS = ["Read", "List", "Search", "Existence"]  # Always available
MODIFICATION_TOOLS = ["Write", "Edit", "Mkdir"]        # Require explicit enable
AGENT_TOOLS = ["Agent"]                                 # Only for main agent
INTERACTIVE_TOOLS = ["AskUserQuestion"]                # Only for main agent
```

### 3. Consider Lazy Tool Loading

Instead of loading all tools at session start:
```python
# Load tools on first use
if tool_name not in loaded_tools:
    load_tool(tool_name)
```

### 4. Context Size Monitoring

Track context growth:
```python
def estimate_tokens(messages: list, tools: list) -> int:
    # Approximate: 1 token ≈ 4 chars
    message_chars = sum(len(m.content) for m in messages)
    tool_chars = sum(len(t.definition) for t in tools)
    return (message_chars + tool_chars) // 4
```

### 5. Skill Loading Strategy

Skills should be:
- Listed in context reminders (available skills)
- Loaded via Skill tool on-demand
- NOT included in tool definitions array
- Cached after first use for the session

## Appendix: Raw Data

### Session Statistics

- Total turns: 37
- Max body size: 268 KB
- Tools loaded (main): 37
- Tools loaded (sub-agent): 28
- System prompt (main): 26,827 chars
- System prompt (sub-agent): 3,152 chars

### Tools in Main Agent

1. Agent
2. AskUserQuestion
3. Bash
4. CronCreate
5. CronDelete
6. CronList
7. Edit
8. EnterPlanMode
9. EnterWorktree
10. ExitPlanMode
11. ExitWorktree
12. ListMcpResourcesTool
13. Monitor
14. NotebookEdit
15. PushNotification
16. Read
17. ReadMcpResourceTool
18. ScheduleWakeup
19. Skill
20. TaskCreate
21. TaskGet
22. TaskList
23. TaskOutput
24. TaskStop
25. TaskUpdate
26. WebFetch
27. WebSearch
28. Write
29-37. MCP email tools (8 tools)

### Tools in Sub-Agent

Same as main agent minus:
- Agent
- AskUserQuestion
- Edit
- EnterPlanMode
- ExitPlanMode
- NotebookEdit
- ScheduleWakeup
- TaskOutput
- Write