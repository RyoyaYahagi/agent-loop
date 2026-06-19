---
name: github-auth
description: "GitHub auth setup: HTTPS tokens, SSH keys, gh CLI login."
version: 1.1.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [GitHub, Authentication, Git, gh-cli, SSH, Setup]
    related_skills: [github-pr-workflow, github-code-review, github-issues, github-repo-management]
---

# GitHub Authentication Setup

This skill sets up authentication so the agent can work with GitHub repositories, PRs, issues, and CI.

## Detection Flow

```bash
git --version
gh --version 2>/dev/null || echo "gh not installed"
gh auth status 2>/dev/null || echo "gh not authenticated"
git config --global credential.helper 2>/dev/null || echo "no git credential helper"
```

## Method 1: Git-Only Authentication (No gh, No sudo)

### Option A: HTTPS with Personal Access Token (Recommended)

Create a PAT at https://github.com/settings/tokens with scopes: `repo`, `workflow`, `read:org`.

```bash
git config --global credential.helper store
git ls-remote https://github.com/<user>/<repo>.git
# Enter username + PAT as password
```

Per-repo URL embedding (avoids prompts):
```bash
git remote set-url origin https://<user>:<token>@github.com/<owner>/<repo>.git
```

### Option B: SSH Key Authentication

```bash
ssh-keygen -t ed25519 -C "email@example.com" -f ~/.ssh/id_ed25519 -N ""
cat ~/.ssh/id_ed25519.pub  # Add to https://github.com/settings/keys
ssh -T git@github.com
git config --global url."git@github.com:".insteadOf "https://github.com/"
```

## Method 2: gh CLI Authentication

```bash
gh auth login                    # Interactive browser
# OR
echo "<token>" | gh auth login --with-token
gh auth setup-git
```

## Using the GitHub API Without gh

```bash
export GITHUB_TOKEN="<token>"
curl -s -H "Authorization: token $GITHUB_TOKEN" https://api.github.com/user
```

Extract from git credential store:
```bash
grep "github.com" ~/.git-credentials 2>/dev/null | head -1 | sed 's|https://[^:]*:\([^@]*\)@.*|\1|'
```

### Agent-Specific Credential Files

```bash
for path in /workspace/.config/agent/github.env ~/.config/agent/github.env /opt/agent/github.env; do
  [ -f "$path" ] && source "$path" && echo "Loaded from $path"
done
```

### Helper: Detect Auth Method

```bash
if command -v gh &>/dev/null && gh auth status &>/dev/null; then
  echo "AUTH_METHOD=gh"
elif [ -n "$GITHUB_TOKEN" ]; then
  echo "AUTH_METHOD=curl"
elif [ -f ~/.hermes/.env ] && grep -q "^GITHUB_TOKEN=" ~/.hermes/.env; then
  export GITHUB_TOKEN=$(grep "^GITHUB_TOKEN=" ~/.hermes/.env | head -1 | cut -d= -f2 | tr -d '\n\r')
  echo "AUTH_METHOD=curl"
elif grep -q "github.com" ~/.git-credentials 2>/dev/null; then
  export GITHUB_TOKEN=$(grep "github.com" ~/.git-credentials | head -1 | sed 's|https://[^:]*:\([^@]*\)@.*|\1|')
  echo "AUTH_METHOD=curl"
else
  echo "AUTH_METHOD=none"
fi
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `git push` asks for password | Use PAT as password, or switch to SSH |
| `remote: Permission to X denied` | Token lacks `repo` scope |
| `fatal: Authentication failed` | Stale credentials — `git credential reject` then re-auth |
| `ssh: connect to host github.com port 22: Connection refused` | Use `Port 443` + `Hostname ssh.github.com` in `~/.ssh/config` |
| Credentials not persisting | Check `credential.helper` is `store` or `cache` |
| `gh auth lost after restart` | Docker: use `GH_TOKEN` env var or mount `~/.config/gh` |

### Docker / Container Auth Persistence

In Docker, `~/.config/gh/hosts.yml` is ephemeral. Prefer `GH_TOKEN` env var.

```bash
if [ -f /.dockerenv ] && [ ! -f ~/.config/gh/hosts.yml ]; then
  echo "WARNING: Docker without ~/.config/gh mounted. Use GH_TOKEN env var."
fi
```
