---
name: github-code-review
description: "Review PRs: diffs, inline comments via gh or REST."
version: 1.1.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
---

# GitHub Code Review

Perform code reviews on local changes or open PRs.

## Prerequisites

- Authenticated with GitHub (see `github-auth`)
- Inside a git repository

## Reviewing Local Changes (Pre-Push)

```bash
# Staged changes
git diff --staged
# All changes vs main
git diff main...HEAD
# Stat summary
git diff main...HEAD --stat
```

### Check for common issues
```bash
git diff main...HEAD | grep -n "print(\|console\.log\|TODO\|FIXME\|HACK\|debugger"
git diff main...HEAD --stat | sort -t'|' -k2 -rn | head -10  # Large files
git diff main...HEAD | grep -in "password\|secret\|api_key\|token.*="
git diff main...HEAD | grep -n "<<<<<<\|>>>>>>\|======="  # Conflict markers
```

### Review Output Format
```
## Code Review Summary

### Critical
- **src/auth.py:45** — SQL injection. Suggestion: parameterized queries.

### Warnings
- **src/models/user.py:23** — Password stored in plaintext.

### Suggestions
- **src/utils/helpers.py:8** — Duplicates logic in core/utils.py:34.

### Looks Good
- Clean separation of concerns
```

## Reviewing a Pull Request on GitHub

### View PR Details

```bash
gh pr view 123
gh pr diff 123
gh pr diff 123 --name-only
```

### Check Out PR Locally

```bash
# With gh
gh pr checkout 123

# With git (no gh needed)
git fetch origin pull/123/head:pr-123
git checkout pr-123
```

### Leave Comments on a PR

General comment:
```bash
gh pr comment 123 --body "Overall looks good, a few suggestions below."
```

Inline comment via API:
```bash
HEAD_SHA=$(gh pr view 123 --json headRefOid --jq '.headRefOid')
gh api repos/$OWNER/$REPO/pulls/123/comments \
  --method POST \
  -f body="This could be simplified." \
  -f path="src/auth/login.py" \
  -f commit_id="$HEAD_SHA" \
  -f line=45 \
  -f side="RIGHT"
```

### Submit a Formal Review

```bash
gh pr review 123 --approve --body "LGTM!"
gh pr review 123 --request-changes --body "See inline comments."
gh pr review 123 --comment --body "Some suggestions."
```

Atomic multi-comment review via curl:
```bash
HEAD_SHA=$(curl -s -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/repos/$OWNER/$REPO/pulls/$PR_NUMBER \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['head']['sha'])")

curl -s -X POST \
  -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/repos/$OWNER/$REPO/pulls/$PR_NUMBER/reviews \
  -d "{
    \"commit_id\": \"$HEAD_SHA\",
    \"event\": \"REQUEST_CHANGES\",
    \"body\": \"Review by Hermes Agent\",
    \"comments\": [
      {\"path\": \"src/auth.py\", \"line\": 45, \"body\": \"Use parameterized queries.\"}
    ]
  }"
```

Event values: `"APPROVE"`, `"REQUEST_CHANGES"`, `"COMMENT"`

## Review Checklist

### Correctness
- Does the code do what it claims?
- Edge cases handled (empty inputs, nulls, large data, concurrency)?
- Error paths handled gracefully?

### Security
- No hardcoded secrets, credentials, or API keys
- Input validation on user-facing inputs
- No SQL injection, XSS, or path traversal
- Auth/authz checks where needed

### Code Quality
- Clear naming, no unnecessary complexity, DRY, focused functions

### Testing
- New code paths tested? Happy path and error cases covered?

### Performance
- No N+1 queries or unnecessary loops, appropriate caching

### Documentation
- Public APIs documented, non-obvious logic has "why" comments

## Review Model Strategy (Cost vs Quality)

**Tier 1 — Routine Reviews (Subagent)**
- Use `delegate_task` to spawn parallel subagents
- Split diffs into ≤300 lines per category
- Assign 1–2 files per subagent for deep review
- Embed diff text directly in context; do not rely on file paths
- Instruct subagents to output one-line findings with severity + file:line + fix

**Tier 2 — Important Design Reviews (Premium Model)**
- Architecture design validation, complex concurrency, security threat-modeling

**Subagent Review Pitfalls & Fixes**

- **Subagent tries to mutate files instead of reviewing**
  → Fix: Explicitly instruct "You are a reviewer ONLY. Do NOT create, modify, or delete any files."
  → Use `toolsets: ["file"]` only — no `write_file` or `patch` access.

- **Subagent cannot access diff files on disk**
  → Fix: Embed diff content directly in the subagent's `context` string.

- **max_iterations / timeout on large diffs**
  → Fix: Split diffs into ≤300 lines per category. Limit parallel subagents to 3.

- **Simple fixes delegated to subagents**
  → Fix: Parent agent applies trivial BLOCKING fixes directly. Reserve subagents for multi-file design changes.

- **Review hallucinations (false positives)**
  → Fix: Parent agent verifies every BLOCKING finding by reading the actual file.

## Supabase RLS Security Patterns

When reviewing migrations or DB schemas with Supabase RLS, watch for these patterns:

### ❌ Dangerous: Authenticated users can INSERT/UPDATE counters/logs
```sql
-- BAD: Users can directly manipulate rate limits, costs, or logs
create policy "Users can insert own rate_limit_counters" on rate_limit_counters for insert ...;
```
**Risk:** Users can reset used_count to bypass rate limits, inject fake error logs.

### ❌ Dangerous: check + increment separated (TOCTOU race)
```typescript
// BAD: read-modify-write pattern
const { data: existing } = await supabase.from("rate_limit_counters").select("used_count")...;
await supabase.from("rate_limit_counters").update({ used_count: existing.used_count + 1 }).eq("id", existing.id);
```
**Risk:** Two parallel requests both read 5, both increment to 6, but limit is 10.

### ✅ Safe: Server-only writes via `security definer` RPC
```sql
-- 1. Remove INSERT/UPDATE policies for server-only tables
-- 2. Provide atomic increment functions with security definer
create or replace function increment_rate_limit_counter(...)
returns void language plpgsql security definer as $$
begin
  insert into rate_limit_counters (...)
  values (...)
  on conflict (user_id, limit_key, period_start, period_end)
  do update set used_count = rate_limit_counters.used_count + p_increment_by;
end;
$$;
```

### ✅ Safe: UTC period boundaries
```typescript
const now = new Date();
const utcNow = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate(),
  now.getUTCHours(), now.getUTCMinutes(), now.getUTCSeconds()));
start.setUTCHours(0, 0, 0, 0);
```

### DB Review Checklist
- [ ] `rate_limit_counters`, `cost_limit_counters`, `api_error_logs` have **no** authenticated INSERT/UPDATE policies
- [ ] Server-side code uses **RPC functions** (`security definer`) for writes
- [ ] `increment_*` functions use `on conflict do update` for atomicity
- [ ] `period_start`/`period_end` use **UTC** boundaries
- [ ] `used_count` / `used_cost_usd` have `check (column >= 0)` constraints
- [ ] `incrementBy` / `costUsd` parameters are validated (reject negative values)
