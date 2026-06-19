---
name: development-git-workflow
title: Development Git Workflow
description: Git workflow rules for this project, covering commits, branches, PRs, and CI.
category: software-development
---

# Development Git Workflow

This skill captures the user's explicit git workflow rules.

## Commit Rules

- **One commit per meaningful change** (1つの意味ある変更ごとにコミット)
- **Each commit must be buildable and testable** (可能な限りビルド・テストが通る状態)
- **No unrelated changes in the same commit** (unrelated changes を同じコミットに混ぜない)

## Branch Rules

- **One branch per task, issue, or sub-issue** (タスク、issue、subissue1つ毎にブランチを分ける)
- **Never push to main** (main には絶対に push しない)

## Push Rules

- **Push only when local test, lint, and typecheck pass** (ローカルテスト・lint・typecheck が通ったタイミングで push)
- After first push, create a **Draft PR**

## PR Template

PR body must include:
1. Purpose (目的)
2. Change description (変更内容)
3. Tests performed (実行したテスト)
4. Remaining tasks (残タスク)
5. Points for human review (人間に確認してほしい点)

## Post-PR Workflow

1. After Draft PR creation, check CI results and diff
2. Send to separate AI review (別AIレビューに回す)
3. Merge to main is done by humans only

## Workflow Summary

```
Code → Local Test/Lint/TypeCheck → Commit → Push → Draft PR → CI Check → AI Review → Human Merge
```

## Pitfalls

- Do not combine multiple unrelated fixes in one commit
- Do not push to main under any circumstances
- Do not create PR before local checks pass
- CI will run automatically on PR creation (usually)

## Issue Selection and Prioritization Rules

When choosing the next issue to implement:

### 1. Always read issue content — never trust labels blindly

- **Missing labels ≠ low priority.** An issue without labels may simply have been forgotten. Read the body to judge actual importance.
- **`Backlog Later` ≠ unimplementable.** Once MVP is complete, these issues become actionable. Read the content and assess priority fresh.
- **`enhancement` ≠ low priority.** Security enhancements or test coverage enhancements can be critical.

### 2. Priority assessment from content

Read the issue body and assess:

| Factor | Higher Priority | Lower Priority |
|--------|----------------|--------------|
| Security/RLS impact | Direct security risk | Refactoring with no user-facing change |
| Test coverage | Missing tests for critical paths | Tests for edge cases already covered |
| Core feature gap | Blocks user workflow | Nice-to-have UI polish |
| Technical debt | Causes bugs or blocks future work | Cosmetic code cleanup |

### 3. Default order

When priority is roughly equal, implement in **issue number order** (ascending). This ensures systematic progress and avoids skipping smaller issues.

> **User override rule:** When the user explicitly says to proceed in number order (e.g. 「やっぱり番号順」/ "actually go with number order"), always follow that instruction even if a priority-based ordering was previously suggested.

### 4. Issue discovery workflow

```bash
# 1. List open issues
gh issue list --state open --limit 100 --json number,title,labels | \
  python3 -c "import sys,json; [print(f\"{i['number']}: {i['title']} [{', '.join(l['name'] for l in i['labels'])}]\") for i in json.load(sys.stdin)]"

# 2. Read each candidate issue in full
gh issue view <number>

# 3. Judge priority from content, not labels
```

## Next.js Static Build Pitfall

**Problem:** `npm run build` fails in CI with:
```
Error: Dynamic server usage: Route /portfolio couldn't be rendered statically because it used `cookies`.
digest: 'DYNAMIC_SERVER_USAGE'
```

**Root cause:** Next.js attempts static generation for pages that call `getCurrentUser()`, which internally uses `cookies()` from `next/headers`. `cookies()` is a dynamic server API and cannot be called during static generation.

**Affected pages:** Any server component that calls `getCurrentUser()` or any function that reads cookies/headers, including:
- `/dashboard`
- `/rules/new`
- `/rules/[sessionId]`
- `/portfolio`
- `/portfolio/positions/new`

**Fix:** Add `export const dynamic = "force-dynamic"` at the top of the page file:
```typescript
export const dynamic = "force-dynamic";

export default async function Page() {
  const user = await getCurrentUser();
  // ...
}
```

**Why not `export const revalidate = 0`?** That opts into dynamic rendering for ISR, but `force-dynamic` is the explicit signal for fully dynamic server rendering, which is what we want for authenticated pages.

**Prevention rule:** When creating a new server component page that calls `getCurrentUser()`, always add `export const dynamic = "force-dynamic"` at the top level.