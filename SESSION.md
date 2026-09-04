# Yoker Session Notes

## What this file is for

Agents record here any project-specific, session-level information they want the NEXT
session to be informed of. Update it when session-worthy knowledge emerges. Typical
entries: warnings that tools may be unstable right after a major refactoring (with the
instruction to stop and report immediately if problems occur), pointers to in-flight
work, environment quirks.

Entries below are ordered newest first; keep them short and dated.

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
