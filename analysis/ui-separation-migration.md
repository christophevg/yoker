# UI Separation - Migration Plan

**Document Status:** Draft
**Created:** 2026-06-11
**Last Updated:** 2026-06-11

## Overview

This document provides a step-by-step migration plan from the current architecture to the target architecture.

**Key Principle:** Clean break - no backward compatibility, no deprecation shims.

---

## Phase 1: Foundation

**Goal:** Create UI module structure with protocols.

### Tasks

1. **Create `yoker/ui/` directory structure**
   ```
   yoker/ui/
   ├── __init__.py
   ├── handler.py
   ├── base.py
   └── bridge.py
   ```

2. **Create `yoker/ui/handler.py`**
   - Define `UIHandler` protocol
   - Document all methods
   - No implementation (protocol only)

3. **Create `yoker/ui/base.py`**
   - Define `BaseUIHandler` abstract class
   - State management only
   - No formatting (implementation-specific)

4. **Create `yoker/ui/bridge.py`**
   - Define `UIBridge` class
   - Bridge EventHandler to UIHandler
   - Dispatch events to UI methods

5. **Create `yoker/ui/__init__.py`**
   - Export public API: `UIHandler`, `BaseUIHandler`, `UIBridge`

6. **Update exceptions module**
   - Ensure `YokerError`, `NetworkError`, etc. exist
   - Document exception hierarchy

### Testing Focus

- Protocol compliance (no runtime tests needed)
- Bridge dispatch logic
- Exception hierarchy

---

## Phase 2: Content Types and Events

**Goal:** Update events to support content types where needed.

### Tasks

1. **Add content_type to events**
   - `ContentChunkEvent`: Add `content_type: str = "text/plain"`
   - `ToolContentEvent`: Already has it, clarify usage

2. **Remove ErrorEvent (if exists)**
   - Replace with exceptions
   - Update any code that emits ErrorEvent

3. **Update tools to set content_type**
   - `ReadTool`: Detect content type
   - `WriteTool`: Set content type to summary
   - `UpdateTool`: Set content type to diff
   - `GitTool`: Use `--no-color`, set content type

4. **Create content type detection utility**
   ```python
   # yoker/content_type.py
   def detect_content_type(content: bytes, path: Path) -> str:
       # Try library detection
       # Fallback to extension
       # Fallback to text/plain
   ```

### Testing Focus

- Content type detection
- Tool output content types
- Event content_type field

---

## Phase 3: UI Implementations

**Goal:** Create InteractiveUIHandler and BatchUIHandler.

### Tasks

1. **Create `yoker/ui/interactive.py`**
   - Move input handling from `__main__.py`
   - Implement `InteractiveUIHandler`
   - Use Rich console for output
   - Use prompt_toolkit for input

2. **Create `yoker/ui/batch.py`**
   - Implement `BatchUIHandler`
   - stdin/stdout/stderr channels
   - Predefined input support

3. **Move LiveDisplay to UI layer**
   - `yoker/ui/spinner.py`
   - Used by InteractiveUIHandler only

4. **Create `yoker/ui/__init__.py` exports**
   - `UIHandler`, `BaseUIHandler`, `UIBridge`
   - `InteractiveUIHandler`, `BatchUIHandler`

### Testing Focus

- Input handling (interactive and batch)
- Output channels (stdout/stderr)
- Streaming behavior
- NOT: Formatting details

---

## Phase 4: Refactor Agent Module

**Goal:** Split `agent.py` into focused modules.

### Tasks

1. **Create `yoker/agent/` directory structure**
   ```
   yoker/agent/
   ├── __init__.py
   ├── core.py
   ├── agent.py
   ├── processing.py
   └── tools.py
   ```

2. **Move `base.py` to `agent/core.py`**
   - `AgentCore` class
   - Event handler management
   - Guardrail validation

3. **Split `agent.py`**
   - Init and properties → `agent/agent.py`
   - Processing logic → `agent/processing.py`
   - Tool registry → `agent/tools.py`
   - **Remove** `begin_session()` and `end_session()` methods

4. **Update imports**
   - `yoker/__init__.py`: `from yoker.agent import Agent, AgentCore`
   - All other imports

5. **Remove old files**
   - Delete `yoker/base.py`
   - Delete `yoker/agent.py`
   - **Remove** `SessionStartEvent` and `SessionEndEvent` from `events/types.py`

### Testing Focus

- Agent processes messages correctly
- Tool calls work
- Events are emitted (except session events)
- Exceptions are raised appropriately
- Context appends correctly
- NOT: Module structure details

4. **Update imports**
   - `yoker/__init__.py`: `from yoker.agent import Agent, AgentCore`
   - All other imports

5. **Remove old files**
   - Delete `yoker/base.py`
   - Delete `yoker/agent.py`

### Testing Focus

- Agent processes messages correctly
- Tool calls work
- Events are emitted
- NOT: Module structure details

---

## Phase 5: Slash Commands

**Goal:** Move slash commands to UI layer.

### Tasks

1. **Create `yoker/ui/commands/` directory**
   ```
   yoker/ui/commands/
   ├── __init__.py
   ├── help.py
   ├── skills.py
   ├── context.py
   ├── think.py
   └── skill_invoke.py
   ```

2. **Move command handlers**
   - `/help` → `commands/help.py` (UI-only)
   - `/skills` → `commands/skills.py` (queries agent)
   - `/context` → `commands/context.py` (queries agent)
   - `/think` → `commands/think.py` (sets agent state)
   - `/<skill-name>` → `commands/skill_invoke.py` (calls agent method)

3. **Add `Agent.inject_skill_context()`**
   ```python
   def inject_skill_context(self, skill_name: str, args: str | None = None) -> None:
       """Inject skill context into conversation.
       
       Same method used by SkillTool when LLM invokes a skill.
       """
       skill = self._core.skill_registry.get(skill_name)
       if skill is None:
           raise SkillError(skill_name, "Unknown skill")
       
       content = format_skill_content(skill, args)
       self._core.context.add_message("system", content)
   ```

4. **Update command registry**
   - Commands receive `UIHandler` reference
   - Commands can query `Agent` for data
   - Commands output via `UIHandler`

### Testing Focus

- Command execution
- Agent API calls
- NOT: Command output formatting

---

## Phase 6: Entry Point Refactoring

**Goal:** Simplify `__main__.py` to thin dispatcher.

### Tasks

1. **Refactor `__main__.py`**
   ```python
   async def main():
       # Parse args (Clevis handles UI config)
       config = get_config(Config, cli=True)
       
       # Create agent
       agent = Agent(config=config)
       
       # Create UI handler based on mode
       if config.ui.mode == "batch":
           ui = BatchUIHandler(
               show_thinking=config.ui.show_thinking,
               show_tool_calls=config.ui.show_tool_calls,
               show_stats=config.ui.show_stats,
           )
       else:
           ui = InteractiveUIHandler(...)
       
       # Bridge events
       bridge = UIBridge(ui)
       agent.add_event_handler(bridge)
       
       # Run session
       await run_session(agent, ui)
   ```

2. **Create `run_session()` helper**
   - Session loop
   - Exception handling
   - Cleanup

3. **Add UI configuration to Config (Clevis-driven)**
   ```python
   # In config.py
   @dataclass
   class UIConfig:
       mode: str = "interactive"  # "interactive" or "batch"
       show_thinking: bool = False
       show_tool_calls: bool = False
       show_stats: bool = False
   
   @dataclass
   class Config:
       backend: BackendConfig
       context: ContextConfig
       ui: UIConfig  # NEW
   ```
   
   Then use via Clevis:
   ```bash
   # Interactive mode (default)
   yoker
   
   # Batch mode
   yoker --ui.mode=batch
   
   # Batch with thinking
   yoker --ui.mode=batch --ui.show-thinking=true
   ```

4. **Remove all print statements from `__main__.py`**
   - All output goes through UIHandler
   - All errors handled by UIHandler

### Testing Focus

- CLI argument parsing
- Mode selection
- Error handling
- NOT: Output formatting

---

## Phase 7: Remove Old Code

**Goal:** Remove deprecated code and clean up.

### Tasks

1. **Remove `ConsoleEventHandler`**
   - Delete `yoker/events/handlers.py`
   - Update `yoker/events/__init__.py`

2. **Remove old command handling from `__main__.py`**
   - Delete inline command dispatch
   - Use `yoker/ui/commands/` instead

3. **Clean up imports**
   - Remove unused imports
   - Update `__all__` exports

4. **Update documentation**
   - Document UIHandler protocol
   - Document BatchUIHandler usage
   - Update examples

### Testing Focus

- All modes still work
- No regression
- Clean import structure

---

## Phase 8: Final Polish

**Goal:** Documentation and examples.

### Tasks

1. **Update README.md**
   - Interactive mode usage
   - Batch mode usage
   - Library usage example

2. **Create examples**
   - `examples/batch_mode.py`
   - `examples/library_usage.py`
   - `examples/custom_handler.py`

3. **Update CLAUDE.md**
   - New module structure
   - UI layer architecture

4. **Create migration guide** (if needed)
   - For users of old API
   - Breaking changes

---

## Testing Strategy

### What to Test

- Agent functionality (message processing, tool calls)
- UI handler protocol compliance
- Exception handling
- Event bridging
- Input handling (interactive and batch)
- Output channels (stdout/stderr in batch)

### What NOT to Test

- Formatting details (colors, styling)
- Output text (implementation detail)
- Module structure (refactoring may change)

---

## Rollback Plan

If issues arise:

1. **Phase 1-2**: Can rollback easily (new files only)
2. **Phase 3-4**: May need to restore old files from git
3. **Phase 5-6**: Full rollback required (core changes)

**Recommendation:** Commit after each phase with clear message.

---

## Timeline Estimate

| Phase | Estimated Time | Dependencies |
|-------|---------------|--------------|
| Phase 1 | 2-3 hours | None |
| Phase 2 | 1-2 hours | Phase 1 |
| Phase 3 | 4-6 hours | Phase 1, 2 |
| Phase 4 | 2-3 hours | Phase 1 |
| Phase 5 | 2-3 hours | Phase 3, 4 |
| Phase 6 | 3-4 hours | Phase 3, 4, 5 |
| Phase 7 | 1-2 hours | All previous |
| Phase 8 | 2-3 hours | All previous |

**Total:** ~17-26 hours (3-4 days)

---

## Notes

### Clean Break

- No backward compatibility
- No deprecation warnings
- Full API redesign
- Clear, simple code

### Future Extensions (Not Part of This Migration)

- `--script FILE` mode (run from file)
- `--prompt TEXT` mode (single prompt)
- Top-level Clevis commands (`yoker run <plugin>`)
- API handler for REST endpoints
- ChatUIHandler for yoker-chat

### Batch Mode Clarification

- **stdin piping already works** for batch mode
- `--batch` flag is for explicit batch mode with options
- No need for complex file/script handling initially

---

**End of Document**

