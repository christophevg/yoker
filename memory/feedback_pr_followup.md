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

2. **Address PR Comments**
   - Use `gh pr view <n> --json reviews` to check review status
   - Use `gh api repos/owner/repo/pulls/n/comments` to get specific comments
   - Fix issues and push new commits
   - Respond to comments if clarification needed

3. **Verify PR Merge**
   - Use `gh pr view <n> --json state,mergedAt` to check merge status
   - After merge: sync local master (`git checkout master && git pull`)
   - Update TODO.md to mark task complete with date
   - Update GitHub issue status if applicable

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
- After review comments: fix, test, commit, push

## Date

2026-05-23