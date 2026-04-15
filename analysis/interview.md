# Interview: Yoke Agent Harness Requirements

**Date**: 2026-04-14
**Interviewer**: Functional Analyst Agent
**Interviewee**: Christophe VG

---

## Question 1: Core Vision and Motivation

**Q:** What specific limitations or pain points are you experiencing with Claude Code that you want to address with Clause?

**A:** I want to be able to define more and specialized tools, to implement specific guardrails and make sure that I can give more permissions to agents to enable them to work more autonomously, without my interaction. I want to be able to run sets of agents without a UI/CLI interface, e.g. daemonized. I want more control over the interaction with the harness and implement additional features that I see fit beyond the vision of Claude Code. I also want to remove a lot of things from Claude Code's implementation that I don't need (such as support for things I don't use). Most importantly, I want to learn to see if this is an important aspect to deal with when futher exploring agentic workflows.

---

## Question 2: Specialized Tools

**Q:** What other specialized tools do you envision?

**A:** The additional examples provided are good ones:
- File system tools with granular permissions
- Network/web interaction tools with boundaries
- Database access tools
- Process/system control tools

---

## Question 3: Guardrails Implementation

**Q:** How would you like guardrails to work?

**A:** The guardrails would be implemented in the tools that are provided to the LLM and are completely tool dependant. A global configuration file will enable setting up the necessary configurations for all these tools.

---

## Question 4: Daemonized Execution

**Q:** What execution models do you envision? How should daemonized agents communicate status?

**A:** The proposed execution models are all good examples:
- Scheduled (cron-like)
- Event-driven
- Continuous (polling)
- On-demand

For communication: logging will be mandatory, status files might be an option. No full message queue infrastructure. Agents will be daemonized in sets, very much like currently a session in Claude Code runs with agents communicating in-process.

---

## Question 5: Removing Unused Features

**Q:** What features of Claude Code do you NOT need?

**A:** (No specific items listed - implicit: features not used in personal workflow)

---

## Question 6: Learning and Autonomy Goals

**Q:** What specific aspects do you want to explore?

**A:** Yes, all the learning topics interest me:
- How custom tools affect agent reliability
- How guardrails affect agent autonomy
- How daemonized execution changes workflow possibilities
- Understanding the architecture of agent harnesses

---

## Question 7: Backend Strategy

**Q:** Single-backend harness (Ollama first) or multi-backend abstraction from the start?

**A:** A single-backend harness (Ollama first, others later)

---

## Question 8: Core Modules

**Q:** Which core modules do you envision?

**A:** All of the mentioned modules:
- Tool system (registration, validation, execution)
- Agent manager (lifecycle, state, communication)
- Configuration system (guardrails, permissions, settings)
- Communication layer (logging, status files, in-process messaging)

---

## Question 9: Framework Relationship

**Q:** What's the relationship with existing frameworks like LangChain, LlamaIndex, AutoGen?

**A:** Currently I see it as an opinionated alternative, for private use.

---

## Question 10: Clitic Integration

**Q:** How do you see Clitic and Clause working together?

**A:** Clause provides the agent runtime, Clitic provides the TUI.

---

## Question 11: Developer Workflow

**Q:** Is the vision that a developer would build agents with Clause APIs, optionally add Clitic CLI, deploy with or without UI?

**A:** All of the above.

---

## Question 12: Independence from Claude Code

**Q:** Is Clause intended to run agents outside Claude Code, inside, or both?

**A:** This harness is completely independent of Claude Code. It's meant to be a harness completely on its own.

---

## Question 13: Tool Definition Approach

**Q:** For tools/guardrails, would Clause define tools in Python registered with LLM backend, translate tool definitions, or provide unified interface?

**A:** Define tools in Python that get registered with an LLM backend.

---

## Question 14: MVP Scope

**Q:** What's the minimum viable feature set?

**A:** MVP = run top-level agent with most important tools, including Agent tool to allow validation that basic sessions already run today in Claude Code are possible, taking into account basic context management, input/output simply console input and output (fancy UI comes later with Clitic).

---

## Question 15: Timeline

**Q:** What's your target timeline for the MVP?

**A:** Quick implementation of MVP/proof of concept, then iterate, learn, refine, until full time replacement of personal use of Claude Code. Then additional features (e.g. daemons, ...)

---

## Question 16: First Iteration Capabilities

**Q:** What should Clause be able to do in its first iteration?

**A:** See MVP scope above.

---

## Question 17: Proof of Concept

**Q:** What's the simplest proof of concept that would convince you Clause is viable?

**A:** An agent that can read/write files within allowed directories (read/write tools enforce access based on config) and be able to spawn subagents.

---

## Question 18: MVP Tools

**Q:** Which tools should be included in the MVP?

**A:** List/Read/Write/Update/Search/Agent seem a bare minimum. I want to try to avoid a generic Bash tool, to be able to have better guardrails.

---

## Question 19: Context Management

**Q:** What does "basic context management" mean for MVP?

**A:** Context building for consecutive LLM calls, it should be persisted. Token management is second phase, yet important and will require research into how to optimize context.

---

## Question 20: Configuration Format

**Q:** Any preference for configuration file format?

**A:** TOML seems a good fit for the multiple tools.

---

## Question 21: Access Control Granularity

**Q:** Should the MVP support simple allowed/blocked directories, per-tool permissions, or per-agent permissions?

**A:** One config file, loaded on start of the harness, each tool takes its configuration (including guardrail configuration) and enforces it, regardless of agents (one for all). Agents themselves will be given access to a possibly reduced set of tools.

---

## Question 22: Subagent Communication

**Q:** Can subagents spawn more subagents? Is there a max depth? How do subagents report back?

**A:** Yes, (sub-)agents can spawn other agents. We could introduce a max (recursion) depth indeed. Reporting: to be investigated/designed.

---

## Question 23: Ollama Model Selection

**Q:** Should the harness use a specific default model, allow model selection in configuration, or require Ollama to already be running?

**A:** All parameters we can pass to the ollama backend will be configurable. Ollama will be running.

---

## User Remarks on Analysis

After reviewing the initial functional analysis, the user provided the following remarks:

### Remark 1: Context Storage Format
- **Original:** JSON format for context storage
- **Feedback:** "Wouldn't JSONL be easier to store large and growing numbers of context conversation lines?"
- **Decision:** Changed to JSONL format for append-friendly storage

### Remark 2: Tool Definitions
- **Original:** Preliminary tool schemas in analysis
- **Feedback:** "For the final definition of the tools and their parameter schema, I think we should look at existing implementations. For now this analysis is already fine."
- **Decision:** Keep preliminary definitions, note that final versions should reference Claude Code/Ollama/OpenAI formats

### Remark 3: Agent Definitions Format
- **Original:** TOML agent definitions
- **Feedback:** "Agent definitions will be Markdown file, with frontmatter. In that frontmatter, the tools available to them will be defined. Again, we will here look at proven standards and follow initially the existing documentation of Claude Code - also to enable reusing existing Claude Code agents without changes."
- **Decision:** Changed to Markdown files with YAML frontmatter, compatible with Claude Code format

### Remark 4: Agent Depth Awareness
- **Original:** Agents know their depth and track it
- **Feedback:** "I don't think there is a need for an Agent to 'know' e.g. its depth. If it tries to spawn another subagent and the max depth is reached, it will have to deal with the error."
- **Decision:** Removed depth awareness from agent interface, agents handle errors when max depth exceeded

### Remark 5: Subagent Workflow
- **Original:** Parent provides task, tools, context, constraints
- **Feedback:** "When spawning a sub-agent, the parent provides an initial prompt. The global/system instructions will contain such instructions to do so. We want to limit the level of mandatory/in-code enforced workflow and allow in-context definition of ways of working and interacting."
- **Decision:** Simplified to parent providing initial prompt only, workflow defined in system prompts

### Remark 6: Subagent Context
- **Original:** Subagent inherits context from parent
- **Feedback:** "Sub-Agents start with a clean context and get their initial prompt from the parent."
- **Decision:** Subagents get fresh, empty context with only initial prompt

### Remark 7: Project Setup
- **Feedback:** "Ensure there is a ReadTheDocs compatible documentation maintained at every level of the project. Although it will be primarily a personal project, I want it to be ready to be published to PyPI. In general: review all structural aspects we have implemented for 'clitic' and apply those same best practices for this project."
- **Decision:** Added Sphinx documentation structure, PyPI-ready pyproject.toml template

### Remark 8: Naming
- **Feedback:** "We need to come up with a nice name for our own agent harness (fun and available as package name on PyPI)"
- **Decision:** Research conducted, "yoker" selected as package name (available on PyPI, pairs with "clitic"). See `docs/NAME.md` for full naming documentation.

---

## Summary of Key Decisions

1. **Backend**: Ollama first, single backend
2. **Tools**: List, Read, Write, Update, Search, Agent (no Bash)
3. **Guardrails**: Tool-specific, enforced by tools, configured via TOML
4. **Agent Definitions**: Markdown with YAML frontmatter
5. **Context**: JSONL format, persisted, fresh for subagents
6. **Depth**: Tracked internally, agents handle errors
7. **Naming**: "yoker" (PyPI available, pairs with "clitic", agent noun from "yoke")
8. **Project**: Sphinx docs, PyPI-ready, following clitic structure