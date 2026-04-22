# Naming Ideas: Agent/Skill/Tool Collections

**Created:** 2026-04-22
**Status:** Idea collection for future decision

## Context

Yoker is designed as an open, configurable framework that behaves as a library. It should have no hidden manipulation or secret context injection. Users run a folder of agents/skills/tools with full visibility and control.

We need a name for such collections, similar to C3 (Christophe Coding Crew/Collection of agents and skills).

## Design Principles

1. **Transparent** - All instructions to the LLM are visible, editable, configurable
2. **Open** - No hidden manipulation or secret context injection
3. **Configurable** - Every aspect is modifiable
4. **Portable** - Collections can be shared, versioned, deployed

## Naming Candidates

### Playful Names

| Name | Vibe | Notes |
|------|------|-------|
| YCP - Yoker Crew Pack | Playful, pack = collection | Similar to C3 naming |
| Crew | Simple, human | Short, memorable |
| Yoker Armory | Tools ready for use | Implies preparedness |
| Pack | Collection of things | Simple, universal |

### Technical Names

| Name | Vibe | Notes |
|------|------|-------|
| Y-Core | Minimal, essential | Core collection |
| Y-Kit | Toolkit feel | Familiar pattern |
| Bundle | Simple, clear | Standard term |
| Module | Technical, standard | May conflict with Python modules |

### Descriptive Names

| Name | Vibe | Notes |
|------|------|-------|
| Collection | Pure description | Generic but accurate |
| Agent Set | Descriptive | Clear what it contains |
| Skill Pack | Descriptive | Focus on skills |
| Tool Suite | Descriptive | Focus on tools |

### Abbreviation-Based

| Name | Vibe | Notes |
|------|------|-------|
| YAC | Yoker Agent Collection | Pronounceable |
| YSC | Yoker Skill Collection | Less pronounceable |
| YTC | Yoker Tool Collection | Less pronounceable |

## Comparison to C3

C3 = **C**hristophe **C**oding **C**rew/Collection

Key attributes:
- Short (2-3 characters)
- Memorable
- Personal yet professional
- Implies a team/crew of agents

## Decision Criteria

1. **Memorability** - Easy to remember and type
2. **Clarity** - Clearly indicates what it is
3. **Distinctiveness** - Doesn't conflict with existing terms
4. **Scalability** - Works for small and large collections
5. **Extensibility** - Works as a folder name, config key, etc.

## Future Considerations

- How do users share collections?
- How do collections reference other collections?
- How are collections versioned?
- How do collections specify dependencies?

## Related Concepts

- **Manifest** - A file describing collection contents
- **Catalog** - A registry of available collections
- **Registry** - Central place to discover collections

---

**Decision**: Pending - needs more exploration and user feedback.