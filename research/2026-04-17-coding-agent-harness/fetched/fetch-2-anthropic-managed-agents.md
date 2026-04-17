# Anthropic Managed Agents Architecture - Fetched Content

**URL**: https://www.anthropic.com/engineering/managed-agents
**Timestamp**: 2026-04-17T10:03:00Z
**Source**: search-1

---

## 1. Brain-Hands-Session Decoupling Pattern

The architecture separates three components through well-defined interfaces:

- **Brain** (Claude + harness): Calls tools via `execute(name, input) → string`
- **Hands** (sandboxes/tools): Perform actions, provisioned via `provision({resources})`
- **Session** (event log): Durably stores all events via `emitEvent(id, event)`

"Decoupling the brain from the hands meant the harness no longer lived inside the container. It called the container the way it called any other tool."

The harness can recover from failures by calling `wake(sessionId)` to resume, then `getSession(id)` to retrieve the event log.

## 2. Security Boundaries

The coupled design had a critical flaw: "any untrusted code that Claude generated was run in the same container as credentials—so a prompt injection only had to convince Claude to read its own environment."

**Two security patterns implemented:**

1. **Auth bundled with resource**: For Git, "we use each repository's access token to clone the repo during sandbox initialization and wire it into the local git remote."

2. **Vault-based auth**: For custom tools via MCP, "Claude calls MCP tools via a dedicated proxy; this proxy takes in a token associated with the session" and fetches credentials from a secure vault.

"The harness is never made aware of any credentials."

## 3. Session Management

The session is an append-only log that persists beyond Claude's context window:

- `getEvents()`: "allows the brain to interrogate context by selecting positional slices of the event stream"
- `emitEvent(id, event)`: Writes durable records during the agent loop
- `getSession(id)`: Retrieves full event log for recovery

"The session provides... a context object that lives outside Claude's context window. But rather than be stored within the sandbox or REPL, context is durably stored in the session log."

Transformations can be applied before passing events to Claude's context, enabling context engineering while preserving recoverability.

## 4. Sandboxing Approaches

Sandbox became interchangeable "cattle" rather than a "pet":

- Containers provisioned only when needed via tool calls
- If a container fails, "a new container could be reinitialized with a standard recipe"
- Interface supports "any custom tool, any MCP server, and our own tools"

"The harness doesn't know whether the sandbox is a container, a phone, or a Pokémon emulator."

## 5. Scaling Strategies

**Many brains**: "Scaling to many brains just meant starting many stateless harnesses, and connecting them to hands only if needed."

**Many hands**: Each hand is a tool via `execute(name, input) → string`. "No hand is coupled to any brain, brains can pass hands to one another."

This eliminated the assumption that "every resource sat next to" the brain, enabling VPC connections without network peering.

## 6. Performance Metrics

**Time-to-First-Token (TTFT)** improvements after decoupling:

- "p50 TTFT dropped roughly 60%"
- "p95 dropped over 90%"

The optimization came from provisioning containers "only if they are needed" rather than upfront for every session.

## 7. Key Design Principles

1. **Meta-harness philosophy**: "unopinionated about the specific harness that Claude will need in the future"

2. **Stable interfaces for changing implementations**: "We virtualized the components of an agent: a session... a harness... and a sandbox... This allows the implementation of each to be swapped without disturbing the others."

3. **Avoiding stale assumptions**: "harnesses encode assumptions about what Claude can't do on its own. However, those assumptions need to be frequently questioned because they can go stale as models improve."

4. **Programs as yet unthought of**: Following OS design, the goal was "abstractions general enough for programs that didn't exist yet."

5. **Opinionated about interfaces, not implementations**: "We're opinionated about the shape of these interfaces, not about what runs behind them."