# Yoker Session Notes

## What this file is for

Agents record here any project-specific, session-level information they want the NEXT
session to be informed of. Update it when session-worthy knowledge emerges. Typical
entries: warnings that tools may be unstable right after a major refactoring (with the
instruction to stop and report immediately if problems occur), pointers to in-flight
work, environment quirks.

Entries below are ordered newest first; keep them short and dated.

---

## 2026-09-14 — compact_ratio hysteresis added; session restart required before behavior is live.

---

## 2026-09-12 — Tool-parameter schema bug fixed: restart between fixes required

The "Invalid content parameter" bug had a chain of three causes, all fixed
and live-verified in this session:

1. `schema.py` `_build_parameter_schema` stripped "Annotated metadata" from
   any subscripted generic, so bare `dict[str, str] | None` (make's
   `env_vars`) was declared `{"type": "string"}` — models correctly sent
   JSON strings, the tool rejected them.
2. The Ollama backend compensated with blunt per-value coercion, which
   mangled legitimate JSON strings for `write.content`.
3. Terse error messages ("Invalid content parameter") gave models no way
   to self-correct.

Now: schema declares real types (make.env_vars → object), per-value
coercion is schema-aware in `_processing._coerce_schema_aware_args`
(rescues legacy string-encoded objects only for object/array-typed
params), and type-mismatch errors name the type + json.dumps remedy.

**Session-worthy lesson**: after EACH of the three fixes, a session
restart was needed before its behavior was live (schema built at agent
startup; harness code loaded at startup). When a live test still fails
after a fix, verify which fix-layer is stale before re-fixing — and
record in SESSION.md which restarts are pending if work spans multiple
fixes.

---

## 2026-09-04 — Dogfooding phase active

We are in a dogfooding phase: we fix problems in Yoker with Yoker. Fixes to
the harness are NOT active in the running session — new code loads only
after a restart. If a fix needs testing, FIRST ask the owner to restart the
session (`--resume` reloads context with the new code active).

Related guidance while dogfooding:

- Don't look for workarounds — address the problem first. You are working
  on your own codebase: you can check the tool's source to confirm a
  failure. If a tool sub-operation is missing: report it, so we can decide
  to add it first.
- Don't spawn a random agent to do something no tool supports.
