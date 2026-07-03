# Session Concept — Deep Analysis

Status: Analysis for owner review
Author: Functional Analyst
Date: 2026-07-03

This document analyses the proposed introduction of a `Session` construct to
Yoker: a "team of agents" coordinator that takes over spawning, lifecycle, and
inter-agent communication, reducing `Agent` to a single-agent chat loop.

---

## 1. Executive Summary

**Verdict: the `Session` concept is valid and recommended.**

The current `Agent` class is doing two distinct jobs. It is, at the same time:

1. **A single-agent chat loop** — talks to one model, manages one context,
   emits one event stream, calls tools. This is the irreducible
   responsibility of an "agent".
2. **A multi-agent orchestrator** — owns the `AgentRegistry`, tracks
   recursion depth, hosts the `agent` sub-agent spawning tool, and (via
   `builtin/agent.py::_create_subagent`) knows how to construct, configure,
   and run child agents with isolated context and model overrides.

These two jobs are entangled in one class and one constructor. The result is
that `Agent` cannot be used as a pure single-agent primitive without also
dragging in the orchestration machinery, and the orchestration machinery
cannot evolve independently of the agent loop (e.g. parallel fan-out, agent
addressing, session-level event aggregation, shared backends).

Introducing `Session` as a separate construct that owns the orchestration
concern is the right separation. It unlocks genuine multi-agent workflows
(teams, pipelines, fan-out/fan-in, inter-agent messaging) that are awkward to
express today, and it lets `Agent` shrink to a single, composable primitive
that is far easier to embed, test, and reason about.

The change is also a prerequisite for MBI-003 (Python API). The
`yoker.session()` proposed in `analysis/mbi-003-python-api-design.md` is
exactly this `Session`, but the design currently hand-waves it as a thin
context manager around `Agent`. Once `Session` is a first-class concept,
MBI-003's Layer 3 (Workflow Primitives) becomes a facade over a real
primitive instead of a facade over a missing one.

**Recommendation: introduce `Session` as MBI-007, sequenced before MBI-003.**
The two can be specified in parallel, but the Session should land first
because MBI-003's `session()`, `spawn()`, and event aggregation all depend on
it.

---

## 2. Current Architecture Review

### 2.1 The `Agent` class today (`src/yoker/agent/agent.py`)

`Agent.__init__` constructs, in one shot:

| Field | Concern | Belongs to agent loop or orchestration? |
|-------|---------|------------------------------------------|
| `self.config: Config` | Frozen config | Shared — but per-agent overrides exist |
| `self.tools: ToolRegistry` | Tools available to this agent | Agent loop |
| `self.skills: SkillRegistry` | Skills available to this agent | Agent loop |
| `self.agents: AgentRegistry` | **Other agents this agent can spawn** | **Orchestration** |
| `self._cli_plugins` | Plugin packages from CLI | Shared |
| `self.definition: AgentDefinition` | This agent's identity/prompt/tools | Agent loop |
| `self.recursion_depth` | **Current depth in a spawn tree** | **Orchestration** |
| `self.max_recursion_depth` | **Configured spawn limit** | **Orchestration** |
| `self.model`, `self.thinking_mode` | Model selection | Agent loop |
| `self._backend: ModelBackend` | Model connection | Agent loop (but could be shared) |
| `self._guardrails` | Path/query/url guardrails | Agent loop |
| `self._tool_backends` | Provider-specific tool backends | Agent loop |
| `self.context: ContextManager` | Conversation history + session ID | Agent loop (but session ID is orchestration) |
| `self._event_handlers` | Event subscribers | Agent loop (but sub-agents don't propagate) |

The orchestration fields are explicit: `agents`, `recursion_depth`,
`max_recursion_depth`. They exist purely to support sub-agent spawning.

### 2.2 Sub-agent spawning (`src/yoker/builtin/agent.py`)

`make_agent_tool(parent_agent)` is the tool registered on the parent agent
when `config.tools.agent.enabled` and there are agents in the registry. It:

- Captures a direct reference to `parent_agent`.
- Reads `parent_agent.recursion_depth` and `parent_agent.max_recursion_depth`
  to enforce the depth limit.
- Calls `parent_agent.agents.resolve(agent_name)` to find the child
  definition.
- Calls `_create_subagent(parent_agent, agent_definition)` which:
  - Reads `parent_agent.context.get_session_id()` to derive a child session id.
  - Reads `parent_agent.config` and uses `dataclasses.replace` to override the
    model from the child definition.
  - Constructs a **brand new `Agent`** with `_recursion_depth=depth+1`.
- Calls `_run_with_timeout(subagent, prompt, timeout_seconds)` which wraps
  `agent.process(prompt)` in `asyncio.wait_for`.

Key observations:

- The child agent is fully isolated: fresh context, fresh event handlers
  (i.e. **none**), fresh tool registry rebuilt from config. The parent's
  event handlers do not see the child's events. The parent's context does
  not see the child's messages. The only thing that comes back is the final
  string response.
- The parent-child relationship is implicit and ephemeral. There is no
  record of which agents were spawned, no way to address them after the call,
  no way to send them a follow-up message.
- The `agent` tool returns a `ToolResult(success, result_string)`. There is
  no structured return, no streaming, no event propagation.
- Session ID derivation is a hack: `f"{parent_session}_{uuid[:8]}"`. It
  creates a new persistence file per sub-agent, which is rarely what anyone
  wants and clutters the sessions directory.

### 2.3 Context and session ID (`src/yoker/context/`)

`ContextManager` (base, `manager.py`) is a `UserList[dict]` with helpers for
adding messages, tool calls, and tool results. It exposes
`get_session_id()` which returns `"in-memory"` for the base class and a real
id for `PersistenceContextManager`.

`PersistenceContextManager` (`persistence.py`) writes JSONL records with
`session_start`, `message`, `tool_result`, `tool_call_message`, `turn_start`,
`turn_end`, `session_end`. It supports `resume(session_id)` to load an
existing session. There is a `list_sessions()` helper in `session.py`.

The session id is currently owned by the context manager, which is owned by
the Agent. There is no higher-level construct that groups multiple agents
under one session id — each sub-agent gets its own derived id and its own
file.

### 2.4 Event system (`src/yoker/events/`)

`Event` is a frozen dataclass with a `type: EventType` and `timestamp`. The
types are: `TURN_START/END`, `THINKING_*`, `CONTENT_*`, `TOOL_CALL/RESULT/
CONTENT`, `COMMAND`. There is no `SESSION_*` event and no
`AGENT_SPAWNED/AGENT_FINISHED` event.

`Agent._event_handlers` is a list of sync-or-async callables. `emit()` in
`_processing.py` fans out each event to all handlers. The `UIBridge` is one
such handler.

Critical gap for multi-agent: **sub-agents do not inherit the parent's event
handlers.** When a sub-agent is spawned in `_create_subagent`, the new
`Agent` is constructed with no event handlers wired. The parent (and the UI)
is blind to everything the sub-agent does until the final string comes back.

### 2.5 Agent registry (`src/yoker/agents/`)

`AgentRegistry` is a `UserDict[str, AgentDefinition]` keyed by namespaced
name. `resolve(name)` handles both namespaced (`pkg:agent`) and bare names
(with ambiguity detection). Definitions are loaded from configured
directories and from plugins.

The registry lives on `Agent`. Every Agent — including every sub-agent —
rebuilds its own registry from config. There is no shared registry across a
spawn tree.

### 2.6 Processing loop (`src/yoker/agent/_processing.py`)

`process_message(agent, message)` runs the chat→tool→chat loop. It emits
turn/thinking/content/tool events through `agent._event_handlers`. It is
purely a single-agent loop. It has no knowledge of sub-agents, registries,
or recursion. This is the part of `Agent` that is genuinely "the agent".

### 2.7 Config (`src/yoker/config/__init__.py`)

Config is a frozen dataclass tree. Orchestration-relevant fields:
- `config.tools.agent.max_recursion_depth` (default 3)
- `config.tools.agent.timeout_seconds` (default 300)
- `config.tools.agent.enabled`
- `config.agents.directories` and `config.agents.definition`
- `config.context.session_id` and `config.context.storage_path`

These are session-level concerns expressed as agent-level config because
there is no Session to hold them.

### 2.8 Entry point (`src/yoker/__main__.py`)

`run_session(agent, ui, commands)` is the interactive loop. Despite its
name, it is not a "session" in the proposed sense — it is a REPL loop that
reads input, dispatches slash commands, and calls `agent.process()`. There
is no multi-agent awareness. The name `run_session` will become confusing
once a real `Session` exists; consider renaming to `run_repl` or similar
in a follow-up.

### 2.9 UI layer (`src/yoker/ui/bridge.py`)

`UIBridge` is an event handler that translates `Event` → `UIHandler` method
calls. It is wired to one Agent via `agent.add_event_handler(bridge)`. The
UI has no session concept — it talks to one agent. When a sub-agent runs,
the UI sees nothing from it.

---

## 3. The Session Concept

A `Session` is a construct that owns the lifecycle of one or more agents and
the relationships between them. It is the "team of agents" container.

Proposed responsibilities:

1. **Agent lifecycle** — create, start, monitor, cancel, destroy agents.
   Today this logic is smeared across `Agent.__init__`,
   `builtin/agent.py::_create_subagent`, and `_run_with_timeout`.
2. **Agent registry** — own the `AgentRegistry` (the team roster). Today
   this is rebuilt per-Agent from config.
3. **Recursion depth tracking** — own the depth tree. Today this is a
   counter threaded through `_recursion_depth` constructor args.
4. **Inter-agent communication** — provide a messaging/routing layer so
   agents can address each other by name. Today this does not exist; the
   only path is "spawn a fresh child and get a string back".
5. **Session ID** — own the session id namespace. Today this is derived
   ad hoc in `_create_subagent`.
6. **Event aggregation** — collect events from all agents in the session
   and re-emit them with agent identity tagged. Today sub-agent events are
   invisible to the parent and UI.
7. **Resource sharing** — share backend connections, tool backends, and
   guardrails across agents where appropriate. Today each sub-agent
   rebuilds its own backend from config.
8. **Context isolation/sharing policy** — decide whether a child gets
   fresh context, a fork of the parent's, or a shared context. Today it is
   always fresh.

What `Agent` becomes after extraction:

- `config` (per-agent, possibly derived from session config)
- `definition` (system prompt, tools, model)
- `tools`, `skills` (per-agent)
- `context` (per-agent; session id assigned by session)
- `model`, `thinking_mode`, `_backend` (per-agent or shared from session)
- `guardrails`, `_tool_backends` (per-agent or shared from session)
- `_event_handlers` (events emitted go to session aggregator)
- `process()` — the single-agent chat loop. Unchanged.

What `Agent` loses:

- `agents: AgentRegistry` → moves to Session
- `recursion_depth`, `max_recursion_depth` → moves to Session
- The `agent` sub-agent tool → becomes a Session-provided tool (or a
  Session method invoked by a thin tool wrapper)
- `_create_subagent`, `_run_with_timeout` → moves to Session
- Session id derivation → moves to Session

---

## 4. Opportunities

### 4.1 True multi-agent orchestration

Today the only multi-agent pattern Yoker supports is "parent spawns child,
child runs to completion, parent gets a string". With a Session:

- **Fan-out/fan-in**: spawn N agents in parallel (`asyncio.gather`), collect
  results. Today this requires manually constructing N `Agent` instances in
  user code, bypassing the `agent` tool entirely.
- **Pipelines**: agent A → agent B → agent C, each with its own model and
  tools, orchestrated by the session.
- **Long-lived teams**: agents that persist across multiple user turns and
  can be re-addressed by name. Today every sub-agent call creates a fresh
  agent with no memory of prior calls.
- **Hierarchical teams**: a session can contain sub-sessions (e.g. a
  "research" sub-session with its own researcher + summarizer agents).

### 4.2 Inter-agent messaging

With a Session acting as router, agents can send messages to each other by
name. Use cases:

- A "reviewer" agent asks a "researcher" agent to look something up mid-turn,
  without the user being in the loop.
- A "coordinator" agent delegates sub-tasks to specialist agents and
  aggregates their responses.
- Agents can stream progress to each other (and to the UI) via events,
  rather than the current all-or-nothing string return.

### 4.3 Session-level event aggregation

Today the UI is blind to sub-agent activity. With a Session:

- All agents' events are aggregated and tagged with the source agent's
  identity.
- The UI can show a unified view: "Researcher is thinking...",
  "Reviewer called read(auth.py)", etc.
- Event recording (`EventRecorder`) becomes session-scoped, producing a
  single replay file per session that captures the entire multi-agent
  trace.

### 4.4 Resource sharing

Each sub-agent today rebuilds its own `ModelBackend`, guardrails, and tool
backends from config. For a fan-out of 10 agents on the same provider, that
is 10 backend instances. A Session can share one backend (with connection
pooling) across all agents in the team.

### 4.5 Cleaner Agent, cleaner tests

`Agent` becomes a single-responsibility class: "given a config, a
definition, a context, and event handlers, chat with a model and call
tools." It becomes trivially testable without spinning up registries,
plugin loaders, or recursion machinery. The orchestration logic moves to
`Session`, which is tested separately.

### 4.6 MBI-003 becomes real

The `yoker.session()` in the MBI-003 design is currently a thin context
manager wrapping one Agent. With a real `Session`, it becomes:

```python
async with yoker.session(id="audit-2026-07-03") as session:
  researcher = session.agent("researcher")
  reviewer = session.agent("reviewer")
  findings = await researcher.process("Audit src/ for security issues.")
  review = await reviewer.process(f"Review these findings: {findings}")
  await session.broadcast("All done.")
```

The `spawn()` method proposed in MBI-003 becomes `session.spawn()` (or
`session.agent(name).process(...)`), and it actually has a coherent
implementation because the Session owns the registry, the depth tree, and
event propagation.

### 4.7 Session persistence and resumption

A Session naturally maps to a persisted unit: one session id, one event
trace, one context tree (parent + children). Today persistence is
per-agent-context, which produces scattered JSONL files with derived ids
that are hard to reconstruct as a coherent session.

### 4.8 Alignment with rationale and NOTES

`docs/rationale.md` emphasizes "Recursive Composition: True Sub-Agents" as a
key differentiator. The current implementation is true sub-agents but only
one level deep, with no addressing, no event visibility, and no shared
resources. Session is the construct that makes the "true sub-agents"
claim fully real.

`NOTES.md` positions Yoker as "Agentic Functions" — LLM capabilities as
ordinary Python function calls. A Session is what makes
`await session.agent("researcher").process(...)` feel like calling a
function in a team, not like orchestrating a framework.

---

## 5. Problems

### 5.1 The `agent` tool must be reworked

`make_agent_tool(parent_agent)` captures the parent Agent. After
extraction, the tool should capture the Session instead. The tool's
behaviour (resolve name, create child, run with timeout, return string)
moves to `Session.spawn(name, prompt, timeout=...)`. The tool becomes a
thin wrapper that calls `session.spawn` and wraps the result in a
`ToolResult`.

This is a clean refactor but it touches the tool registration path in
`Agent.__init__` (lines 123-125 of `agent.py`).

### 5.2 `AgentRegistry` moves off `Agent`

`self.agents` on Agent is used in two places:
- `Agent._load_agents()` populates it from config directories.
- `make_agent_tool` resolves names from it.
- `_resolve_agent_definition` resolves the *own* definition from it.

After extraction:
- The registry is owned by Session. The Session populates it from config
  and plugins.
- An Agent still needs to resolve *its own* definition. That can be passed
  in directly (already supported via `agent_definition` / `agent_path`
  constructor args) or resolved through the session.
- The `agent` tool no longer reads `parent_agent.agents`; it reads
  `session.agents`.

Backward compatibility: code that reads `agent.agents` directly will break.
We should provide a deprecation path (e.g. a property that returns the
session's registry, with a warning) or accept the break since the public
API surface is small.

### 5.3 Recursion depth moves off `Agent`

`recursion_depth` and `max_recursion_depth` are used in:
- `Agent.__init__` (validation via `validate_recursion_depth`)
- `make_agent_tool` (depth check before spawning)
- `_create_subagent` (compute child depth)
- Logging

After extraction, the Session tracks depth. An Agent no longer needs to
know its depth. The `agent` tool asks the Session "can I spawn at depth
N+1?" and the Session decides.

Backward compatibility: `Agent(_recursion_depth=...)` is a public constructor
arg. We can keep it as a no-op/ignored parameter with a deprecation warning,
or remove it. Since it is prefixed with `_`, it is conventionally private
and removal is acceptable.

### 5.4 Sub-agent events are invisible today — Session fixes this, but it is a behaviour change

Currently sub-agents run silently from the UI's perspective. After
introduction of Session, if event aggregation is on by default, the UI will
start showing sub-agent activity. This is a user-visible behaviour change.
It is strictly an improvement, but it will change the look and feel of
existing workflows and may surprise users who relied on the quiet behaviour.
Mitigation: make aggregation opt-in via config, or expose a "verbose
sub-agents" toggle.

### 5.5 `run_session()` in `__main__.py` needs rethinking

The function named `run_session` is actually the REPL loop, not a Session.
Once a real `Session` exists:
- `main()` should construct a `Session` (which owns the agent registry,
  config, and event aggregation).
- The REPL loop (rename to `run_repl`) drives one Agent within that Session.
- The `agent` tool, when invoked, uses the Session to spawn children, and
  the Session's event aggregator feeds sub-agent events to the same UIBridge.

This is the largest integration change but it is localised to `__main__.py`.

### 5.6 The bootstrap wizard

`BootstrapWizard` runs before any Agent exists. It produces a Config.
This is unaffected by Session — Session is constructed from Config, same
as Agent is today. No change needed.

### 5.7 Plugins

`load_configured_plugins(agent, config, cli_plugins)` is called from
`Agent.__init__` and populates `agent.tools`, `agent.skills`, `agent.agents`.
After extraction:
- Plugins should be loaded by the Session, populating the shared
  registries (tools-defaults, skills, agents).
- Individual Agents inherit/select from the session's registries based on
  their definition.
- This is a moderate refactor of `yoker/plugins/registration.py` and the
  `load_configured_plugins` entry point.

---

## 6. Challenges

### 6.1 Async lifecycle

A Session must manage the lifetimes of multiple concurrent agents:
- Creation: lazy (on demand) vs eager (at session start).
- Awaiting: `process()` calls are async; the session must track outstanding
  tasks.
- Cancellation: if the user Ctrl+C's, all running agents should be
  cancelled cleanly. Today `asyncio.wait_for` handles one child; the
  Session needs `asyncio.TaskGroup` (Python 3.11+) or equivalent.
- Cleanup: backends, context managers, and event handlers must be closed.

Recommended pattern: `async with Session() as session:` using
`asynccontextmanager` or an `__aenter__`/`__aexit__` pair. Inside, use
`asyncio.TaskGroup` for spawned agents.

### 6.2 Inter-agent message routing

Two design options:

**(a) Routed through Session** — agents call `session.send(to="researcher",
message="...")`. The Session looks up the target agent and calls
`target.process(message)`. Pro: centralised, observable, easy to enforce
permissions and rate limits. Con: every message goes through an extra hop;
agents must hold a reference to the session.

**(b) Direct addressing** — agents hold references to each other (via
weak refs or an address book) and call `other.process(...)` directly. Pro:
no hop. Con: harder to observe, harder to enforce boundaries, lifecycle
coupling (who keeps who alive?).

**Recommendation: (a) routed through Session.** It aligns with the
transparency philosophy (all inter-agent traffic is observable via session
events) and keeps lifecycle management centralised. The "extra hop" is
trivial in a Python function call.

### 6.3 Agent addressing

Agents should be addressable by name (the name from their
`AgentDefinition`). The Session maintains a name→agent map. Names must be
unique within a session. If two agents with the same definition are spawned,
disambiguate with an instance suffix (`researcher`, `researcher-2`).

### 6.4 Context isolation vs sharing

Default: fresh context per agent (current behaviour). But the Session
should support policies:
- `fresh` — new empty context (default, current behaviour).
- `fork` — copy parent context at spawn time (useful for "continue with
  this context but a different agent/model").
- `shared` — multiple agents read/write the same context (advanced,
  requires locking; defer to a later phase).

### 6.5 Event propagation

Two layers:
- **Agent-level events**: the existing `Event` stream from one agent's
  `process()` loop. Unchanged.
- **Session-level events**: a new envelope that wraps agent events with
  `agent_name`, `session_id`, and possibly `depth`. The Session emits
  these; the UI and recorders consume them.

New event types to consider: `SESSION_START`, `SESSION_END`,
`AGENT_SPAWNED`, `AGENT_FINISHED`, `AGENT_MESSAGE` (inter-agent). These
are additive to `EventType`.

### 6.6 Backpressure and flow control

If agent A streams content to agent B in real-time, and B is slow, the
Session needs backpressure. For the initial MBI, we can avoid this by
making inter-agent messaging request-response (not streaming): A sends a
message, B processes and returns a string. Streaming inter-agent
communication is a follow-up.

### 6.7 Error handling and recovery

- If a sub-agent raises, the Session should catch, log, and optionally
  retry or report to the parent. Today the `agent` tool already catches
  exceptions and returns error strings; that behaviour should be preserved
  at the Session level.
- Session-level errors (e.g. backend down) should propagate to all agents
  in the session.

### 6.8 Plugin interaction with Session

Plugins currently register tools/skills/agents onto an `Agent` instance.
With Session, plugins should register onto the Session (or onto a
"session template" that is used to construct agents). This is a moderate
refactor of the plugin registration path but it aligns with the
"registries belong to the team, not the individual" model.

### 6.9 Persistence

Session persistence should write one coherent record per session,
including the agent tree, all events, and all contexts. Today's
per-agent JSONL files with derived ids are a poor substitute. The
`EventRecorder` already records events to JSONL; extending it to record
session-level events (with agent identity) is the natural path. Context
persistence per agent can remain as-is, with the session id as the
namespace.

### 6.10 Backward compatibility

The main public API (`Agent`, `Config`, events) stays. The breaking changes
are:
- `agent.agents` (registry) — moves to Session. Provide a deprecation
  property on Agent that proxies to the session, or accept the break.
- `agent.recursion_depth`, `agent.max_recursion_depth` — remove (private
  `_`-prefixed, acceptable).
- `Agent(_recursion_depth=...)` constructor arg — remove or ignore.
- The `agent` built-in tool — internally reworked, externally identical
  behaviour.

For the interactive CLI user, no change is visible. For the library user
(embedding Yoker in Python), the migration is: wrap your `Agent` in a
`Session` if you want multi-agent features; keep using bare `Agent` for
single-agent use cases.

---

## 7. Architecture Questions (open for owner input)

1. **Is `Session` a container, a coordinator, or both?**
   Recommendation: both. It holds the agents (container) and routes
   messages/spawns (coordinator).

2. **How do agents address each other?**
   Recommendation: by name, resolved through the Session. The Session
   maintains the name→agent map.

3. **What is the message format for inter-agent communication?**
   Recommendation: a simple `Message(from: str, to: str, content: str,
   metadata: dict)` dataclass. The content is a plain string (the prompt).
   Streaming inter-agent messages are deferred.

4. **Should `Session` be an async context manager?**
   Recommendation: yes. `async with Session(config=...) as session:`. This
   handles lifecycle, cleanup, and cancellation cleanly.

5. **How does the UI consume session-level events?**
   Recommendation: the `UIBridge` is registered on the Session (not on
   individual agents). The Session fans out aggregated events to its
   handlers. The `UIHandler` protocol gains optional methods for
   `agent_spawned(name)`, `agent_finished(name)`, and existing methods
   receive events tagged with `agent_name`.

6. **Does `Session` replace `run_session()` in `__main__.py`?**
   Recommendation: `run_session` (the REPL loop) is renamed to `run_repl`
   and operates inside a Session. The Session is constructed in `main()`.

7. **How does Session interact with Config?**
   Recommendation: Session is constructed from a `Config`. The Config may
   gain a `[session]` section (max_agents, default_isolation_policy,
   event_aggregation). Per-agent config overrides use `dataclasses.replace`
   (existing pattern).

8. **Does the `agent` tool become a Session method?**
   Recommendation: yes. `Session.spawn(name, prompt, timeout=...)` is the
   canonical API. The `agent` built-in tool becomes a thin wrapper that
   calls `ctx.session.spawn(...)` and wraps the result in a `ToolResult`.
   The `ToolContext` gains a `session` reference.

9. **Should the Session own the backend, or should each Agent own one?**
   Recommendation: Session owns a "backend factory" and shares backends
   across agents using the same provider config. Each Agent gets a backend
   reference (not a fresh instance) unless its definition overrides the
   model/provider (in which case the Session creates a new backend for
   that agent).

10. **Does Session replace `AgentRegistry` on Agent entirely?**
    Recommendation: yes. `Agent.agents` is removed. The Session holds the
    registry. An Agent that needs to resolve its own definition does so via
    the Session (or via the explicit `agent_definition`/`agent_path`
    constructor args, which remain).

---

## 8. Impact Analysis

| Component | Impact | Effort |
|-----------|--------|--------|
| `src/yoker/agent/agent.py` | Loses `agents`, `recursion_depth`, `max_recursion_depth`, the agent-tool registration. Constructor shrinks. | M |
| `src/yoker/agent/_setup.py` | `validate_recursion_depth` moves to Session. | S |
| `src/yoker/builtin/agent.py` | Rewritten to capture Session instead of parent_agent. `_create_subagent` and `_run_with_timeout` move to Session. | M |
| `src/yoker/agents/registry.py` | No change to the class; ownership moves to Session. | S |
| `src/yoker/context/` | No change to managers. Session id assignment moves to Session. | S |
| `src/yoker/events/` | New session-level event types (`SESSION_START/END`, `AGENT_SPAWNED/FINISHED`, `AGENT_MESSAGE`). `EventRecorder` becomes session-scoped. | M |
| `src/yoker/ui/bridge.py` | Registered on Session, not Agent. Optional new handler methods for sub-agent events. | M |
| `src/yoker/ui/handler.py` | Optional new protocol methods (`agent_spawned`, `agent_finished`). Default implementations no-op. | S |
| `src/yoker/__main__.py` | Construct Session in `main()`, rename `run_session` to `run_repl`, register UIBridge on Session. | M |
| `src/yoker/config/` | Optional new `[session]` config section. Move `tools.agent.max_recursion_depth` semantics to session. | S |
| `src/yoker/plugins/` | `load_configured_plugins` targets Session instead of Agent. Registration populates session-level registries. | M |
| New: `src/yoker/session/` | New module: `Session` class, `Message` dataclass, spawn logic, event aggregator, lifecycle. | L |
| Tests | New session tests; existing agent tests updated to not use recursion_depth/agents registry. | M |
| `docs/rationale.md` | Update "Recursive Composition" section to reflect real multi-agent support. | S |
| `analysis/mbi-003-python-api-design.md` | Update Layer 3 to reference the real Session. | S |

---

## 9. Recommendation

**Proceed with the Session concept.** It is architecturally sound, aligns
with Yoker's philosophy (transparency, library-first, true sub-agents), and
is a prerequisite for the MBI-003 Python API to deliver on its "workflow
primitives" promise.

### Sequencing

Introduce Session as **MBI-007**, sequenced **before MBI-003**:

- MBI-007 (Session) extracts orchestration from Agent and introduces the
  Session primitive.
- MBI-003 (Python API) builds its `yoker.session()`, `spawn()`, and event
  hooks on top of the real Session.

They can be specified in parallel (the MBI-003 design doc already sketches
the intended session surface), but MBI-007 should land first so that
MBI-003's Layer 3 is a facade over a real primitive rather than a facade
that has to invent one.

### Scope for MBI-007

In scope:
- `Session` class with lifecycle (async context manager).
- Agent registry moves to Session.
- Recursion depth moves to Session.
- Sub-agent spawning via `Session.spawn(name, prompt, timeout=...)`.
- Event aggregation (sub-agent events visible to session handlers).
- The `agent` built-in tool reworked to use Session.
- `run_session` in `__main__.py` reworked to construct a Session.
- Plugin loading targets Session.
- New session-level event types.
- Config: optional `[session]` section; recursion config moves.
- Tests for Session lifecycle, spawn, event aggregation, depth limits.
- Docs update (rationale, CLAUDE.md module structure).

Out of scope (defer to follow-up MBIs):
- Inter-agent streaming communication (request-response only in MBI-007).
- Shared context policy (`shared` mode) — only `fresh` and `fork` in
  MBI-007.
- Session persistence/resumption (one coherent session record) — keep
  per-agent context persistence as-is for MBI-007; full session
  persistence is a follow-up.
- Sub-sessions / hierarchical sessions.
- Backend connection pooling (Session shares backends, but no pool
  management in MBI-007).

---

## 10. Proposed MBI: MBI-007 — Session

### Goal

Introduce a `Session` construct that manages a team of agents: their
lifecycle (create, spawn, monitor, cancel), their registry, recursion
depth tracking, event aggregation, and inter-agent messaging. Reduce
`Agent` to a single-agent chat loop with no orchestration
responsibilities. Establish the primitive that MBI-003 (Python API) builds
its workflow layer on top of.

### Value

- **Unlocks true multi-agent workflows**: fan-out, pipelines, long-lived
  teams, inter-agent messaging — none of which are expressible today.
- **Cleans up `Agent`**: single responsibility, easier to test, easier to
  embed. The orchestration logic that does not belong in a single-agent
  primitive moves to where it belongs.
- **Makes sub-agents visible**: event aggregation means the UI and event
  recorders see the full multi-agent trace, not just the parent's view.
  This directly serves Yoker's transparency philosophy.
- **Prerequisite for MBI-003**: the `yoker.session()` workflow primitive
  becomes a facade over a real Session instead of a missing one.
- **Aligns with rationale**: the "Recursive Composition: True Sub-Agents"
  claim becomes fully real (addressing, persistence, event visibility,
  shared resources).

### Status: Ready

### Components

- [ ] RES: Finalise Session API surface (lifecycle, spawn, messaging,
      event aggregation, addressing) — owner decision on open questions in
      §7.
- [ ] DEV: Create `src/yoker/session/` module (`Session` class,
      `Message` dataclass, `spawn()`, event aggregator, lifecycle via
      `async with`).
- [ ] DEV: Move `AgentRegistry` ownership from `Agent` to `Session`;
      plugin loading targets Session.
- [ ] DEV: Move recursion depth tracking from `Agent` to `Session`.
- [ ] DEV: Rework `builtin/agent.py` to capture Session; `_create_subagent`
      and `_run_with_timeout` move to Session as `spawn()`.
- [ ] DEV: Add session-level event types (`SESSION_START/END`,
      `AGENT_SPAWNED/FINISHED`, `AGENT_MESSAGE`); extend `EventRecorder` to
      be session-scoped.
- [ ] DEV: Wire `UIBridge` to Session; add optional UIHandler methods for
      sub-agent events with no-op defaults.
- [ ] DEV: Rework `__main__.py`: construct Session in `main()`, rename
      `run_session` to `run_repl`, register bridge on Session.
- [ ] DEV: Add optional `[session]` config section; relocate
      `tools.agent.max_recursion_depth` semantics.
- [ ] DEV: Update `ToolContext` to carry a `session` reference so the
      agent tool (and future session-aware tools) can reach the Session.
- [ ] TEST: Session lifecycle (create, spawn, cancel, cleanup); recursion
      limits; event aggregation; inter-agent messaging; backward
      compatibility for single-agent use.
- [ ] DOCS: Update `docs/rationale.md` (Recursive Composition section),
      `CLAUDE.md` (module structure), `analysis/mbi-003-python-api-design.md`
      (Layer 3 references real Session).
- [ ] CHECK: `make check` green; existing examples unchanged in behaviour
      for single-agent use.

### Acceptance Criteria

- [ ] `Session` exists as an async context manager that owns an
      `AgentRegistry`, tracks recursion depth, and aggregates events from
      all agents it manages.
- [ ] `Agent` no longer holds `agents`, `recursion_depth`, or
      `max_recursion_depth`. Single-agent construction and `process()` work
      unchanged.
- [ ] `Session.spawn(name, prompt, timeout=...)` creates a child agent,
      runs it, and returns the response string. Recursion depth is
      enforced by the Session.
- [ ] Events emitted by spawned agents are visible to handlers registered
      on the Session (tagged with source agent name).
- [ ] The built-in `agent` tool works identically to today from the model's
      perspective (same parameters, same string return) but is implemented
      via `Session.spawn`.
- [ ] `python -m yoker` interactive mode works unchanged for the user;
      sub-agent activity is observable in the UI when aggregation is
      enabled.
- [ ] Existing examples (`library_usage.py`, `batch_mode.py`,
      `research_workflow.py`) continue to work without modification.
- [ ] `make check` green.
- [ ] New `examples/session_demo.py` demonstrates spawning multiple agents
      in one session.
- [ ] `docs/rationale.md` updated to reflect real multi-agent support.

### Dependencies

- MBI-006 (Multi-Provider Backend) should be complete or at least Phase 1
  complete, so that Session can share backends across agents regardless of
  provider. If MBI-006 is still in progress, Session can initially create
  per-agent backends (current behaviour) and share them later.

### Out of scope

- Inter-agent streaming communication (request-response only).
- Shared context policy beyond `fresh` and `fork`.
- Full session persistence/resumption (one coherent session record).
- Sub-sessions / hierarchical sessions.
- Backend connection pooling.

### Open design decisions needing owner input

The questions in §7 should be confirmed before implementation. The most
important ones:

1. Routed-through-Session messaging vs direct agent-to-agent (recommend
   routed).
2. `Agent.agents` removal: hard break or deprecation shim (recommend hard
   break, the field is small surface).
3. Session as async context manager vs explicit `start()/stop()` (recommend
   async context manager).
4. Event aggregation on by default vs opt-in (recommend on by default, with
   a config toggle).
5. Should `Session` own backends or should each Agent still create its own
   (recommend Session owns a factory and shares where possible; per-agent
   override creates a new one).