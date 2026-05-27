# Consensus Summary: Task 2.1 Skill Infrastructure

**Task**: 2.1 Skill Infrastructure
**Priority**: P1 (MVP Phase 2)
**Context**: Package Plugin System (Issue #14)
**Date**: 2026-05-27
**Status**: Ready for Implementation

## Executive Summary

Both API and security reviews agree on the core approach: skills are **context injection modules** (not tools or agents) that inject guidance into LLM conversations via user-level messages. The infrastructure mirrors the existing `AgentDefinition` pattern, leveraging proven security controls from `agents/loader.py` and `PathGuardrail`.

**Key Insight**: Skills differ from Claude Code's implementation only in namespace handling. Claude Code uses `c3:{skill}` format; yoker will use `{package}:{skill}` for package-provided skills and plain names for user/project skills.

## Agreed Approach

### 1. Skill Definition Pattern

Skills are Markdown files with YAML frontmatter, following the `AgentDefinition` pattern:

```markdown
---
name: git-commit
description: Guide git commit operations with atomic commits
triggers:
  - "commit changes"
  - "create a commit"
  - "/commit"
tools:
  - Bash
  - Read
---

## Purpose
Create well-structured git commits with clear messages.

## Workflow
1. Stage changes
2. Write message
3. Verify
4. Commit
```

**Rationale**: Mirrors existing agent definition pattern, enables skill discovery, allows optional metadata (triggers, tools).

### 2. Architecture

```
src/yoker/
  skills/
    __init__.py          # Public API exports
    schema.py            # Skill dataclass (frozen)
    loader.py            # load_skill(), load_skills()
    registry.py          # SkillRegistry class
    injection.py         # inject_skill_context(), inject_skills_listing()
```

**Key Components**:
1. **Skill dataclass** (`schema.py`): Immutable skill definition
2. **SkillLoader** (`loader.py`): Parse frontmatter, validate fields, load from directories
3. **SkillRegistry** (`registry.py`): Register, list, lookup skills
4. **Context injection** (`injection.py`): Inject skill content into user messages

### 3. Context Injection Pattern

Skills inject context via `<skill>` tags in user-level messages:

```python
# Skills listing (always injected)
<system-reminder>
The following skills are available for use with the /skill command:

- git-commit: Guide git commit operations
- research: Research topics comprehensively
</system-reminder>

# Skill invocation (on-demand via /skill-name)
<skill>
# git-commit

## Purpose
Create well-structured git commits...
</skill>
```

**Why user-level messages?**
- No system prompt modification
- Skills visible to LLM but don't affect agent definition
- Lightweight (~500 bytes for 10 skills listing, 1-3KB per skill invocation)

### 4. Namespace Strategy

**Two-tier naming**:
- **Project/User skills**: Plain names (`git-commit`, `research`)
- **Package skills**: Namespaced (`pkgq:find`, `c3:research`)

**Priority on conflict**:
1. Project skills (highest priority)
2. User skills
3. Package skills (lowest priority)

**Example**: If `./skills/research.md` exists and `c3` package provides `research` skill:
- `/research` invokes project skill (higher priority)
- `/c3:research` invokes package skill (namespaced)

## Key Design Decisions

### From API Review

1. **Skill != Tool**: Skills provide guidance; tools execute actions
   - **Tool**: `git status` → Returns repository status
   - **Skill**: `git-commit` → Injects commit workflow guidance
   - **Agent**: Developer agent → Autonomously implements feature

2. **Frozen dataclass for immutability**: Matches `AgentDefinition` pattern

3. **`yaml.safe_load()` for all YAML parsing**: Prevents arbitrary code execution (critical security control)

4. **Skill registry per agent**: Allows different agents to have different skills

5. **No modification to system prompts**: Skills inject via user-level messages

6. **Built-in skills directory**: `src/yoker/skills/builtin/` for default skills

7. **Graceful failure on missing skills**: Log warning, continue without built-in skills

### From Security Review

1. **Critical Security Controls** (MUST implement):

   | ID | Requirement | Implementation |
   |----|-------------|----------------|
   | SEC-1 | Use `yaml.safe_load()` | `skills/loader.py:parse_frontmatter()` |
   | SEC-2 | Validate skill directories | Use `PathGuardrail` for allowed paths |
   | SEC-3 | Enforce skill size limits | Reject skills >100KB |
   | SEC-4 | Resolve symlinks before validation | `os.path.realpath()` before path check |
   | SEC-5 | Namespace package skills | `{package}:{skill}` format |

2. **Trust Levels** (SHOULD implement):

   ```python
   class SkillTrust(Enum):
       PROJECT = "project"  # Skills in ./skills/ - medium trust
       USER = "user"        # Skills in ~/.yoker/skills/ - high trust
       PACKAGE = "package"  # Skills from packages - low trust
   ```

3. **Content Pattern Blocking** (SHOULD implement):

   Block known malicious patterns:
   ```python
   BLOCKED_SKILL_PATTERNS = (
       r"read.*\.env",          # Read env files
       r"read.*\.ssh",          # Read SSH keys
       r"send.*https?://",      # Exfiltration
       r"curl.*\|",             # Command injection
       r"eval\s*\(",            # Code execution
   )
   ```

4. **Audit Trail** (SHOULD implement):

   Log skill loading with content hashes:
   ```python
   log.info("skill_loaded", path=path, hash=content_hash, size_kb=size)
   ```

## Security Requirements (MUST Implement)

### Critical Requirements (Blocking)

**SEC-1: Safe YAML Parsing**
- **What**: All YAML parsing MUST use `yaml.safe_load()`
- **Why**: Prevents arbitrary code execution via YAML deserialization
- **CVEs**: CVE-2017-18342, CVE-2020-1747, CVE-2020-14343
- **Implementation**: `skills/loader.py:parse_frontmatter()`
- **Verification**: Static analysis check, security test

**SEC-2: Directory Validation**
- **What**: Skill directories MUST be validated against allowed filesystem paths
- **Why**: Prevents path traversal attacks, loading from sensitive locations
- **Implementation**: Reuse `PathGuardrail._is_within_allowed_paths()`
- **Verification**: Unit test attempting to load from `/etc/`

**SEC-3: Content Size Limits**
- **What**: Skill content MUST be limited to 100KB maximum
- **Why**: Prevents resource exhaustion, DoS attacks
- **Implementation**: Check `len(content.encode('utf-8')) / 1024 <= 100`
- **Verification**: Unit test with skill >100KB

**SEC-4: Symlink Resolution**
- **What**: Symlinks in skill directory paths MUST be resolved before validation
- **Why**: Prevents symlink attacks that escape allowed paths
- **Implementation**: `Path(os.path.realpath(directory))`
- **Verification**: Unit test with symlink escaping allowed directory

**SEC-5: Namespace Prefix**
- **What**: Package-provided skills MUST use namespace-prefixed names
- **Why**: Prevents package skills from overriding user/project skills
- **Format**: `{package}:{skill}` (e.g., `pkgq:find`)
- **Verification**: Integration test with package plugin

### High Priority Recommendations (SHOULD Implement)

**SEC-6: Content Pattern Blocking**
- Block known malicious patterns in skill content
- Defense-in-depth against prompt injection
- Log warning but don't reject (user may have legitimate reason)

**SEC-7: Trust Levels**
- Implement `SkillTrust` enum for skill sources
- Enable differentiated security policies
- Log trust level when loading skill

**SEC-8: Audit Trail**
- Log all loaded skills with content hashes
- Enable forensic analysis of skill usage
- Include: path, hash, size, trust level

**SEC-9: World-Writable Directory Warning**
- Check if skill directory is world-writable
- Log warning (security best practice)
- Don't reject (user may have legitimate reason)

**SEC-10: Package Skill Warning**
- Warn when loading skills from external packages
- User awareness of potential risks
- Log: package name, skill count, skill names

## Implementation Order

### Phase 1: Core Infrastructure (MVP)

1. **Create module structure**:
   ```
   src/yoker/skills/
     __init__.py          # Export Skill, load_skill, load_skills, SkillRegistry
     schema.py            # Skill dataclass (frozen)
     loader.py            # parse_frontmatter, load_skill, load_skills
     registry.py          # SkillRegistry class
   ```

2. **Implement Skill dataclass** (`schema.py`):
   - Frozen dataclass with: `name`, `description`, `triggers`, `tools`, `content`, `source_path`
   - Follows `AgentDefinition` pattern

3. **Implement SkillLoader** (`loader.py`):
   - `parse_frontmatter(content: str) -> tuple[dict, str]`
   - `load_skill(path: Path) -> Skill`
   - `load_skills(directory: Path) -> dict[str, Skill]`
   - **Critical**: Use `yaml.safe_load()` (SEC-1)
   - **Critical**: Validate size limit (SEC-3)

4. **Implement SkillRegistry** (`registry.py`):
   - `register(skill: Skill) -> None`
   - `get(name: str) -> Skill | None`
   - `list_skills() -> list[Skill]`
   - `get_skills_listing() -> str`
   - **Critical**: Detect duplicate names

5. **Write unit tests**:
   - `tests/test_skills/test_loader.py`
   - `tests/test_skills/test_registry.py`
   - Include security tests (SEC-1 through SEC-5)

### Phase 2: Context Injection

1. **Implement injection functions** (`injection.py`):
   - `inject_skill_context(skill: Skill) -> str`
   - `inject_skills_listing(skills: list[Skill]) -> str`

2. **Write injection tests**:
   - `tests/test_skills/test_injection.py`
   - Verify `<skill>` tag format
   - Verify `<system-reminder>` tag format

### Phase 3: Agent Integration

1. **Add skill_registry to Agent**:
   - Add `skill_registry` parameter to `Agent.__init__`
   - Initialize `SkillRegistry()` if not provided

2. **Load built-in skills**:
   - Implement `_load_builtin_skills()` method
   - Load from `src/yoker/skills/builtin/`
   - Graceful failure on error

3. **Inject skills listing**:
   - Implement `_build_user_message()` method
   - Inject skills listing before user input

4. **Write integration tests**:
   - `tests/test_agent/test_skills_integration.py`

### Phase 4: CLI Integration

1. **Implement SkillCommand** (`commands/skill.py`):
   - `/skill` (list available skills)
   - `/{skill_name}` (invoke skill)
   - Tab completion for skill names

2. **Update __main__.py**:
   - Initialize skill registry
   - Register SkillCommand

3. **Write CLI tests**:
   - `tests/test_cli/test_skill_command.py`

### Phase 5: Security Hardening

1. **Implement directory validation**:
   - Reuse `PathGuardrail` for skill directory validation (SEC-2)
   - Resolve symlinks before validation (SEC-4)

2. **Implement content validation**:
   - Check blocked patterns (SEC-6)
   - Add trust levels (SEC-7)
   - Add audit logging (SEC-8)

3. **Write security tests**:
   - `tests/test_security/test_skill_loader.py`

### Phase 6: Package Plugin Support (Task 2.2)

1. **Namespace handling**:
   - Prefix package skills with `{package}:` (SEC-5)
   - Priority system for conflicts

2. **Package discovery**:
   - Check for `SKILLS` list in `{package}.yoker` module
   - Register with namespace prefix

## Acceptance Criteria

### Functional Requirements

- [ ] **Skill dataclass defined**: Frozen dataclass with required fields (name, description) and optional fields (triggers, tools, content, source_path)
- [ ] **SkillLoader implemented**: Load skills from Markdown files with YAML frontmatter
- [ ] **SkillLoader validates**: Reject missing required fields, invalid YAML, duplicate names
- [ ] **SkillRegistry implemented**: Register, list, lookup skills by name
- [ ] **Context injection works**: Skills listing injected on every turn, skill content injected on `/skill-name`
- [ ] **Built-in skills loaded**: Default skills from `src/yoker/skills/builtin/` loaded at agent initialization
- [ ] **CLI integration complete**: `/skill` command lists skills, `/{skill_name}` invokes skill

### Security Requirements

- [ ] **SEC-1**: All YAML parsing uses `yaml.safe_load()` (verified by code review)
- [ ] **SEC-2**: Skill directories validated against allowed paths (verified by test)
- [ ] **SEC-3**: Skill content limited to 100KB (verified by test)
- [ ] **SEC-4**: Symlinks resolved before validation (verified by test)
- [ ] **SEC-5**: Package skills use namespace prefix (verified by integration test)

### Testing Requirements

- [ ] **Unit tests**: Loader, registry, injection functions
- [ ] **Security tests**: Path traversal, symlink escape, size limits, YAML safety
- [ ] **Integration tests**: Agent skill loading, CLI command execution
- [ ] **Test coverage**: >80% for skills module

### Documentation Requirements

- [ ] **README.md**: Add "Skills" section with usage examples
- [ ] **docs/skills.md**: Skill file format reference, creating custom skills
- [ ] **docs/security.md**: Security considerations for skill loading (or extend existing docs)
- [ ] **Code comments**: Security comments for critical controls (SEC-1, SEC-2, etc.)

### Performance Requirements

- [ ] **Loading performance**: Skills loaded once at initialization (<100ms for 50 skills)
- [ ] **Registry lookup**: O(1) by skill name
- [ ] **Context size**: Skills listing <500 bytes for 10 skills

### Compatibility Requirements

- [ ] **Existing patterns**: Follows `AgentDefinition` pattern from `agents/` module
- [ ] **Existing tools**: Reuses `PathGuardrail` for path validation
- [ ] **Existing exceptions**: Uses `ConfigurationError`, `FileNotFoundError` from `exceptions.py`

## Dependencies

### Required (Already in Project)

- `pyyaml>=6.0` - YAML frontmatter parsing
- `structlog>=23.0.0` - Logging
- PathGuardrail (from `tools/path_guardrail.py`)

### New (None Required)

No new dependencies. Skill system uses existing infrastructure.

## Risks and Mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| **Malicious skill content** | Medium | Content pattern blocking (SEC-6), size limits (SEC-3), trust levels (SEC-7) |
| **Path traversal attack** | High | Directory validation (SEC-2), symlink resolution (SEC-4) |
| **YAML code execution** | Critical | `yaml.safe_load()` (SEC-1), PyYAML >=5.4 |
| **Package skill override** | Medium | Namespace prefix (SEC-5), priority system |
| **Resource exhaustion** | Low | Size limits (SEC-3), timeout on loading |

## Out of Scope

The following are **not** part of Task 2.1:

1. **Skill dependencies**: Skills requiring other skills (future enhancement)
2. **Natural language triggers**: Detecting skill invocation from phrases (future enhancement)
3. **Skill sets**: Swappable skill collections (Phase 3.6)
4. **Skill validation**: Checking tool availability (future enhancement)
5. **Skill signing**: Cryptographic verification of package skills (future enhancement)
6. **Dynamic skill loading**: Loading skills at runtime from LLM-provided paths (security risk)

## Related Tasks

- **Task 2.2**: Package Plugin System - Uses skill infrastructure for package skills
- **Task 3.4**: Configurable Components Infrastructure - Future skill sets
- **Task 3.6**: Skills Sets Implementation - Swappable skill collections

## References

### Code References

- `src/yoker/agents/loader.py` - Agent definition loader pattern
- `src/yoker/agents/schema.py` - AgentDefinition dataclass pattern
- `src/yoker/tools/path_guardrail.py` - Path validation for directory checks
- `src/yoker/tools/registry.py` - Tool registry pattern

### Documentation References

- `analysis/api-skill-infrastructure.md` - Full API design
- `analysis/security-skill-infrastructure.md` - Full security review
- `analysis/context-injection-analysis.md` - Context injection patterns from Claude Code

### Standards References

- OWASP Top 10:2021 - A01: Broken Access Control, A03: Injection, A05: Injection
- CWE-22: Path Traversal
- CWE-427: Uncontrolled Search Path
- CVE-2017-18342, CVE-2020-1747, CVE-2020-14343 - YAML vulnerabilities

## Estimated Time

**2-3 hours** as specified in TODO.md.

Breakdown:
- **Core infrastructure** (1 hour): Skill dataclass, loader, registry
- **Context injection** (30 minutes): Injection functions, agent integration
- **CLI integration** (30 minutes): SkillCommand, __main__.py changes
- **Security hardening** (30 minutes): Directory validation, size limits
- **Tests** (30 minutes): Unit tests, security tests

## Next Steps

1. **Review consensus**: Ensure both API and security reviews are addressed
2. **Begin implementation**: Start with Phase 1 (Core Infrastructure)
3. **Continuous testing**: Write tests as you implement
4. **Security review**: Run security tests before merge
5. **Update documentation**: Add skill documentation as you implement

---

**Consensus Achieved**: API and security reviews agree on approach
**Implementation Status**: Ready to begin
**Blockers**: None