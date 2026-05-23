# Agent Session Continuity

## Context

When invoking agents that ask clarifying questions, always use `SendMessage` to continue the conversation. Never bypass the agent by doing the task manually.

## Problem

During Task 1.7.1 implementation, the git-manager agent asked a clarifying question about which files to commit. Instead of using `SendMessage` to answer and let the agent complete the commit, I bypassed the agent and ran git commands manually.

## Correct Pattern

```python
# 1. Launch agent
response = Agent(subagent_type="c3:git-manager", prompt="...")
# Returns: agentId: abc123, question about which files

# 2. Use SendMessage to continue
SendMessage(to="abc123", content="Option 1 - proceed with core files")

# 3. Agent completes the task
```

## Incorrect Pattern

```python
# 1. Launch agent
response = Agent(subagent_type="c3:git-manager", prompt="...")
# Returns: agentId: abc123, question about which files

# 2. Bypass agent and do it manually ❌
Bash("git add ...")
Bash("git commit ...")
```

## Reference

See global CLAUDE.md instructions under "Agent Session Continuity":
> When conducting multi-turn interactions with agents:
> 1. Launch agent once - Use the Agent tool to start the interaction
> 2. Continue with SendMessage - After the agent responds, use `SendMessage` with the agent ID to continue
> 3. Never restart mid-conversation - Do NOT launch a new Agent for follow-up questions

## Date

2026-05-23