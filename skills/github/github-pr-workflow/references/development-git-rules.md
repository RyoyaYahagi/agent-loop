---
name: development-git-workflow
title: Development Git Workflow
description: Git workflow rules covering commits, branches, PRs, CI, and issue prioritization.
category: software-development
---

# Development Git Rules

## Commit Rules

- **One commit per meaningful change**
- **Each commit must be buildable and testable** whenever possible
- **No unrelated changes in the same commit**

## Branch Rules

- **One branch per task, issue, or sub-issue**
- **Never push to main**

## Push Rules

- **Push only when local test, lint, and typecheck pass**
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

## Issue Selection and Prioritization Rules

### 1. Always read issue content — never trust labels blindly

- **Missing labels ≠ low priority.** An issue without labels may simply have been forgotten. Read the body to judge actual importance.
- **`Backlog Later` ≠ unimplementable.** Once MVP is complete, these issues become actionable.
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

When priority is roughly equal, implement in **issue number order** (ascending). This ensures systematic progress.

> **User override rule:** When the user explicitly says to proceed in number order (e.g. 「やっぱり番号順」/ "actually go with number order"), always follow that instruction.

### 4. Issue discovery workflow

```bash
# 1. List open issues
gh issue list --state open --limit 100 --json number,title,labels

# 2. Read each candidate issue in full
gh issue view <number>

# 3. Judge priority from content, not labels
```

## Next.js Static Build Pitfall

**Problem:** `npm run build` fails in CI with:
```
Error: Dynamic server usage: Route /portfolio couldn't be rendered statically because it used `cookies`.
```

**Root cause:** Next.js attempts static generation for pages that call `getCurrentUser()`, which internally uses `cookies()` from `next/headers`.

**Affected pages:** Any server component that calls `getCurrentUser()` or reads cookies/headers.

**Fix:** Add `export const dynamic = "force-dynamic"` at the top of the page file:
```typescript
export const dynamic = "force-dynamic";

export default async function Page() {
  const user = await getCurrentUser();
  // ...
}
```

**Why not `export const revalidate = 0`?** That opts into dynamic rendering for ISR, but `force-dynamic` is the explicit signal for fully dynamic server rendering.

**Prevention rule:** When creating a new server component page that calls `getCurrentUser()`, always add `export const dynamic = "force-dynamic"` at the top level.
