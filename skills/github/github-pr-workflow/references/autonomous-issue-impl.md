---
name: autonomous-issue-implementation
description: "Orchestrate autonomous AI coding agents to implement GitHub issues end-to-end: planning, branch creation, code generation, testing, PR creation, and review."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos]
---

# Autonomous Issue Implementation

Orchestrate one or more AI coding agents to pick up GitHub issues, implement them, and deliver review-ready PRs with minimal human intervention.

## When to Use

- User says "implement the next issue", "start auto-impl loop", or "work on open issues"
- User wants parallel implementation of multiple issues
- User wants a repeatable, hands-off issue-to-PR pipeline

## Workflow Overview

```
Issue → Plan → Branch → Implement → Test → PR → AI Review → Merge
```

## Phase 1: Issue Selection

```bash
gh issue list --state open --limit 50 --json number,title,labels
gh issue view <number> --json title,body,labels
```

Pick the lowest-numbered unimplemented issue, or the one the user named.

## Phase 2: Planning

1. Summarize requirements in your own words
2. Identify affected areas (files, services, DB schema, API routes, UI components)
3. Create a brief implementation plan with checkboxes
4. Estimate scope: small (< 1h), medium (1–3h), large (> 3h)
5. **Report the plan to the user before proceeding** unless they explicitly asked for autonomous mode

## Phase 3: Branch Creation

```bash
git checkout develop
git pull origin develop
git checkout -b feature/issue-<N>-<short-kebab-title>
```

## Phase 4: Implementation Options

### Option A: External Coding Agent (OpenCode / Claude Code / Codex)
```bash
opencode run 'Implement GitHub issue #<N>: <title>. Follow existing code style. Add tests. Do NOT commit.'
```

### Option B: Delegate Task Subagents
```python
delegate_task(
  goal="Implement the attached issue in this codebase. Follow existing patterns. Add tests. Do not commit.",
  context="Issue #N: ...",
  role="leaf",
  toolsets=["terminal", "file"]
)
```

**Parallel delegation:** Split large issues into independent subtasks and delegate each to a separate subagent.

### Option C: Direct Implementation (Hermes native)
For small, well-understood changes, implement directly with terminal/read_file/write_file/patch tools.

## Phase 5: Git Commits

### Pre-Commit Guard: `.gitignore` Check

Before the first `git add -A` in a fresh repo or new package, verify `.gitignore` exists and excludes `node_modules/`, `dist/`, lockfiles:

```bash
git check-ignore node_modules 2>/dev/null || echo "WARNING: node_modules is not ignored"
```

If missing, create `.gitignore` **before** staging:
```bash
cat > .gitignore <<'EOF'
node_modules/
dist/
*.log
.DS_Store
*.local
.env
.vscode-test/
EOF
```

**Why:** `git add -A` in a monorepo with newly initialized packages will commit thousands of `node_modules` files.

### Commit Rules
1. **One logical change per commit**
2. **Each commit should build and pass tests** where possible
3. **Commit message format:** `feat(#<N>): brief description`
4. **Do NOT push to `main` or `develop` directly**

## Phase 6: Quality Gates (Before Push)

```bash
npm run lint
npm run typecheck
npm test
```

If any gate fails, fix, re-run, and commit separately: `fix(#<N>): resolve lint/type/test failures`

## Phase 7: Push & PR Creation

```bash
git push -u origin feature/issue-<N>-<description>
gh pr create --draft --title "feat(#<N>): <Title>" --body-file pr-body.md
```

**REST API fallback** for `gh pr create` failures:
```bash
gh api repos/<owner>/<repo>/pulls \
  -f title="feat(#<N>): <Title>" \
  -f body="Implements #<N>." \
  -f head="feature/issue-<N>-<description>" \
  -f base="develop"
```

## Phase 8: AI Review

Run AI review using the project's review skill. Address all BLOCKING issues before merging. Only merge if AI review finds no blocking issues.

## Phase 9: Merge & Cleanup

```bash
gh pr merge <number> --squash --delete-branch
```

**REST API fallback:**
```bash
gh api -X PUT repos/<owner>/<repo>/pulls/<number>/merge \
  -f commit_title="feat(#<N>): <Title>" \
  -f merge_method=squash
```

```bash
git branch -d feature/issue-<N>-<description>
git push origin --delete feature/issue-<N>-<description>
```

## Parallel Implementation Pattern

For implementing multiple issues at once:

```bash
git worktree add /tmp/issue-56 feature/issue-56
git worktree add /tmp/issue-57 feature/issue-57

opencode run 'Implement issue #56' --cwd /tmp/issue-56 &
opencode run 'Implement issue #57' --cwd /tmp/issue-57 &
wait
```

Or use `delegate_task` with `max_concurrent_children` (default 3) to run subagents in parallel.

**Parallel adapter pattern:** Spawn one subagent per independent adapter/package with isolated file targets to avoid merge conflicts.

## Post-Delegation Integration Check

After parallel subagents return, **always** run an integration audit:

```bash
git status --short
git diff --cached --name-only | sort | uniq -d  # Overlapping modifications
git diff --cached --stat | head -30  # Check for node_modules or lockfiles
```

## Pitfalls

- **Skipping planning:** Never start coding without at least a mental plan
- **Over-delegating:** Too many subagents on the same codebase causes merge conflicts
- **Ignoring CI:** Local tests passing does not guarantee CI passes
- **Merge without review:** The user requires AI review. Never merge solely because tests pass
- **Stale branches:** Rebase from `develop` early and often
- **PR body `@` symbols:** Inline `--body` with `@scope/package` is misinterpreted by bash as file redirection. Always use `--body-file` or REST API
- **GitHub CLI merge failures:** `gh pr merge` can fail with GraphQL errors. Use REST API `PUT .../merge` fallback
- **Token export in Docker:** `gh` CLI and git HTTPS push inside Docker often need `GITHUB_TOKEN` exported explicitly
- **Develop drift:** After merging one PR, always `git pull origin develop` before creating the next feature branch
- **Accidentally committing node_modules:** Always verify `.gitignore` and run `git status --short | head -20` before committing
- **Subagent merge conflicts:** Parallel subagents may overwrite each other's changes. Always audit before committing
- **PR eventual consistency lag:** Immediately after PR creation via REST API, `gh pr merge` may fail. Wait 2 seconds or use REST API fallback
