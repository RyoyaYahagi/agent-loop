---
name: github-pr-workflow
description: "GitHub PR lifecycle: branch, commit, open, CI, merge."
version: 1.2.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [GitHub, Pull-Requests, CI/CD, Git, Automation, Merge]
    related_skills: [github-auth, github-code-review]
---

# GitHub Pull Request Workflow

Complete guide for managing the PR lifecycle. Each section shows the `gh` way first, then the `git` + `curl` fallback for machines without `gh`.

## Prerequisites

- Authenticated with GitHub (see `github-auth` skill)
- Inside a git repository with a GitHub remote

### Quick Auth Detection

```bash
# Determine which method to use throughout this workflow
if command -v gh &>/dev/null && gh auth status &>/dev/null; then
  AUTH="gh"
else
  AUTH="git"
  # Ensure we have a token for API calls
  if [ -z "$GITHUB_TOKEN" ]; then
    if [ -f ~/.hermes/.env ] && grep -q "^GITHUB_TOKEN=" ~/.hermes/.env; then
      GITHUB_TOKEN=$(grep "^GITHUB_TOKEN=" ~/.hermes/.env | head -1 | cut -d= -f2 | tr -d '\n\r')
    elif grep -q "github.com" ~/.git-credentials 2>/dev/null; then
      GITHUB_TOKEN=$(grep "github.com" ~/.git-credentials 2>/dev/null | head -1 | sed 's|https://[^:]*:\([^@]*\)@.*|\1|')
    fi
  fi
fi
echo "Using: $AUTH"
```

### Extracting Owner/Repo from the Git Remote

Many `curl` commands need `owner/repo`. Extract it from the git remote:

```bash
# Works for both HTTPS and SSH remote URLs
REMOTE_URL=$(git remote get-url origin)
OWNER_REPO=$(echo "$REMOTE_URL" | sed -E 's|.*github\.com[:/]||; s|\.git$||')
OWNER=$(echo "$OWNER_REPO" | cut -d/ -f1)
REPO=$(echo "$OWNER_REPO" | cut -d/ -f2)
echo "Owner: $OWNER, Repo: $REPO"
```

---

## 0. Pre-Implementation Check

Before starting any issue implementation, verify the issue is not already done:

```bash
# Check if the issue is already closed on GitHub
cd /workspace/dev/app/Ruletrade-AI
gh issue view <number> --json number,title,state

# Check if the issue title appears in recent commit history
git log --oneline --all --grep="#<number>" | head -5
git log --oneline --all --grep="<issue-title-keyword>" -i | head -10

# Check if the feature files already exist
ls src/features/<feature-name>/ 2>/dev/null && echo "FEATURE ALREADY EXISTS"

# Check if the migration already exists
ls supabase/migrations/*<keyword>*.sql 2>/dev/null | head -5
```

**Why this matters:** In multi-session work, another agent or a previous session may have already implemented the issue. Starting from scratch wastes time and creates merge conflicts. The `state` field from `gh issue view` is the source of truth — even if commits exist, the issue may still be OPEN on GitHub (needs manual close).

**When the issue is already implemented:**
1. Verify the implementation is actually merged to `develop`
2. Close the GitHub issue with a comment referencing the merge commit/PR
3. Move to the next open issue immediately
4. Do NOT re-implement

**When the remote branch already has the work:**
```bash
# Another session pushed the branch but didn't PR/merge
git fetch origin
git branch -r | grep feature/issue-<number>

# Reset local to match remote (if local has conflicts)
git checkout feature/issue-<number>
git reset --hard origin/feature/issue-<number>

# Or checkout the remote branch fresh
git fetch origin feature/issue-<number>:feature/issue-<number>
git checkout feature/issue-<number>
```

This part is pure `git` — identical either way:

```bash
# Make sure you're up to date
git fetch origin
git checkout main && git pull origin main

# Create and switch to a new branch
git checkout -b feat/add-user-authentication
```

Branch naming conventions:
- `feat/description` — new features
- `fix/description` — bug fixes
- `refactor/description` — code restructuring
- `docs/description` — documentation
- `ci/description` — CI/CD changes

## 2. Making Commits

Use the agent's file tools (`write_file`, `patch`) to make changes, then commit:

```bash
# Stage specific files
git add src/auth.py src/models/user.py tests/test_auth.py

# Commit with a conventional commit message
git commit -m "feat: add JWT-based user authentication

- Add login/register endpoints
- Add User model with password hashing
- Add auth middleware for protected routes
- Add unit tests for auth flow"
```

Commit message format (Conventional Commits):
```
type(scope): short description

Longer explanation if needed. Wrap at 72 characters.
```

Types: `feat`, `fix`, `refactor`, `docs`, `test`, `ci`, `chore`, `perf`

### User-Defined Git Workflow Rules (Project-Specific)

Some teams have strict PR workflow rules. When a user provides such rules, embed them in this skill and follow them exactly.

**Ruletrade-AI Project Rules (confirmed by user):**

```
1. Commit per meaningful change (atomic commits)
2. Each commit should be buildable/testable whenever possible
3. No unrelated changes in the same commit
4. Separate branches per task/issue/subissue
5. Never push to main
6. Push working branches only after local tests/lint/typecheck pass
7. Create Draft PR after first push
8. PR body includes: purpose, changes, tests run, remaining tasks, points for human review
9. After Draft PR creation, check CI results and diff, then send to AI review
10. Merge to develop (agent-managed), never to main
11. Humans handle develop→main merge only
12. After PR merge, clean up both remote and local branches immediately:
    git switch develop
    git pull
    git branch -d <branch>
    git fetch --prune
```

When applying these rules:
- Run `npm run lint`, `npm run typecheck`, `npm test` (or equivalents) before every push
- Create the PR with `--draft` flag
- Verify the PR body contains all required sections (see `templates/pr-body-japanese.md` for Japanese projects)
- Only the human user merges to main — never merge via the agent
- Branch cleanup is mandatory after every merge, not optional

### develop Branch Integration Environment (AI-Managed Loop)

When the project uses a `develop` branch as the **AI integration branch** (agent-managed, human merges to main):

```
Branch from develop → implement → PR (targets develop) → AI review → fix → merge to develop → CI check → fix if needed → next issue
```

**The agent owns the entire loop except the final develop→main merge.**

```bash
# 1. Always branch from latest develop
git checkout develop && git pull origin develop
git checkout -b feat/issue-42-rule-creation

# 2. Implement, commit atomically, run local checks
npm run lint && npm run typecheck && npm test

# 3. Push and create Draft PR targeting develop
git push -u origin HEAD
gh pr create --draft --base develop --title "..." --body "..."

# 4. AI review via subagent (delegate_task with kimi-k2.6 or similar)
# 5. Fix review comments, push updates
# 6. When clean, merge to develop (agent action)
gh pr ready <number>  # if still draft
gh pr merge <number> --merge --subject "..."

# 7. CI runs on develop automatically
#    If CI fails, fix immediately on a new branch from develop
#    Then PR → merge to develop again

# 8. Clean up merged branch
git switch develop
git pull origin develop
git branch -d feat/issue-42-rule-creation
git fetch --prune

# 9. Next issue: branch from develop again
git checkout -b feat/issue-43-ai-provider
```

**Key rules for this workflow:**
- `develop` is the integration branch — all AI work merges here
- `main` is human-only — the user decides when develop→main happens
- The agent loops indefinitely on develop: branch → implement → PR → review → merge → CI → repeat
- Never leave CI failing on develop — fix immediately
- Always `git pull origin develop` before creating a new branch to avoid stale base

### Branch Cleanup After Merge

When a PR is merged to develop (or main), clean up both local and remote branches immediately:

```bash
# 1. Switch to the integration branch
git switch develop   # or main

# 2. Pull latest (includes the merge commit)
git pull origin develop

# 3. Delete the local feature branch
git branch -d <branch-name>
# Use -D if the branch was not fully merged (force delete)

# 4. Prune remote tracking branches
git fetch --prune

# 5. (Optional) Delete remote branch if not auto-deleted by merge
git push origin --delete <branch-name>
```

**Pitfall:** Forgetting `git fetch --prune` leaves stale `remotes/origin/*` entries that clutter `git branch -a` output and confuse future sessions.

**Pitfall:** Deleting the local branch before pulling the merge commit causes `git branch -d` to warn "not fully merged" and requires `-D`. Always pull first.

### Deferred Follow-ups (Review Comment Resolution)

When review comments remain unaddressed at merge time, classify each one instead of leaving it as "will do later":

| Category | Action |
|----------|--------|
| **Resolved** | Already fixed in a commit — link the commit |
| **Spin-off Issue** | Out of scope or large — create a new issue, link in PR comment |
| **Not needed** | Intentionally skipped — write a 1-2 sentence reason |
| **Pending human** | Needs user decision — flag explicitly |

**Rules:**
- Blocking / Security / CI failure comments → **must be resolved before merge**
- Suggestion / Nit / scope improvements → **must not be left unattended** even if skipped
- Never write "will fix later" as a PR comment without a linked issue
- After classification, add a "Deferred follow-ups" section to the PR body or a summary comment

See `references/deferred-follow-ups.md` for the full template.

### develop Branch Integration Environment

When the project uses a `develop` branch as the AI integration environment (where AI agents manage the latest state):

```bash
# 1. Create develop branch from main (one-time setup)
git checkout main && git pull origin main
git checkout -b develop
git push -u origin develop

# 2. All PRs target develop, not main
gh pr create --draft --base develop --title "..." --body "..."
# Or change base of existing PR:
gh pr edit <number> --base develop

# 3. main is only merged to by humans
git checkout main && git pull origin main
```

**Key difference from main-only workflow:**
- PR base: `develop` instead of `main`
- `develop` acts as the integration staging area for AI-managed changes
- `main` remains the production-ready branch, merged only by humans
- After `develop` accumulates changes, humans decide when to merge `develop` → `main`

### Draft PR Lifecycle

```bash
# 1. Push after local checks pass
git push -u origin HEAD

# 2. Create Draft PR
gh pr create --draft --title "..." --body "..."

# 3. Check CI status
gh pr checks --watch

# 4. After CI passes, send to AI review (via delegate_task subagents)
# 5. Once AI review is clean, mark Ready for Review
gh pr ready

# 6. Human merges to main
```

### Draft PR Merge Pitfall

**Important:** Draft PRs cannot be merged directly. The GitHub API returns:
```
GraphQL: Pull Request is still a draft (mergePullRequest)
```

**Always convert to Ready for Review before merging:**

```bash
# Make the PR ready for review first
gh pr ready <number>

# Then merge
gh pr merge <number> --merge --subject "..."
```

```bash
# 1. Push after local checks pass
git push -u origin HEAD

# 2. Create Draft PR
gh pr create --draft --title "..." --body "..."

# 3. Check CI status
gh pr checks --watch

# 4. After CI passes, send to AI review (via delegate_task subagents)
# 5. Once AI review is clean, mark Ready for Review
gh pr ready

# 6. Human merges to main
```

Before creating a PR, verify the branch diff is clean and does not contain build artifacts, local worktrees, or other files that should be ignored.

### Check for accidentally-committed files

```bash
# Quick audit of what will be in the PR
git diff --name-only main..HEAD | grep -v '^\.' | sort

# Check for common accidentally-committed directories
git diff --name-only main..HEAD | grep -E '^(\.claude|\.next|node_modules|frontend-design|\.venv|\.hermes/plans)/'
```

If any appear, add them to `.gitignore` (or `.eslintignore` if they cause lint noise) and remove from tracking:

```bash
# 1. Add to the appropriate ignore file
echo ".claude/**" >> .gitignore
echo "frontend-design/**" >> .gitignore
echo ".claude/**" >> eslint.config.mjs   # if they cause lint errors

# 2. Remove from git tracking (keep files locally)
git rm -r --cached .claude/ frontend-design/

# 3. Commit the cleanup
git commit -m "chore: remove accidentally committed directories from tracking

- .claude/ (Claude Code worktrees)
- frontend-design/ (design assets)"
```

### Common accidentally-committed directories

| Directory | Why it leaks | Cleanup command | Ignore entry |
|-----------|-------------|-----------------|--------------|
| `.claude/` | Claude Code worktrees | `git rm -r --cached .claude/` | `.claude/**` |
| `.next/` | Next.js build output | `git rm -r --cached .next/` | `.next/**` |
| `node_modules/` | npm dependencies | `git rm -r --cached node_modules/` | `node_modules/**` |
| `frontend-design/` | Design mockups/assets | `git rm -r --cached frontend-design/` | `frontend-design/**` |
| `.hermes/plans/` | Agent plan files | `git rm -r --cached .hermes/plans/` | `.hermes/plans/**` |
| `.agents/skills/notebooklm/` | Large external skill packages | `git rm -r --cached .agents/skills/notebooklm/` | `.agents/skills/notebooklm/` |

**Example: removing a large external package like notebooklm**

When an external skill or package (e.g., `.agents/skills/notebooklm/` with 400+ files) is accidentally committed:

```bash
# 1. Add to .gitignore
echo ".agents/skills/notebooklm/" >> .gitignore

# 2. Remove from git tracking (keeps files locally)
git rm -r --cached .agents/skills/notebooklm/

# 3. Regenerate lockfile if the package affected dependencies
npm install --package-lock-only

# 4. Commit the cleanup
git add .gitignore package-lock.json
git commit -m "chore: ignore external package directory

- Remove .agents/skills/notebooklm/ from git tracking (400+ files)
- Regenerate package-lock.json to sync dependencies"
```

**Why this matters:** Large external packages often contain test fixtures, mock credentials, or YAML cassettes that trigger secret scans (e.g., `gitleaks detect` reports "leaks found: 22"). Removing them from tracking fixes both repo bloat and CI secret-scan failures.

Always check with `git diff --stat main..HEAD` (or `git diff --name-only main..HEAD`) before opening a PR.

```bash
# Quick audit of what will be in the PR
git diff --name-only main..HEAD | grep -v '^\.' | sort
```

If build artifacts or worktree files appear, remove them from tracking:

```bash
git rm -r --cached <directory>
git commit -m "chore: remove accidentally committed <directory> files"
```

### Remove Accidentally-Tracked Files from Git

When large directories (e.g., agent worktrees, external packages, build artifacts) are accidentally committed, remove them from git tracking without deleting local files:

```bash
# 1. Add to .gitignore
echo ".agents/skills/notebooklm/" >> .gitignore

# 2. Remove from git tracking (keeps files locally)
git rm -r --cached .agents/skills/notebooklm/

# 3. Regenerate lockfile if needed
npm install

# 4. Commit the cleanup
git add .gitignore package-lock.json
git commit -m "fix(ci): remove notebooklm skill from tracking and update lockfile

- Remove .agents/skills/notebooklm/ from git tracking (400+ files)
- Regenerate package-lock.json to sync prettier and prettier-plugin-tailwindcss"
```

**Pitfall:** If the remote branch already has these files (from another session), pushing will fail or create merge conflicts. In that case, prefer the remote's version:

```bash
git fetch origin
git checkout --ours .gitignore
git add .gitignore
git rebase --continue
```

### Pre-Push Verification Checklist

Before every push, run:

```bash
# 1. Check for accidentally-committed files
git diff --stat --cached
# or
git status

# 2. Verify no build artifacts or external packages are staged
git diff --cached --name-only | grep -E '^\.(claude|next|venv|agents/skills)/' && echo "WARNING: external files staged"

# 3. Run quality checks
npm run lint
npm run typecheck
npm test
npm run format:check   # add this to catch prettier failures before CI

# 4. Optional: create .env.local for sandbox testing (if not already present)
#    See templates/.env.local.sandbox for a dummy-env template
#    that lets the dev server start without real Supabase credentials.

# 5. Only then push
git push origin HEAD
```

**Optional: Start dev server for quick smoke test before push**
See `references/local-dev-server-testing.md` for how to start a Next.js dev server in the Docker sandbox and verify pages render correctly. For Supabase-specific local development (migrations, DB reset, mock auth), see `supabase-local-development` skill.

```bash
npm run lint
npm run typecheck
npm test
```

Push only after all three pass.

## 3. Pushing and Creating a PR

### Push the Branch (same either way)

```bash
git push -u origin HEAD
```

### Create the PR

**With gh:**

```bash
gh pr create \
  --title "feat: add JWT-based user authentication" \
  --body "## Summary
- Adds login and register API endpoints
- JWT token generation and validation

## Test Plan
- [ ] Unit tests pass

Closes #42"
```

**Pitfall: backticks in `--body` are interpreted by bash.**

When the PR body contains markdown backticks (e.g. `code`, `` `command` ``), passing it inline via `--body "..."` causes bash to try to execute the backtick content as a command. This leads to garbled PR bodies or command-not-found errors.

**Solutions:**

1. Use a here-document and pipe to `gh pr create`:

```bash
gh pr create --title "feat: add auth" --body-file - <<'EOF'
## Summary
- Adds `login()` and `register()` endpoints
- Uses `JWT` tokens

Closes #42
EOF
```

2. Write the body to a temp file first:

```bash
cat > /tmp/pr-body.md <<'EOF'
## Summary
- Adds `login()` and `register()` endpoints
EOF
gh pr create --title "feat: add auth" --body-file /tmp/pr-body.md
```

3. If you must use `--body`, escape every backtick or avoid them:

```bash
gh pr create --title "feat: add auth" --body 'Adds login() and register() endpoints'
```

Options: `--draft`, `--reviewer user1,user2`, `--label "enhancement"`, `--base develop`

**With git + curl:**

```bash
BRANCH=$(git branch --show-current)

curl -s -X POST \
  -H "Authorization: token $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github.v3+json" \
  https://api.github.com/repos/$OWNER/$REPO/pulls \
  -d "{
    \"title\": \"feat: add JWT-based user authentication\",
    \"body\": \"## Summary\nAdds login and register API endpoints.\n\nCloses #42\",
    \"head\": \"$BRANCH\",
    \"base\": \"main\"
  }"
```

The response JSON includes the PR `number` — save it for later commands.

To create as a draft, add `"draft": true` to the JSON body.

## 4. Monitoring CI Status

### Check CI Status

**With gh:**

```bash
# One-shot check
gh pr checks

# Watch until all checks finish (polls every 10s)
gh pr checks --watch
```

**With git + curl:**

```bash
# Get the latest commit SHA on the current branch
SHA=$(git rev-parse HEAD)

# Query the combined status
curl -s \
  -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/repos/$OWNER/$REPO/commits/$SHA/status \
  | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(f\"Overall: {data['state']}\")
for s in data.get('statuses', []):
    print(f\"  {s['context']}: {s['state']} - {s.get('description', '')}\")"

# Also check GitHub Actions check runs (separate endpoint)
curl -s \
  -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/repos/$OWNER/$REPO/commits/$SHA/check-runs \
  | python3 -c "
import sys, json
data = json.load(sys.stdin)
for cr in data.get('check_runs', []):
    print(f\"  {cr['name']}: {cr['status']} / {cr['conclusion'] or 'pending'}\")"
```

### Poll Until Complete (git + curl)

```bash
# Simple polling loop — check every 30 seconds, up to 10 minutes
SHA=$(git rev-parse HEAD)
for i in $(seq 1 20); do
  STATUS=$(curl -s \
    -H "Authorization: token $GITHUB_TOKEN" \
    https://api.github.com/repos/$OWNER/$REPO/commits/$SHA/status \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['state'])")
  echo "Check $i: $STATUS"
  if [ "$STATUS" = "success" ] || [ "$STATUS" = "failure" ] || [ "$STATUS" = "error" ]; then
    break
  fi
  sleep 30
done
```

### Detecting Unconfigured CI

```bash
# Check if CI workflows exist locally
cd /workspace/dev/app/Ruletrade-AI && find .github/workflows -type f 2>/dev/null || echo "No .github/workflows directory"

# Check if CI checks are reported on the PR
gh pr checks <number>
# → "no checks reported" means no CI is configured

# Verify on GitHub web UI: PR → Checks tab → should list workflows
```

**When CI is not configured:**

1. **Create a basic CI workflow** at `.github/workflows/ci.yml`:

```yaml
name: CI
on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm
      - run: npm ci
      - run: npm run lint
  typecheck:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm
      - run: npm ci
      - run: npm run typecheck
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm
      - run: npm ci
      - run: npm test
```

2. **Commit and push** — CI will run on the next push/PR update.

3. **Check for remote conflicts** before pushing:
   ```bash
   git fetch origin
   git log origin/<branch>..HEAD
   ```
   If the remote already has CI files (from another session), a rebase conflict may occur. In that case, prefer the remote's version.

**Pitfall:** Creating a CI file when the remote branch already has one (from a parallel session or earlier push) causes rebase conflicts. Always `git fetch` first.

## 5. Auto-Fixing CI Failures

When CI fails, diagnose and fix. This loop works with either auth method.

### Step 1: Get Failure Details

**With gh:**

```bash
# List recent workflow runs on this branch
gh run list --branch $(git branch --show-current) --limit 5

# View failed logs
gh run view <RUN_ID> --log-failed
```

**With git + curl:**

```bash
BRANCH=$(git branch --show-current)

# List workflow runs on this branch
curl -s \
  -H "Authorization: token $GITHUB_TOKEN" \
  "https://api.github.com/repos/$OWNER/$REPO/actions/runs?branch=$BRANCH&per_page=5" \
  | python3 -c "
import sys, json
runs = json.load(sys.stdin)['workflow_runs']
for r in runs:
    print(f\"Run {r['id']}: {r['name']} - {r['conclusion'] or r['status']}\")"

# Get failed job logs (download as zip, extract, read)
RUN_ID=<run_id>
curl -s -L \
  -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/repos/$OWNER/$REPO/actions/runs/$RUN_ID/logs \
  -o /tmp/ci-logs.zip
cd /tmp && unzip -o ci-logs.zip -d ci-logs && cat ci-logs/*.txt
```

### Step 2: Fix and Push

After identifying the issue, use file tools (`patch`, `write_file`) to fix it:

```bash
git add <fixed_files>
git commit -m "fix: resolve CI failure in <check_name>"
git push
```

### Step 3: Verify

Re-check CI status using the commands from Section 4 above.

### Auto-Fix Loop Pattern

When asked to auto-fix CI, follow this loop:

1. Check CI status → identify failures
2. Read failure logs → understand the error
3. Use `read_file` + `patch`/`write_file` → fix the code
4. `git add . && git commit -m "fix: ..." && git push`
5. Wait for CI → re-check status
6. Repeat if still failing (up to 3 attempts, then ask the user)

## 6. Merging

**With gh:**

```bash
# Squash merge + delete branch (cleanest for feature branches)
gh pr merge --squash --delete-branch

# Enable auto-merge (merges when all checks pass)
gh pr merge --auto --squash --delete-branch
```

**With git + curl:**

```bash
PR_NUMBER=<number>

# Merge the PR via API (squash)
curl -s -X PUT \
  -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/repos/$OWNER/$REPO/pulls/$PR_NUMBER/merge \
  -d "{
    \"merge_method\": \"squash\",
    \"commit_title\": \"feat: add user authentication (#$PR_NUMBER)\"
  }"

# Delete the remote branch after merge
BRANCH=$(git branch --show-current)
git push origin --delete $BRANCH

# Switch back to main locally
git checkout main && git pull origin main
git branch -d $BRANCH
```

Merge methods: `"merge"` (merge commit), `"squash"`, `"rebase"`

### Enable Auto-Merge (curl)

```bash
# Auto-merge requires the repo to have it enabled in settings.
# This uses the GraphQL API since REST doesn't support auto-merge.
PR_NODE_ID=$(curl -s \
  -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/repos/$OWNER/$REPO/pulls/$PR_NUMBER \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['node_id'])")

curl -s -X POST \
  -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/graphql \
  -d "{\"query\": \"mutation { enablePullRequestAutoMerge(input: {pullRequestId: \\\"$PR_NODE_ID\\\", mergeMethod: SQUASH}) { clientMutationId } }\"}"
```

## 7. Complete Workflow Example

```bash
# 1. Start from clean main
git checkout main && git pull origin main

# 2. Branch
git checkout -b fix/login-redirect-bug

# 3. (Agent makes code changes with file tools)

# 4. Commit
git add src/auth/login.py tests/test_login.py
git commit -m "fix: correct redirect URL after login

Preserves the ?next= parameter instead of always redirecting to /dashboard."

# 5. Push
git push -u origin HEAD

# 6. Create PR (picks gh or curl based on what's available)
# ... (see Section 3)

# 7. Monitor CI (see Section 4)

# 8. Merge when green (see Section 6)
```

## 8. Troubleshooting

### Push fails with "could not read Username"

```bash
# Symptom: git push fails with "could not read Username for 'https://github.com'"
# Cause: gh auth lost (common in Docker where ~/.config/gh/ does not persist)

# Diagnosis
echo "GH_TOKEN: ${GH_TOKEN:-not set}"
gh auth status

# Fix 1: If GH_TOKEN is set but gh is not configured
gh auth setup-git   # configures git to use gh as credential helper

# Fix 2: If GH_TOKEN is not set
export GH_TOKEN=<your-token>
gh auth login --with-token  # pipe token if needed
gh auth setup-git

# Fix 3: If token is set but gh CLI still not working
git remote set-url origin "https://${GH_TOKEN}@github.com/OWNER/REPO.git"
# ← Use only as last resort; exposes token in git remote output
```

**Prevention:** In Docker/container environments, `GH_TOKEN` as an environment variable is more reliable than `~/.config/gh/hosts.yml`, which gets wiped on container restart.

### Rebase conflict: remote has newer version of the same file

```bash
# Symptom: git pull --rebase fails with "CONFLICT (add/add)" or "CONFLICT (modify/delete)"
# Common cause: Another agent/session pushed to the same branch

# Option A: Keep remote version (theirs) and re-apply your changes on top
git checkout --ours <file>   # "ours" = remote version during rebase
git add <file>
git rebase --continue
# Then manually re-apply your intended changes

# Option B: Keep your version (yours) and force push
git checkout --theirs <file>  # "theirs" = local version during rebase
git add <file>
git rebase --continue
git push --force-with-lease   # safer than --force

# Option C: Abort and investigate
git rebase --abort
git log --oneline origin/<branch>..HEAD
git log --oneline HEAD..origin/<branch>
```

**Prevention:** Before starting work, always `git fetch origin` and check if the remote branch is ahead of local.

### package-lock.json Out of Sync

**Symptom:** `npm ci` fails with:
```
npm error `npm ci` can only install packages when your package.json and package-lock.json or npm-shrinkwrap.json are in sync.
npm error Missing: <package-name> from lock file
```

**Cause:** `package.json` was modified (e.g., prettier added) but `package-lock.json` was not regenerated.

**Fix:**
```bash
# Regenerate lock file without installing
npm install --package-lock-only

# Or full install if needed
npm install

# Commit the updated lock file
git add package-lock.json
git commit -m "chore: sync package-lock.json with package.json"
```

**Prevention:** When adding/removing dependencies, always commit both `package.json` and `package-lock.json` together.

### Prettier Format Mismatch (Local vs CI)

**Symptom:** Local `npx prettier --write .` passes, but CI `npm run format:check` fails with "Code style issues found in N files."

**Cause:** Prettier version or configuration differs between local and CI. CI installs exact versions from `package-lock.json`, while local may have a different version cached in `node_modules`. Also, files modified by other tools after the prettier run (e.g., by subagents or patch operations) may reintroduce formatting errors.

**Fix — Full cleanup:**
```bash
# 1. Regenerate lock file to ensure CI gets the same versions
npm install --package-lock-only

# 2. Re-install locally to match CI
rm -rf node_modules package-lock.json
npm install

# 3. Run prettier through the local installation
npx prettier --write .

# 4. Commit both node_modules changes (if any) and the formatting
git add -A
git commit -m "style: apply prettier formatting"
```

**Fix — When bulk run still leaves files unformatted:**
After `npx prettier --write .`, CI may still report some files as unformatted (often files modified by other tools after the prettier run). Check CI logs for the specific files:

```bash
# Check which files CI thinks are unformatted
gh run view <run-id> --log-failed | grep "warn\]"
# Example output:
# [warn] src/features/rules/services/rule-session-service.ts
# [warn] src/lib/ai/subagent/orchestrator.ts

# Fix only those specific files
npx prettier --write <file1> <file2>

# Commit as a follow-up
git add -A
git commit -m "style: fix remaining prettier formatting in N files"
```

**Prevention:**
1. Always run `npx prettier --write .` after `npm install` from a clean lock file
2. After running prettier, verify with `npm run format:check` before pushing
3. If subagents or other tools modify files after prettier, re-run prettier on the affected files before commit

**Diagnosis:**
```bash
# Check which files CI thinks are unformatted
gh run view <run-id> --job <job-id> --log | grep "warn\]"

# Fix only those specific files
npx prettier --write <file1> <file2>
```

### Secret Scan Failures from External Packages

**Symptom:** `gitleaks detect` reports leaks like:
```
WRN leaks found: 22
```

**Cause:** An external package or skill (e.g., `.agents/skills/notebooklm/`) was accidentally committed. These often contain test fixtures, cassettes, or example configs with mock credentials that look like real secrets to scanners.

**Fix:**
```bash
# 1. Add the directory to .gitignore
echo ".agents/skills/notebooklm/" >> .gitignore

# 2. Remove from git tracking (keep files locally)
git rm -r --cached .agents/skills/notebooklm/

# 3. Commit
git add .gitignore
git commit -m "chore: ignore external package directory

- .agents/skills/notebooklm/ contains test fixtures that trigger secret scans"
```

**Prevention:** Before creating a PR, check for large directories that shouldn't be tracked:
```bash
git diff --name-only main..HEAD | grep -E '^\.(agents|claude|next|venv)/'
```

**Note:** If the external package is intentionally needed, consider adding a `.gitleaksignore` file or updating the CI workflow to exclude the directory from scanning, rather than ignoring the entire package.

### CI Workflow File Already Exists on Remote

**Symptom:** You create `.github/workflows/ci.yml` locally, push, and get a rebase conflict because the remote branch already has a (more comprehensive) version.

```
CONFLICT (add/add): Merge conflict in .github/workflows/ci.yml
```

**Resolution:** Prefer the remote version:
```bash
git checkout --ours .github/workflows/ci.yml
git add .github/workflows/ci.yml
git rebase --continue
```

**Lesson:** Always `git fetch origin` and check `git log origin/<branch>..HEAD` before assuming the remote is unchanged. Another session or agent may have already pushed CI files.

## Useful PR Commands Reference

| Action | gh | git + curl |
|--------|-----|-----------|
| List my PRs | `gh pr list --author @me` | `curl -s -H "Authorization: token $GITHUB_TOKEN" "https://api.github.com/repos/$OWNER/$REPO/pulls?state=open"` |
| View PR diff | `gh pr diff` | `git diff main...HEAD` (local) or `curl -H "Accept: application/vnd.github.diff" ...` |
| Add comment | `gh pr comment N --body "..."` | `curl -X POST .../issues/N/comments -d '{"body":"..."}'` |
| Request review | `gh pr edit N --add-reviewer user` | `curl -X POST .../pulls/N/requested_reviewers -d '{"reviewers":["user"]}'` |
| Close PR | `gh pr close N` | `curl -X PATCH .../pulls/N -d '{"state":"closed"}'` |
| Check out someone's PR | `gh pr checkout N` | `git fetch origin pull/N/head:pr-N && git checkout pr-N` |
