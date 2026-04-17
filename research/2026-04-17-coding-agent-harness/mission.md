# Research Mission

This document describes what I want you to research, how to approach it and why. IF anything isn't clear from this assignment, first ask me questions to ensure a proper understanding of the goal. You can do meta-searches to learn more about how to optimally execute your mission, if you deem this useful.

**IMPORTANT** Because this might be a very long research, ensure that I can interrupt you at any time and resume the work later. So make sure to clearly document intermediate steps and any progress in a way you can resume it from your research documentation. The current implementation of the researcher agent should support this.

## Goal

Compile a book of knowledge about the implementation of an Coding Agent Harness.

## Rationale

If we want to create our own Coding Agent Harness, we benefit from knowing the current state of the art regarding such implementations. We can learn from existing work, what works, what doesn't work, what are the common pitfalls. This will allow us to better specify our own architecture and features.

## Mission Description

First research the general architecture of an agent harness. The prime example is Claude Code. See a top-5 below.

Next research each architectural component by itself. Below I've included an initial overview of Coding Agent Harness Architecture for you to start from. Ensure you look for more architectural components to validate the list is complete. Then research each of them in detail. What implementations work, what strategies do they implement (e.g. for context management, system context, context reduction,...) I've also included some initial information specific on the topic of context management, because this is the most complex aspect of the coding agent harness.

Finally, based on this research, present a consolidated functional breakdown of a coding agent harness.

## Deliverables

The research documentation will be used by the functional analyst to further detail the required features of this project.

## Top 5 Coding Agent Harnesses

### Cursor
Best For: Overall IDE Experience.
Why: Cursor is an AI-native editor (VS Code fork) that boasts high adoption in professional settings (e.g., NVIDIA). It is frequently ranked as the top AI tool for daily coding workflows.

### Claude Code
Best For: Deep Reasoning & Complex Tasks.
Why: Operating directly in the terminal (claude CLI), it is praised for superior logic in solving multi-file issues. It excels at complex, long-running agent tasks by using "deep agents" to plan and verify code.

### Aider
Best For: Git-Native & CLI Workflows.
Why: Aider connects directly to your local terminal, maps your repository, and automatically handles git commits with proper messages. It is heavily lauded for its efficiency in refactoring and model-agnostic capabilities.

### Windsurf
Best For: Flow State & Speed.
Why: Developed by Codeium, Windsurf offers a "proactive" agent (Cascade) that provides a polished, fast experience similar to Cursor but with a different, often more competitive, pricing structure.

### Cline (formerly RooCode/Roo-Cline)
Best For: Reliability on Large Changes.
Why: Cline is an open-source, IDE-based agent (VS Code) that acts as a "reliability-first" tool. Users often turn to it when other agents fail to manage large-scale code changes or fall into "agent thrashing" (repeatedly failing the same step).

## Coding Agent Harness Architecture

A coding agent harness is the infrastructure surrounding a Large Language Model (LLM) that turns it into an autonomous developer, acting as an operating system. Its core components include a sandbox for isolated code execution, a tool registry for file/terminal access, a memory/state manager for session context, and a loop manager that handles the "observe-inspect-choose-act" cycle to self-correct errors. 

### Key Architectural Components:

**Sandboxed Execution Environment**: An isolated, containerized, or virtual environment where the agent safely reads/writes files, installs dependencies, and runs code without affecting the host machine.

**Action Service/Tool Registry**: A catalog of tools authorized for use (e.g., shell command execution, file system I/O, Git, HTTP requests, web browser access).

**Observation Service**: Mechanisms that collect outputs—code diffs, compiler errors, stack traces, and test results—and feed them back to the model for inspection.

**Memory & Context Management**: Techniques to maintain state across sessions, such as conversation history summaries, file summaries, or persistent file-based memory (e.g., <agent>.md files).

**Agentic Loop (Orchestration)**: The control logic that drives the agent through a continuous cycle of planning, acting, observing, and reflecting.

**Guardrails and Governance**: Safety constraints that prevent infinite loops, restrict network access, and manage token costs, often allowing only specified commands.

**Guides (Feedforward Controls)**: Pre-emptive instructions (e.g., AGENTS.md or LSP configurations) that provide the agent with project context, conventions, and rules before it acts. 

### Architecture Patterns:

**Single-agent Loop**: A single model instance managing all tool use, memory, and verification.

**Initializer-Executor Split**: A two-part system where one agent sets up the environment and another makes incremental updates.

**Multi-agent Coordination**: A specialized setup where the harness dispatches different agents for research, writing, and review.

## Context Management

Coding agent harnesses manage context by treating it as a scarce, expensive resource, employing strategies to keep the model's window efficient, relevant, and accurate. Key techniques include compaction (summarizing history), context pruning (removing irrelevant tool outputs), state persistence via filesystem memory, and rag-based retrieval to inject necessary documentation or file snippets only when needed, preventing context rot.  Here are the primary context management strategies:

**Compaction/Summarization**: When the context window fills up, the harness uses compaction to summarize older conversational turns or tool results, retaining essential information while freeing up tokens.

**Tool-Result Clearing (Pruning)**: To prevent context overload, harnesses often clear out large, noisy outputs from tool calls (e.g., massive file reads) once they are no longer needed, keeping only the final result or relevant snippets.

**Persistent Memory (Filesystem as Memory)**: Harnesses use the file system for long-term memory (e.g., .agents.md files). Agents read/write to these files across sessions, ensuring context survives, mitigating the, "start from zero" problem.

**Context Engineering & Retrieval**: Instead of dumping an entire repository into the context, the harness injects relevant context (e.g., specific code files, definitions, documentation) using RAG tools based on the current task.

**Workspace Summarization**: The harness proactively gathers information about the environment, such as folder structures, git status, and relevant code signatures, to build a "workspace summary" that is initialized in the prompt.

**Context Isolation (Sub-agents)**: For complex tasks, the harness may break down work into sub-tasks, handing them off to specialized agents. This isolates the context, preventing irrelevant sub-task details from polluting the main task's context window. 

### Core Components of a Harness

**RAM/Short-term memory**: Manages the active conversation and prompt context.
Filesystem/Long-term memory: Durable storage for persistent memory, git state, and task logs.

**Tools**: External services (web search, file system, code editor) managed by the harness. 

### Common Tools/Systems

**Claude Code**: Uses native mechanisms to manage 200,000+ token contexts, including specialized commands to manage context and state.

**LangChain Agent Harnesses**: Uses agentic frameworks that emphasize RAG-based context injection, file system persistence, and proactive tool use.
