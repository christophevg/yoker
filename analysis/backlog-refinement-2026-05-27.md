# Backlog Refinement Session

**Date**: 2026-05-27
**Goal**: Refine the project backlog to ensure optimal organization for value delivery
**Outcome**: MVP-focused reorganization around Issue #14

## Session Summary

This refinement session reorganized the TODO.md from a phase-based structure with many completed items still in the backlog to a clear, MVP-focused timeline.

## Context Analysis

### Initial State

The TODO.md had 11 phases with significant issues:

| Issue | Impact |
|-------|--------|
| Completed phases still in backlog | Confusion about actual remaining work |
| Non-sequential phase numbering (1 → 1.5 → 1.6 → 1.7 → 2) | Difficult to understand progression |
| No clear MVP definition | Unclear what's needed for next release |
| 60+ items across phases | Overwhelming scope |

### Completed Work Discovery

After analysis, significant work was already done:

| Phase | Status | Items |
|-------|--------|-------|
| Standard Project Setup | ✅ Complete | 1 |
| Phase 1.5 UI/UX Fixes | ✅ Complete | 5 |
| Phase 1.6 Documentation | ✅ Complete | 2 |
| Phase 1 Core Infrastructure | ✅ Complete | 5 |
| Phase 1.7 Async Architecture | ✅ Complete | 9 |
| Phase 2 Tool Implementation | 🔄 14/22 done | 14 complete, 8 remaining |
| Phase 3 Backend Integration | 🔄 3/10 done | 3 complete, 7 remaining |
| Phase 4 Agent Runner | ✅ Complete | 3 |
| Phase 5 Polish | ⏳ Not started | 0 |
| Phase 6 Release Prep | ⏳ Not started | 0 |

**Key insight**: 70% of planned work was complete, but buried in a long backlog.

## User Intent Discovery

### Question 1: Refinement Goal

**Asked**: "What is your primary goal for this backlog refinement?"

**Options**:
- Clean up completed items
- Prioritize remaining work
- Plan v1.0 release
- All of the above

**Answer**: Prioritize remaining work

**Reasoning**: User wanted to focus on what's next, not reorganize history.

### Question 2: Release Scope

**Asked**: "What's the target scope for the next release?"

**Answer**: MVP focused on GitHub Issue #14 - Package plugin system for loading tools/skills from Python packages.

**Specific requirements**:
- `yoker --with <package>` CLI argument
- Package provides tools/skills via `{package}.yoker` module
- Skills become slash commands like `/pkgq:create`
- Requires: list, glob, read, write tools (already implemented)

### Question 3: Tool Priority

**Asked**: "Which tools are highest priority for your use cases?"

**Answer**: Skill Tool is the biggest missing piece for MVP.

**Clarification**: User noted "I don't see why this would be specific to C3" - indicating Skill Tool should be generic, not tied to a specific system.

## Technical Analysis

### Issue #14 Deep Dive

**Current state** (from issue description):
```console
% uvx yoker
Using default configuration
Yoker v0.4.0 - Using model: llama3.2:latest
```

**Desired state**:
```console
% uvx --with pkgq yoker --with pkgq
Using default configuration
Yoker v0.4.0 - Using model: llama3.2:latest

> /pkgq:create
```

**Gap analysis**:
| Component | Status | Gap |
|-----------|--------|-----|
| Tools (Read, List, Write) | ✅ Implemented | None |
| Agent definition loader | ✅ Implemented | None |
| Skill infrastructure | ❌ Missing | Full implementation needed |
| Package plugin system | ❌ Missing | Import mechanism needed |
| CLI --with argument | ❌ Missing | Argument parsing needed |
| Skill commands | ❌ Missing | Command routing needed |

### Context Management Research Review

Reviewed `analysis/context-management-research.md` for skill integration patterns:

**Key findings**:
1. Skills are NOT loaded as tools
2. Skills are referenced by name in context reminders
3. Skills are invoked through the `Skill` tool
4. Skill content is loaded on-demand and injected into context

**Implementation pattern**:
```python
# Skills are listed in system reminders
"The following skills are available: c3:start-baseweb-project, c3:pa-session..."

# Skill tool loads skill content when called
class SkillTool(Tool):
    def execute(self, skill_name: str, args: dict):
        skill = self._load_skill(skill_name)
        # Inject skill content as user-level message
        return skill_content
```

**User clarification**: Skills should be introduced as user-level messages in the context, similar to how Claude Code does it.

### Skill Model Decision

**Asked**: "How should skills work in the MVP?"

**Options**:
- Prompt injection (LLM-driven): User invokes skill, content injected into system prompt
- Tool wrapper (call-driven): Skills are callable tools that invoke sub-behaviors

**Answer**: Prompt injection model - skill content introduced as user-level message.

**Reference**: Use existing context management research to understand the pattern.

### MVP Components

**Final decision**: Full MVP with three components:

| Component | Description | Dependencies |
|-----------|-------------|--------------|
| Skill Infrastructure | Skill loader, skill format, context injection | None |
| Package Plugin System | Load packages, discover tools/skills | None |
| CLI Integration | `--with <package>` argument, `/skill` commands | Both above |

**Estimated effort**: 5-8 hours total

## Decisions Made

### 1. Reorganize TODO.md Structure

**Decision**: Create MVP-focused structure with clear timeline.

**Rationale**: 
- Makes release goals explicit
- Separates completed work from active work
- Provides clear priority order

**New structure**:
```
MVP: Package Plugin System (Issue #14)
    ├── Phase 2: Plugin & Skill System
    │   ├── 2.1 Skill Infrastructure
    │   ├── 2.2 Package Plugin System
    │   └── 2.3 CLI --with Argument
    │
    ├── Phase 5: Polish (Post-MVP)
    │   ├── Error Handling
    │   ├── Documentation
    │   └── Testing
    │
    ├── Phase 6: Release Preparation
    │   ├── PyPI Package
    │   └── Examples and Tutorials
    │
    └── Future Work (Post-Release)
        ├── Additional Tools (Phase 2 continued)
        ├── Backend Integration (Phase 3)
        └── Future Features

Done
    ├── Phase 1.7: Async Architecture
    ├── Phase 1.6: Documentation
    ├── Phase 1.5: UI/UX Fixes
    ├── Phase 1: Core Infrastructure
    ├── Phase 2: Tools (Core)
    ├── Phase 3: Backend (Partial)
    ├── Phase 4: Agent Runner
    ├── Standard Project Setup
    └── Issues Completed
```

### 2. Move Completed Phases to Done Section

**Decision**: All completed phases moved to Done section.

**Rationale**:
- Backlog should only contain pending work
- Done section provides project history
- Easier to see what's remaining

**Phases moved**:
- Phase 1.5 UI/UX Fixes (5 tasks)
- Phase 1.6 Documentation (2 tasks)
- Phase 1 Core Infrastructure (5 tasks)
- Phase 1.7 Async Architecture (9 tasks)
- Phase 4 Agent Runner (3 tasks)

### 3. Prioritize Remaining Work

**Decision**: Priority order P1-P6 for future work.

**Rationale**:
| Priority | Work | Reason |
|----------|------|--------|
| P1 | MVP (Issue #14) | Release-blocking |
| P2 | Phase 5 Polish | Release quality |
| P3 | Phase 6 Release Prep | Distribution |
| P4 | Additional Tools | Feature expansion |
| P5 | Configurable Components | Advanced features |
| P6 | Future Features | Nice-to-have |

### 4. Rename Phase 2 for MVP Focus

**Decision**: Create "Phase 2: Plugin & Skill System" for MVP.

**Rationale**:
- Original Phase 2 had 22 tasks, many already done
- New Phase 2 has exactly 3 tasks for MVP
- Clear scope and timeline
- Remaining tool work moved to "Future Work"

### 5. Keep Configurable Components for Later

**Decision**: Phase 3 (Configurable Components) moved to Future Work (P5).

**Rationale**:
- Nice-to-have, not required for MVP
- MVP can work with single prompt/skill/agent set
- Can be added post-release based on user feedback

## Task Breakdown

### Task 2.1: Skill Infrastructure

**Goal**: Enable skill loading and invocation.

**Components**:
1. **Skill format** - Markdown + YAML frontmatter (similar to AgentDefinition)
2. **SkillLoader** - Load from directory, parse frontmatter
3. **Context injection** - User-level message with skill content
4. **Discovery** - `list_skills()` method
5. **Registry** - Track loaded skills

**Estimated time**: 2-3 hours

**Acceptance criteria**:
- Can load skill from `{skill_dir}/{skill_name}.md`
- Skill content injected as user message
- Can list available skills
- Skills namespaced by package

### Task 2.2: Package Plugin System

**Goal**: Load tools/skills from Python packages.

**Components**:
1. **Module import** - Import `{package}.yoker` if present
2. **Extraction** - Get `TOOLS`, `SKILLS`, `AGENTS` lists
3. **Registration** - Add to respective registries
4. **Namespace** - Format `{package}:{component}`
5. **Error handling** - Graceful failure for non-yoker packages

**Estimated time**: 2-3 hours

**Acceptance criteria**:
- Can load package with `yoker` submodule
- Extracts and registers tools/skills/agents
- Namespaced components work correctly
- Handles missing submodule gracefully

### Task 2.3: CLI --with Argument

**Goal**: User-facing CLI integration.

**Components**:
1. **Argument parsing** - Add `--with <package>` to CLI
2. **Multiple packages** - Support `--with pkg1 --with pkg2`
3. **Loading order** - Load before agent starts
4. **Skill commands** - `/skill-name` command routing
5. **Error messages** - User-friendly errors

**Estimated time**: 1-2 hours

**Dependencies**: Tasks 2.1, 2.2

**Acceptance criteria**:
- `yoker --with pkgq` loads package
- `/pkgq:create` invokes skill
- Multiple packages work
- Clear error on package not found

## Timeline

```
Week 1: MVP Development
───────────────────────
Day 1-2: Task 2.1 (Skill Infrastructure)
Day 2-3: Task 2.2 (Package Plugin System)
Day 3:   Task 2.3 (CLI Integration)
Day 4-5: Testing & Polish
───────────────────────
Result: Issue #14 complete

Week 2-3: Polish & Release
───────────────────────
Phase 5: Error handling, documentation, testing
Phase 6: PyPI package, examples
───────────────────────
Result: v1.0 release candidate
```

## Open Questions

### Resolved Questions

1. **What is the MVP scope?** → Issue #14: Package plugin system
2. **How should skills work?** → User-level message injection
3. **What priority order?** → P1: MVP, P2: Polish, P3: Release, P4+: Features
4. **Should completed phases move?** → Yes, to Done section

### Remaining Questions

1. **Glob tool needed?** - SearchTool supports regex patterns; may not need separate glob tool
2. **Skill caching strategy?** - Load once per session or cache across sessions?
3. **Package version validation?** - Issue #14 says "no version validation required"

## Action Items

- [x] Reorganize TODO.md with MVP focus
- [x] Move completed phases to Done section
- [x] Create clear task breakdown for Issue #14
- [x] Document prioritization rationale
- [ ] Implement Task 2.1 (Skill Infrastructure)
- [ ] Implement Task 2.2 (Package Plugin System)
- [ ] Implement Task 2.3 (CLI Integration)

## References

- Issue #14: Feature request for package plugin system
- `analysis/context-management-research.md`: Skill integration patterns
- `analysis/configurable-components-design.md`: Future component architecture
- `TODO.md`: Updated backlog structure

## Appendix: Original TODO.md Structure

```
# Original Structure (before refinement)

## Backlog
- Standard Project Setup (1 item)
- Phase 1.5: UI/UX Fixes (5 items) ← ALL COMPLETE
- Phase 1.6: Documentation (2 items) ← ALL COMPLETE
- Phase 1: Core Infrastructure (5 items) ← ALL COMPLETE
- Phase 1.7: Async Architecture (9 items) ← ALL COMPLETE
- Future Features (4 items)
- Phase 2: Tool Implementation (22 items, 14 complete)
- Phase 3: Backend Integration (10 items, 3 complete)
- Phase 4: Agent Runner (3 items) ← ALL COMPLETE
- Phase 5: Polish (3 items)
- Phase 6: Release Preparation (2 items)

## Done
- [25 individual completed items, unorganized]

# New Structure (after refinement)

## MVP: Package Plugin System (Issue #14)
- Phase 2: Plugin & Skill System (3 items)
- Phase 5: Polish (3 items)
- Phase 6: Release Preparation (2 items)
- Future Work (21 items)

## Done
- [Organized by phase, clear history]
```

**Improvement**: Clear timeline, focused MVP, organized history.