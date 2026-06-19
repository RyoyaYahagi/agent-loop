# Accidental Commit Cleanup Reference

## Problem

Local development tools (Claude Code worktrees, build caches, design prototypes) sometimes get committed to the repo before their ignore patterns are added to `.gitignore` or `.eslintignore`. These files bloat PR diffs and cause CI/lint noise.

## Detection

```bash
# See what files are in the branch diff that shouldn't be
git diff --name-only main..HEAD | grep -E '^\.(claude|next|turbo)/|^frontend-design/|^docs/ai-handoffs/'

# See total diff stat to spot unexpectedly large additions
git diff --stat main..HEAD | tail -5
```

## Removal from git tracking (keeps files locally)

```bash
# Remove directory from tracking but keep on disk
git rm -r --cached .claude/
git commit -m "chore: remove accidentally committed .claude/ worktree files"

# Also add to .gitignore if not already there
echo ".claude/" >> .gitignore
git add .gitignore
git commit -m "chore: add .claude/ to .gitignore"
```

## Common directories to audit before PR

| Tool / Framework | Directory | Ignore pattern |
|------------------|-----------|----------------|
| Claude Code | `.claude/` | `.claude/**` |
| Next.js | `.next/` | `.next/**` |
| Vite / Turbopack | `dist/`, `.turbo/` | `dist/**`, `.turbo/**` |
| Design prototypes | `frontend-design/` | `frontend-design/**` |
| AI handoff docs | `docs/ai-handoffs/` | `docs/ai-handoffs/**` |
| Python venv | `.venv/`, `venv/` | `.venv/**`, `venv/**` |

## ESLint-specific cleanup

If lint is scanning build output or prototype directories, add them to `eslint.config.mjs` (or `.eslintignore`):

```js
import { globalIgnores } from "eslint/config";

const eslintConfig = defineConfig([
  // ... existing configs
  globalIgnores([
    ".next/**",
    ".claude/**",
    "frontend-design/**",
    "docs/ai-handoffs/**",
  ]),
]);
```

## Prevention checklist

- [ ] `cat .gitignore | grep <tool-name>` — verify ignore pattern exists
- [ ] `git status` before first commit — catch untracked directories early
- [ ] `git diff --name-only main..HEAD` before PR — audit the full diff
