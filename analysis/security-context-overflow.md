# Security Review: IP-12 Context Overflow Management

Cross-domain design review (security-engineer) for IP-12 from MBI-008.
Branch: master @ 4b634f6.

## Owner's Proposal (quoted verbatim from `analysis/mbi-prompt-sets.md`)

> R12a: The framework must provide default context overflow management (drop oldest non-system messages when over threshold) without requiring a prompt set template. If the backend supports the `context_management` API field, pass through the thinking token clearing directive.

> Framework default: drop oldest non-system messages when over threshold (keeping first user message with config injections)

> If backend supports `context_management` API field (Anthropic), pass through thinking token clearing directive
> If backend does not support it, strip thinking blocks from message history programmatically
> Optional `on_context_overflow` hook for prompt sets that want custom truncation strategies

> Framework responsibility (always active):
> - Estimate context size before each request (heuristic or tokenizer-based)
> - If over threshold, drop oldest non-system messages (keeping the first user message with config injections)
> - If the backend supports `context_management`, pass through the thinking token clearing directive
> - If the backend does not support it, strip thinking blocks from message history programmatically

> Prompt set hook (optional, for advanced strategies):
> - `on_context_overflow` hook fires with message_count, estimated_tokens, max_tokens, messages
> - If the prompt set provides a `context_overflow.j2` template, it can return a modified message list
> - If no template, the framework's default truncation applies
> - This is an extension point, not the primary mechanism

Owner-stated worry (D3): the owner's initial mental model was that compaction is LLM-driven; the research corrected this. The owner explicitly chose framework-driven truncation over LLM summarization.

## Executive Summary

The proposal is sound and aligns with how Claude Code itself behaves. The default
truncation strategy preserves the safety-critical message positions (system prompt +
first user message with config injections). The main security-relevant risks are
(a) precisely which messages qualify as "non-system" and must be protected from
dropping, (b) integrity of the `on_context_overflow` hook output, and (c) a cheap
DoS-resistance property for the per-request size check. No critical vulnerabilities;
three Medium findings, all addressable inside the owner's proposal without adding
new abstractions.

## Threat Analysis (STRIDE-filtered)

### Tampering — Truncation of safety-critical messages

**Concern.** The framework drops "oldest non-system messages" but keeps "the first
user message with config injections" and "the system message." In Yoker today
(`context/manager.py`, `context/basic.py`), safety-relevant content lives in:

1. The single collapsed `system` message (`SimpleContextManager.setup_initial_context`)
   that fuses the environment reminder + the agent definition (`<agent-definition>…`).
   This is the primary safety policy carrier.
2. The skill-discovery `user` message appended by `add_skill_discovery_block()` —
   also a first-user-position message in practice (it's added right after the
   system message at agent setup).
3. The first real user turn.

The owner's proposal keeps "system messages" and "the first user message." That
covers (1) and (3). It does **not** explicitly cover (2) the skill-discovery user
message — which is a `user`-role message that sits between the system message and
the first user turn. If the truncator treats "first user message" as "first
`role=user` in the list," the skill block is preserved. If it treats it as "first
*real* user turn" and skips injected user-role scaffolding, the skill discovery
block could be dropped — losing skill context that the agent was told it has.

**Severity:** Medium (CVSS ~5.0). Not a direct exploit, but a quiet regression of
an existing safety/behavior contract.

**Recommendation (no new abstraction).** Specify the truncation invariant
precisely in the framework, using message *roles* the codebase already produces:

> "Keep all `role=system` messages, plus the contiguous prefix of `role=user`
> scaffolding messages emitted during agent setup (system-prompt collapse + skill
> discovery), plus the first real user turn. Drop the oldest *other* messages
> first."

Concretely: drop from the **tail** of the assistant/tool/user-turn sequence, never
from the setup prefix. "Oldest" should mean "most recent in time is kept" — i.e.
drop the oldest *non-setup* messages. (The CC research finding supports this: "CC
keeps the first user message … and the system message … and drops everything
else.") A simple implementation: walk the list from the end, drop entries with
`role` in `{assistant, tool, user (real turns)}` until under threshold, never
touch index 0 (system) and the contiguous `role=user` block immediately after it.

This is a specification refinement, not a new guard.

### Tampering / Elevation of Privilege — Exploitation via truncation by flooding

**Concern.** An attacker (or a compromised/misbehaving tool) could emit very large
tool outputs to fill the context, triggering truncation that drops earlier
safety-relevant assistant reasoning or earlier user instructions — effectively
shaping what the model "remembers." With the setup-prefix protection above, the
system prompt and skill discovery are safe; but earlier *user turns* and
*assistant reasoning* (including, e.g., an earlier "do not do X" instruction from
the user) can still be pushed out.

**Severity:** Medium (CVSS ~5.5). This is inherent to any fixed-window context
management strategy (CC has the same property). The mitigations available are:
(a) per-tool output size caps (Yoker already has `max_output_kb` on `make` and
`github`, `max_size_kb` on `webfetch`, `max_content_bytes` on content display), and
(b) dropping *oldest* first means a flood of recent tool output evicts *older*
context, not the system prompt — which is the correct direction for safety.

**Recommendation.** No new framework guard. This is the owner's proposal working
as designed. The existing per-tool output caps are the right control point. Two
operational notes for the implementer:

- Document that the truncation order is "drop oldest non-setup first," so a flood
  evicts history, not policy.
- Consider a per-message size cap when *estimating* context size, so a single
  pathological 2 MB tool result doesn't blow the threshold in one step before
  truncation can react. This is an implementation detail, not a design change.

### Information Disclosure — Cross-context leakage via truncation

**Concern.** If the truncation mutates the in-memory `_messages` list in place and
a `fork`-isolation spawn copies the truncated list, could a child see a partially
truncated parent context? Conversely, could dropping history cause the model to
"forget" that it was told not to reveal something?

**Severity:** Low (CVSS ~3.0). Isolation is governed by `SessionConfig.default_isolation_policy`
(`fresh` vs `fork`) which is a separate mechanism. Truncation operates on one
agent's `_messages`; it does not mix agents. The "forgetting an earlier
instruction" risk is the same as the flooding case above — inherent to fixed
windows, mitigated by setup-prefix protection.

**Recommendation.** No new guard. The implementation should truncate on a copy
emitted by `get_context()` (which already returns `list(self._messages)`), not
mutate `_messages` in place — this preserves the persisted history and the
session's audit trail. State this as an implementation invariant, not a security
feature.

### Repudiation — Audit trail for truncation events

**Concern.** If the framework silently drops messages, an observer reviewing the
session log cannot tell what was removed and when. This matters for incident
forensics ("why did the agent do X?") more than for attack prevention.

**Severity:** Low (CVSS ~2.5).

**Recommendation.** Emit a new event type (e.g. `CONTEXT_OVERFLOW_EVENT`) when
truncation fires, carrying `dropped_count`, `estimated_tokens_before`,
`estimated_tokens_after`. The event system (`events/types.py`) already has
lifecycle events; one more is consistent. This is optional for the owner — it's
observability, not a security control. Flagging as a Related finding.

### Denial of Service — Per-request size estimation cost

**Concern.** The proposal says "estimate context size before each request
(heuristic or tokenizer-based)." A full tokenizer pass on every request, on every
message, is O(n) per turn and O(n²) over a long session — a self-DoS vector for
long-running sessions, and a real cost for an agent in a tight tool loop.

**Severity:** Low (CVSS ~2.5). The owner already hedged ("heuristic or
tokenizer-based").

**Recommendation.** Use a cheap heuristic (chars/4 or similar) for the threshold
check, not a real tokenizer. Only invoke a tokenizer if a backend specifically
requires exact counts. This is an implementation note; no design change.

### The `on_context_overflow` hook — Abuse surface

**Concern.** A prompt set's `context_overflow.j2` returns a "modified message
list." Risks: (a) the template could inject attacker-controlled content into the
system prompt position; (b) the returned list could be malformed (wrong roles,
missing tool_call/tool_result pairing) and crash the backend or break tool-use
invariants; (c) the template runs with the same Jinja2 trust as other prompt-set
templates.

**Mitigation already present.** Prompt sets are distributed via plugins, and
plugins go through the existing trust gate (`plugins/security.py`: global opt-in
+ per-plugin `[plugins.trusted]` table + non-interactive deny-by-default). A
prompt set is only loaded if its plugin is trusted. So the hook is not an
unauthenticated attack surface; it's a trusted-extension point, same as every
other IP-1..IP-13 template.

**Severity:** Low (CVSS ~2.5) given the trust gate.

**Recommendations (all inside the owner's proposal).**

1. **Validate the hook's return shape.** The framework must verify the returned
   list is a valid message list (roles in `{system, user, assistant, tool}`, each
   assistant `tool_calls` entry has a matching `tool` result, no orphaned
   `tool_id`s). On validation failure, fall back to the framework's default
   truncation and log the event. This is the single non-trivial guard the hook
   earns, because a malformed message list can crash the backend request path —
   a concrete, documented threat (broken tool-use pairing → backend 400 → agent
   loop deadlock), not defense-in-depth.
2. **Never let the hook drop `role=system` messages.** Enforce the same
   setup-prefix invariant as the default strategy on the hook's output. A hook
   that tries to drop system messages is overridden for those messages only.
3. **Jinja2 sandboxing.** If not already in use for IP-1..IP-13, use
   `jinja2.sandbox.SandboxedEnvironment` for prompt-set templates (prompt-set
   templates are trusted, but sandboxing is cheap insurance against template
   authoring mistakes that could exfiltrate via `{{ }}` attribute access). Flag
   as Related — applies to the whole prompt-set system, not just IP-12.

### Thinking-block stripping — Safety implications

**Concern.** Programmatically stripping `thinking` fields from message history
(when the backend lacks `context_management`) removes the model's prior reasoning
trace. Could this cause the model to repeat an unsafe action it had previously
reasoned *against*?

**Severity:** Low (CVSS ~2.0). The thinking trace is not a safety control — it's
intermediate state. The model's *decisions* are in the assistant `content`. CC
itself does this server-side via `clear_thinking_20251015` with `keep: "all"` (per
the D3 research), and the owner's proposal mirrors that behavior client-side for
non-Anthropic backends. The model has the same final-content history either way.

**Recommendation.** No new guard. This is the owner's proposal matching CC. One
implementation note: strip only `thinking` fields, never `content`. Preserve the
assistant message itself. State this as an invariant.

## Findings Classification

| Finding | Classification | Action |
|---------|---------------|--------|
| Skill-discovery user message not explicitly protected by truncation invariant | Blocking | Specify setup-prefix invariant before implementing |
| Hook return-shape validation (orphaned tool_id, role validation) | Blocking | Add to hook call site |
| Hook must not drop system messages | Blocking | Enforce on hook output |
| Truncate on `get_context()` copy, not `_messages` in place | Related | Implementation invariant |
| Emit `CONTEXT_OVERFLOW_EVENT` for audit | Related | Optional, owner's call |
| Heuristic (not tokenizer) for per-request size check | Related | Implementation note |
| Jinja2 `SandboxedEnvironment` for all prompt-set templates | Related (applies to all IPs) | Apply system-wide, not just IP-12 |
| Per-message size cap when estimating | New (backlog) | Consider if flooding becomes a real problem |

## Positive Observations

- The owner chose framework-driven truncation over LLM-driven summarization,
  eliminating an entire class of prompt-injection-via-summarization risks (the
  summarizer could be tricked into "summarizing" safety policy away).
- The existing per-tool output caps (`max_output_kb`, `max_size_kb`,
  `max_content_bytes`) already provide the flooding mitigation at the right
  control point.
- The plugin trust gate already covers the `on_context_overflow` hook — no new
  trust mechanism is needed.
- The `get_context()` method already returns a copy, making "truncate on copy"
  trivially achievable.

## Security Open Questions for the Owner

1. **Setup-prefix invariant wording.** Confirm the precise set of messages the
   truncator must never drop: "all `role=system` messages + the contiguous
   `role=user` scaffolding block emitted during agent setup (system-prompt
   collapse + skill discovery) + the first real user turn." Is the skill
   discovery block (`add_skill_discovery_block`) in scope to protect, or is it
   acceptable to drop it under pressure? (Recommend: protect it.)

2. **Hook output validation strictness.** When `context_overflow.j2` returns a
   malformed list, do you want (a) fall back to default truncation + log warning,
   or (b) hard error and abort the turn? (Recommend (a).)

3. **Truncation audit event.** Emit a `CONTEXT_OVERFLOW_EVENT` for observability,
   or keep truncation silent to avoid event-stream noise? (Recommend emit —
   matches existing event-rich design and helps incident forensics.)

4. **Where does the size check live?** In the context manager (so it's
   backend-agnostic and tested in isolation) or in `_processing.py` just before
   `_chat_stream`? (No security difference; simplicity suggests context manager
   as the single source of truth for `_messages`.)

## Files Reviewed

- `/Users/xtof/Workspace/agentic/yoker/analysis/mbi-prompt-sets.md` (IP-12, D3, R12a, T3.5)
- `/Users/xtof/Workspace/agentic/yoker/src/yoker/context/manager.py`
- `/Users/xtof/Workspace/agentic/yoker/src/yoker/context/basic.py`
- `/Users/xtof/Workspace/agentic/yoker/src/yoker/context/validator.py`
- `/Users/xtof/Workspace/agentic/yoker/src/yoker/context/persisted.py`
- `/Users/xtof/Workspace/agentic/yoker/src/yoker/core/_processing.py`
- `/Users/xtof/Workspace/agentic/yoker/src/yoker/events/types.py`
- `/Users/xtof/Workspace/agentic/yoker/src/yoker/config/__init__.py`
- `/Users/xtof/Workspace/agentic/yoker/src/yoker/backends/protocol.py`
- `/Users/xtof/Workspace/agentic/yoker/src/yoker/plugins/security.py`