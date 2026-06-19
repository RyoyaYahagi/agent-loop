---
name: github-issues
description: "Create, triage, label, assign GitHub issues via gh or REST."
version: 1.1.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
---

# GitHub Issues Management

Create, search, triage, and manage GitHub issues.

## Prerequisites

- Authenticated with GitHub (see `github-auth`)
- Inside a git repo with a GitHub remote, or specify repo explicitly

### Remote host alias pitfall

If origin uses a nonstandard SSH host alias (e.g. `git@github-hermes:owner/repo.git`), `gh` may fail to infer the repo. Pass `-R owner/repo` explicitly:
```bash
gh issue list -R OWNER/REPO --state open
```

## Viewing Issues

```bash
gh issue list
gh issue list --state open --label "bug"
gh issue view 42
```

curl fallback:
```bash
curl -s -H "Authorization: token $GITHUB_TOKEN" \
  "https://api.github.com/repos/$OWNER/$REPO/issues?state=open&per_page=20"
```

## Creating Issues

```bash
gh issue create --title "..." --body "..." --label "bug,backend" --assignee "username"
```

### Bug Report Template
```
## Bug Description
<What's happening>

## Steps to Reproduce
1. <step>
2. <step>

## Expected Behavior
<What should happen>

## Actual Behavior
<What actually happens>

## Environment
- OS: <os>
- Version: <version>
```

### Feature Request Template
```
## Feature Description
<What you want>

## Motivation
<Why this would be useful>

## Proposed Solution
<How it could work>

## Alternatives Considered
<Other approaches>
```

## Managing Issues

| Action | gh | curl endpoint |
|--------|-----|--------------|
| Add labels | `gh issue edit N --add-label ...` | `POST /repos/{o}/{r}/issues/N/labels` |
| Assign | `gh issue edit N --add-assignee ...` | `POST /repos/{o}/{r}/issues/N/assignees` |
| Comment | `gh issue comment N --body ...` | `POST /repos/{o}/{r}/issues/N/comments` |
| Close | `gh issue close N` | `PATCH /repos/{o}/{r}/issues/N` |
| Search | `gh issue list --search "..."` | `GET /search/issues?q=...` |

## Issue Triage Workflow

1. **List untriaged:** `gh issue list --label "needs-triage" --state open`
2. **Read and categorize** each issue
3. **Apply labels and priority**
4. **Assign** if owner is clear
5. **Comment with triage notes**

## Implementation Priority

**Default:** issue number ascending (smallest first).

- Filter out `Backlog Later` unless explicitly requested
- Unlabeled issues are NOT automatically low priority — read the body
- Confirm with user if priority seems unusual

### Decision Tree
```
Open issues without "Backlog Later"?
  ├── Yes → Pick smallest issue number → Read body → Start implementation
  └── No  → User wants "Backlog Later" issues?
               ├── Yes → Pick smallest among those
               └── No  → Ask user what to work on next
```

## Bulk Operations

```bash
# Close all issues with a specific label
gh issue list --label "wontfix" --json number --jq '.[].number' | \
  xargs -I {} gh issue close {} --reason "not planned"
```

## Linking Issues to PRs

Issues auto-close when a PR merges with keywords in the body:
```
Closes #42
Fixes #42
Resolves #42
```

Create branch from issue:
```bash
gh issue develop 42 --checkout
```
