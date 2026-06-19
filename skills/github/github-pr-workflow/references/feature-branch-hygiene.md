---
name: feature-branch-workflow
description: "Git workflow for feature-branch development: branch hygiene, commit rules, PR templates, review handling, CI troubleshooting, and post-merge cleanup."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
---

# Feature Branch Hygiene

## Branch Model

```
main      — production (protected)
  ↑
develop   — daily integration
  ↑
feature/issue-42-auth
feature/issue-43-db-schema
```

## Commit Rules

- One commit per meaningful change
- Each commit must be buildable and testable
- No unrelated changes in the same commit
- Use prefixes: `feat(<scope>)`, `fix(<scope>)`, `refactor(<scope>)`, `test(<scope>)`, `docs(<scope>)`, `chore(<scope>)`

## PR Body Template

```markdown
## 概要
...

## 検証結果
- [x] lint
- [x] typecheck
- [x] test

Closes #<NUMBER>
```

## Review Comment Categories

When handling AI or human review comments, classify and prioritize:

1. **🔴 Critical** — Security, auth, data loss, production breakage
2. **🟠 High** — Type safety, error handling, observability
3. **🟡 Medium** — DB alignment, a11y, responsive design
4. **🟢 Low** — Formatting, naming, minor suggestions

## CI Troubleshooting

- **Checks not running** — CI workflow may use `paths` filter; push a new commit to re-trigger
- **GraphQL error from `gh pr checks`** — Token permissions; use `gh pr view --json mergeStateStatus` as fallback
- **Format check fails** — Run `npx prettier --write .` and re-commit

## Post-Merge Cleanup

```bash
git checkout develop
git pull origin develop
git branch -d feature/issue-N-description  # local delete
# Remote branch is deleted by --delete-branch on merge
```

## Sequential Work

When implementing issues back-to-back, `develop` almost always diverges between branch creation and PR merge because previous PRs were squash-merged. This is expected.

**Standard merge command:**
```bash
git pull origin develop && gh pr merge {pr_number} --squash --delete-branch
```

If fast-forward aborts:
```bash
git merge --abort 2>/dev/null || true
git pull origin develop
gh pr merge {pr_number} --squash --delete-branch
```

## Recovering from Diverged Branches

If develop has moved far ahead and rebase conflicts on every commit:

```bash
git checkout develop && git pull origin develop
git checkout -b feature/issue-N-v2
git cherry-pick <original-sha> --no-commit
git commit -m "feat: description"
git push origin feature/issue-N-v2
gh pr close OLD_PR
gh pr create --base develop --head feature/issue-N-v2 ...
```
