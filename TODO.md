# TODO

## Priority Overview

| Priority | MBI/Task | Status |
|----------|----------|--------|
| **P1** | MBI-007: Session | Complete (2026-07-06) |
| **P1** | MBI-006: Multi-Provider Backend (Phase 1) | Complete |
| **P1** | MBI-006 Phase 2: LitellmBackend | Complete |
| **P1** | MBI-002: Bootstrap | Complete |
| **P1** | MBI-001 Validation | Complete (v0.6.0 released to PyPI) |
| **P2** | MBI-003: Python API | Ready (unblocked — MBI-007 merged) |
| **P2** | MBI-004: yoker Commands | Backlog (after Python API) |
| **P2** | MBI-005: Assistant Integration | Backlog (showcase project) |
| **P3** | Maintenance Tasks | M.1-M.4 |
| **P3** | Maintenance Tasks | M.6 (done in MBI-006 Phase 1) |
| **P4+** | Launch Preparation, Architecture, Future Work | See sections below |

---

## Done: MBI-007: Session (2026-07-06)

**Goal:** Introduce a `Session` construct that manages a team of agents: lifecycle, registry, recursion depth, event aggregation, inter-agent messaging, and backend sharing. Reduce `Agent` to a single-agent chat loop. Establish the primitive that MBI-003 (Python API) builds on.

**Design source of truth:** `analysis/session-concept-analysis.md` (finalized, owner-approved — all 10 decisions in §7 resolved via PR #42; 4 round-1 clarifications in §7.3 + 5 round-2 clarifications in §7.4 resolved via PR #43).

**Milestone:** A real `Session` primitive lands in master; `Agent` is a single-agent chat loop; sub-agents are visible via event aggregation; MBI-003 unblocks.

**Status:** Design finalized (incl. PR #43 round-1 & round-2 clarifications). Detailed implementation task breakdown below (40 sub-tasks; `ListAgents` deferred per Clarification 6).

**Key PR #43 round-1 clarifications (see analysis §7.3):**
- **No backward-compat shims** — implement the final design only; no deprecation warnings, no proxy properties, no ignored args. Remove the old field/arg outright.
- **SpawnAgent tool** — the `agent` built-in tool becomes `SpawnAgent`, injected by the Session (closure-captured back-reference to Session). Session-injected, not Agent-registered.
- **Agent allowlist** — Session checks the requester's `AgentDefinition.agents` allowlist before spawning. Source of truth is the definition's allowlist, not a derived list.
- **SendMessage tool** — Session-injected tool enabling inter-agent messaging via tool calls. (`ListAgents` was recommended in round 1 but is deferred per round-2 Clarification 6.)

**Key PR #43 round-2 clarifications (see analysis §7.4):**
- **SpawnAgent returns the spawned agent's unique id** to the caller (Clarification 5). `Session.spawn()` returns a `SpawnResult(agent_id, response)`; the `SpawnAgent` tool renders both into the `ToolResult` so the model can read the spawned agent's id.
- **ListAgents deferred to a follow-up MBI** (Clarification 6). MBI-007 scope is the tree-like hierarchy (parent knows children via `SpawnAgent` return value). `ListAgents` enables swarm/team discovery, a separate use case. Task 7.8.7 is marked DEFERRED.
- **`finished` state dropped** (Clarification 7). Visible agent states are `{idle, running}` only. Finished agents are removed from the Session's active list. `AGENT_FINISHED` events still emitted as lifecycle signals.
- **BaseUIHandler NOT recreated** (Clarification 8). `agent_spawned` / `agent_finished` added directly to the `UIHandler` protocol as optional methods; the `UIBridge` guards calls with `hasattr` / `getattr`. No new `src/yoker/ui/base.py`.
- **SessionEvent envelope wrapper** (Clarification 9). Agent-id tagging uses a `SessionEvent(agent_id, event)` frozen envelope; no changes to existing frozen event dataclasses or their construction sites.

### Dependency Graph

```
7.6 (Config) ────────────────────────────┐
                                         ▼
7.1 (Session foundation) ──┬──► 7.3 (Registry migration) ──► 7.2 (Agent refactor)
                           │                                      │
                           ├──► 7.5 (Backend factory)            │
                           │                                      │
                           ├──► 7.7 (Event aggregation)          │
                           │                                      │
                           ├──► 7.4 (Inter-agent messaging) ◄───┘
                           │
                           └──► 7.8 (Integration) ◄── 7.2, 7.3, 7.4, 7.5, 7.7
                                 ├── 7.8.1 ToolContext.session
                                 ├── 7.8.2 Session.spawn() (returns SpawnResult)
                                 ├── 7.8.3 SpawnAgent tool (Session-injected)
                                 ├── 7.8.6 SendMessage tool (Session-injected)
                                 ├── 7.8.7 ListAgents tool — DEFERRED (Clarification 6)
                                 ├── 7.8.4 run_session → run_repl
                                 └── 7.8.5 Construct Session in main()
                                      │
                                      ▼
                                   7.9 (Tests/docs)
```

### Detailed Task Breakdown

---

#### 7.1 Session module foundation — Session class, async context manager, lifecycle

**Satisfies:** D1, D2, D3, D4, D10 (foundation)
**Depends on:** 7.6 (for SessionConfig defaults)

- [ ] **[MBI-007] 7.1.1 Create session package skeleton + Message dataclass**
  - Create `src/yoker/session/__init__.py` (exports: `Session`, `Message`)
  - Create `src/yoker/session/message.py` with `Message` frozen dataclass:
    `from: str`, `to: str`, `content: str`, `metadata: dict` (default `field(default_factory=dict)`)
    — plain-string content, no streaming (D3)
  - **Files:** `src/yoker/session/__init__.py` (new), `src/yoker/session/message.py` (new)
  - **Acceptance:**
    - `from yoker.session import Message` works
    - `Message(from="a", to="b", content="hello")` is frozen; `metadata` defaults to `{}`
    - Attempting to set an attribute on a Message instance raises `FrozenInstanceError`
  - **Satisfies:** D3
  - **Depends on:** —

- [ ] **[MBI-007] 7.1.2 Session class: async context manager + lifecycle**
  - Create `src/yoker/session/session.py` with `Session` class
  - Constructor: `Session(config: Config, *, session_id: str | None = None)`
  - Implements `__aenter__` / `__aexit__` (D4) — emits `SESSION_START` on enter,
    `SESSION_END` on exit; cancels outstanding agent tasks on exit
  - Uses `asyncio.TaskGroup` (Python 3.11+) for spawned agent task management
  - Stores: `self.config`, `self.id` (generated or from arg), `self._agents_map: dict[str, Agent]`
    (name→instance, D2), `self._agent_registry: AgentRegistry` (D10),
    `self._recursion_depths: dict[str, int]`, `self._event_handlers: list[EventCallback]`,
    `self._backends: dict[str, ModelBackend]` (for 7.5)
  - `add_event_handler(handler)` / `remove_event_handler(handler)` methods
    (replaces `agent.add_event_handler` for session-scoped consumers)
  - **Files:** `src/yoker/session/session.py` (new)
  - **Acceptance:**
    - `async with Session(config=Config()) as session:` enters and exits cleanly
    - `session.id` is a non-empty string
    - `session.add_event_handler` registers a handler that receives events
    - On `__aexit__`, outstanding spawned tasks are cancelled
  - **Satisfies:** D1, D4
  - **Depends on:** 7.6.1 (SessionConfig exists in Config), 7.7.1 (session event types for START/END)

- [ ] **[MBI-007] 7.1.3 Session ID management + name→agent map**
  - Session generates a unique session ID (UUID-based or config-derived) on construction
  - Replaces ad-hoc `f"{parent_session}_{uuid[:8]}"` derivation in `_create_subagent`
  - `session.spawn()` (implemented in 7.8.2) assigns derived session IDs to child agents
  - Name disambiguation: if two agents with same definition name are spawned, suffix with
    `-2`, `-3`, etc. (D2) — e.g. `researcher`, `researcher-2`
  - `session.get_agent(name: str) -> Agent | None` lookup method
  - **Files:** `src/yoker/session/session.py` (extend)
  - **Acceptance:**
    - `session.id` is unique per Session instance
    - Name disambiguation produces `researcher`, `researcher-2` for duplicate spawns
    - `session.get_agent("researcher")` returns the spawned agent instance
  - **Satisfies:** D2
  - **Depends on:** 7.1.2

---

#### 7.2 Agent class refactoring — remove orchestration from Agent, keep only chat loop

**Satisfies:** Agent becomes single-responsibility primitive
**Depends on:** 7.1 (Session exists), 7.3 (registry already moved to Session)

**PR #43 directive (Clarification 1 — no backward-compat shims):** implement the
final design only. No deprecation warnings, no proxy properties, no silently-ignored
constructor args. Remove the old fields/args outright; callers that pass them get
`TypeError` / `AttributeError`. This applies to `agent.agents`, `_recursion_depth`,
`recursion_depth`, `max_recursion_depth`, and the `run_session` name.

- [ ] **[MBI-007] 7.2.1 Remove `agents: AgentRegistry` from Agent**
  - Remove `self.agents = AgentRegistry()` from `Agent.__init__` (line 94 of `agent/__init__.py`)
  - Remove `_load_agents()` method (lines 414-423) — relocated to Session in 7.3.1
  - Remove the agent-tool registration block (lines 123-125) — Session injects `SpawnAgent`
    (7.8.3), Agent does not register it
  - Update `_resolve_agent_definition`: when a name lookup is needed, use the Session's
    registry (via `self._session.agents.resolve()`) or the explicit `agent_definition` /
    `agent_path` constructor args (which remain)
  - **No proxy property** — `agent.agents` raises `AttributeError` (no deprecation shim)
  - **Files:** `src/yoker/agent/__init__.py` (modify)
  - **Acceptance:**
    - `Agent()` no longer creates an `AgentRegistry`; `hasattr(agent, 'agents')` is False
    - Accessing `agent.agents` raises `AttributeError` (no compatibility shim)
    - Agent with explicit `agent_definition` param still resolves correctly
    - Agent constructed within a Session resolves definitions via `session.agents`
  - **Satisfies:** D10 (Agent loses registry), PR #43 Clarification 1
  - **Depends on:** 7.3.1 (Session owns registry), 7.3.4 (cleanup)

- [ ] **[MBI-007] 7.2.2 Remove `recursion_depth` and `max_recursion_depth` from Agent**
  - Remove `self.recursion_depth` and `self.max_recursion_depth` from `Agent.__init__`
  - Remove `_recursion_depth` constructor parameter (no shim — removed, not ignored)
  - Remove `validate_recursion_depth` import and call from `agent/_setup.py`
  - Move `validate_recursion_depth` logic to Session (or remove — Session tracks depth
    internally via `_recursion_depths` map)
  - **Files:** `src/yoker/agent/__init__.py` (modify), `src/yoker/agent/_setup.py` (modify)
  - **Acceptance:**
    - `Agent()` has no `recursion_depth` or `max_recursion_depth` attributes
    - `Agent(_recursion_depth=1)` raises `TypeError` (unexpected keyword arg) —
      no deprecation warning, no silent ignore (PR #43 Clarification 1)
    - `validate_recursion_depth` is no longer called in Agent init
  - **Satisfies:** D1 (depth tracking moves to Session), PR #43 Clarification 1
  - **Depends on:** 7.1.2 (Session tracks depth)

- [ ] **[MBI-007] 7.2.3 Agent receives optional session reference**
  - Add `session: Session | None = None` constructor parameter to `Agent.__init__`
  - Store as `self._session` for use by tools (via ToolContext in 7.8.1) and by
    event routing (events go to session aggregator when session is present)
  - When `self._session` is set, `agent.add_event_handler()` routes to session's
    aggregator instead of local handlers (or: session auto-registers as the agent's
    sole handler and fans out)
  - Single-agent use without Session: Agent maintains its own `_event_handlers` list
    — this is a first-class path (single-agent primitive), not a compatibility shim
  - **Files:** `src/yoker/agent/__init__.py` (modify)
  - **Acceptance:**
    - `Agent(session=session)` stores `self._session`
    - `Agent()` without session still works as a single-agent chat loop
    - Events emitted by Agent with session reach session's event handlers
  - **Satisfies:** D1, D5 (event routing to session)
  - **Depends on:** 7.1.2, 7.7.2 (event aggregator)

- [ ] **[MBI-007] 7.2.4 Adapt plugin loading for Session-aware Agent**
  - `load_configured_plugins(agent, config, cli_plugins)` currently populates
    `agent.tools`, `agent.skills`, `agent.agents` (in `plugins/loader.py`)
  - After 7.3 moves `agent.agents` to Session, plugin loading must split:
    - Agent definitions → `session.agents` (Session's AgentRegistry)
    - Tools and skills → remain per-agent (or session-shared; design says registries
      belong to the team for agents, but tools/skills are per-agent filtered by
      definition)
  - Refactor `load_configured_plugins` signature to accept a Session (for agent
    registration) and an Agent (for tools/skills), or split into two functions
  - Update `plugins/registration.py::register_agents` call site
  - **Files:** `src/yoker/plugins/loader.py` (modify), `src/yoker/plugins/registration.py`
    (modify if signature changes), `src/yoker/agent/__init__.py` (call site)
  - **Acceptance:**
    - Plugin agents appear in `session.agents`, not `agent.agents`
    - Plugin tools/skills still populate `agent.tools` / `agent.skills`
    - `--with <package>` CLI flag still works end-to-end
  - **Satisfies:** D10 (registry on Session), plugin interaction (§6.8)
  - **Depends on:** 7.3.1, 7.3.2

---

#### 7.3 AgentRegistry migration — move from Agent to Session

**Satisfies:** D10
**Depends on:** 7.1 (Session exists to receive the registry)

- [ ] **[MBI-007] 7.3.1 Session owns and populates AgentRegistry**
  - `Session.__init__` creates `self.agents: AgentRegistry = AgentRegistry()`
  - Relocate `Agent._load_agents()` logic to Session: load from
    `config.agents.directories` using `load_agent_definitions(directory)`
  - Session loads agent definitions before any Agent is constructed
  - **Files:** `src/yoker/session/session.py` (extend), `src/yoker/agent/__init__.py`
    (remove `_load_agents`)
  - **Acceptance:**
    - `session.agents` is an `AgentRegistry` populated from `config.agents.directories`
    - Agent no longer loads agents from directories
  - **Satisfies:** D10
  - **Depends on:** 7.1.2

- [ ] **[MBI-007] 7.3.2 Plugin agent registration targets Session**
  - In `load_configured_plugins`, the `register_agents(plugin.agents, agent.agents, ...)`
    call changes to target `session.agents`
  - The `yoker` builtin plugin's `agents_dir="agents"` loads built-in agent definitions
    into Session's registry
  - **Files:** `src/yoker/plugins/loader.py` (modify)
  - **Acceptance:**
    - Plugin agents (including built-in `yoker` agents) appear in `session.agents`
    - `session.agents.names` includes built-in agent names after plugin load
  - **Satisfies:** D10
  - **Depends on:** 7.3.1

- [ ] **[MBI-007] 7.3.3 Agent allowlist enforcement (source: AgentDefinition.agents)**
  - PR #43 Clarification 3: the Session checks the requesting agent's
    `AgentDefinition.agents` allowlist **before** spawning — the source of truth is
    the definition's allowlist, not a derived list on the Agent.
  - `AgentDefinition.agents` is the tuple of agent names this agent is allowed to
    spawn (existing field). Empty tuple means "no spawns allowed" (conservative
    default) — confirm and document the chosen semantic in implementation.
  - `Session.spawn(name, prompt, *, requester: Agent | None = None)` checks
    `requester.definition.agents` before resolving/spawning:
    - If `requester` is None (top-level spawn, e.g. from `main()`), skip the
      allowlist check — the top-level caller is trusted.
    - If `requester.definition.agents` is empty → reject with a clear error
      ("agent '{requester}' has no allowed spawns").
    - If `name` not in `requester.definition.agents` → reject with a clear error
      ("agent '{name}' not in '{requester}' allowlist").
  - Allowlist check happens **before** recursion-depth / `max_agents` checks —
    an allowlist violation is a permissions error, not a capacity error.
  - The existing `config.tools.agent.enabled` flag remains the global kill-switch;
    the per-agent allowlist is the finer-grained gate.
  - The `SpawnAgent` tool (7.8.3) bakes available names from
    `requester.definition.agents` (intersected with `session.agents.names`) into
    the tool description so the model only sees names it is allowed to spawn.
  - **Files:** `src/yoker/session/session.py` (extend `spawn()` signature and logic),
    `src/yoker/builtin/agent.py` (tool description reads allowlist)
  - **Acceptance:**
    - `session.spawn("researcher", prompt, requester=agent)` rejects when
      `"researcher"` is not in `agent.definition.agents`
    - Allowlist rejection takes precedence over depth/capacity rejection
    - Top-level spawn (no requester) bypasses the allowlist
    - `SpawnAgent` tool description lists only allowlisted names
  - **Satisfies:** PR #43 Clarification 3 (Agent allowlist enforcement)
  - **Depends on:** 7.3.1, 7.3.2

- [ ] **[MBI-007] 7.3.4 Remove `agent.agents` attribute entirely**
  - After all code paths are updated (7.2.1, 7.3.1-7.3.3), remove the `self.agents`
    field from Agent completely
  - Update `builtin/agent.py` (no longer reads `parent_agent.agents`)
  - Update any tests that reference `agent.agents`
  - **Files:** `src/yoker/agent/__init__.py` (final cleanup), `src/yoker/builtin/agent.py`
    (updated in 7.8.3), tests
  - **Acceptance:**
    - `agent.agents` raises `AttributeError`
    - No code in `src/` references `agent.agents` or `self.agents` on an Agent
  - **Satisfies:** D10
  - **Depends on:** 7.2.1, 7.3.1, 7.3.2, 7.8.3

---

#### 7.4 Inter-agent messaging — Message dataclass, routing through Session

**Satisfies:** D3
**Depends on:** 7.1 (Session + Message exist), 7.2 (Agent is single-responsibility)

- [ ] **[MBI-007] 7.4.1 Finalize Message dataclass (created in 7.1.1)**
  - Verify `Message` in `src/yoker/session/message.py` matches the design:
    `@dataclass(frozen=True) class Message: from: str; to: str; content: str; metadata: dict`
  - `content` is a plain string (the prompt) — no streaming (D3, §6.6)
  - Add `__all__` export and update `session/__init__.py`
  - **Files:** `src/yoker/session/message.py` (verify/finalize)
  - **Acceptance:**
    - `Message` is frozen, has exactly 4 fields, `metadata` defaults to `{}`
    - `from yoker.session import Message` works
  - **Satisfies:** D3
  - **Depends on:** 7.1.1

- [ ] **[MBI-007] 7.4.2 Session.send() routing method**
  - Implement `async def session.send(message: Message) -> str` on Session
  - Looks up target agent by `message.to` in `self._agents_map`
  - Calls `await target_agent.process(message.content)`
  - Emits `AGENT_MESSAGE` event (from 7.7.1) with the Message before processing
  - Request-response only: returns the target agent's response string (D3, §6.6)
  - Error handling: if target agent not found, raises `ValueError`; if target agent
    raises, catch and return error string (preserving current `agent` tool behaviour)
  - **Files:** `src/yoker/session/session.py` (extend)
  - **Acceptance:**
    - `await session.send(Message(from="coordinator", to="researcher", content="find X"))`
      calls `researcher.process("find X")` and returns the response
    - `AGENT_MESSAGE` event is emitted to session handlers
    - Sending to unknown name raises `ValueError`
  - **Satisfies:** D3, D6.2 (routing through Session)
  - **Depends on:** 7.1.2, 7.1.3, 7.7.1 (AGENT_MESSAGE event type)

- [ ] **[MBI-007] 7.4.3 Agent addressing: unique ID generation**
  - `Session._generate_agent_name(definition_name: str) -> str` — checks
    `self._agents_map` for existing names; if taken, appends `-2`, `-3`, etc. (D2)
  - Called by `session.spawn()` (7.8.2) when registering a new agent
  - The generated name is the agent's unique address within the session
  - **Files:** `src/yoker/session/session.py` (extend)
  - **Acceptance:**
    - First spawn of "researcher" → name "researcher"
    - Second spawn of "researcher" → name "researcher-2"
    - Names are unique within a session
  - **Satisfies:** D2
  - **Depends on:** 7.1.3

---

#### 7.5 Backend factory and sharing — Session owns backends, shares across same-provider agents

**Satisfies:** D9
**Depends on:** 7.1 (Session exists)

- [ ] **[MBI-007] 7.5.1 Session backend factory**
  - Session owns `self._backends: dict[str, ModelBackend]` keyed by provider config hash
    (or `(provider, model, base_url, api_key)` tuple)
  - `session.get_backend(config: Config) -> ModelBackend`:
    - Computes a cache key from the active provider config
    - Returns existing backend if key matches (shared across same-provider agents — D9)
    - Creates new backend via `create_backend(config)` if no match
  - Per-agent model/provider override: when `agent_definition.model` differs, Session
    uses `with_model()` helper (from MBI-006 Phase 1) to create a derived config and
    a fresh backend for that agent
  - **Files:** `src/yoker/session/session.py` (extend), `src/yoker/backends/factory.py`
    (no change — `create_backend` already exists)
  - **Acceptance:**
    - Two agents with the same provider config share the same `ModelBackend` instance
    - An agent with a model override gets a fresh backend instance
    - `session.get_backend(config)` is idempotent for same config
  - **Satisfies:** D9
  - **Depends on:** 7.1.2

- [ ] **[MBI-007] 7.5.2 Agent receives backend from Session**
  - When an Agent is constructed via Session (spawn or primary agent), Session passes
    the shared/fresh backend via the existing `backend=` constructor parameter
  - Agent no longer calls `create_backend(self.config)` directly when a Session is
    present — it receives the backend from Session
  - Single-agent use without Session: Agent still calls `create_backend(self.config)`
    (backward compatible)
  - **Files:** `src/yoker/agent/__init__.py` (modify — use session backend when available),
    `src/yoker/session/session.py` (pass backend when spawning)
  - **Acceptance:**
    - Agent constructed via Session uses the Session-provided backend
    - Agent constructed without Session creates its own backend (unchanged)
    - `agent._backend` is set in both cases
  - **Satisfies:** D9
  - **Depends on:** 7.5.1, 7.2.3 (session reference on Agent)

---

#### 7.6 Config `[session]` section — SessionConfig dataclass, validation

**Satisfies:** D7
**Depends on:** — (foundational, no dependencies)

- [ ] **[MBI-007] 7.6.1 Add SessionConfig dataclass**
  - Add to `src/yoker/config/__init__.py`:
    ```python
    @dataclass(frozen=True)
    class SessionConfig:
      max_agents: int = 10
      default_isolation_policy: str = "fresh"
      event_aggregation: bool = True
    ```
  - Validation in `__post_init__`:
    - `max_agents` must be positive (`validate_positive_int`)
    - `default_isolation_policy` must be in `("fresh", "fork")` (`validate_choice`)
  - **Files:** `src/yoker/config/__init__.py` (modify)
  - **Acceptance:**
    - `SessionConfig()` yields `max_agents=10`, `default_isolation_policy="fresh"`,
      `event_aggregation=True`
    - `SessionConfig(max_agents=0)` raises `ValidationError`
    - `SessionConfig(default_isolation_policy="shared")` raises `ValidationError`
  - **Satisfies:** D7
  - **Depends on:** —

- [ ] **[MBI-007] 7.6.2 Add `session` field to Config + CLI args**
  - Add `session: SessionConfig = field(default_factory=SessionConfig)` to the `Config`
    dataclass (after `ui` field or in logical position)
  - Add `SessionConfig` to `__all__` exports
  - Verify Clevis auto-generates `--session-max-agents`, `--session-default-isolation-policy`,
    `--session-event-aggregation` CLI args
  - Verify old TOML files without `[session]` section still load (strict superset —
    defaults fill in)
  - Verify `render_config_toml` omits `[session]` when all values are defaults (or
    includes it — consistent with existing writer behaviour)
  - **Files:** `src/yoker/config/__init__.py` (modify)
  - **Acceptance:**
    - `Config().session` is a `SessionConfig` with defaults
    - `--session-max-agents 5` CLI arg works
    - Existing `~/.yoker.toml` files load unchanged (no migration needed)
  - **Satisfies:** D7
  - **Depends on:** 7.6.1

- [ ] **[MBI-007] 7.6.3 Relocate recursion depth config semantics**
  - `config.tools.agent.max_recursion_depth` (currently on `AgentToolConfig`) remains
    in config but is now read by Session instead of Agent
  - Session reads `config.tools.agent.max_recursion_depth` as the session-level
    recursion limit
  - `config.tools.agent.timeout_seconds` remains on AgentToolConfig (used by the
    agent tool wrapper in 7.8.3)
  - Keep backward compatibility: the config field stays in the same location; only
    the consumer changes (Agent → Session)
  - **Files:** `src/yoker/config/__init__.py` (no change to field location),
    `src/yoker/session/session.py` (read from config)
  - **Acceptance:**
    - Session reads `config.tools.agent.max_recursion_depth` for depth enforcement
    - Old TOML files with `[tools.agent] max_recursion_depth = 3` still work
  - **Satisfies:** D7
  - **Depends on:** 7.6.2

---

#### 7.7 Event aggregation — Session-level event fan-out, UIBridge changes, UIHandler changes

**Satisfies:** D5
**Depends on:** 7.1 (Session exists)

- [ ] **[MBI-007] 7.7.1 New session-level event types**
  - Add to `EventType` enum in `src/yoker/events/types.py`:
    `SESSION_START`, `SESSION_END`, `AGENT_SPAWNED`, `AGENT_FINISHED`, `AGENT_MESSAGE`
  - Create event dataclasses:
    - `SessionStartEvent(type, timestamp, session_id: str)`
    - `SessionEndEvent(type, timestamp, session_id: str)`
    - `AgentSpawnedEvent(type, timestamp, agent_name: str, agent_id: str, parent_id: str | None)`
    - `AgentFinishedEvent(type, timestamp, agent_name: str, agent_id: str)`
    - `AgentMessageEvent(type, timestamp, message: Message)` (or from/to/content fields)
  - Update `serialize_event` / `deserialize_event` in `events/recorder.py` for new types
  - Update `events/__init__.py` exports
  - **Files:** `src/yoker/events/types.py` (modify), `src/yoker/events/recorder.py`
    (modify), `src/yoker/events/__init__.py` (modify)
  - **Acceptance:**
    - New EventType members exist
    - New event dataclasses are frozen, serializable, and deserializable
    - `from yoker.events import SessionStartEvent, AgentSpawnedEvent` works
  - **Satisfies:** D5 (event infrastructure)
  - **Depends on:** 7.1.1 (Message dataclass for AgentMessageEvent)

- [ ] **[MBI-007] 7.7.2 Session event aggregator (SessionEvent envelope, fan-out with agent_id tagging)**
  - Session collects events from all agents it manages and re-emits them to
    session-level handlers, tagged with the source agent's name/ID (D5)
  - **PR #43 Clarification 9 — `SessionEvent` envelope wrapper:** tagging is
    done by wrapping each agent event in a frozen
    `SessionEvent(agent_id: str, event: Event)` dataclass. **No changes to
    existing frozen event dataclasses** (`TurnStartEvent`,
    `ContentChunkEvent`, etc.) and no changes to their construction sites in
    `agent/_processing.py`.
  - Create `SessionEvent` in `src/yoker/events/session_event.py` (or
    `src/yoker/session/events.py`):
    ```python
    @dataclass(frozen=True)
    class SessionEvent:
        agent_id: str
        event: Event
    ```
  - When Session spawns an agent (7.8.2), it registers an internal forwarding
    handler on the agent that:
    - Wraps each emitted `Event` in `SessionEvent(agent_id=<agent's runtime name>, event=<original>)`
    - Forwards the wrapped `SessionEvent` to `session._event_handlers`
  - Emits `AGENT_SPAWNED` when an agent is spawned, `AGENT_FINISHED` when it
    completes. **PR #43 Clarification 7:** on `AGENT_FINISHED`, the agent is
    **removed from `session._agents_map`** — there is no `finished` state;
    visible agent states are `{idle, running}` only.
  - When `config.session.event_aggregation` is False, sub-agent events are NOT
    forwarded (preserves current quiet behaviour as opt-out)
  - **Files:** `src/yoker/session/session.py` (extend), new
    `SessionEvent` dataclass module (new)
  - **Acceptance:**
    - Events from spawned agents reach session-level handlers wrapped in
      `SessionEvent` carrying the source `agent_id`
    - The inner `Event` is dispatched unchanged (no modifications to existing
      event dataclasses)
    - `AGENT_SPAWNED` / `AGENT_FINISHED` events are emitted at lifecycle boundaries
    - Finished agents are removed from `session._agents_map` (no `finished` state)
    - When `event_aggregation=False`, sub-agent events do not reach session handlers
  - **Satisfies:** D5, PR #43 Clarifications 7 & 9
  - **Depends on:** 7.1.2, 7.7.1

- [ ] **[MBI-007] 7.7.3 UIBridge registered on Session + handles new events + SessionEvent envelope**
  - `UIBridge.__call__` handles both wrapped (`SessionEvent`) and unwrapped
    (bare `Event`) incoming events (PR #43 Clarification 9):
    - If the incoming event is a `SessionEvent`: unpack it — use `agent_id`
      for tagging/display, dispatch the inner `event` to the existing
      `UIHandler` method unchanged.
    - If the incoming event is a bare `Event` (single-agent path): dispatch
      as today with no `agent_id` tag.
  - `UIBridge.__call__` handles new session-level event types:
    - `SESSION_START` / `SESSION_END` → no UI action (UI start/shutdown called directly)
    - `AGENT_SPAWNED` → call `self.ui.agent_spawned(name)` if the handler
      implements it (guard with `hasattr` / `getattr` — PR #43 Clarification 8)
    - `AGENT_FINISHED` → call `self.ui.agent_finished(name)` if the handler
      implements it (same guard)
    - `AGENT_MESSAGE` → optional display (or no-op for now)
  - Existing event methods receive the inner event; the `agent_id` from the
    envelope is available for tagging in the UI display
  - Registration moves from `agent.add_event_handler(bridge)` to
    `session.add_event_handler(bridge)` in `__main__.py` (7.8.5)
  - **Files:** `src/yoker/ui/bridge.py` (modify)
  - **Acceptance:**
    - UIBridge unpacks `SessionEvent` envelopes and dispatches the inner event
    - UIBridge handles bare `Event` (single-agent path) unchanged
    - UIBridge handles `AGENT_SPAWNED` by calling `ui.agent_spawned(name)` when
      the method exists on the handler
    - UIBridge handles `AGENT_FINISHED` by calling `ui.agent_finished(name)` when
      the method exists on the handler
    - Handlers that do not implement `agent_spawned` / `agent_finished` are not
      broken (no `AttributeError`)
  - **Satisfies:** D5, PR #43 Clarifications 8 & 9
  - **Depends on:** 7.7.1, 7.7.2, 7.7.4

- [ ] **[MBI-007] 7.7.4 UIHandler new optional methods (no BaseUIHandler recreation)**
  - **PR #43 Clarification 8 — do NOT recreate `BaseUIHandler`.** The
    `agent_spawned` / `agent_finished` methods are added **directly to the
    `UIHandler` protocol** as optional methods (documented, not enforced —
    Python `Protocol` structural typing). No new `src/yoker/ui/base.py` file
    is created; `InteractiveUIHandler` and `BatchUIHandler` do **not** inherit
    from a new `BaseUIHandler`.
  - Document `agent_spawned(name: str) -> None` and
    `agent_finished(name: str) -> None` as optional protocol methods in
    `src/yoker/ui/handler.py` (the protocol already has optional methods; this
    is consistent).
  - `InteractiveUIHandler` implements `agent_spawned(name)`: prints
    "Agent spawned: {name}" (or a styled indicator).
  - `InteractiveUIHandler` implements `agent_finished(name)`: prints
    "Agent finished: {name}".
  - `BatchUIHandler`: does **not** implement the methods (sub-agent activity
    not shown in batch mode). The `UIBridge` guards calls with
    `hasattr(handler, 'agent_spawned')` / `getattr(..., None)` before invoking,
    so handlers that omit the methods are unaffected.
  - The `UIBridge` is the sole caller of these methods; the guard lives in
    task 7.7.3.
  - **Files:** `src/yoker/ui/handler.py` (modify — document optional methods),
    `src/yoker/ui/interactive.py` (modify — implement the methods),
    `src/yoker/ui/batch.py` (no change — does not implement the optional methods)
  - **Acceptance:**
    - `UIHandler` protocol documents `agent_spawned` / `agent_finished` as
      optional methods
    - No `src/yoker/ui/base.py` file is created
    - `InteractiveUIHandler` implements `agent_spawned` / `agent_finished`
    - `BatchUIHandler` does not implement them and is not broken (the UIBridge
      guards calls)
    - No `BaseUIHandler` class is introduced anywhere in the codebase
  - **Satisfies:** D5, PR #43 Clarification 8
  - **Depends on:** 7.7.3 (UIBridge guard)

- [ ] **[MBI-007] 7.7.5 EventRecorder session-scoped**
  - `EventRecorder` registered on Session (via `session.add_event_handler(recorder)`)
    instead of on individual agents
  - Captures all agents' events (wrapped in `SessionEvent` envelopes — PR #43
    Clarification 9) in one coherent JSONL trace
  - `serialize_event` handles `SessionEvent` envelopes: serializes the
    `agent_id` alongside the inner event's serialized form
  - Produces one replay file per session that captures the entire multi-agent trace
  - **Files:** `src/yoker/events/recorder.py` (modify — SessionEvent-aware
    serialize/deserialize), `src/yoker/session/session.py` (recorder
    registration site)
  - **Acceptance:**
    - `EventRecorder` on Session captures sub-agent events (wrapped in
      `SessionEvent`)
    - Serialized events include `agent_id` from the envelope
    - One JSONL file contains the full session trace
  - **Satisfies:** D5, §6.9 (session persistence foundation), PR #43 Clarification 9
  - **Depends on:** 7.7.2

---

#### 7.8 Integration: __main__.py, Session-injected tools (SpawnAgent, SendMessage), ToolContext

**Satisfies:** D6, D8, PR #43 Clarifications 2, 4, 5 & 6
**Depends on:** 7.1-7.7 (all core work)

**PR #43 note (Clarifications 2, 4 & 6):** the `agent` built-in tool becomes
`SpawnAgent`, a **Session-injected** tool (the Session holds a back-reference to
itself and registers the tool on Agents it owns). `SendMessage` is also
Session-injected. `ListAgents` is **deferred** to a follow-up MBI (PR #43
Clarification 6) and is not part of MBI-007. Session-injected tools are **not**
registered by the Agent itself and are not part of the Agent's static tool set.

- [ ] **[MBI-007] 7.8.1 ToolContext gains session reference**
  - Add `session: Session | None = None` field to `ToolContext` dataclass in
    `src/yoker/tools/context.py` (D8)
  - Update `_build_tool_context()` in `agent/_processing.py` (line 573-595) to pass
    `session=agent._session` when building the context
  - Load-bearing for `SendMessage` (PR #43 Clarification 4; `ListAgents` is
    deferred per Clarification 6); `SpawnAgent` may use closure capture
    instead (implementation choice)
  - **Files:** `src/yoker/tools/context.py` (modify), `src/yoker/agent/_processing.py`
    (modify)
  - **Acceptance:**
    - `ToolContext` has a `session` field (default `None`)
    - Tools with `ctx: ToolContext` parameter receive `ctx.session` when running
      within a Session
    - Single-agent use without Session: `ctx.session` is `None`
  - **Satisfies:** D8, PR #43 Clarification 4
  - **Depends on:** 7.2.3 (Agent has `_session`)

- [ ] **[MBI-007] 7.8.2 Session.spawn() canonical API (returns SpawnResult)**
  - Implement `async def session.spawn(name: str, prompt: str, timeout: int = 300,
    *, requester: Agent | None = None) -> SpawnResult` (D8, PR #43
    Clarifications 3 & 5)
  - **PR #43 Clarification 5 — return both agent id and response.** Define a
    frozen `SpawnResult(agent_id: str, response: str)` dataclass in
    `src/yoker/session/spawn_result.py` (or in `session.py`). `Session.spawn()`
    returns `SpawnResult` instead of a bare string. The `SpawnAgent` tool
    (7.8.3) renders both fields into its `ToolResult` so the model can read
    the spawned agent's id and the response.
  - On error / timeout / allowlist rejection: return
    `SpawnResult(agent_id="", response=<error string>)` (or raise —
    implementation choice; the tool layer wraps either into a
    `ToolResult(success=False, ...)`). Preserve the current `agent` tool's
    "return error string, do not raise" behaviour at the tool boundary.
  - Relocate `_create_subagent` logic from `src/yoker/builtin/agent.py` into Session:
    - **Allowlist check (PR #43 Clarification 3):** if `requester` is not None, check
      `name in requester.definition.agents` *before* resolving/spawning; reject with
      a clear error if not allowed. Top-level spawn (`requester=None`) bypasses the
      check.
    - Resolve agent definition from `session.agents.resolve(name)`
    - Generate unique agent ID via `_generate_agent_name()` (7.4.3)
    - Create child `Agent` with: session reference, shared/fresh backend (7.5),
      agent definition, derived config (model override via `with_model` if needed)
    - Register agent in `self._agents_map` with unique ID (state `idle`)
    - Track recursion depth (`self._recursion_depths[agent_id] = parent_depth + 1`)
    - Enforce `max_recursion_depth` and `max_agents` limits (after allowlist check)
    - **Inject Session tools** (PR #43 Clarifications 2 & 4): register `SpawnAgent`
      and `SendMessage` on the child Agent (Session-injected, capture Session via
      closure). **`ListAgents` is NOT injected** — deferred per PR #43
      Clarification 6. The Agent does not register these itself.
    - Register session's event aggregator on the child agent (7.7.2)
    - Emit `AGENT_SPAWNED` event
  - Relocate `_run_with_timeout` logic: `asyncio.wait_for(agent.process(prompt), timeout)`
    wrapped in the Session's `TaskGroup`
  - On completion: emit `AGENT_FINISHED`, **remove the agent from
    `self._agents_map`** (PR #43 Clarification 7 — no `finished` state; the
    agent is removed from the active list)
  - On timeout: return error string in `SpawnResult` (preserving current agent
    tool behaviour)
  - On exception: catch, log, return error string in `SpawnResult` (preserving
    current behaviour)
  - Returns `SpawnResult(agent_id=<spawned id>, response=<response string>)`
  - **Files:** `src/yoker/session/session.py` (extend),
    `src/yoker/session/spawn_result.py` (new — `SpawnResult` dataclass),
    `src/yoker/builtin/agent.py` (logic removed — `agent` tool replaced by
    `SpawnAgent` in 7.8.3)
  - **Acceptance:**
    - `await session.spawn("researcher", "analyze this")` returns a
      `SpawnResult` with `agent_id="researcher"` and the response string
    - `session.spawn("researcher", prompt, requester=agent)` rejects when
      `"researcher"` not in `agent.definition.agents` (allowlist first)
    - `AGENT_SPAWNED` and `AGENT_FINISHED` events are emitted
    - After completion, the spawned agent is removed from
      `session._agents_map` (no `finished` state)
    - Recursion depth is enforced (spawn beyond `max_recursion_depth` returns error)
    - `max_agents` limit enforced (spawn beyond cap returns error)
    - Timeout returns an error string in `SpawnResult`, not an exception
    - Spawned Agent has `SpawnAgent` and `SendMessage` tools registered
      (Session-injected); **no `ListAgents` tool** (deferred)
  - **Satisfies:** D8, D1 (Session as coordinator), PR #43 Clarifications 2, 3, 5, 6, 7
  - **Depends on:** 7.1.2, 7.1.3, 7.3.1, 7.3.3, 7.5.1, 7.7.2, 7.8.3, 7.8.6

- [ ] **[MBI-007] 7.8.3 SpawnAgent tool (Session-injected, replaces `agent` tool, returns spawned id)**
  - PR #43 Clarification 2: the `agent` built-in tool becomes `SpawnAgent`,
    Session-injected.
  - **PR #43 Clarification 5 — return the spawned agent's id to the caller.**
    The tool's `ToolResult` carries both the spawned agent's unique id and
    the response string so the model can address the spawned agent later via
    `SendMessage`.
  - Create `make_spawn_agent_tool(session)` (replaces `make_agent_tool(parent_agent)`)
    — the Session captures itself in the closure (back-reference), so the tool does
    not need `ctx.session` (implementation choice; closure capture matches the
    existing `parent_agent` pattern).
  - The tool function signature (model-facing):
    `SpawnAgent(agent_name: str, prompt: str, timeout_seconds: int = 300) -> ToolResult`
  - Internally: calls `await session.spawn(agent_name, prompt, timeout_seconds,
    requester=<calling agent>)` which returns a `SpawnResult(agent_id, response)`
    (7.8.2). Wraps this into a `ToolResult`:
    - On success: `ToolResult(success=True, result=<rendered>)` where `<rendered>`
      includes both the spawned agent's id and the response (e.g.
      `"agent_id: researcher-2\n\n{response}"` — exact rendering is an
      implementation detail; the contract is "the model can read the spawned
      agent's id from the result").
    - On failure (allowlist rejection, timeout, depth/capacity error, agent
      exception): `ToolResult(success=False, error=<error string>)` — preserving
      the current `agent` tool's "do not raise" contract.
  - The calling agent is passed as `requester` so the allowlist check (PR #43
    Clarification 3) fires — the tool must capture or receive the calling Agent
    (e.g. via `ctx` with the agent identity, or by capturing the agent at injection
    time since Session-injected tools are per-Agent).
  - Available agent names baked into the tool description come from
    `requester.definition.agents` (intersected with `session.agents.names`) —
    only allowlisted names are shown to the model.
  - Remove `_create_subagent`, `_run_with_timeout`, `_clamp` from `builtin/agent.py`
    (moved to Session in 7.8.2).
  - Rename the tool module/file from `builtin/agent.py` to `builtin/spawn_agent.py`
    (or keep filename, rename the tool factory + tool name) — implementation choice.
  - **Files:** `src/yoker/builtin/agent.py` (rewrite/rename), `src/yoker/builtin/__init__.py`
    (update manifest: `agent` tool becomes `SpawnAgent`)
  - **Acceptance:**
    - The `SpawnAgent` tool is registered on Agents by the Session, not by the Agent
    - `SpawnAgent` has the same effective parameters as the old `agent` tool
    - On success, the `ToolResult.result` contains **both** the spawned agent's
      unique id and the response string (the model can read the spawned id)
    - On failure, the `ToolResult` has `success=False` and an error string (no
      exception raised)
    - Internally calls `session.spawn(...)` with `requester` set
    - Tool description lists only allowlisted agent names
    - `_create_subagent` and `_run_with_timeout` no longer exist in `builtin/agent.py`
  - **Satisfies:** PR #43 Clarifications 2 & 5 (SpawnAgent, Session-injected, returns id)
  - **Depends on:** 7.8.1, 7.8.2

- [ ] **[MBI-007] 7.8.6 SendMessage tool (Session-injected)**
  - PR #43 Clarification 4: `SendMessage` is a tool available to agents when in a
    Session, injected by the Session (same injection mechanism as `SpawnAgent`).
    Enables inter-agent messaging via tool calls, not just via the
    `session.send(...)` Python API.
  - Create `make_send_message_tool(session)` — Session captures itself in the
    closure. The tool may also read `ctx.session` (7.8.1) — implementation choice;
    pick one and be consistent across the three Session-injected tools.
  - Tool signature (model-facing):
    `SendMessage(to: str, message: str) -> ToolResult`
  - Internally: builds a `Message(from=<calling agent name>, to=to, content=message)`
    and calls `await session.send(message)` (7.4.2); wraps the response string in
    `ToolResult(success=True, result=response)`.
  - `from` is the calling agent's runtime name (Decision 2 — the unique ID assigned
    by Session). The tool must know which agent it was injected into; capture the
    agent at injection time (Session-injected tools are per-Agent).
  - Error handling: unknown target → `ToolResult(success=False, error=...)` (not
    an exception — preserves tool-call contract).
  - The tool description should explain that `to` must be an active agent name
    — the caller knows its spawned children's ids from `SpawnAgent`'s return
    value (PR #43 Clarification 5). (`ListAgents` is deferred per Clarification
    6 and is not available in MBI-007.)
  - **Files:** `src/yoker/builtin/send_message.py` (new), `src/yoker/builtin/__init__.py`
    (extend manifest — `SendMessage` is Session-injected, not auto-registered)
  - **Acceptance:**
    - `SendMessage` tool is registered on Agents by the Session, not by the Agent
    - `SendMessage(to="researcher", message="hi")` calls `session.send(...)` and
      returns the target agent's response string
    - Unknown target returns a `ToolResult` with `success=False` (no exception)
    - `from` field of the Message is the calling agent's runtime name
  - **Satisfies:** PR #43 Clarification 4 (SendMessage, Session-injected)
  - **Depends on:** 7.4.2 (session.send), 7.8.1 (ToolContext.session, if used)

- [ ] ~~**[MBI-007] 7.8.7 ListAgents tool~~ — **DEFERRED to a follow-up MBI
  (PR #43 Clarification 6)**
  - PR #43 Clarification 6: `ListAgents` is **deferred** out of MBI-007. The
    owner framed `ListAgents` as enabling a swarm/team-based discovery model
    (any agent can find any other active agent), which is a separate use case
    from MBI-007's tree-like hierarchy scope. A parent knows its children
    directly via the id returned by `SpawnAgent` (PR #43 Clarification 5); no
    discovery tool is needed for the tree-hierarchy case.
  - The §7.3 Clarification 4 recommendation to include `ListAgents` in
    MBI-007 is **superseded** by this clarification.
  - **Not implemented in MBI-007.** No `ListAgents` tool is created; no
    `src/yoker/builtin/list_agents.py` file is created; the Session does not
    inject `ListAgents` onto Agents. Task 7.8.5, 7.8.2, and 7.9.6 do not
    reference `ListAgents`.
  - **Follow-up MBI scope (deferred):** `ListAgents` as a Session-injected
    tool returning `(name, status)` for active agents; revisit agent status
    semantics (the `{idle, running}` states from Clarification 7 are
    sufficient for active agents — finished agents are removed, so
    `ListAgents` would return only active agents). The follow-up MBI should
    also revisit swarm discovery scope (visibility of agents the caller did
    not spawn) and naming authority.
  - **Satisfies:** PR #43 Clarification 6 (ListAgents deferred)
  - **Depends on:** — (not part of MBI-007)

- [ ] **[MBI-007] 7.8.4 Rename run_session() to run_repl()**
  - Rename `run_session` function to `run_repl` in `src/yoker/__main__.py` (D6)
  - PR #43 Clarification 1: no alias / no shim — the old name is removed, not kept
    as a deprecated alias.
  - `run_repl` operates inside a Session — signature changes to accept Session
    (or the agent/session pair)
  - Update the call site in `main()`
  - Update any imports/references to `run_session` in tests or examples
  - **Files:** `src/yoker/__main__.py` (modify)
  - **Acceptance:**
    - `run_repl` function exists; `run_session` does not (no alias)
    - No references to `run_session` remain in `src/` or `tests/`
  - **Satisfies:** D6, PR #43 Clarification 1
  - **Depends on:** —

- [ ] **[MBI-007] 7.8.5 Construct Session in main() + wire UIBridge on Session**
  - In `main()`: after config is loaded and bootstrap completes, construct a `Session`:
    `async with Session(config=agent.config) as session:`
  - Create the primary Agent within the session: `Agent(config=..., session=session, ...)`
  - The Session injects `SpawnAgent` and `SendMessage` onto the primary
    Agent (PR #43 Clarifications 2 & 4; `ListAgents` is deferred per
    Clarification 6)
  - Register `UIBridge` on Session: `session.add_event_handler(bridge)` (not on Agent)
  - Plugin loading targets Session for agent registry (7.2.4)
  - Call `run_repl(session, agent, ui, commands)` inside the `async with` block
  - The user-visible behaviour of `python -m yoker` is unchanged
  - **Files:** `src/yoker/__main__.py` (modify — main restructure)
  - **Acceptance:**
    - `python -m yoker` interactive mode works unchanged for the user
    - Session is constructed in `main()`; UIBridge is registered on Session
    - Primary Agent has `SpawnAgent` and `SendMessage` tools (Session-injected);
      no `ListAgents` tool (deferred)
    - Sub-agent activity is visible in the UI when `event_aggregation=True`
  - **Satisfies:** D6, D5 (UIBridge on Session), PR #43 Clarifications 2, 4 & 6
  - **Depends on:** 7.1.2, 7.2.3, 7.2.4, 7.7.3, 7.8.2, 7.8.3, 7.8.4, 7.8.6

---

#### 7.9 Tests, docs, verification

**Depends on:** 7.1-7.8

- [ ] **[MBI-007] 7.9.1 Session lifecycle tests**
  - Test `async with Session(config=...) as session:` enter/exit
  - Test cleanup on normal exit (outstanding tasks cancelled)
  - Test cleanup on exception exit
  - Test `max_agents` limit enforcement
  - Test `session.id` is unique per instance
  - **Files:** `tests/test_session/test_lifecycle.py` (new)
  - **Acceptance:** All lifecycle tests pass
  - **Depends on:** 7.1, 7.6

- [ ] **[MBI-007] 7.9.2 Spawn and recursion tests**
  - Test `session.spawn()` returns response string
  - Test recursion depth enforcement (spawn beyond limit returns error)
  - Test timeout enforcement
  - Test agent name disambiguation (researcher, researcher-2)
  - Test agent definition resolution via `session.agents`
  - Test **allowlist enforcement** (PR #43 Clarification 3):
    - `session.spawn("x", prompt, requester=agent)` rejects when
      `"x"` not in `agent.definition.agents`
    - Top-level spawn (`requester=None`) bypasses the allowlist
    - Allowlist rejection takes precedence over depth/capacity rejection
  - **Files:** `tests/test_session/test_spawn.py` (new)
  - **Acceptance:** All spawn tests pass
  - **Depends on:** 7.8.2

- [ ] **[MBI-007] 7.9.3 Event aggregation tests**
  - Test events from spawned agents reach session-level handlers wrapped in
    `SessionEvent` envelopes (PR #43 Clarification 9)
  - Test the inner `Event` inside a `SessionEvent` is dispatched unchanged
    (no modifications to existing event dataclasses)
  - Test `agent_id` from the envelope is available to handlers
  - Test `AGENT_SPAWNED` / `AGENT_FINISHED` events emitted
  - Test finished agents are **removed from `session._agents_map`** (no
    `finished` state — PR #43 Clarification 7)
  - Test `event_aggregation=False` suppresses sub-agent events
  - Test `EventRecorder` on Session captures full multi-agent trace (with
    `agent_id` from envelopes)
  - **Files:** `tests/test_session/test_events.py` (new)
  - **Acceptance:** All event aggregation tests pass
  - **Depends on:** 7.7

- [ ] **[MBI-007] 7.9.4 Inter-agent messaging tests**
  - Test `session.send(Message(...))` routes to target agent
  - Test request-response pattern returns response string
  - Test `AGENT_MESSAGE` event emitted
  - Test sending to unknown agent raises `ValueError`
  - **Files:** `tests/test_session/test_messaging.py` (new)
  - **Acceptance:** All messaging tests pass
  - **Depends on:** 7.4

- [ ] **[MBI-007] 7.9.5 Backend sharing tests**
  - Test two agents with same provider config share the same `ModelBackend` instance
  - Test per-agent model override creates a fresh backend
  - Test `session.get_backend()` is idempotent for same config
  - **Files:** `tests/test_session/test_backends.py` (new)
  - **Acceptance:** All backend sharing tests pass
  - **Depends on:** 7.5

- [ ] **[MBI-007] 7.9.6 Session-injected tools tests (SpawnAgent, SendMessage)**
  - PR #43 Clarifications 2, 4, 5 & 6 (`ListAgents` deferred — not tested here)
  - Test `SpawnAgent` tool is registered on Agents by the Session (not by Agent)
  - Test `SpawnAgent` calls `session.spawn(...)` with `requester` set and returns
    a `ToolResult` whose `result` contains **both** the spawned agent's id and
    the response string (PR #43 Clarification 5)
  - Test `SpawnAgent` on failure returns `ToolResult(success=False, ...)` (no
    exception raised)
  - Test `SpawnAgent` tool description lists only allowlisted agent names
  - Test `SendMessage` tool routes via `session.send(...)` and returns a `ToolResult`
    (success=True with response, or success=False on unknown target — no exception)
  - Test `SendMessage` sets `Message.from` to the calling agent's runtime name
  - Test that no `ListAgents` tool is registered on Agents (PR #43 Clarification 6
    — deferred)
  - **Files:** `tests/test_session/test_session_tools.py` (new)
  - **Acceptance:** All Session-injected tool tests pass
  - **Depends on:** 7.8.2, 7.8.3, 7.8.6

- [ ] **[MBI-007] 7.9.7 Single-agent path and no-shim tests (PR #43 Clarification 1)**
  - Test single-agent `Agent()` without Session works as a chat loop
  - Test `Agent(config=...)` + `agent.process()` still works
  - Test existing examples (`library_usage.py`, `batch_mode.py`,
    `research_workflow.py`) run without modification
  - Test `Agent(_recursion_depth=...)` raises `TypeError` (no deprecation
    warning, no silent ignore — PR #43 Clarification 1)
  - Test `agent.agents` raises `AttributeError` (no proxy property)
  - Test `run_session` name is gone (no alias); only `run_repl` exists
  - Test old TOML files without `[session]` section still load
  - **Files:** `tests/test_session/test_single_agent.py` (new), existing tests
  - **Acceptance:**
    - All existing tests pass without modification
    - Existing examples run without modification
    - Old config files load with default `[session]` values
    - Removed args/fields raise loudly (TypeError / AttributeError), no shims
  - **Depends on:** 7.1-7.8

- [ ] **[MBI-007] 7.9.8 New session_demo.py example**
  - Create `examples/session_demo.py` demonstrating:
    - Constructing a Session
    - Spawning multiple agents in one session
    - **Reading the spawned agent's id from `SpawnResult`** and using it to
      address the child via `SendMessage` (PR #43 Clarification 5 — the
      tree-hierarchy pattern; no `ListAgents` needed)
    - Inter-agent messaging via `session.send()` (Python API)
    - Inter-agent messaging via `SendMessage` tool (tool-call path)
    - Event aggregation visibility
  - **Files:** `examples/session_demo.py` (new)
  - **Acceptance:**
    - Example runs successfully (with a configured backend)
    - Demonstrates spawning, the SpawnResult id, messaging (both paths), and
      event visibility
  - **Depends on:** 7.1-7.8

- [ ] **[MBI-007] 7.9.9 Documentation updates**
  - Update `docs/rationale.md` "Recursive Composition: True Sub-Agents" section
    to reflect real multi-agent support (addressing, event visibility, shared
    backends, Session-injected tools)
  - Update `CLAUDE.md` module structure to include `src/yoker/session/`
  - Update `analysis/mbi-003-python-api-design.md` Layer 3 to reference the real
    `Session` construct (note: MBI-003 is on hold, but the doc cross-reference
    should be updated)
  - Document the Session-injected tools (`SpawnAgent`, `SendMessage`) and
    the agent allowlist enforcement. Note that `ListAgents` is deferred to a
    follow-up MBI (PR #43 Clarification 6).
  - **Files:** `docs/rationale.md` (modify), `CLAUDE.md` (modify),
    `analysis/mbi-003-python-api-design.md` (modify)
  - **Acceptance:**
    - `docs/rationale.md` reflects real multi-agent support
    - `CLAUDE.md` includes `session/` in module structure
    - MBI-003 design doc references real Session
    - Session-injected tools and allowlist documented
  - **Depends on:** 7.1-7.8

- [ ] **[MBI-007] 7.9.10 Final verification: make check green**
  - Run `make check` end-to-end (format, lint, typecheck, test) — all green
  - Verify no existing tests were modified to make the refactor pass
    (behaviour unchanged for single-agent path)
  - Verify `python -m yoker` interactive mode works unchanged
  - Verify `python -m yoker` batch mode works unchanged
  - Verify existing examples run without modification
  - Verify new `examples/session_demo.py` runs
  - **Acceptance:**
    - `make check` green
    - Zero behaviour change on the single-agent path
    - All new session tests pass
    - All existing examples work
  - **Depends on:** 7.9.1-7.9.9

---

### Concerns and Risks

1. **No transitional shims (PR #43 Clarification 1):** The migration is a clean
   break, not a phased deprecation. The registry must be moved to Session (7.3)
   *before* it is removed from Agent (7.2.1) — but during the in-flight commit
   sequence there is no "Agent temporarily has both" state shipped; the two
   changes land together. The ordering in the dependency graph is about
   implementation order within a single merge, not about shipping an intermediate
   state. No proxy properties, no deprecation warnings, no ignored args.

2. **`BaseUIHandler` is NOT recreated (PR #43 Clarification 8):** the owner
   explicitly rejected recreating `BaseUIHandler`. Task 7.7.4 adds
   `agent_spawned` / `agent_finished` **directly to the `UIHandler` protocol**
   as optional methods; the `UIBridge` guards calls with `hasattr` /
   `getattr`. No `src/yoker/ui/base.py` is created.
   `InteractiveUIHandler` implements the methods; `BatchUIHandler` does not
   (and is not broken).

3. **Plugin loading is tightly coupled to Agent:** `load_configured_plugins(agent,
   config, cli_plugins)` populates `agent.tools`, `agent.skills`, and
   `agent.agents` in one call. After the migration, agent definitions must go to
   `session.agents` while tools/skills remain per-agent. Task 7.2.4 splits this
   call. The `yoker` builtin plugin manifest (`__YOKER_MANIFEST__`) loads agents
   from `agents_dir="agents"` — this must target Session's registry. The
   `SpawnAgent`/`SendMessage` tools are **not** loaded via the plugin
   manifest — they are Session-injected (PR #43 Clarifications 2 & 4;
   `ListAgents` is deferred per Clarification 6).

4. **`_resolve_agent_definition` uses `self.agents.resolve()`:** Agent's
   definition resolver (line 358 of `agent/__init__.py`) looks up agent
   definitions by name in its own registry. After the registry moves to Session,
   this must route through `self._session.agents.resolve()` when a session is
   present, or use the explicit `agent_definition` / `agent_path` constructor
   args (which remain unchanged).

5. **`ToolContext` is a frozen dataclass:** Adding a `session` field is additive
   but requires updating all `ToolContext` construction sites. There is only one
   construction site: `_build_tool_context()` in `agent/_processing.py`. The
   field defaults to `None` so existing code that doesn't set it remains valid.

6. **`make_spawn_agent_tool` bakes available names at construction time:** The
   factory reads `requester.definition.agents` (intersected with
   `session.agents.names`) to build the tool description (PR #43 Clarification 3).
   If agents are dynamically added to the session after the tool is constructed,
   the description won't reflect them. This matches current behaviour (names
   are baked at Agent init time) and is acceptable for MBI-007.

7. **Event `agent_id` tagging approach (PR #43 Clarification 9):** the
   `SessionEvent` envelope wrapper is the chosen approach — a frozen
   `SessionEvent(agent_id, event)` dataclass wraps each agent event. **No
   changes to existing frozen event dataclasses** and no changes to their
   construction sites in `agent/_processing.py`. The `UIBridge` and
   `EventRecorder` handle both `SessionEvent` (multi-agent) and bare `Event`
   (single-agent) inputs. This supersedes the earlier "design choice"
   formulation in task 7.7.2.

8. **`Agent(_recursion_depth=...)` is a public constructor arg:** Removing it
   breaks any caller using it. Since it is `_`-prefixed (conventionally private)
   and PR #43 Clarification 1 mandates no shims, removal is the chosen path.
   Task 7.2.2 removes it; the implementation raises `TypeError` (unexpected
   keyword) — no deprecation warning, no silent ignore.

9. **Session-injected tools are per-Agent:** `SpawnAgent` and `SendMessage`
   need to know which Agent they were injected into (for the `requester` /
   `from` fields and the allowlist-intersected description). The factory
   functions should capture the Agent at injection time, producing a distinct
   tool instance per Agent. This is a per-Agent injection, not a single shared
   tool across the Session. (`ListAgents` is deferred per PR #43
   Clarification 6.)

### Note: Config Factory (belongs to MBI-003, not MBI-007)

The owner requested (PR #42 Comment 1) a **Config factory** for creating `Config` in code, with a flag to enable/skip normal config loading (TOML discovery + CLI args). This is needed by the `agent()` factory function in MBI-003's Python API. It is recorded in `analysis/session-concept-analysis.md` §7.2 and tracked on the MBI-003 entry in PLAN.md. It will be addressed when MBI-003 resumes after MBI-007 merges to master.

---

## Active: MBI-002: Bootstrap

**Goal:** Interactive guided setup for first-time users without configuration.

**Milestone:** Users run `yoker` and are guided through backend selection, model selection, Ollama account creation, and config creation.

### Tasks

- [x] **2.0 Change Config Default Model to `gemini-3-flash-preview:cloud` (single location)** ✅ (2026-07-01)
  - Update **only** `OllamaConfig.model` in `src/yoker/config/__init__.py` from
    `llama3.2:latest` to `gemini-3-flash-preview:cloud`. This is the **single
    source** of the default model (owner PR #34 point 1).
  - Audit the codebase for any other location referencing a default model
    (literals in `src/`, tests, docs, examples, agent defaults). Any code that
    needs the default must obtain it from the `Config` class (e.g.
    `Config().backend.ollama.model`), not by redefining the literal. Test
    assertions and docs that currently hardcode `llama3.2:latest` are updated to
    the new default or to read it from `Config`.
  - Rationale (owner): frictionless first run — cloud model, no local download
    needed. `llama3.2:latest` would force a download on first use.
  - This default is referenced by the wizard's Step 5 curated list (via
    `Config()`, not a literal) and by the generated config.
  - Write unit tests (assert the single default value; verify no duplicate
    default literals remain in `src/`).
  **Satisfies:** Frictionless default model
  **Design:** See `analysis/bootstrap-wizard-design.md` (Resolved Q2 + task 2.0; PR #34 point 1)

- [x] **2.1 Detect Missing Configuration (`config_provided() -> bool`)** ✅ (2026-07-01)
  - Implement `config_provided() -> bool` in `src/yoker/bootstrap/detect.py`
    (owner PR #34 point 2 — replaces the `ConfigStatus` / `detect_config()` /
    state-machine design).
  - "Provided" means the user induced any config source: `~/.yoker.toml` exists,
    `./yoker.toml` exists, or CLI args override defaults. No field-presence
    check, no `REQUIRED_CONFIG_FIELDS`, no `missing/incomplete/complete` state.
  - Trigger: `if not config_provided(): <wizard or warn-and-exit>`.
  - Wire into `__main__.py::main()` as a pre-flight check before `Agent()`;
    library mode (`Agent(config=...)`) skips detection.
  - Edge cases: empty TOML file exists → `True` (sparse is still provided);
    malformed TOML → `ConfigurationError` (not silent); permission denied →
    error; dangling symlink → treated as not existing.
  - **Write unit tests for the logic** (boolean, file-existence, CLI-arg
    detection) — this is logic, not IO.
  **Satisfies:** Bootstrap trigger condition
  **API design:** See `analysis/bootstrap-config-detection.md`.

- [x] **2.2 Welcome & Guided-vs-Manual Flow** ✅ (2026-07-01)
  - Step 0: explain yoker (provider-neutral AI backend for agentic workflows)
  - Step 1: report no config found; offer guided (recommended) vs manual setup
  - Manual path: print config skeleton + docs link, exit without writing
  - All I/O via `UIHandler` (UI-layer separation intact)
  - **No unit tests** — pure IO/user interaction (owner PR #34 point 3);
    testing is user-driven.
  **Satisfies:** Bootstrap entry / low-friction onboarding
  **Design:** See `analysis/bootstrap-wizard-design.md`

- [x] **2.3 Ollama Account & Connection-Method Steps** ✅ (2026-07-01)
  - Step 2: backend intro (single backend today: Ollama, free tier, no fake
    multi-way menu)
  - Step 3: "Do you have an ollama account?" → no: **open the docs guide URL**
    (may launch browser via `webbrowser.open()`), say we'll wait, then resume
    — the wizard does **not** abort or exit. yes: continue.
  - Step 4: split choice — (1) ollama app signed in (default backend, no API key)
    or (2) API key (masked input, optional guide link). Locked wording (app-first
    key-second):
    "Connect via: 1) The ollama app running locally (recommended — no key needed)
     2) An ollama API key"
  - Per-owner principle: least-possible steps to a minimal yet complete config
  - **No unit tests** — pure IO/user interaction (owner PR #34 point 3);
    testing is user-driven.
  **Satisfies:** Account/connection guidance
  **Design:** See `analysis/bootstrap-wizard-design.md`

- [x] **2.4 Model Selection Wizard** ✅ (2026-07-01)
  - `modellist.py`: holds a **curated list** of recommended models (including
    the default, read from `Config().backend.ollama.model` — not a literal) plus
    a **free-text entry** option — **NO network call**. Live fetch via
    `AsyncClient.list()` / `GET /api/tags` was considered and **rejected** for
    first-install UX (owner: first-time install has no models pulled yet, so
    the tag list is empty/useless). Curated list + free text is the **primary
    and only** approach.
  - Step 5 prompt: pick from curated list / accept default / free text
  - Default model `gemini-3-flash-preview:cloud` (matches task 2.0's single
    Config default — cloud, no download needed)
  - **No unit tests** — pure IO/user interaction (owner PR #34 point 3);
    testing is user-driven.
  **Satisfies:** Model selection capability
  **Design:** See `analysis/bootstrap-wizard-design.md` (Resolved Q2, Q5)

- [x] **2.5 Config Writer (in the config module) & Continue into Session** ✅ (2026-07-01)
  - **Lives in `src/yoker/config/writer.py`**, NOT `yoker/bootstrap/writer.py`
    (owner PR #34 point 4). It is a general-purpose config-writing utility;
    the bootstrap wizard calls it, it does not own it. Reusable for in-session
    config augmentation (e.g. "add `plugins enabled = true` to your
    configuration?").
  - **Annotation-driven / generic** (owner PR #34 point 5): reads config-class
    metadata/`help` annotations to render full default `Config` → TOML with
    inline comments. Adding a config field requires NO writer change —
    instrument the config class instead. Never hardcode current field names.
  - Override only non-default values collected by wizard (model, optionally
    api_key/base_url); merge preserving unknown keys.
  - Write to user-level `~/.yoker.toml` (works across all yoker-based apps)
  - **`chmod 600`** every yoker config file written
  - API key stored **only** in `~/.yoker.toml`; never project config, never
    env var, never logged, never echoed
  - Brief confirmation that config was created (home-folder level, shared by
    all yoker-based apps) and that **yoker is continuing into the normal
    session now** — the user does NOT need to rerun `yoker`
  - **Return control to `__main__.py`**, which proceeds straight into normal
    Agent startup using the freshly-written config, as if a config had existed
    all along. The wizard does NOT exit the process or ask the user to relaunch.
  - **Write unit tests for the rendering logic** (TOML output, overrides,
    annotation-driven comments, chmod) — this is logic, not IO.
  **Satisfies:** Config creation capability (generic, reusable)
  **Design:** See `analysis/bootstrap-wizard-design.md` (Annotation-Driven
  ConfigWriter section; PR #34 points 4 & 5)

- [x] **2.6 Non-Interactive Path & `__main__.py` Wiring** ✅ (2026-07-01)
  - Wire `config_provided()` → `BootstrapWizard` in interactive mode (async).
    The wizard returns after writing config; `__main__.py` then continues into
    normal Agent startup (does not exit after bootstrap).
  - Non-interactive mode (BatchUIHandler): do **not** instantiate wizard; print
    approved stderr warning and exit non-zero:
    "No yoker configuration found at ~/.yoker.toml.
     Run `yoker` interactively to configure, or see <docs URL>.
     Aborting (non-interactive mode)."
  - Library mode (`Agent(config=...)`) skips bootstrap entirely
  - **No unit tests for the wizard IO path** (owner PR #34 point 3); the
    boolean gate logic is tested in 2.1.
  **Satisfies:** Safe non-interactive behavior
  **Design:** See `analysis/bootstrap-wizard-design.md` (Resolved Q3)

- [x] **2.7 Bootstrap Documentation Guide (docs site)** ✅ (2026-07-01)
  - **One merged page** covering ollama account creation + local app/proxy
    install + (optional) API-key creation, with screenshots; optional per-OS
    variants
  - Wizard links to anchors within this page (account check, key creation)
  - Decision: one merged page (least duplication; resolved Q4)
  **Satisfies:** External account/install guidance (referenced by wizard)
  **Owner:** Confirmed new requirement
  **Design:** See `analysis/bootstrap-wizard-design.md` (Resolved Q4)

- [x] **2.8 End-to-end onboarding guide (Python/uv install → yoker → wizard → hello agent)** ✅ (2026-06-28)
  - New docs page `docs/guides/getting-started.md`: Python + uv setup (macOS,
    Windows, Linux), install yoker, run the bootstrap wizard, and perform a
    first "hello agent" interaction on Ollama's free tier.
  - Placed at the top of the `docs/index.md` toctree (entry point for new users).

---

## Active: MBI-006: Multi-Provider Backend Support (Phase 1)

**Goal:** Introduce the `ModelBackend` async Protocol and provider-neutral `ChatChunk` stream type, reimplement the existing Ollama behaviour on top of them, widen the config schema to the tagged-union shape, make subagent spawn provider-agnostic, and add optional stats fields to `TurnEndEvent`. **Pure refactor — no behaviour change, no new provider, no wizard changes.**

**Design source of truth:** `analysis/multi-provider-backend-design.md` §5 (Phase 1). Functional counterpart: `analysis/functional-multi-provider-backend.md`.

**Preconditions:** PRE-1 (M.5 — populate `Agent._tool_backends` for Ollama) — DONE/merged.

**Out of scope for Phase 1:** OpenAI backend, Anthropic backend, bootstrap wizard provider selection, `build_bootstrap_overrides` provider-awareness, web tools for non-Ollama providers, live API model discovery.

### Tasks

- [x] **[MBI-006] 6.1 Backends package: ModelBackend Protocol + ChatChunk types** ✅ (2026-06-29)
  - Create new `src/yoker/backends/` package
  - `src/yoker/backends/protocol.py`: define `ModelBackend` async Protocol with
    `provider` property and `chat_stream(*, model, messages, tools, think, **kwargs) -> AsyncIterator[ChatChunk]` (signature per design §4.3; `**kwargs` purely internal per Q20)
  - `src/yoker/backends/protocol.py`: define provider-neutral stream types:
    `ChatChunkEvent` enum (CONTENT_START/DELTA/STOP, THINKING_START/DELTA/STOP, TOOL_CALL_START/DELTA/STOP, USAGE, DONE), `ToolCallDelta` (index, id, name, arguments_delta), `UsageStats` (input_tokens, output_tokens, prompt_eval_count, eval_count, total_duration_ms), and `ChatChunk` (event, index, text, tool_call, usage) — per design §4.2
  - `src/yoker/backends/__init__.py`: re-export `ModelBackend`, `ChatChunk`, `ChatChunkEvent`, `ToolCallDelta`, `UsageStats` (and `create_backend` once 6.5 lands)
  - Design `ChatChunk` to accommodate Anthropic's block-style streaming even though Anthropic is Phase 3 (explicit `index` for block indexing; START/DELTA/STOP bracketing)
  - Write unit tests asserting the dataclasses are frozen and field defaults are correct
  - **Acceptance:**
    - `from yoker.backends import ModelBackend, ChatChunk, ChatChunkEvent, ToolCallDelta, UsageStats` works
    - `ChatChunk` is frozen; exactly one of `text`/`tool_call`/`usage` is set per `event`
    - `UsageStats` preserves Ollama-native fields (`prompt_eval_count`/`eval_count`/`total_duration_ms`) alongside `input_tokens`/`output_tokens`
    - `make check` green (no existing tests modified)
  **Satisfies:** Protocol + neutral stream type foundation
  **Depends on:** —

- [x] **[MBI-006] 6.2 TurnEndEvent: optional input_tokens/output_tokens stats fields** ✅ (2026-06-29)
  - `src/yoker/events/types.py`: add `input_tokens: int = 0` and `output_tokens: int = 0` to `TurnEndEvent` (Q15)
  - Keep Ollama-native `prompt_eval_count`/`eval_count`/`total_duration_ms` for backwards compatibility
  - Non-breaking: defaults of 0 preserve existing behaviour
  - Update UIBridge/stats display to read whichever is non-zero (UI reads `input_tokens`/`output_tokens` when Ollama-native fields are 0)
  - Write unit tests asserting new fields default to 0 and existing Ollama-native stats still populate
  - **Acceptance:**
    - `TurnEndEvent` has `input_tokens` and `output_tokens` fields defaulting to 0
    - Existing Ollama sessions still populate `prompt_eval_count`/`eval_count`/`total_duration_ms`
    - All existing event tests pass without modification
  **Satisfies:** Provider-agnostic stats surface
  **Depends on:** —

- [x] **[MBI-006] 6.3 Config tagged-union shape + Clevis CLI args** ✅ (2026-06-29)
  - `src/yoker/config/__init__.py`: widen `BackendConfig` to discriminated-dataclass shape — add `openai: OpenAIConfig | None = None` and `anthropic: AnthropicConfig | None = None` Optional fields (Q2)
  - Forward-declare `OpenAIConfig`/`AnthropicConfig` stubs under `TYPE_CHECKING` (Phase 2/3 populate them; Phase 1 only needs the field slots to exist with `None` defaults)
  - Widen `provider` whitelist from `("ollama",)` to `("ollama", "openai", "anthropic")` so the choice arg lists all future providers, but only wire the ollama validation guard in `__post_init__` (require `backend.ollama` when `provider == "ollama"`; openai/anthropic guards added in Phase 2/3)
  - Keep `OllamaParameters.top_k`/`num_ctx` Ollama-specific (Q4); do NOT introduce a shared parameter base class
  - Keep `provider` default `"ollama"` (Q9)
  - Verify Clevis auto-generates `--backend-provider {ollama,openai,anthropic}` and `--backend-openai-*` / `--backend-anthropic-*` args (default None, ignored at runtime in Phase 1)
  - Write unit tests: default `BackendConfig()` yields `provider="ollama"`, `openai=None`, `anthropic=None`; old TOML files (single-Ollama shape) still load (Q8 — strict superset, no migration); `provider="openai"` with `openai=None` does NOT raise in Phase 1 (guard only enforces ollama) — or raises a clear `ValidationError` per design §4.5; pick the behaviour consistent with the design note and document it
  - **Acceptance:**
    - `BackendConfig()` defaults to `provider="ollama"` with `openai`/`anthropic` None
    - Existing `~/.yoker.toml` files load unchanged (no migration script)
    - `--backend-provider` lists all three providers; `--backend-openai-*`/`--backend-anthropic-*` args exist and default to None
    - `make check` green
  **Satisfies:** Config schema superset for all three phases
  **Depends on:** —

- [x] **[MBI-006] 6.4 render_config_toml union-aware** ✅ (2026-06-29)
  - `src/yoker/config/writer.py::render_config_toml`: confirm the generic dataclass walk omits `None` per-provider sub-configs; add explicit handling/tests if needed (Q7 split — writer stays in Phase 1 because it lives in the config module and is reusable)
  - Do NOT touch `build_bootstrap_overrides` (wizard-specific, deferred with §8)
  - Write unit tests asserting a config with `openai=None`/`anthropic=None` writes a TOML file with no `[backend.openai]`/`[backend.anthropic]` section, and that the written file round-trips back to an equal `BackendConfig`
  - **Acceptance:**
    - `render_config_toml` omits `None` per-provider sub-configs
    - Round-trip: `load(render_config_toml(cfg)) == cfg` for an Ollama-only config
    - `make check` green
  **Satisfies:** Config writer union-awareness (reusable, non-wizard)
  **Depends on:** 6.3

- [x] **[MBI-006] 6.5 OllamaBackend adapter + create_backend factory** ✅ (2026-06-29)
  - `src/yoker/backends/ollama.py`: new `OllamaBackend` wrapping `ollama.AsyncClient`
    - Constructor builds the client from `config.backend.ollama` (relocate `agent/_setup.py::create_client` logic here — no behaviour change)
    - `provider` property returns `"ollama"`
    - `chat_stream(*, model, messages, tools, think, **kwargs)` calls `self._client.chat(model, messages, tools, think=think, stream=True)` and translates each native chunk into `ChatChunk`:
      - `message.thinking` -> `THINKING_START`/`THINKING_DELTA`/`THINKING_STOP` (synthesise START before first thinking delta, STOP at end of thinking)
      - `message.content` -> `CONTENT_START` (before first content delta) / `CONTENT_DELTA` / `CONTENT_STOP` (synthesise boundaries; Ollama is delta-style per design §4.2)
      - `message.tool_calls` -> `TOOL_CALL_START`/`TOOL_CALL_DELTA`/`TOOL_CALL_STOP` per call
      - `chunk.done` + native stats (`prompt_eval_count`/`eval_count`/`total_duration`) -> `USAGE` (populate `UsageStats` native fields) then terminal `DONE`
    - Preserves native `think=` flag mapping (Q11) and native stats (Q15)
  - `src/yoker/backends/factory.py`: new. `create_backend(config) -> ModelBackend`; `BACKENDS = {"ollama": lambda cfg: OllamaBackend(cfg)}` only in Phase 1. Unknown provider raises `ConfigurationError` listing configured providers (Q10 — no silent fallback)
  - `src/yoker/agent/_setup.py`: remove `create_client()` (moved into `OllamaBackend`); keep `create_web_guardrails`, `validate_recursion_depth`, `add_skill_discovery_block` unchanged
  - Write unit tests:
    - `create_backend(Config())` returns an `OllamaBackend` instance
    - `create_backend` with unknown provider raises `ConfigurationError` naming configured providers
    - `OllamaBackend.chat_stream` fed a recorded Ollama chunk sequence emits `CONTENT_START` before first `CONTENT_DELTA`, `THINKING_START`/`STOP` around thinking deltas, `TOOL_CALL_START`/`DELTA`/`STOP` per call, and a terminal `DONE` with `UsageStats` populated from native fields
  - **Acceptance:**
    - `create_backend(Config())` is an `OllamaBackend`
    - Unknown provider -> `ConfigurationError` (Agent never starts)
    - `OllamaBackend.chat_stream` emits the documented `ChatChunk` event sequence with synthesised block boundaries
    - `make check` green
  **Satisfies:** Ollama adapter on the new Protocol + factory dispatch
  **Depends on:** 6.1, 6.3

- [x] **[MBI-006] 6.6 Agent wiring: _backend, _resolve_model, _chat_stream, _consume_stream rewrite** ✅ (2026-06-29)
  - `src/yoker/agent/agent.py`:
    - Replace `self._client: AsyncClient | None` with `self._backend: ModelBackend | None`
    - Replace `create_client(self.config, AsyncClient)` with `create_backend(self.config)`
    - Keep optional `backend: ModelBackend | None = None` injection param (renamed from `client`)
    - `_resolve_model()`: read from the active provider's sub-config, not `config.backend.ollama.model` directly. Introduce helper `_active_backend_config(config)` (or `getattr(config.backend, config.backend.provider)`) — keep returning the Ollama model in Phase 1
  - `src/yoker/agent/_processing.py`:
    - `_chat_stream()`: replace `agent._client.chat(...)` with `agent._backend.chat_stream(model=..., messages=..., tools=..., think=...)`
    - `_consume_stream()`: rewrite to iterate `ChatChunk` instead of Ollama-native chunks. Map `ChatChunkEvent` to existing `Event` types (ThinkingStart/Chunk/End, ContentStart/Chunk/End, ToolCallEvent). Accumulate tool calls from `TOOL_CALL_START`/`DELTA`/`STOP`. Build `TurnEndEvent` from `UsageStats`: map `prompt_eval_count`/`eval_count`/`total_duration_ms` to native fields; fall back to `input_tokens`/`output_tokens` for non-Ollama (set native fields to 0 when absent)
  - Add a golden-stream unit test: feed a recorded sequence of `ChatChunk` through `_consume_stream` and assert the emitted `Event` sequence matches a captured Ollama session (design §5.4 acceptance)
  - Do NOT change event types (beyond 6.2), UIBridge mapping, or UI handlers
  - **Acceptance:**
    - All existing tests pass without modification (behaviour unchanged)
    - Golden-stream test: recorded `ChatChunk` sequence -> expected `Event` sequence
    - Ollama round-trip works exactly as before through the new Protocol (interactive + batch)
    - `make check` green
  **Satisfies:** Agent hot path on the new Protocol
  **Depends on:** 6.5, 6.2

- [x] **[MBI-006] 6.7 Subagent spawn provider-agnostic** ✅ (2026-06-29)
  - Introduce `with_model(backend: BackendConfig, model: str) -> BackendConfig` helper in `src/yoker/backends/__init__.py` (or `config` module) — returns a copy of `backend` with `model` overridden on the active sub-config via `getattr`/`dataclasses.replace` (design §9.3)
  - `src/yoker/builtin/agent.py::_create_subagent`: replace the hardcoded `BackendConfig(provider=..., ollama=OllamaConfig(...))` rebuild with the provider-agnostic copy using `with_model`
  - `src/yoker/bootstrap/modellist.py`: read default model from the active provider config (helper), not `config.backend.ollama.model` directly. Curated list stays Ollama-only in Phase 1
  - Phase 1 implements `with_model` for `ollama` only; Phase 2/3 extend to `openai`/`anthropic`
  - Write unit tests: subagent spawn produces a `Config` whose `backend` is a faithful copy of the parent's with only the model overridden, regardless of provider (test under `provider="ollama"`)
  - **Acceptance:**
    - Subagent `Config.backend` equals parent's `backend` with only `model` overridden
    - No hardcoded `OllamaConfig` rebuild in `_create_subagent`
    - `make check` green
  **Satisfies:** Provider-agnostic subagent spawn
  **Depends on:** 6.3, 6.6

- [x] **[MBI-006] 6.8 Phase 1 verification** ✅ (2026-06-29)
  - Run `make check` end-to-end (format, lint, typecheck, test) — all green
  - Verify no existing tests were modified to make the refactor pass (behaviour unchanged)
  - Verify `~/.yoker.toml` written by the wizard still produces a working Ollama session (round-trip unchanged — manual or integration check)
  - Verify `render_config_toml` writes a config with `openai`/`anthropic` absent when those sub-configs are `None`
  - Verify `create_backend(Config())` returns an `OllamaBackend` and unknown provider raises `ConfigurationError`
  - Confirm wizard files (`bootstrap/wizard.py`, `bootstrap/steps.py`) are unchanged (deferred per §8)
  - Confirm `build_bootstrap_overrides` is NOT touched (deferred with the wizard)
  - Confirm web tools (`websearch`/`webfetch`) under Ollama still work (PRE-1 base) and are not extended to other providers
  - **Acceptance:**
    - `make check` green; zero behaviour change on the Ollama path
    - All Phase 1 design §5.4 acceptance criteria verified
    - No wizard changes; no `build_bootstrap_overrides` changes; no new provider wired
  **Satisfies:** Phase 1 completion gate
  **Depends on:** 6.1-6.7

---

## Maintenance Tasks

Unsorted improvements and fixes.

- [ ] **M.1 Rename yoker: plugin tools to builtin:**
  - Rename namespace from `yoker:` to `builtin:`
  - When listing tools (e.g. /tools), don't include the `builtin:` prefix
  - Update documentation
  **Priority:** P3

- [ ] **M.2 Default Tools Behavior**
  - When agent has no explicit tools configuration, ALL tools should be available
  - Update agent initialization logic
  - Write unit tests
  **Priority:** P3

- [ ] **M.3 Namespace Frontmatter Configuration**
  - Allow namespace configuration in skill and agent frontmatter
  - Update SkillLoader and AgentLoader
  - Write unit tests
  **Priority:** P3

- [ ] **M.4 Clean Up Duplicate Tests**
  - Review all tests for duplicates (e.g. tests/test_tools/test_base.py and tests/tools/test_base.py)
  - Consolidate duplicate tests
  - Ensure full coverage maintained
  **Priority:** P4

- [x] ✅ **M.5 Populate `Agent._tool_backends` for Ollama web tools (prerequisite for multi-provider backend)**
  - `Agent._tool_backends` is initialised to `{}` and never populated, so the
    `websearch` and `webfetch` built-in tools already fail today with
    "No backend configured" regardless of provider. This is a pre-existing bug
    independent of the multi-provider backend design.
  - Fix scope: populate `Agent._tool_backends` with the
    `OllamaWebSearchBackend` / `OllamaWebFetchBackend` instances when the
    configured provider is Ollama, so the web tools actually work. Keep it small
    and focused — this is a bug fix, not a feature.
  - **Prerequisite for:** the multi-provider backend work
    (`analysis/multi-provider-backend-design.md`). The design note documents
    this gap (§7.4 and §9.17 Q17 Option B) and the owner has decided to fix it
    as a separate precondition before the backend phases begin. Do this before
    Phase 1 of the multi-provider backend effort.
  - Write unit tests asserting the `websearch` / `webfetch` backends are
    populated under the Ollama provider and that the tools execute successfully.
  - Do not extend web tools to non-Ollama providers — that remains out of scope
    (design note §7.4); the multi-provider backend effort will handle the
    "Ollama provider required" error path for other providers.
  **Priority:** P2
  **Date:** 2026-06-28

- [x] **M.6 Exclude api_key from Clevis CLI generation** ✅ (2026-06-29)
  - Clevis released `metadata={'cli': False}` support (FR christophevg/clevis#30).
  - Implemented in Phase 1 task 6.3 as part of the config tagged-union + Clevis
    CLI args work (see MBI-006 task 6.3 acceptance criteria).
  - This is a follow-up to the multi-provider backend security review
    (`analysis/security-multi-provider-backend.md`, finding H1) and amends
    design decision Q6 (`analysis/multi-provider-backend-design.md` §11.6).
  - `api_key` fields on `OllamaConfig`/`OpenAIConfig`/`AnthropicConfig` will be
    annotated with `metadata={"cli": False}` in Phase 1 task 6.3; test asserts
    no `--backend-*-api-key` CLI arg is generated.
  **Priority:** P3
  **Date:** 2026-06-29

---

## Active: UI Separation Migration (Complete)

**Status:** Completed 2026-06-15 via PR #27

**Goal:** Separate UI from Agent in the yoker codebase, establishing a clean boundary where the Agent layer is purely event-driven and the UI layer handles all presentation.

**Approach:** Clean break - no backward compatibility, no deprecation shims.

**Related Analysis:**
- [Overview and Architecture](analysis/ui-separation-overview.md)
- [IO Operations Catalog](analysis/ui-separation-io-catalog.md)
- [Error Handling Strategy](analysis/ui-separation-errors.md)
- [Agent Module Refactoring](analysis/ui-separation-agent-module.md)
- [UI Handler Design](analysis/ui-separation-ui-design.md)
- [Migration Plan](analysis/ui-separation-migration.md)

**Outcome:** All migration phases complete (UI-001 through UI-055). PR #27 merged the final documentation and examples.

---


## Done: MBI-001: Package Plugin System (2026-06-25)

**Goal:** Enable Python packages to provide tools and skills to yoker via `yoker --with <package>`

**Status:** Core implementation complete. Validation with pkgq project pending before final PyPI release.

### Completed Phases

- [x] **Phase 2: Skill System (Core)** — Skill Infrastructure, Slash Commands, Skill Tool
- [x] **Phase 3: Package Plugin System** — Package Plugin Discovery, CLI --with Argument
- [x] **Phase 5: Polish** — Error Handling, Documentation, Testing
- [x] **Phase 6.2: Examples and Tutorials**

### Remaining

- See **MBI-001 Validation** section above for pkgq validation and PyPI release tasks

---

## Launch Preparation: Public Announcement (2026-06-17)

**Source:** Email from Christophe, 2026-06-17
**Goal:** Prepare marketing materials and dedicated website for Yoker's public announcement.
**USP:** "Add LLM capabilities to your Python apps and modules without worrying about the agentic foundations. Agentic Functions."

### Social Media Launch Plan

- [ ] **L.1 Storyboard of Publications**
  - Define ideal sequence to announce and introduce Yoker on social media
  - Predominantly LinkedIn and Instagram
  - Refer to the website in all publications
  - **Priority:** P1

- [ ] **L.2 Publication Timeline**
  - Prepare timeline for releasing articles, posts
  - Investigate: how many posts?
  - Investigate: how long between posts?
  - Investigate: repeating schedule?
  - **Depends on:** L.1
  - **Priority:** P1

### Website Research

- [ ] **L.3 Website Structure Research**
  - Research dedicated website structure for Yoker
  - **Priority:** P1

- [ ] **L.4 Website Examples and Framework Comparisons**
  - Research examples from other frameworks
  - Create comparison with other agent frameworks
  - **Priority:** P1

- [ ] **L.5 Strong Front Page**
  - Research and design a strong front page example
  - **Priority:** P1

- [ ] **L.6 Clear Getting Started Guide**
  - Research and design clear getting started guide
  - **Priority:** P1

- [ ] **L.7 Best Practices Research**
  - Learn from good examples, find best practices for developer tool websites
  - **Priority:** P2

- [ ] **L.8 Look and Feel Research**
  - Research look and feel for the website
  - **Priority:** P2

- [ ] **L.9 Low Entry / Bootstrapping Showcase**
  - Show low entry barrier and good support for bootstrapping
  - Highlight free Ollama account support
  - **Priority:** P2

---

## Architecture Refactoring: Plugin Config Registration

**Goal:** Enable plugins to register configuration fields dynamically, allowing tool-specific settings without hardcoding in ToolsConfig.

**Related Analysis:**
- [Plugin Architecture](analysis/plugin-architecture.md)

### Phase 7: Config System Refactoring

**Status:** Design required

**Priority:** P5 (Post-MVP architectural improvement)

**Problem:** The current config system uses frozen dataclasses for `ToolsConfig`, which cannot be extended dynamically. Plugins added via `--with` need to register their own configuration fields (e.g., `[tools.pkgq]` settings). This requires architectural changes to the config system.

- [ ] **7.1 Plugin Config Registration System Design**
  - Analyze Clevis `register_field` mechanism
  - Design plugin config registration API
  - Determine how plugins register their config schema
  - Design config discovery and validation flow
  - Document interaction with existing `WebGuardrailConfig` duplication
  - **Priority:** P5
  - **Estimated time:** 4-6 hours (design only)
  - **Note:** This is a design task. Implementation will be a separate task.

- [ ] **7.2 ToolsConfig Dynamic Extension**
  - Change `ToolsConfig` from frozen to mutable dataclass
  - Implement `register_tool_config(name: str, config_class: type)` API
  - Support config field injection at runtime
  - Update existing hardcoded tool configs to use registration pattern
  - **Depends on:** 7.1
  - **Priority:** P5
  - **Estimated time:** 8-12 hours
  - **Note:** Requires Clevis support or local workaround

- [ ] **7.3 Consolidate WebGuardrailConfig Classes**
  - Remove `WebGuardrailConfig` duplication between `tools/web/guardrail.py` and `config/__init__.py`
  - Create single unified `WebGuardrailConfig` class
  - Update `WebSearchToolConfig` and `WebFetchToolConfig` to compose guardrail config
  - Ensure config passes guardrail settings directly to guardrails
  - Update `agent/_setup.py` to use consolidated config classes
  - **Depends on:** 7.2
  - **Priority:** P5
  - **Estimated time:** 2-4 hours
  - **Note:** This task should NOT be done separately. It depends on the plugin config registration system being in place first, because:
    1. The duplication exists because `ToolsConfig` is frozen
    2. When plugins can register config fields, the pattern will change
    3. Hardcoded `WebSearchToolConfig`/`WebFetchToolConfig` will become anti-patterns
    4. Consolidating now would create a pattern that contradicts the plugin system design

**Rationale for Dependency Order:**
- Item 7.1 must complete first to establish the design
- Item 7.2 implements the mechanism that plugins will use
- Item 7.3 consolidates existing configs using the new mechanism
- Doing 7.3 before 7.2 would create throwaway code that contradicts the plugin architecture

**Related Issue:** The duplication in `WebGuardrailConfig` classes is currently intentional:
- `tools/web/guardrail.py::WebGuardrailConfig` is a runtime guardrail config (unfrozen)
- `config/__init__.py::WebSearchToolConfig`/`WebFetchToolConfig` are frozen TOML configs
- `agent/_setup.py` converts frozen configs to runtime configs
- This is a workaround that will be eliminated by proper plugin config registration

---

## Security Improvements

- [ ] **S.1 Secure API Key Storage with Keyring**
  - Use Python `keyring` library to securely store API keys instead of plain text in config files
  - During bootstrap wizard, use `keyring.set_password('yoker', '<provider>', api_key)` to store
  - On startup, retrieve with `keyring.get_password('yoker', '<provider>')`
  - Fallback to config file if keyring is unavailable or user opts out
  - Support all providers: Ollama, OpenAI, Anthropic, Gemini
  - Update `BootstrapWizard` to use keyring for API key collection
  - Update config loading to check keyring first, then config file
  - Document the keyring integration in security docs
  - Write unit tests with mocked keyring backend
  - **Priority:** P2
  - **Reference:** User request 2026-07-01

---

## Future Work (Post-Release)

### Additional Tools (Phase 2 continued)

- [ ] **2.15 Python Tool**
  - Depends on: 2.14 Python Tool Research (complete)
  - Implement Python script execution functionality
  - Support virtual environment activation (uv, pyenv, venv)
  - Implement code validation guardrails (6-layer defense)
  - Define allowed operations and permissions
  - Add timeout and resource limits
  - Write unit tests
  - See `analysis/api-python-tool.md` for API design
  - **Priority:** P4

- [ ] **2.16 Pytest Tool**
  - Implement test execution functionality via pytest
  - Support running all tests, single test file, or selection
  - Add optional `activate_venv` parameter
  - Add optional `filter` parameter for grep pattern
  - Add optional `max_lines` parameter for output
  - Apply PathGuardrail for test file paths
  - Add timeout enforcement
  - Write unit tests
  - See `analysis/api-pytest-tool.md` for API design
  - **Priority:** P4

- [ ] **2.17 AskUserQuestion Tool**
  - Implement interactive question asking capability
  - Support choice-based questions with predefined options
  - Support open-ended questions
  - Add timeout and default value handling
  - Integrate with TUI for interactive sessions
  - Write unit tests
  - See `analysis/api-askuserquestion-tool.md` for API design
  - **Priority:** P4

- [ ] **2.18 Development Workflow Tools**
  - Implement RuffTool for linting/formatting operations
  - Implement MyPyTool for type checking
  - Implement ToxTool for multi-version testing
  - Implement MakeTool for Makefile target execution
  - Implement PyPiTool for package publishing
  - All tools use PathGuardrail for path validation
  - All tools have timeout enforcement
  - Write unit tests for each tool
  - See `analysis/api-dev-tools.md` for API design
  - **Priority:** P4

- [ ] **2.19 GitHub Tool**
  - Implement GitHub CLI wrapper tool for repository operations
  - Support read-only operations: repo_view, issue_list/view, pr_list/view, workflow_list/view, release_list/view
  - Use `gh` CLI with `--json` output for structured responses
  - Add operation allowlist guardrail
  - Add timeout enforcement (default 30 seconds)
  - Add result count limits (max 100 for lists)
  - Handle authentication errors gracefully
  - Subprocess execution with list args (no shell=True)
  - Write unit tests
  - See `analysis/api-github-tool.md` for API design
  - See `analysis/security-github-tool.md` for security analysis
  - **Priority:** P4

- [ ] **2.20 Add [start:stop] Arguments to Output-Heavy Tools**
  - Extend offset/limit pattern to tools with large outputs
  - Add `offset` and `limit` parameters to SearchTool results
  - Add `offset` and `limit` parameters to ListTool
  - Use consistent parameter naming (offset/limit)
  - Add result count metadata (total_matches, shown_matches, has_more)
  - Update tool descriptions
  - Write unit tests for pagination edge cases
  - **Priority:** P4

- [ ] **2.22 uv Tool**
  - Implement uv CLI wrapper tool for Python package management
  - Support common operations: install, sync, add, remove, run, venv
  - Add operation allowlist guardrail
  - Add timeout enforcement (default 60 seconds)
  - Use PathGuardrail for virtual environment paths
  - Handle virtual environment activation
  - Add result parsing for structured output
  - Subprocess execution with list args (no shell=True)
  - Write unit tests
  - See `analysis/api-uv-tool.md` for API design
  - **Priority:** P4

### Backend Integration (Phase 3)

- [ ] **3.4 Configurable Components Infrastructure**
  - Create base classes (SetMetadata, ComponentSet, ComponentLoader)
  - Implement resolution strategy (additional_dirs override set)
  - Create directory structure (prompts/sets/, skills/sets/, agents/sets/)
  - Implement metadata.toml parsing
  - Add configuration support to Config schema
  - Write unit tests
  - See `analysis/configurable-components-design.md` for design
  - **Priority:** P5

- [ ] **3.5 Prompt Sets Implementation**
  - Create prompts/sets/default/ with main.md, general-purpose.md, explore.md, plan.md
  - Create prompts/sets/minimal/ with shortened prompts
  - Create prompts/sets/detailed/ with verbose prompts
  - Implement PromptTemplate with variable rendering
  - Implement PromptLoader with set support
  - Integrate with Agent class
  - Write unit tests
  - **Depends on:** 3.4
  - **Priority:** P5

- [ ] **3.6 Skills Sets Implementation**
  - Create skills/sets/default/ with core skills
  - Create skills/sets/minimal/ with essential skills
  - Implement Skill class with frontmatter parsing
  - Implement SkillLoader with set support
  - Integrate with SkillTool
  - Add skill discovery
  - Write unit tests
  - **Depends on:** 3.4
  - **Priority:** P5

- [ ] **3.7 Agent Sets Implementation**
  - Create agents/sets/default/ with main.md, researcher.md, developer.md, reviewer.md
  - Create agents/sets/research/ with research-focused agents
  - Create agents/sets/development/ with development-focused agents
  - Implement AgentDefinition class with frontmatter parsing
  - Implement AgentLoader with set support
  - Integrate with existing agent.py
  - Add tool filtering per agent definition
  - Write unit tests
  - **Depends on:** 3.4
  - **Priority:** P5

- [ ] **3.8 Context Reminders Implementation**
  - Implement ContextReminder protocol
  - Implement SkillsReminder (list available skills)
  - Implement ClaudeMdReminder (global + project CLAUDE.md)
  - Implement CurrentDateReminder
  - Implement WorkingDirectoryReminder
  - Implement GitContextReminder (branch, status)
  - Create ReminderComposer class
  - Integrate with Agent message building
  - Write unit tests
  - See `analysis/context-implementation-plan.md` for design
  - **Priority:** P5

- [ ] **3.9 Lazy Loading Implementation**
  - Implement LazyToolRegistry (load tools on first use)
  - Implement LazySkillLoader (load skills on demand)
  - Create core tools set (Read, List, Search, Existence)
  - Add tool caching after first load
  - Implement get_tools_for_request()
  - Add configuration for lazy vs eager loading
  - Write unit tests
  - **Depends on:** 3.4, 3.5, 3.6, 3.7
  - **Priority:** P5

### Future Features (Low Priority)

- [ ] **2.13.1 Local WebSearch Backend**
  - Implement LocalWebSearchBackend using DDGS library
  - Support multiple search backends (bing, brave, ddg, google)
  - Add rate limiting and error handling
  - Integrate with WebSearchTool via plugin system
  - Write unit tests
  - Note: OllamaWebSearchBackend is working, this is for offline-first
  - **Priority:** P6

- [ ] **2.13.2 Local WebFetch Backend**
  - Implement LocalWebFetchBackend using httpx + Trafilatura
  - Implement content extraction with Trafilatura
  - Add SSRF protection and DNS rebinding defense
  - Integrate with WebFetchTool via plugin system
  - Write unit tests
  - Note: OllamaWebFetchBackend is working, this is for full control
  - **Priority:** P6

- [ ] **R.1 Hermes Agent Comparison**
  - Research Hermes Agent architecture and capabilities
  - Compare Hermes to Yoker architecture
  - Compare Hermes to C3 Agentic Harness approach
  - Document findings in research folder
  - Identify features worth incorporating
  - **Priority:** P6

- [ ] **F.1 Multi-Agent Chat Room Demo**
  - Design multi-agent chat room architecture
  - Implement spawn command in TUI to spawn agent from folder
  - Create agent folder structure for spawned agents
  - Implement agent-to-agent communication protocol
  - Create demonstration scenario
  - **Priority:** P6

---

## Done

### MBI-001 Validation: Package Plugin System (2026-07-03)

**Goal:** Final validation before MBI-001 closure.

- [x] **1.1 Validate with pkgq Project** ✅ (2026-07-03)
  - Test plugin system with pkgq project locally
  - Verify all acceptance criteria work
  - Document any issues found
  - Validated, v0.6.0 released
  **Priority:** P1

- [x] **1.2 Publish Release to PyPI** ✅ (2026-07-03)
  - Finalize pyproject.toml metadata
  - Test installation from source distribution
  - Upload to TestPyPI
  - Upload to PyPI
  - Published v0.6.0 to PyPI
  **Priority:** P1
  **Note:** Requires release manager credentials

### MBI-006 Phase 2: LitellmBackend for Multi-Provider Support (2026-07-01)

**Goal:** Implement `LitellmBackend` wrapping the litellm library to support OpenAI, Anthropic, and 100+ other providers through a unified interface.

**Design source of truth:** `analysis/dual-backend-architecture.md` (Phase 2). This replaces the original Phase 2 (OpenAI backend) and Phase 3 (Anthropic backend) with a single unified approach.

**Architecture decision:** Dual backend — OllamaBackend (Phase 1, native SDK) for Ollama, LitellmBackend (Phase 2, new) for all other providers.

**Out of scope for Phase 2:** Bootstrap wizard provider selection, `build_bootstrap_overrides` provider-awareness, live API model discovery for non-Ollama providers, extending web tools to non-Ollama providers.

#### Tasks

- [x] **[MBI-006] 8.1 Add litellm dependency** ✅ (2026-07-01)
  - Add `litellm>=1.90.0` to `pyproject.toml` dependencies
  - Run `uv sync` to install the dependency
  - Verify litellm supports Ollama, OpenAI, Anthropic in dependency documentation
  - **Acceptance:**
    - `litellm>=1.90.0` in `pyproject.toml`
    - `uv lock` updated with litellm and its transitive dependencies
    - Import `litellm` succeeds in Python environment
  **Satisfies:** Dependency foundation for LitellmBackend
  **Depends on:** —

- [x] **[MBI-006] 8.2 Create LitellmBackend implementation** ✅ (2026-07-01)
  - Create `src/yoker/backends/litellm.py` with `LitellmBackend` class
  - Implement `ModelBackend` Protocol from `backends/protocol.py`
  - Constructor takes Yoker config, extracts provider credentials
  - `provider` property returns current provider name
  - `chat_stream()` method:
    - Map Yoker model to litellm model string (`ollama/llama3.2`, `openai/gpt-4o`, `anthropic/claude-sonnet-4`, etc.)
    - Call `litellm.acompletion()` with streaming enabled
    - Translate `ModelResponseStream` chunks to Yoker `ChatChunk` events
    - Synthesize START/STOP events (litellm only emits deltas)
    - Handle `reasoning_content` for thinking/reasoning models
  - Write unit tests with mocked litellm
  - **Acceptance:**
    - `LitellmBackend` implements all `ModelBackend` Protocol methods
    - Constructor extracts API keys from provider-specific config
    - `chat_stream()` returns `AsyncIterator[ChatChunk]`
    - Model string mapping works for OpenAI, Anthropic, and Ollama prefixes
  **Satisfies:** LitellmBackend core implementation
  **Depends on:** 8.1

- [x] **[MBI-006] 8.3 Implement stream translation** ✅ (2026-07-01)
  - Create `_translate_chunk()` method in LitellmBackend
  - Translate litellm's `ModelResponseStream` to Yoker's `ChatChunk`
  - State tracking for `CONTENT_START`/`CONTENT_STOP` synthesis
  - State tracking for `THINKING_START`/`THINKING_STOP` synthesis (from `reasoning_content`)
  - State tracking for `TOOL_CALL_START`/`TOOL_CALL_STOP` synthesis
  - Emit `USAGE` with `input_tokens`/`output_tokens` from litellm usage stats
  - Emit terminal `DONE` after final chunk
  - Handle litellm exceptions gracefully (network errors, rate limits, auth errors)
  - Write unit tests with recorded chunk sequences
  - **Acceptance:**
    - Delta-only litellm chunks correctly synthesized into START/DELTA/STOP sequences
    - `reasoning_content` mapped to THINKING events
    - Tool calls properly bracketed with START/STOP
    - USAGE event contains token counts from litellm
    - Terminal DONE event always emitted (even on error)
  **Satisfies:** Stream translation layer
  **Depends on:** 8.2

- [x] **[MBI-006] 8.4 Register LitellmBackend in factory** ✅ (2026-07-01)
  - Update `src/yoker/backends/factory.py`
  - Map OpenAI, Anthropic, and other providers to `LitellmBackend`
  - Keep Ollama mapping to `OllamaBackend` (dual backend architecture)
  - Unknown providers default to `LitellmBackend` (leverages litellm's 100+ providers)
  - Import `LitellmBackend` in `backends/__init__.py`
  - Write unit tests asserting correct backend instantiation per provider
  - **Acceptance:**
    - `create_backend(Config(backend=BackendConfig(provider="openai")))` returns `LitellmBackend`
    - `create_backend(Config(backend=BackendConfig(provider="anthropic")))` returns `LitellmBackend`
    - `create_backend(Config(backend=BackendConfig(provider="ollama")))` returns `OllamaBackend`
    - Unknown provider like `"groq"` returns `LitellmBackend` (litellm handles it)
  **Satisfies:** Factory dispatch for dual backend
  **Depends on:** 8.2

- [x] **[MBI-006] 8.5 Preserve base_url trust boundary** ✅ (2026-07-01)
  - Keep existing trust boundary validation from Phase 1 (OllamaBackend)
  - Apply to all providers (not just Ollama)
  - `base_url` warning/confirmation for custom endpoints
  - Batch mode `YOKER_ALLOW_CUSTOM_BASE_URL` environment variable support
  - Document security implications in code comments
  - Write unit tests for trust boundary behavior
  - **Acceptance:**
    - Custom `base_url` triggers warning in interactive mode
    - Batch mode requires `YOKER_ALLOW_CUSTOM_BASE_URL=1` for custom endpoints
    - Behavior consistent across Ollama, OpenAI, Anthropic providers
  **Satisfies:** Security: base_url validation
  **Depends on:** 8.2

- [x] **[MBI-006] 8.6 Configure litellm from Yoker config** ✅ (2026-07-01)
  - Extract API key from provider-specific config (`config.backend.openai.api_key`, `config.backend.anthropic.api_key`, etc.)
  - Map provider-specific parameters to litellm kwargs (`num_ctx`, `budget_tokens`, etc.)
  - Handle `think` flag mapping:
    - OpenAI o-series: `reasoning_effort` parameter
    - Anthropic: `budget_tokens` parameter
    - Other providers: pass through or warn
  - Support all Phase 1 config fields (`model`, `base_url`, `api_key`)
  - Write unit tests for config mapping
  - **Acceptance:**
    - API keys correctly extracted from provider sub-configs
    - Provider-specific parameters passed to litellm
    - `think` flag mapped appropriately per provider
    - Missing API key raises clear `ConfigurationError`
  **Satisfies:** Config → litellm parameter mapping
  **Depends on:** 8.2, 8.4

- [x] **[MBI-006] 8.7 Verify web tools dispatch** ✅ (2026-07-01)
  - Verify web tools (`websearch`/`webfetch`) still work with Ollama (native SDK path)
  - Verify graceful failure for non-Ollama providers
  - `Agent._create_tool_backends()` only populates web backends when `provider == "ollama"`
  - No changes to web tools implementation (they remain Ollama-specific)
  - Write unit tests asserting web tools behavior per provider
  - **Acceptance:**
    - Ollama provider: web tools populated and functional
    - OpenAI provider: web tools not populated (no error)
    - Anthropic provider: web tools not populated (no error)
    - Attempting to use web tools with non-Ollama provider raises clear error
  **Satisfies:** Web tools dual-backend behavior
  **Depends on:** 8.4

- [x] **[MBI-006] 8.8 Update with_model helper** ✅ (2026-07-01)
  - Extend `with_model()` helper from Phase 1 to support LitellmBackend
  - Model override works for all litellm providers (simple prefix change in model string)
  - Ollama model override continues to work (Phase 1 behavior)
  - Write unit tests for all providers
  - **Acceptance:**
    - `with_model(backend, "gpt-4o")` produces correct config for OpenAI
    - `with_model(backend, "claude-sonnet-4")` produces correct config for Anthropic
    - `with_model(backend, "llama3.2")` produces correct config for Ollama
    - Unknown provider model strings work via litellm prefix logic
  **Satisfies:** Provider-agnostic model override
  **Depends on:** 8.4, 8.6

- [x] **[MBI-006] 8.9 Phase 2 verification** ✅ (2026-07-01)
  - Run `make check` end-to-end (format, lint, typecheck, test) — all green
  - Verify no existing tests modified (behaviour unchanged for Ollama path)
  - Write integration tests with mocked OpenAI/Anthropic API responses
  - Optional: integration tests with real OpenAI API (requires API key)
  - Verify `create_backend()` returns `LitellmBackend` for non-Ollama providers
  - Verify `TurnEndEvent` carries `input_tokens`/`output_tokens` from litellm
  - Verify `base_url` trust boundary enforcement
  - **Acceptance:**
    - `make check` green
    - Ollama path unchanged (all existing tests pass)
    - OpenAI backend works end-to-end (mocked or real API)
    - Anthropic backend works end-to-end (mocked or real API)
    - Web tools work with Ollama, fail gracefully with others
    - Native Ollama features preserved (stats, thinking, web tools)
    - Phase 2 acceptance criteria from `analysis/dual-backend-architecture.md` verified
  **Satisfies:** Phase 2 completion gate
  **Depends on:** 8.1-8.8

**Completion Summary (2026-07-01):** All Phase 2 tasks (8.1-8.9) implemented and merged in PR #37. LitellmBackend wraps the litellm library to support OpenAI, Anthropic, and 100+ other providers through a unified interface. Dual backend architecture: OllamaBackend (native SDK) for Ollama, LitellmBackend for all other providers. `make check` green; Ollama path unchanged; OpenAI/Anthropic backends verified end-to-end.

### Completed 2026-06-15

- [x] **16.1 Migrate Configuration System to Clevis** (2026-06-15)
  - Replaced custom yoker/config/ module with Clevis package
  - Migrated config/loader.py to Clevis loader pattern
  - Migrated config/schema.py to Clevis schema with frozen dataclasses
  - Migrated config/validator.py to Clevis validation hooks
  - Preserved custom validation via `__post_init__` on config classes
  - Supported environment variables via TOML interpolation (Clevis native)
  - Implemented configuration discovery: user < project < CLI (Clevis pattern)
  - Ensured minimal breaking changes to public config file format
  - **See:** Issue #16
  - **Satisfies:** Configuration infrastructure modernization

- [x] **3.1 Package Plugin Discovery** (2026-06-15)
  - Import `{package}.yoker` module if present (using importlib)
  - Extract `TOOLS`, `SKILLS`, `AGENTS` lists from module
  - Handle graceful failure when package lacks yoker support
  - Implement namespace format: `{package}:{tool|skill|agent}` (e.g., `pkgq:find`)
  - Register discovered components with respective registries
  - Write unit tests for plugin discovery and registration
  - **See:** Issue #14
  - **Satisfies:** Package integration capability

### Phase 1: UI Module Structure (2026-06-11)

- [x] **UI-001: Create UI module directory structure** (2026-06-11)
  - Created `yoker/ui/` directory with empty `__init__.py`
  - Created placeholder files: `handler.py`, `base.py`, `bridge.py`
  - Reference: analysis/ui-separation-migration.md#phase-1-foundation
  - Acceptance: Directory structure exists, imports work

- [x] **UI-002: Define UIHandler protocol** (2026-06-11)
  - Added `UIHandler` protocol to `yoker/ui/handler.py`
  - Included all methods: lifecycle, input, content output, diagnostic output, streaming
  - Reference: analysis/ui-separation-ui-design.md#1-uihandler-protocol
  - Acceptance: Protocol defined with all required methods, type hints complete

- [x] **UI-003: Create BaseUIHandler abstract class** (2026-06-11)
  - Added `BaseUIHandler` to `yoker/ui/base.py`
  - Implemented state management (turn count, streaming state)
  - Provided default implementations for convenience methods
  - No formatting logic (implementation-specific)
  - Reference: analysis/ui-separation-ui-design.md#3-base-ui-handler
  - Acceptance: Abstract class with state management, clear abstract methods

- [x] **UI-004: Create UIBridge event dispatcher** (2026-06-11)
  - Added `UIBridge` to `yoker/ui/bridge.py`
  - Bridged EventHandler protocol to UIHandler protocol
  - Dispatched events to appropriate UI methods
  - Handled all event types (TURN_START, TURN_END, THINKING_*, CONTENT_*, TOOL_*, ERROR)
  - Reference: analysis/ui-separation-ui-design.md#2-event-bridge
  - Acceptance: Bridge dispatches all event types correctly

- [x] **UI-005: Update exceptions module** (2026-06-11)
  - Verified `YokerError` base exception exists
  - Ensured `NetworkError`, `ToolError`, `ConfigError`, `AgentError`, `SkillError` exist
  - Added `recoverable` attribute to `NetworkError`
  - Reference: analysis/ui-separation-errors.md#2-exception-hierarchy
  - Acceptance: Exception hierarchy complete, documented

- [x] **UI-006: Export UI module public API** (2026-06-11)
  - Updated `yoker/ui/__init__.py`
  - Exported: `UIHandler`, `BaseUIHandler`, `UIBridge`
  - Reference: analysis/ui-separation-migration.md#phase-1-foundation
  - Acceptance: Public API imports correctly

### Phase 2: Content Types and Events (2026-06-15)

- [x] **UI-007: Add content_type to ContentChunkEvent** (2026-06-15)
  - Added `content_type: str = "text/plain"` field to `ContentChunkEvent`
  - Updated event creation in Agent
  - Reference: analysis/ui-separation-io-catalog.md#31-events-with-variable-content-types
  - Acceptance: ContentChunkEvent has content_type field, default "text/plain"

- [x] **UI-008: Verify ToolContentEvent content_type** (2026-06-15)
  - Ensured `ToolContentEvent` has `content_type` field
  - Documented expected content types (text/plain, text/x-diff, application/json)
  - Reference: analysis/ui-separation-io-catalog.md#31-events-with-variable-content-types
  - Acceptance: Field exists, documented in code comments

- [x] **UI-009: Remove ErrorEvent** (2026-06-15)
  - Removed `ErrorEvent` from `events/types.py`
  - Removed any code that emits `ErrorEvent`
  - Replaced with exception raising
  - Reference: analysis/ui-separation-errors.md#7-migration-notes
  - Acceptance: ErrorEvent removed, exceptions used instead

- [x] **UI-010: Create content type detection utility** (2026-06-15)
  - Created `yoker/content_type.py`
  - Implemented `detect_content_type(content: bytes, path: Path) -> str`
  - Library detection, fallback to extension, fallback to text/plain
  - Reference: analysis/ui-separation-io-catalog.md#33-content-type-detection
  - Acceptance: Utility detects content types, fallbacks work correctly

- [x] **UI-011: Update tools to set content_type** (2026-06-15)
  - `ReadTool`: Detect content type from file
  - `WriteTool`: Set content type to summary (or text/plain)
  - `UpdateTool`: Set content type to diff (text/x-diff)
  - `GitTool`: Use `--no-color`, set content type to text/plain
  - Reference: analysis/ui-separation-io-catalog.md#42-tool-implementation
  - Acceptance: All tools set content_type appropriately

### Phase 3: UI Implementations (2026-06-15)

**PR:** #22

#### Interactive UI Tasks

- [x] **UI-012: Create InteractiveUIHandler skeleton** (2026-06-15)
  - Created `yoker/ui/interactive.py`
  - Extended `BaseUIHandler`
  - Initialized Rich console and prompt_toolkit session
  - Reference: analysis/ui-separation-ui-design.md#4-interactive-ui-handler
  - Acceptance: Class skeleton exists, initializes correctly

- [x] **UI-013: Implement interactive input handling** (2026-06-15)
  - Implemented `get_input()` with prompt_toolkit
  - Support multiline input (Esc+Enter)
  - Support command history
  - Handle EOF and KeyboardInterrupt
  - Reference: analysis/ui-separation-ui-design.md#interactive-ui-handler
  - Acceptance: Input works, multiline supported, history works

- [x] **UI-014: Implement interactive lifecycle methods** (2026-06-15)
  - Implemented `start()` - print banner and config info
  - Implemented `shutdown()` - print goodbye message
  - Reference: analysis/ui-separation-ui-design.md#interactive-ui-handler
  - Acceptance: Lifecycle methods display appropriate messages

- [x] **UI-015: Implement interactive content streaming** (2026-06-15)
  - Implemented `start_content_stream()`, `stream_content()`, `end_content_stream()`
  - Use Rich Live display for streaming
  - Handle ANSI codes from LLM output
  - Reference: analysis/ui-separation-ui-design.md#interactive-ui-handler
  - Acceptance: Content streams with live display, ANSI preserved

- [x] **UI-016: Implement interactive thinking streaming** (2026-06-15)
  - Implemented thinking stream methods
  - Show thinking in gray/dim style
  - Respect `show_thinking` setting
  - Reference: analysis/ui-separation-ui-design.md#interactive-ui-handler
  - Acceptance: Thinking streams separately from content

- [x] **UI-017: Implement interactive tool output** (2026-06-15)
  - Implemented `output_tool_call()`, `output_tool_result()`, `output_tool_content()`
  - Respect `show_tool_calls` setting
  - Format tool information appropriately
  - Reference: analysis/ui-separation-ui-design.md#interactive-ui-handler
  - Acceptance: Tool calls and results displayed correctly

- [x] **UI-018: Implement interactive error display** (2026-06-15)
  - Implemented `output_error()` with Rich formatting
  - Handle different error types (NetworkError, ToolError, etc.)
  - Format based on error type and recoverability
  - Reference: analysis/ui-separation-errors.md#42-interactive-implementation
  - Acceptance: Errors displayed with appropriate formatting

#### Batch UI Tasks

- [x] **UI-019: Create BatchUIHandler skeleton** (2026-06-15)
  - Created `yoker/ui/batch.py`
  - Extended `BaseUIHandler`
  - Support stdin/stdout/stderr channels
  - Reference: analysis/ui-separation-ui-design.md#5-batch-ui-handler
  - Acceptance: Class skeleton exists, channels defined

- [x] **UI-020: Implement batch input handling** (2026-06-15)
  - Implemented `get_input()` from stdin
  - Support predefined input messages (set_input_messages)
  - Handle EOF
  - Reference: analysis/ui-separation-ui-design.md#batch-ui-handler
  - Acceptance: Input from stdin works, predefined messages supported

- [x] **UI-021: Implement batch output channels** (2026-06-15)
  - Content → stdout
  - Thinking, errors, stats → stderr
  - No formatting, preserve ANSI
  - Reference: analysis/ui-separation-ui-design.md#batch-ui-handler
  - Acceptance: Output goes to correct channels

- [x] **UI-022: Implement batch streaming** (2026-06-15)
  - Implemented streaming methods (no buffering needed)
  - Direct output to appropriate channels
  - Respect show_thinking, show_tool_calls, show_stats settings
  - Reference: analysis/ui-separation-ui-design.md#batch-ui-handler
  - Acceptance: Streaming works without buffering

#### Shared UI Tasks

- [x] **UI-023: Move LiveDisplay to UI layer** (2026-06-15)
  - Created `yoker/ui/spinner.py`
  - Moved LiveDisplay implementation from `yoker/events/handlers.py`
  - Reference: analysis/ui-separation-migration.md#phase-3-ui-implementations
  - Acceptance: LiveDisplay available to InteractiveUIHandler

- [x] **UI-024: Update UI module exports** (2026-06-15)
  - Updated `yoker/ui/__init__.py`
  - Export: `UIHandler`, `BaseUIHandler`, `UIBridge`, `InteractiveUIHandler`, `BatchUIHandler`
  - Reference: analysis/ui-separation-migration.md#phase-3-ui-implementations
  - Acceptance: All UI classes import correctly

### Phase 4: Refactor Agent Module (2026-06-15)

**PR:** #23

- [x] **UI-025: Create agent package directory structure** (2026-06-15)
  - Created `yoker/agent/` directory
  - Created placeholder files: `__init__.py`, `core.py`, `agent.py`, `processing.py`, `tools.py`
  - Reference: analysis/ui-separation-agent-module.md#2-target-structure
  - Acceptance: Directory structure exists

- [x] **UI-026: Refactor ContextManager to be list-like** (2026-06-15)
  - Modified `ContextManager` to extend `UserList`
  - Implemented `append()` to persist on add
  - Agent sees context as a plain list
  - Reference: analysis/ui-separation-overview.md#4-context-and-contextmanager
  - Acceptance: ContextManager works as list, Agent can use plain list too

- [x] **UI-027: Move AgentCore to agent/core.py** (2026-06-15)
  - Moved `AgentCore` class from `base.py` to `agent/core.py`
  - Included event handler management
  - Included guardrail validation
  - Reference: analysis/ui-separation-agent-module.md#41-agentcorepy
  - Acceptance: AgentCore works in new location

- [x] **UI-028: Extract Agent initialization and properties** (2026-06-15)
  - Created `Agent` class in `agent/agent.py`
  - Moved initialization and property accessors
  - Delegated to AgentCore
  - Reference: analysis/ui-separation-agent-module.md#42-agentagentpy
  - Acceptance: Agent initializes correctly, properties work

- [x] **UI-029: Extract message processing logic** (2026-06-15)
  - Created processing logic module in `agent/processing.py`
  - Extracted streaming, tool calls, event emission
  - Kept as methods on Agent class (not separate)
  - Reference: analysis/ui-separation-agent-module.md#43-agentprocessingpy
  - Acceptance: Processing logic in agent module, not separate file

- [x] **UI-030: Extract tool registry building** (2026-06-15)
  - Created `_build_tool_registry()` in `agent/tools.py`
  - Moved tool initialization logic
  - Reference: analysis/ui-separation-agent-module.md#44-agenttoolspy
  - Acceptance: Tool registry builds correctly

- [x] **UI-031: Remove Agent session lifecycle** (2026-06-15)
  - Removed `begin_session()` and `end_session()` methods from Agent
  - Removed `SessionStartEvent` and `SessionEndEvent` from events
  - Agent lifecycle is create → use → discard
  - Reference: analysis/ui-separation-overview.md#6-agent-lifecycle-no-session
  - Acceptance: No session methods, no session events

- [x] **UI-032: Update context module for list-like interface** (2026-06-15)
  - Created `context/` module
  - Created `manager.py` with `ContextManager` extending `UserList`
  - Created `basic.py` with `BasicContextManager`
  - Created placeholder for `PersistenceContextManager`
  - Reference: analysis/ui-separation-overview.md#45-module-structure
  - Acceptance: Context module structure complete

- [x] **UI-033: Update imports throughout codebase** (2026-06-15)
  - Updated `yoker/__init__.py` to import from `yoker.agent`
  - Updated all imports from old locations
  - Reference: analysis/ui-separation-agent-module.md#54-update-imports
  - Acceptance: All imports work, tests pass

- [x] **UI-034: Remove old files** (2026-06-15)
  - Deleted `yoker/base.py`
  - Deleted `yoker/agent.py`
  - Removed session events from `events/types.py`
  - Reference: analysis/ui-separation-agent-module.md#55-remove-old-files
  - Acceptance: Old files deleted, no references remain

### Phase 5: Slash Commands (2026-06-15)

**PR:** #24

- [x] **UI-035: Create commands directory structure** (2026-06-15)
  - Create `yoker/ui/commands/` directory
  - Create `__init__.py` with command registry
  - Create placeholder files for each command
  - Reference: analysis/ui-separation-migration.md#phase-5-slash-commands
  - Acceptance: Directory structure exists

- [x] **UI-036: Add Agent.inject_skill_context() method** (2026-06-15)
  - Add method to inject skill context into conversation
  - Used by skill invocation commands
  - Reference: analysis/ui-separation-migration.md#phase-5-slash-commands
  - Acceptance: Method works, skill context injected correctly

- [x] **UI-037: Move /help command to UI layer** (2026-06-15)
  - Create `commands/help.py`
  - Move help logic from `__main__.py`
  - Command receives UIHandler, outputs via UIHandler
  - Reference: analysis/ui-separation-migration.md#phase-5-slash-commands
  - Acceptance: /help command works in new location

- [x] **UI-038: Move /think command to UI layer** (2026-06-15)
  - Create `commands/think.py`
  - Move think logic
  - Command sets Agent thinking_mode state
  - Reference: analysis/ui-separation-migration.md#phase-5-slash-commands
  - Acceptance: /think command works

- [x] **UI-039: Move /skills command to UI layer** (2026-06-15)
  - Create `commands/skills.py`
  - Command queries Agent for skill list
  - Outputs via UIHandler
  - Reference: analysis/ui-separation-migration.md#phase-5-slash-commands
  - Acceptance: /skills command works

- [x] **UI-040: Move /context command to UI layer** (2026-06-15)
  - Create `commands/context.py`
  - Command queries Agent for context state
  - Outputs via UIHandler
  - Reference: analysis/ui-separation-migration.md#phase-5-slash-commands
  - Acceptance: /context command works

- [x] **UI-041: Create skill invocation command** (2026-06-15)
  - Create `commands/skill_invoke.py`
  - Handle `/<skill-name>` commands
  - Call `Agent.inject_skill_context()`
  - Reference: analysis/ui-separation-migration.md#phase-5-slash-commands
  - Acceptance: Skill invocation works

- [x] **UI-042: Create command registry** (2026-06-15)
  - Create registry in `yoker/ui/commands/__init__.py`
  - Register all commands
  - Provide dispatch mechanism
  - Reference: analysis/ui-separation-migration.md#phase-5-slash-commands
  - Acceptance: Command registry dispatches commands correctly

### Phase 6: Entry Point Refactoring (2026-06-15)

**PR:** #25

- [x] **UI-043: Add UI configuration to Config** (2026-06-15)
  - Add `UIConfig` dataclass to config
  - Include mode, show_thinking, show_tool_calls, show_stats
  - Reference: analysis/ui-separation-migration.md#phase-6-entry-point-refactoring
  - Acceptance: Config has UI section

- [x] **UI-044: Create run_session() helper** (2026-06-15)
  - Create session loop function
  - Handle exception catching and UI error display
  - Handle cleanup
  - Reference: analysis/ui-separation-migration.md#phase-6-entry-point-refactoring
  - Acceptance: Session loop works with UI handler

- [x] **UI-045: Refactor __main__.py to use UIHandler** (2026-06-15)
  - Create UI handler based on mode (interactive or batch)
  - Create UIBridge and connect to Agent
  - Call `ui.start()` and `ui.shutdown()` directly
  - Remove all print statements
  - Reference: analysis/ui-separation-migration.md#phase-6-entry-point-refactoring
  - Acceptance: __main__.py uses UI handler, no print statements

- [x] **UI-046: Implement mode selection logic** (2026-06-15)
  - Parse CLI arguments for mode
  - Create appropriate UI handler
  - Wire up with Clevis config
  - Reference: analysis/ui-separation-migration.md#phase-6-entry-point-refactoring
  - Acceptance: Mode selection works (interactive vs batch)

- [x] **UI-047: Remove old command dispatch from __main__.py** (2026-06-15)
  - Remove inline command handling
  - Use command registry from UI layer
  - Reference: analysis/ui-separation-migration.md#phase-6-entry-point-refactoring
  - Acceptance: Command dispatch uses registry

### Phase 7: Remove Old Code (2026-06-15)

**PR:** #26

- [x] **UI-048: Remove ConsoleEventHandler** (2026-06-15)
  - Delete `yoker/events/handlers.py`
  - Update `yoker/events/__init__.py`
  - Verify all references removed
  - Reference: analysis/ui-separation-migration.md#phase-7-remove-old-code
  - Acceptance: ConsoleEventHandler removed, no references

- [x] **UI-049: Clean up imports** (2026-06-15)
  - Remove unused imports from all files
  - Update `__all__` exports
  - Reference: analysis/ui-separation-migration.md#phase-7-remove-old-code
  - Acceptance: No unused imports, exports clean

- [x] **UI-050: Remove old code from __main__.py** (2026-06-15)
  - Remove all deprecated code paths
  - Verify no dead code
  - Reference: analysis/ui-separation-migration.md#phase-7-remove-old-code
  - Acceptance: __main__.py is clean, minimal

### Phase 8: Final Polish (2026-06-15)

**PR:** #27

**Goal:** Documentation and examples.

**Dependency:** All previous phases complete

- [x] **UI-051: Update README.md** (2026-06-15)
  - Document interactive mode usage
  - Document batch mode usage
  - Add library usage example
  - Reference: analysis/ui-separation-migration.md#phase-8-final-polish
  - Acceptance: README updated with new usage patterns

- [x] **UI-052: Create batch mode example** (2026-06-15)
  - Create `examples/batch_mode.py`
  - Show batch mode usage
  - Reference: analysis/ui-separation-migration.md#phase-8-final-polish
  - Acceptance: Example works correctly

- [x] **UI-053: Create library usage example** (2026-06-15)
  - Create `examples/library_usage.py`
  - Show how to use yoker as library
  - Reference: analysis/ui-separation-migration.md#phase-8-final-polish
  - Acceptance: Example works correctly

- [x] **UI-054: Create custom handler example** (2026-06-15)
  - Create `examples/custom_handler.py`
  - Show how to implement custom UIHandler
  - Reference: analysis/ui-separation-migration.md#phase-8-final-polish
  - Acceptance: Example works correctly

- [x] **UI-055: Update CLAUDE.md** (2026-06-15)
  - Document new module structure
  - Document UI layer architecture
  - Update current state section
  - Reference: analysis/ui-separation-migration.md#phase-8-final-polish
  - Acceptance: CLAUDE.md reflects new architecture

### Phase 1.7: Async-First Agent Architecture

- [x] **1.7.1 Extract AgentCore Class** (2026-05-23)
  - Created `src/yoker/base.py` with shared state and utilities
  - 51 tests, 98% coverage
  - See: `reporting/1.7.1-agentcore-extraction/summary.md`

- [x] **1.7.2 Async-Only Agent** (2026-05-23)
  - Renamed AsyncAgent to Agent (async-only)
  - All methods are async
  - 1047 tests passing

- [x] **1.7.3 Async Tool Execution** (2026-05-23)
  - All tools converted to async
  - Tool base class has abstract async method

- [x] **1.7.4 Async CLI Integration** (2026-05-23)
  - Created `main_async()` function
  - Uses `prompt_async()` for async input

- [x] **1.7.5 Update Documentation** (2026-05-25)
  - Updated docs/quickstart.md
  - Updated REQUIREMENTS.md

- [x] **1.7.7 Async Event Handler Support** (2026-05-25)
  - Updated ConsoleEventHandler for async operation
  - See: `reporting/1.7.7-async-event-handler/functional-review.md`

- [x] **1.7.8 Async Test Coverage** (2026-05-25)
  - 1047 tests passing, 82% coverage

- [x] **1.7.9 Documentation Updates** (2026-05-25)
  - Async-only architecture documented

- [x] **1.8 Config Auto-Discovery and Agent Definition Path** (2026-05-26)
  - Added `definition` field to `AgentsConfig`
  - Implemented `discover_config()` and `Config.discover()`
  - Environment variable support
  - PR: #13

### Phase 1.6: Documentation

- [x] **1.6.1 Update Documentation Folder**
  - Reviewed and updated all docs/
  - Added feature checkboxes and "Why Yoker?" section
  - See: `reporting/1.6.1-documentation/summary.md`

- [x] **1.6.2 Define Project Rationale**
  - Created rationale document
  - Identified gaps in existing solutions
  - See: `docs/rationale.md`

### Phase 1.5: UI/UX Fixes

- [x] **1.5.1 Remove Thinking Headers**
  - Removed "[thinking]" and "[response]" text headers
  - Used visual styling for thinking sections

- [x] **1.5.2 Fix Mouse Selection in Interactive Mode**
  - Set `mouse_support=False` in PromptSession
  - Text selection works in terminal output
  - See: `reporting/1.5.2-mouse-selection/summary.md`

- [x] **1.5.3 Update Demo Session Script**
  - Updated tool display format
  - Cyan color for tool name
  - Improved replay mode
  - See: `reporting/1.5.3-demo-session/functional-review.md`

- [x] **1.5.4 Event Logging System**
  - Created EventLogger class for JSONL logging
  - EventReplayAgent for full replay
  - See: `reporting/1.5.4-event-logging/summary.md`

- [x] **1.5.5 Show Write/Update Tool Content in CLI** (2026-05-05)
  - Added ToolContentEvent to event types
  - Added ContentDisplayConfig to configuration
  - See: `reporting/1.5.5-write-update-display/consensus.md`

- [x] **1.5.6 Complete Tool Content Display** (2026-05-16)
  - Agent emits ToolContentEvent
  - ConsoleEventHandler displays tool content
  - 47 tests converted from stubs
  - See: `reporting/1.5.6-tool-content-display/summary.md`

### Phase 1: Core Infrastructure

- [x] **1.1 Project Setup**
  - Created Python package structure
  - Set up pyproject.toml
  - Configured development environment

- [x] **1.2 Configuration System**
  - Implemented TOML config loader
  - Defined configuration schema
  - Created example configurations

- [x] **1.3 Agent Definition Loader**
  - Implemented Markdown file parser
  - Parsed YAML frontmatter
  - Created example agent definitions
  - See: `reporting/1.3-agent-definition-loader/summary.md`

- [x] **1.5 Logging System**
  - Integrated structlog for structured logging
  - See: `reporting/1.5-logging-system/summary.md`

### Phase 2: Tool Implementation (Core Tools)

- [x] **2.1 Tool Base Framework**
  - Defined Tool abstract base class
  - Defined ToolResult and ValidationResult types
  - Implemented tool registry

- [x] **2.1.5 Shared PathGuardrail Implementation**
  - Implemented PathGuardrail with config permissions
  - Path traversal prevention, symlinks, blocked patterns
  - See: `analysis/security-list-tool.md`

- [x] **2.2 List Tool**
  - Implemented directory listing
  - Path restriction guardrails
  - See: `analysis/api-list-tool.md`

- [x] **2.3 Read Tool**
  - Implemented file reading
  - Path restriction guardrails
  - See: `reporting/2.3-read-tool/summary.md`

- [x] **2.4 Write Tool**
  - Implemented file writing
  - Overwrite protection, size limits
  - See: `reporting/2.4-write-tool/summary.md`

- [x] **2.5 Update Tool**
  - Implemented file editing operations
  - Exact match validation, diff size limits
  - See: `reporting/2.5-update-tool/summary.md`

- [x] **2.6 Search Tool**
  - Implemented content search (grep-like)
  - Implemented filename search (glob-like)
  - Regex complexity limits, timeout enforcement
  - See: `reporting/2.6-search-tool/summary.md`

- [x] **2.7 Agent Tool**
  - Implemented subagent spawning
  - Recursion depth tracking, timeout handling
  - See: `reporting/2.7-agent-tool/consensus.md`

- [x] **2.8 File Existence Tool**
  - Implemented file/folder existence check
  - Path restriction guardrails
  - See: `reporting/2.8-existence-tool/summary.md`

- [x] **2.9 Folder Creation Tool**
  - Implemented folder creation (mkdir -p)
  - Path restriction guardrails
  - See: `reporting/2.9-mkdir-tool/summary.md`

- [x] **2.10 Git Tool**
  - Implemented Git operations (status, log, diff, branch, show)
  - Permission handlers for write operations
  - Command sanitization
  - See: `reporting/2.10-git-tool/summary.md`

- [x] **2.11 WebSearch and WebFetch Tools Research**
  - Recommended custom implementation
  - See: `analysis/websearch-webfetch-research.md`

- [x] **2.12 WebSearch Tool**
  - Implemented WebSearchTool with OllamaWebSearchBackend
  - WebGuardrail with SSRF protection
  - See: `reporting/2.12-websearch-tool/summary.md`

- [x] **2.12 WebFetch Tool**
  - Implemented WebFetchTool with OllamaWebFetchBackend
  - Domain whitelist/blacklist
  - See: `reporting/2.12-webfetch-tool/summary.md`

- [x] **2.14 Python Tool Research**
  - Recommended subprocess isolation + AST validation
  - 6-layer defense model
  - See: `research/2026-05-05-python-execution-safety/README.md`

### Phase 3: Backend Integration

- [x] **3.1 Ollama Client**
  - Implemented HTTP client for Ollama API
  - Streaming response handling
  - Supports local Ollama and ollama.com with API key

- [x] **3.2 Tool Call Processing**
  - Parse tool call requests from LLM responses
  - Route to appropriate tool implementation
  - Tool call loop with deduplication

- [x] **3.3 Context Management Research**
  - Analyzed logged sessions for context patterns
  - Documented sub-agent context isolation
  - See: `analysis/context-management-research.md`

### Phase 4: Agent Runner

- [x] **4.1 Agent Lifecycle**
  - Implemented Agent class with state management
  - Load agent definition from Markdown file

- [x] **4.2 Main Execution Loop**
  - Implemented message exchange loop
  - Context management, tool call loop

- [x] **4.3 Hierarchical Spawning**
  - Implemented internal depth tracking
  - Fresh context for subagents
  - See: AgentTool implementation

### Standard Project Setup

- [x] **migrate-to-hatchling** (2026-04-29)
  - Migrated from setuptools to hatchling
  - See: `reporting/migrate-to-hatchling/summary.md`

- [x] **migrate-to-uv** (2026-04-30)
  - Migrated from pyenv virtualenv to uv
  - Updated Makefile and CI workflow
  - See: `analysis/uv-migration-checklist.md`

### Issues Completed

- [x] **Issue #7: Config Auto-Discovery and Agent Definition Path** (2026-05-26)
  - Config auto-discovery, environment variables
  - PR: #13

- [x] **Issue #10: Add Type Exports** (2026-05-25)
  - Added AgentDefinition and load_agent_definition exports
  - PR: #12

- [x] **Issue #9: Fix ~ in Storage Path** (2026-05-25)
  - Fixed tilde expansion bug
  - PR: #11


