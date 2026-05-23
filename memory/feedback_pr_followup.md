# PR Follow-up Workflow

## Context

After creating a PR, the workflow must follow up on:
1. CI status (wait for checks to pass)
2. PR comments (address review feedback)
3. PR resolution (merge/close status)

## Workflow Steps

### After PR Creation

1. **Check CI Status**
   - Use `gh run list --limit 3` to see recent runs
   - Poll with timeout (max 3 attempts, 30s each) - don't use `--watch` (blocks indefinitely)
   - If stuck run (queued with 0 jobs), report to user

2. **Check PR Comments**
   - Use `gh pr view <n> --json comments` for issue comments
   - Use `gh api repos/owner/repo/pulls/n/comments` for review comments
   - Address each comment:
     - Answer questions
     - Fix issues and push new commits
     - Respond to comment if clarification needed
   - Use `gh pr comment <n> --body "..."` to respond

3. **Verify PR Merge**
   - Use `gh pr view <n> --json state,mergedAt` to check merge status
   - After merge: sync local master (`git checkout master && git pull`)
   - Update TODO.md to mark task complete with date
   - Update GitHub issue status if applicable

### Checking for Comments

**Issue Comments (on PR conversation):**
```bash
gh pr view <n> --json comments --jq '.comments[] | "💬 \(.author.login): \(.body)"'
```

**Review Comments (on specific code lines):**
```bash
gh api repos/owner/repo/pulls/n/comments --jq '.[] | "📍 \(.path):\(.line) - \(.body)"'
```

### Responding to Comments

1. **Questions:** Answer directly with `gh pr comment`
2. **Code changes needed:** Fix locally, commit, push, respond to comment
3. **Clarification needed:** Ask for more details

### Stuck Run Handling

If CI run is stuck (queued with 0 jobs):
1. Report to user: "CI run is stuck (queued with 0 jobs). This is a GitHub infrastructure issue."
2. Options: wait, push new commit, or user cancels manually from web UI
3. Document in gh-ci skill

### PR Comment Resolution

When reviewer leaves comments:
1. Read each comment carefully
2. Make required changes locally
3. Run tests/lint locally: `make test && make lint`
4. Commit with message referencing review: `refactor: X per review feedback`
5. Push to trigger new CI run
6. Respond to comment if clarification needed

## Integration Points

- After commit: use `c3:gh-ci` skill to check CI
- After PR merge: update TODO.md, close/update GitHub issue
- After review comments: fix, test, commit, push, respond

## Example Workflow

```
1. Push → PR created
2. Check CI with gh run list
3. Check PR comments with gh pr view --json comments
4. If comments exist:
   - gh api .../pulls/n/comments for review comments
   - Address each comment
   - Respond with gh pr comment
5. If code changes needed:
   - Fix locally
   - make test && make lint
   - git commit -m "fix: address review feedback"
   - git push
6. Wait for merge
7. After merge:
   - git checkout master && git pull
   - Update TODO.md with completion date
```

## Date

2026-05-23