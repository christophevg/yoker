# API Design: GitHub Tool

**Document Version**: 1.0
**Date**: 2026-04-30
**Status**: Draft

## 1. Overview

### 1.1 Purpose

The GitHub tool provides a secure wrapper around the GitHub CLI (`gh`) for common repository operations. It enables agents to interact with GitHub repositories, issues, pull requests, and workflows while maintaining strict security boundaries.

### 1.2 Design Principle

**Wrapper, not replacement**: This tool wraps `gh` CLI commands rather than implementing a direct GitHub API client. This approach:
- Leverages existing authentication (`gh auth login`)
- Benefits from `gh` maturity and edge case handling
- Reduces maintenance burden
- Provides consistent output formatting

### 1.3 Scope

**In Scope (MVP)**:
- Repository information viewing
- Issue listing and viewing
- Pull request listing and viewing
- Workflow run viewing
- Release listing and viewing

**Out of Scope (MVP)**:
- Creating/deleting repositories
- Merging pull requests (destructive)
- Deleting branches (destructive)
- Pushing commits (use Git tool)
- Managing secrets
- Organization-level operations

## 2. Tool Interface

### 2.1 Schema

```json
{
  "name": "github",
  "parameters": {
    "operation": {
      "type": "string",
      "enum": [
        "repo_view",
        "issue_list",
        "issue_view",
        "pr_list",
        "pr_view",
        "workflow_list",
        "workflow_view",
        "release_list",
        "release_view"
      ],
      "description": "The GitHub operation to perform"
    },
    "repo": {
      "type": "string",
      "description": "Repository in OWNER/REPO format (optional, defaults to current repo)"
    },
    "number": {
      "type": "integer",
      "description": "Issue/PR/workflow number (for view operations)"
    },
    "limit": {
      "type": "integer",
      "description": "Maximum items to return (for list operations, default 30, max 100)"
    },
    "state": {
      "type": "string",
      "enum": ["open", "closed", "all"],
      "description": "Filter by state (for issue/pr list operations)"
    },
    "label": {
      "type": "string",
      "description": "Filter by label (for issue list operations)"
    }
  }
}
```

### 2.2 Operations

#### repo_view

View repository information.

```json
{
  "operation": "repo_view",
  "repo": "owner/repo"  // optional
}
```

**Returns**: Repository name, description, visibility, stars, forks, language, URL.

#### issue_list

List issues in a repository.

```json
{
  "operation": "issue_list",
  "repo": "owner/repo",      // optional
  "state": "open",           // optional, default "open"
  "label": "bug",            // optional
  "limit": 30                // optional, default 30, max 100
}
```

**Returns**: List of issues with number, title, state, labels, author, created date.

#### issue_view

View details of a specific issue.

```json
{
  "operation": "issue_view",
  "repo": "owner/repo",      // optional
  "number": 123
}
```

**Returns**: Issue title, body, state, labels, author, assignees, comments count.

#### pr_list

List pull requests in a repository.

```json
{
  "operation": "pr_list",
  "repo": "owner/repo",      // optional
  "state": "open",           // optional, default "open"
  "limit": 30                // optional, default 30, max 100
}
```

**Returns**: List of PRs with number, title, state, author, branch, created date.

#### pr_view

View details of a specific pull request.

```json
{
  "operation": "pr_view",
  "repo": "owner/repo",      // optional
  "number": 456
}
```

**Returns**: PR title, body, state, author, base/head branches, mergeable status, files changed.

#### workflow_list

List GitHub Actions workflow runs.

```json
{
  "operation": "workflow_list",
  "repo": "owner/repo",      // optional
  "limit": 10                // optional, default 10, max 50
}
```

**Returns**: List of workflow runs with name, status, conclusion, branch, triggered by, date.

#### workflow_view

View details of a specific workflow run.

```json
{
  "operation": "workflow_view",
  "repo": "owner/repo",      // optional
  "number": 789              // run ID
}
```

**Returns**: Workflow run details including jobs, steps, and status.

#### release_list

List releases in a repository.

```json
{
  "operation": "release_list",
  "repo": "owner/repo",      // optional
  "limit": 10                // optional, default 10, max 50
}
```

**Returns**: List of releases with tag, name, draft status, prerelease status, created date.

#### release_view

View details of a specific release.

```json
{
  "operation": "release_view",
  "repo": "owner/repo",      // optional
  "number": 1                // release number or tag
}
```

**Returns**: Release name, tag, body, assets, download count.

## 3. Implementation Details

### 3.1 Command Mapping

Each operation maps to a `gh` command:

| Operation | gh Command |
|-----------|------------|
| repo_view | `gh repo view [OWNER/REPO]` |
| issue_list | `gh issue list [OWNER/REPO] --state --label --limit` |
| issue_view | `gh issue view NUMBER [OWNER/REPO]` |
| pr_list | `gh pr list [OWNER/REPO] --state --limit` |
| pr_view | `gh pr view NUMBER [OWNER/REPO]` |
| workflow_list | `gh run list [OWNER/REPO] --limit` |
| workflow_view | `gh run view NUMBER [OWNER/REPO]` |
| release_list | `gh release list [OWNER/REPO] --limit` |
| release_view | `gh release view NUMBER [OWNER/REPO]` |

### 3.2 Output Format

All operations use `--json` flag for structured output:

```bash
gh issue view 123 --json number,title,body,state,labels,author,createdAt
```

This provides consistent, parseable output without screen-scraping.

### 3.3 Error Handling

| Error | Handling |
|-------|----------|
| `gh` not installed | Return error: "GitHub CLI not installed" |
| Not authenticated | Return error: "GitHub CLI not authenticated. Run 'gh auth login'" |
| Rate limited | Return error: "GitHub API rate limit exceeded" |
| Repo not found | Return error: "Repository not found" |
| Issue/PR not found | Return error: "Issue/PR not found" |
| Permission denied | Return error: "Permission denied for this operation" |

## 4. Configuration

### 4.1 TOML Configuration

```toml
[tools.github]
enabled = true
# No destructive operations in MVP
allowed_operations = [
  "repo_view",
  "issue_list",
  "issue_view",
  "pr_list",
  "pr_view",
  "workflow_list",
  "workflow_view",
  "release_list",
  "release_view"
]
# Require explicit repo specification (don't auto-detect from git remote)
require_explicit_repo = false  # if true, repo parameter is required
# Maximum execution time for gh commands
timeout_seconds = 30
```

### 4.2 Agent Definition

```markdown
---
name: developer
tools: List, Read, Write, GitHub
---
```

## 5. Future Considerations

### 5.1 Phase 2 Operations

**Write Operations** (require additional security):
- `issue_create` - Create new issues
- `issue_comment` - Add comments to issues
- `pr_create` - Create pull requests
- `pr_comment` - Add comments to PRs
- `release_create` - Create releases

**Destructive Operations** (require explicit permission):
- `pr_merge` - Merge a pull request
- `branch_delete` - Delete a branch

These would require:
- Additional guardrail configuration
- Explicit permission in config
- Confirmation prompts (configurable)

### 5.2 Enterprise GitHub

Support for GitHub Enterprise:
- Custom base URL configuration
- Enterprise-specific authentication
- Organization-level operations

### 5.3 Direct API Mode

Alternative implementation using direct HTTP API:
- For environments without `gh` installed
- For finer-grained control
- For batch operations

## 6. Testing Strategy

### 6.1 Unit Tests

- Schema validation for all parameters
- Operation allowlist enforcement
- Timeout handling
- Error message formatting

### 6.2 Integration Tests

- Mock `gh` commands using subprocess patching
- Test with `gh` not installed
- Test with not authenticated state
- Test rate limit handling

### 6.3 Manual Testing

```bash
# Verify gh is installed and authenticated
gh auth status

# Test basic operations
python -c "from yoker.tools.github import GitHubTool; t = GitHubTool(); print(t.execute(operation='repo_view'))"
```