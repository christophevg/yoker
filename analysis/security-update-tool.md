# Security Analysis: Update Tool

## Executive Summary

The Update Tool introduces unique security risks beyond other filesystem tools because it performs **read-modify-write** operations. The central threat is the **Time-of-Check to Time-of-Use (TOCTOU)** window: a file can change between when the agent reads it and when the update is applied. Additionally, imprecise matching can cause unintended modifications (deleting the wrong content, injecting text at the wrong location), and diff size limits must be enforced to prevent massive uncontrolled changes.

## STRIDE Threat Model

| Category | Threat | Impact | Mitigation |
|----------|--------|--------|------------|
| **Spoofing** | LLM crafts update parameters claiming to match file content, but actually modifies different content | Unintended file corruption | Require exact match validation; reject ambiguous matches |
| **Tampering** | File modified by external process between read and update (TOCTOU) | Update applied to wrong content; corruption | Re-read file immediately before applying; verify search content still matches |
| **Tampering** | Partial match replaces wrong occurrence (e.g., first of multiple matches) | Unintended changes elsewhere in file | Require exact match or require unique match; reject multiple matches when `require_exact_match=True` |
| **Repudiation** | Update succeeds but no audit trail of what changed | Cannot debug or rollback | Log before/after hashes and diff summaries |
| **Information Disclosure** | Error messages leak file content or line counts | Information leakage via error feedback | Sanitize errors; never return file content in error messages |
| **Denial of Service** | Massive replacement content writes huge diff | Disk exhaustion; context window overflow | Enforce `max_diff_size_kb`; enforce resulting file size limits |
| **Elevation of Privilege** | Update tool bypasses write restrictions by updating instead of writing | Circumvents `allow_overwrite=False` and blocked extensions | Treat update as write-equivalent: enforce blocked extensions, apply overwrite logic, require path guardrail |

## Critical Risks

### 1. TOCTOU Race Condition

The typical flow is: Agent reads file -> Agent decides what to change -> Agent calls `UpdateTool`. Between read and update, the file may have changed. Applying updates based on stale read data causes silent corruption.

**Mitigation**: Re-read file fresh in `execute()`, then verify search text exists in current content.

### 2. Exact Match Validation Failures

If `require_exact_match=True` (the default), the tool must guarantee the search text matches exactly and uniquely. Naive substring search (`str.replace()`) may match partial lines or match multiple times.

**Mitigation**: Use literal string search only. When `require_exact_match=True` and multiple occurrences exist, reject the operation.

### 3. Regex Injection

If the `search` parameter is accidentally treated as a regex, special characters could cause ReDoS or unintended matches.

**Mitigation**: Use **literal string search** (`str.find()`, `str.replace()`) only. Never use `re.sub()` for the `search` parameter.

### 4. Update as Write Bypass

The Update Tool could circumvent Write Tool restrictions by creating new files or overwriting blocked extensions.

**Mitigation**: File must exist before update. Apply same extension checks as read/write tools.

## Required Guardrail Checks

- PathGuardrail must validate paths for update tool (already supported)
- Add file existence and extension checks to PathGuardrail for update operations
- Add diff size validation against `max_diff_size_kb`
- Re-read file fresh in tool execution to prevent TOCTOU
- Use atomic write (temp file + `os.replace()`)
- Sanitize error messages to prevent path/content leakage

## Test Cases

| Test | Description | Expected Result |
|------|-------------|-----------------|
| `test_update_guardrail_blocks_traversal` | Update with `../../../etc/passwd` | Blocked by PathGuardrail |
| `test_update_rejects_symlink` | Update via symlink path | Tool layer rejects before resolution |
| `test_update_nonexistent_file` | Update file that does not exist | Error: "File not found" |
| `test_update_exact_match_multiple_occurrences` | Search text appears 3 times, `require_exact_match=True` | Error: "ambiguous match" |
| `test_update_exact_match_single_occurrence` | Search text appears 1 time | Success |
| `test_update_no_match` | Search text not in file | Error: "Search text not found" |
| `test_update_diff_size_exceeded` | Replacement is 200KB, limit is 100KB | Error: "Diff size exceeds limit" |
| `test_update_line_number_out_of_range` | `line_number=999` in 10-line file | Error: "Line number out of range" |
| `test_update_blocked_extension` | Update `.exe` file | PathGuardrail blocks |
| `test_update_blocked_pattern` | Update `.env` file | PathGuardrail blocks |
| `test_update_permission_denied` | No write permission | Sanitized error, no path leakage |

## OWASP Mapping

| OWASP ID | Category | Relevance |
|----------|----------|-----------|
| A01 | Broken Access Control | Path traversal, symlink bypass, extension bypass |
| A05 | Injection | Regex injection if search interpreted as pattern |
| A06 | Insecure Design | TOCTOU race condition |
| A08 | Software/Data Integrity | Partial writes, ambiguous matches |
| A09 | Security Logging Failures | Update operations must be auditable |
