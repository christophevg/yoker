# Monitoring Usage & Run Statistics

Yoker records what happens during a run in two complementary channels: the
**telemetry log** (an append-only JSONL file of events) and the **context
log** (the conversation state file). This guide explains both and the tools
you and your agents have to read them.

## The telemetry log

Every yoker session appends records to `~/.yoker/usage.jsonl` (configurable
via `[usage] path` in `yoker.toml`; enabled by default). One record per
line, written atomically — safe under concurrent sessions.

Each record carries a `kind` and, where applicable, the session-assigned
agent identity (`agent_id` + `parent_agent_id`):

| kind | records | carries |
|------|---------|---------|
| `llm_call` | One row per LLM API call | `input_tokens`, `output_tokens`, `duration_ms`, model, agent |
| `tool_call` | One row per tool execution | `tool`, `success`, `duration_ms`, `bytes_in`/`bytes_out` |
| `turn` | One row per completed agent turn | wall-clock `duration_ms`, `llm_calls`, `tool_calls_count` — **no tokens** |
| `spawn` / `release` | Agent lifecycle | parent linkage, requester |
| `run_start` / `run_end` | One bracket per session | pid, `outcome` (completed/error), run duration, agents-active |
| `compaction` | One row per compaction run | per-stage impact report in `detail` |
| `error` | Operational errors | idle-watchdog timeouts, retry-limit escalations |

Two invariants make the log trustworthy:

- **Tokens appear only on `llm_call` rows.** Summing the log counts every
  token exactly once — `turn` rows deliberately carry none.
- **The run bracket closes.** `run_end` is written before agent teardown,
  so a `run_start` without a matching `run_end` means the process died
  before clean shutdown — the crash signature.

## The `stats` tool (agent-facing)

Agents can read their own statistics via the Session-injected
`yoker:stats` tool — the same tool your own yoker agent has (it appears
in the tool list as `stats`). Three scopes:

- `self` — the calling agent only
- `subtree` — the calling agent plus everything it spawned, directly or
  transitively (resolved from spawn records and the live session map; a
  child released earlier still counts)
- `session` — all agents in the session, including spawn/release counts
  and peak agent concurrency (session scope additionally reports the
  caller's own numbers, so an agent sees itself in session perspective
  without a second call)

Optional `since` watermark (ISO-8601): counts only records strictly after
that timestamp. The classic pattern for delta measurements — call `stats`,
remember the timestamp, call again later, and diff:

```
stats(scope="self")                       # baseline (note the ts of this call)
... do work ...
stats(scope="self", since="<that ts>")    # what this agent did since then
```

The tool is read-only and never writes to the log. Like the other
session tools (`agent`, `send_message`, `release_agent`), it is stripped
when an agent definition declares an explicit `tools:` list that does not
grant it.

## Reading the log yourself

### Token/cost report

The Makefile target wraps the bundled report script:

```bash
make usage            # per-model totals: calls, tokens, cost
make usage ARGS=...   # (script accepts a custom file + --json)
```

Or directly: `uv run python scripts/usage_report.py [--json]` — reads
`~/.yoker/usage.jsonl` by default and applies Ollama pricing from
`scripts/ollama_pricing.json`.

### Crash detection

Find a `run_start` without a matching `run_end`:

```bash
jq -r 'select(.kind=="run_start" or .kind=="run_end") | [.kind, .ts, .session_id] | @tsv' \
  ~/.yoker/usage.jsonl | tail -20
```

An unpaired `run_start` with a pid that is no longer alive = crashed run.
`detail.outcome` on `run_end` tells you whether the body completed or
errored.

### Per-agent attribution

```bash
jq -r 'select(.kind=="llm_call") | .agent_id // "legacy"' ~/.yoker/usage.jsonl | sort | uniq -c
```

Rows from sessions predating the per-agent identity feature carry no
`agent_id` (`legacy` above) — they count toward session-scope totals but
cannot be attributed per agent.

## The context log (session state)

Session state lives under `~/.cache/yoker/sessions/<session-id>.jsonl`
(configurable via `[context] storage_path`). Unlike the telemetry log it
is a **state** file, rewritten on change — use it for conversation
replay and compaction inspection (`python scripts/context_report.py
<session.jsonl> [--json]`), not for timing analysis. Timing belongs to
the telemetry log.

## Disabling or relocating

```toml
[usage]
enabled = false          # stop telemetry collection entirely
path = "/var/log/yoker/usage.jsonl"   # relocate the log
```