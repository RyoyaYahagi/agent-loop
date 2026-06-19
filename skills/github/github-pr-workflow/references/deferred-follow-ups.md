# Deferred Follow-ups — Review Comment Resolution

Condensed workflow for handling unaddressed review comments at merge time. Never leave comments as "will fix later" without tracking.

## Classification Rules

| Severity | Merge Block? | Required Action |
|----------|-------------|-----------------|
| **Blocking** | Yes | Must be resolved before merge |
| **Security** | Yes | Must be resolved before merge |
| **CI failure** | Yes | Must be resolved before merge |
| **Suggestion** | No | Classify — do not leave unattended |
| **Nit** | No | Classify — do not leave unattended |
| **Scope improvement** | No | Classify — do not leave unattended |

## Four Categories

Every unaddressed comment must be placed in exactly one of these:

### 1. Resolved
Already fixed in a commit. Link the commit hash.

```markdown
| # | Comment | Resolution | Commit |
|---|---------|-----------|--------|
| 3 | Use `getUser()` instead of `getClaims()` | Changed to `getUser()` for token refresh | `a1b2c3d` |
```

### 2. Spin-off Issue
Out of scope, large, or needs separate design. Create a GitHub issue, link it in the PR comment.

```markdown
| # | Comment | Spin-off Issue |
|---|---------|----------------|
| 5 | Separate Supabase client for server/client | #104 — [Refactor] Supabase client separation |
```

**Rule:** The PR comment (or body) must link the new issue number. Never write "will do in a separate PR" without an issue.

### 3. Not Needed
Intentionally skipped. Write a 1-2 sentence reason.

```markdown
| # | Comment | Reason |
|---|---------|--------|
| 7 | Rename `ruleJson` to `ruleJSON` | Project convention uses camelCase even for acronyms; lint/typecheck pass with current naming |
```

### 4. Pending Human
Needs user decision. Flag explicitly with the question.

```markdown
| # | Comment | Question |
|---|---------|----------|
| 9 | `ruleJson` should store structured data, not string | Q: Should we store parsed JSON or raw string? Current implementation stores string; changing affects migration |
```

## PR Comment Template

Post this as a top-level comment on the PR before merging:

```markdown
## Deferred follow-ups — Review resolution summary

### Resolved (N items)
| # | Comment | Resolution | Commit |
|---|---------|-----------|--------|
| ... | ... | ... | ... |

### Spin-off Issues (N items)
| # | Comment | Issue |
|---|---------|-------|
| ... | ... | #... |

### Not Needed (N items)
| # | Comment | Reason |
|---|---------|--------|
| ... | ... | ... |

### Pending Human Decision (N items)
| # | Comment | Question |
|---|---------|----------|
| ... | ... | ... |

---
All blocking/security/CI items resolved. Merge is safe.
```

## Automation Checklist

Before posting the comment, verify:
- [ ] Every review comment from the AI review is accounted for
- [ ] No comment is left as "TODO" or "later" without a category
- [ ] Spin-off issues are actually created (not just mentioned)
- [ ] PR body or a comment links all spin-off issue numbers
- [ ] The "Deferred follow-ups" section is added to PR body or as a comment

## Anti-Patterns

❌ **"Will fix in a follow-up PR"** — without a linked issue  
❌ **"Not important enough"** — without a written reason  
❌ **Leaving comments unacknowledged** — every comment must be classified  
❌ **"TODO: ask user about X"** — use "Pending Human" with the exact question
