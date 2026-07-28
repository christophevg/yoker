# Consensus — UI Back-Port (InteractiveUIHandler merge)

**Date:** 2026-07-28
**Task:** Back-port RichUIHandler output improvements to InteractiveUIHandler

## Domain Reviews

| Agent | Verdict | Key Contribution |
|-------|---------|-----------------|
| functional-analyst | Approved | 35+ method merge plan, LiveDisplay usage audit, test strategy, 14 acceptance criteria |
| api-architect | Approved | Protocol/Bridge/Batch unchanged, LiveDisplay safe to remove, __init__ params to preserve, f-string bug found |
| ui-ux-designer | Approved | Append-only output is right direction, 5 blockers flagged (stubbed methods must be implemented), long-value guard, processing feedback concern |

## Owner Corrections (binding)

1. **start() signature**: KEEP `title`/`version` kwargs — external consumers (yoker-assistant) use them. API-architect's "no caller uses them" was checking only within the yoker repo.
2. **output_prompt**: KEEP as a SEPARATE method — not absorbed into get_input. yoker-assistant is a prime example where prompts come from email (MCP), not terminal input.
3. **Processing feedback**: Use `rich.status` with manual start/stop (not context manager) — stop when first response token arrives. NOT a LiveDisplay grid, just a single status line.
4. **Visual formatting**: Preserve all of RichUIHandler's output improvements (inline tool args, result size, prompt Panel, tools list in banner, grey74 thinking).

## Confirmed Design

- **Base**: RichUIHandler (stable, append-only console.print, no Live region)
- **Input**: prompt_toolkit with lazy PromptSession (created on first get_input, not in __init__)
- **Input rendering**: erase_when_done=True → input erased → output_prompt renders in Panel
- **Processing feedback**: rich.status manual start/stop — stop on first token
- **Removed**: LiveDisplay (spinner.py), _exit_live, _ensure_live, state flags, spinner
- **Added back**: output_step_title, output_command_result, output_content, confirm_approval, agent_spawned/agent_finished, _print_wrapped, shutdown — adapted to stable console.print
- **Preserved from old**: FileHistory, multi-line Esc+Enter, set_input_messages, history_file, wrap_width, show_* flags, show_stats=True default
- **Fixed**: output_stats f-string bug (missing f prefix in RichUIHandler)
- **Guard**: _format_tool_details caps values > 60 chars, suppresses content/old_string/new_string for write/update

## Acceptance Criteria

1. LiveDisplay (spinner.py) removed — no Live region, no _exit_live/_ensure_live
2. Lazy PromptSession — created on first get_input, not in __init__
3. erase_when_done=True on get_input/get_secret_input
4. output_prompt renders input in styled Panel after erase
5. Processing feedback via rich.status (manual start/stop, stop on first token)
6. Inline tool args (key=value) in output_tool_call
7. Result size (N chars) in output_tool_result
8. Tools list in welcome banner
9. All stubbed methods implemented: output_command_result, output_step_title, get_secret_input, confirm_approval
10. FileHistory, multi-line, agent_spawned/agent_finished, shutdown preserved
11. start() preserves title/version kwargs
12. output_prompt is a separate method (not absorbed into get_input)
13. make check passes
14. Manual REPL smoke test: input → Panel → Processing... → response streams