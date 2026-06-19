---
name: pr-lifecycle-workflow
description: "End-to-end PR lifecycle: implement, review, fix, CI, merge. Covers subagent review, timeout-proof strategies, large-PR splitting, and tool-call budget management."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
---

# PR Lifecycle with Subagent Review

## Phase 1 — Implement & Verify Locally

```bash
git checkout develop && git pull origin develop
git checkout -b feature/issue-N-description
# Implement
npm run format:check
npm run lint
npm run typecheck
npm test
npm run build
```

## Phase 2 — Push & Create Draft PR

```bash
npx prettier --write src/ docs/ supabase/migrations/
git add -A
git commit -m "feat(scope): description (Issue #N)"
git push origin feature/issue-N-description

gh pr create --base develop --head feature/issue-N-description \
  --draft --title "[WIP] feat(scope): description (Issue #N)" \
  --body "## 概要\n\nIssue #N description\n\n## 検証結果\n- [x] lint\n- [x] typecheck\n- [x] test\n\n## レビュー依頼\n別AIレビューをお願いします。"
```

**Important:** Inline `--body` containing `@` characters (e.g., `@scope/package`, `@mention`) is misinterpreted by bash as file-path redirections. Prefer `--body-file` with a heredoc, or use the REST API fallback.

**REST API fallback:**
```bash
gh api repos/<owner>/<repo>/pulls \
  -f title="[WIP] feat(scope): description (Issue #N)" \
  -f body="Implements #N." \
  -f head="feature/issue-N-description" \
  -f base="develop"
```

## Phase 3 — Parallel AI Review (delegate_task)

Run 3 parallel subagent reviews, each scoped to a domain:

```python
delegate_task(
    goal="Review DB migrations, RLS policies, and Zod schemas for security, consistency, and constraint alignment.",
    context="DB_SCHEMA_DIFF_HERE",
    toolsets=["file"],
    role="leaf"
)
```

**Split by category:**
- DB + Schema diff: `git diff develop..HEAD -- supabase/migrations/ src/schemas/`
- Service + API + Prompts: `git diff develop..HEAD -- src/features/*/services/ src/features/*/prompts/ src/app/api/`
- UI + Components + Pages: `git diff develop..HEAD -- src/features/*/components/ src/features/*/pages/ src/app/`

## Phase 4 — Fix & Re-verify

Combine findings and fix by priority:
1. 🔴 Critical — Security, auth, data loss
2. 🟠 High — Observability, type safety, error handling
3. 🟡 Medium — DB alignment, a11y
4. 🟢 Low — Formatting, naming

## Phase 5 — Undraft & Merge

```bash
gh pr ready PR_NUMBER
gh pr checks PR_NUMBER --watch
gh pr merge PR_NUMBER --merge
```

**REST API merge fallback:**
```bash
gh api -X PUT repos/<owner>/<repo>/pulls/<PR_NUMBER>/merge \
  -f commit_title="feat(scope): description (Issue #N)" \
  -f merge_method=squash
```

## Large PR / Tool-Call-Budget Strategy

With ~50 tool calls per turn, a big implementation + review + merge cannot complete in one turn.

**Split across turns:**
- **Turn 1–2:** Implementation via `delegate_task` (max 3 parallel subagents)
- **Turn 2–3:** Local verification in one terminal call
- **Turn 3–4:** Draft PR + parallel AI review
- **Turn 4–5:** Apply fixes + re-verify
- **Turn 5:** Merge (ensure >15 tool calls remaining)

Never run `gh pr merge` after already consuming 35+ tool calls in the same turn.

## Timeout-Proof Review

When `delegate_task` subagents hit `max_iterations` or diffs are too large:

1. **Split by category** — Never send 2000+ lines to one reviewer
2. **Limit scope** — Each subagent reviews only files in its domain
3. **Preserve context** — Pass issue body, PR description, and test results, not just diff

## Handling Conflicts

If develop diverged since branch creation:

```bash
git checkout develop && git pull origin develop
git checkout feature/issue-N-description
git merge develop
# Fix conflicts, commit, push
```

If rebase has too many conflicts, create a fresh branch from latest develop and cherry-pick:

```bash
git checkout develop && git pull origin develop
git checkout -b feature/issue-N-description-v2
git cherry-pick <original-sha> --no-commit
git commit -m "feat(scope): description"
git push origin feature/issue-N-description-v2
gh pr close OLD_PR
gh pr create --base develop --head feature/issue-N-description-v2 ...
```

## Pitfalls

- **Permission denied on .git/** — `sudo chown -R $(whoami):$(whoami) .git/`
- **Checks showing 0 / not running** — CI workflow may use `paths` filter; push a new commit to re-trigger
- **gh pr checks GraphQL error** — Token permissions; fallback to `gh pr view N --json mergeStateStatus`
- **PR body special characters** — Use `--body-file` with a heredoc instead of inline `--body`
- **gh pr merge GraphQL errors** — Use REST API `PUT .../pulls/N/merge` fallback
- **Old feature branch base** — If develop moved far ahead, abandon rebase and create a fresh branch
