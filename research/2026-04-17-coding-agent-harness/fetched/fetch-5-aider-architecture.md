# Aider Core Architecture - Fetched Content

**URL**: https://deepwiki.com/Aider-AI/aider/2-core-architecture
**Timestamp**: 2026-04-17T10:09:00Z
**Source**: search-4

---

## Aider Core Architecture Summary

### 1. Coder Class Implementation
The `Coder` class is "the heart of Aider's architecture" managing "the lifecycle of chat interactions, coordinates between subsystems, and maintains state."

**Key Responsibilities:**
- **File Management**: `abs_fnames`, `abs_read_only_fnames` via `add_rel_fname()`, `drop_rel_fname()`
- **Message History**: `cur_messages`, `done_messages` with `move_back_cur_messages()`, `format_messages()`
- **Repository Integration**: `repo`, `repo_map` via `get_repo_map()`, `get_repo_messages()`
- **Model Communication**: `main_model`, `stream` via `send_message()`, `send_completion()`
- **Cost Tracking**: `total_cost`, `message_cost`, `total_tokens_sent`, `total_tokens_received`

The `Coder.create()` factory method "instantiates the appropriate coder subclass based on the `edit_format` parameter." When switching coders, it preserves files, message history, and clones the `Commands` instance.

### 2. Repository Map
The content references `repo_map` and `get_repo_map()` but notes: "For details on repository understanding and code context generation, see [Repository Mapping System](/Aider-AI/aider/4.1-repository-mapping-system)." Tree-sitter details are not in this page.

### 3. Edit Formats
Edit strategies are referenced but implementation details are on a separate page: "For information about specific edit strategies...see [Edit Strategies and Format Implementations](/Aider-AI/aider/3.1-edit-format-implementations)."

### 4. Architect/Editor Pattern
Referenced as `/architect` command "via `cmd_chat_mode()`" which "Switch to architect mode." Detailed implementation is on the separate "Architect Mode" page.

### 5. Git Integration (GitRepo Class)
The `GitRepo` class provides "git repository operations, including commits with attribution, diff generation, and file tracking."

**Commit Attribution Logic** handles:
- `--attribute-author`: "Modifies Git author to 'User Name (aider)'"
- `--attribute-committer`: "Modifies Git committer"
- `--attribute-co-authored-by`: "Adds 'Co-authored-by: aider (model)' trailer"

Logic differs for AI-generated vs user-initiated changes.

### 6. Request Processing Flow
**Message Preprocessing:**
1. Check if input is command via `Commands.is_command()`
2. Extract file mentions via `check_for_file_mentions()`
3. Detect URLs via `check_for_urls()`

**Message Formatting** (`format_messages()`):
1. System prompt with instructions
2. Repository map (if enabled)
3. Read-only files content
4. Chat files content
5. Conversation history
6. Current user message

**Role Alternation Enforcement**: `ensure_alternating_roles()` "fixes non-alternating message sequences by inserting empty messages."

### 7. Model Support Flexibility
**Model Initialization Flow:**
1. Resolve alias via `MODEL_ALIASES` dictionary
2. Fetch metadata via `ModelInfoManager.get_model_info()`
3. Apply settings via `configure_model_settings()`
4. Validate environment for required API keys
5. Initialize weak and editor models if needed

**ModelSettings dataclass** defines: `edit_format`, `use_repo_map`, `weak_model_name`, `editor_model_name`, `cache_control`, `streaming`, `use_system_prompt`, `use_temperature`.

### 8. Voice Input Feature
Not detailed in this page; referenced as separate "[Voice-to-Code Mode](/Aider-AI/aider/5.3-voice-to-code-mode)" page.

### 9. Linting Integration
Not detailed in this page; referenced as separate "[Code Quality and Linting](/Aider-AI/aider/4.5-code-quality-and-linting)" page.

### State Management
| Category | Attributes | Persistence |
|----------|------------|-------------|
| File Context | `abs_fnames`, `abs_read_only_fnames` | Session only |
| Message History | `cur_messages`, `done_messages` | Optional (chat history file) |
| Git Tracking | `aider_commit_hashes` | Session only |
| Cost Tracking | `total_cost`, `message_cost` | Session only |

**History Summarization**: When messages exceed threshold, `summarize_start()` spawns background thread calling `ChatSummary.summarize()` with weak model.