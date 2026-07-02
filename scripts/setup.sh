#!/usr/bin/env bash
#
# agent-loop machine-level setup.
#
# Installs the agent-loop CLI (the `agent-loop-*` commands) onto this machine
# once, using uv. After this, you operate on any repository by changing into it
# and running the commands — no per-repo install is needed.
#
# Scope is intentionally minimal: this script installs the toolkit and *checks*
# prerequisites (git, gh, GitHub auth), warning if they are missing. It does NOT
# auto-install git, gh, or any repair backend (hermes/claude/codex/opencode).
#
# Usage:
#   ./scripts/setup.sh                 # install/upgrade the CLI, check prereqs
#   ./scripts/setup.sh --upgrade       # force reinstall to pick up local changes
#   ./scripts/setup.sh --bootstrap-uv  # install uv first if it is missing
#   ./scripts/setup.sh --dev           # editable venv install for contributors/CI
#   ./scripts/setup.sh -h | --help
#
# Exit codes:
#   0  success (missing prereqs only WARN, they do not fail setup)
#   1  uv is missing and --bootstrap-uv was not given
#   2  the toolkit install failed
#   3  usage error

set -euo pipefail

# Resolve the repo root from this script's location — never hardcode a path,
# so the script works wherever the repo is cloned, on any machine.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

BOOTSTRAP_UV=0
UPGRADE=0
DEV=0

info()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
ok()    { printf '\033[1;32m  ✓\033[0m %s\n' "$*"; }
warn()  { printf '\033[1;33m  ⚠\033[0m %s\n' "$*" >&2; }
die()   { printf '\033[1;31m  ✗\033[0m %s\n' "$*" >&2; exit "${2:-2}"; }

usage() {
    sed -n '2,30p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

while [ $# -gt 0 ]; do
    case "$1" in
        --bootstrap-uv) BOOTSTRAP_UV=1 ;;
        --upgrade)      UPGRADE=1 ;;
        --dev)          DEV=1 ;;
        -h|--help)      usage; exit 0 ;;
        *) printf 'Unknown argument: %s\n\n' "$1" >&2; usage; exit 3 ;;
    esac
    shift
done

# --- 1. Ensure uv ----------------------------------------------------------

ensure_uv() {
    if command -v uv >/dev/null 2>&1; then
        ok "uv found ($(uv --version))"
        return
    fi
    if [ "$BOOTSTRAP_UV" -eq 1 ]; then
        info "Installing uv via the official installer…"
        curl -LsSf https://astral.sh/uv/install.sh | sh
        # The installer drops uv in ~/.local/bin; make it visible for this run.
        export PATH="$HOME/.local/bin:$PATH"
        command -v uv >/dev/null 2>&1 || die "uv install ran but uv is still not on PATH"
        ok "uv installed ($(uv --version))"
    else
        die "uv is not installed. Install it (https://docs.astral.sh/uv/) or re-run with --bootstrap-uv" 1
    fi
}

# --- 2. Install the toolkit ------------------------------------------------

install_dev() {
    info "Dev install: creating .venv and installing editable with test deps…"
    ( cd "$REPO_ROOT" && uv venv && uv pip install -e ".[test]" )
    ok "Dev environment ready at $REPO_ROOT/.venv"
    info "Activate it with:  source \"$REPO_ROOT/.venv/bin/activate\""
}

install_tool() {
    local args=(tool install --from "$REPO_ROOT" agent-loop)
    [ "$UPGRADE" -eq 1 ] && args+=(--reinstall)
    info "Installing agent-loop CLI with uv tool install…"
    uv "${args[@]}" || die "uv tool install failed" 2
    ok "agent-loop CLI installed"
}

# --- 3. Prerequisite checks (warn only) ------------------------------------

check_prereqs() {
    info "Checking prerequisites (warnings do not block setup)…"

    if command -v git >/dev/null 2>&1; then
        ok "git found ($(git --version | head -1))"
    else
        warn "git not found — required for ledger snapshots and PR workflows."
    fi

    if command -v gh >/dev/null 2>&1; then
        ok "gh found ($(gh --version | head -1))"
    else
        warn "gh (GitHub CLI) not found — required for PR guard / repair-merge. See https://cli.github.com/"
    fi

    # Reuse the existing auth-detection helper instead of duplicating its logic.
    local gh_env="$REPO_ROOT/skills/github/github-auth/scripts/gh-env.sh"
    if [ -f "$gh_env" ]; then
        # shellcheck disable=SC1090
        if source "$gh_env" >/dev/null 2>&1 && [ "${GH_AUTH_METHOD:-none}" != "none" ]; then
            ok "GitHub auth detected (method: ${GH_AUTH_METHOD})"
        else
            warn "No GitHub auth detected — run 'gh auth login' or set GITHUB_TOKEN before using PR features."
        fi
    fi
}

# --- 4. PATH + smoke test --------------------------------------------------

check_path_and_smoke() {
    local bin_dir
    bin_dir="$(uv tool dir --bin 2>/dev/null || true)"
    if [ -n "$bin_dir" ] && ! printf '%s' ":$PATH:" | grep -q ":$bin_dir:"; then
        warn "uv tool bin dir is not on PATH: $bin_dir"
        warn "Add it (e.g. in ~/.bashrc):  export PATH=\"$bin_dir:\$PATH\"   — or run: uv tool update-shell"
    fi

    if command -v agent-loop-evaluate >/dev/null 2>&1; then
        agent-loop-evaluate --help >/dev/null 2>&1 \
            && ok "Smoke test passed: agent-loop-evaluate is runnable" \
            || warn "agent-loop-evaluate is on PATH but --help failed"
    else
        warn "agent-loop-evaluate not yet on PATH (open a new shell, or fix PATH as above)"
    fi
}

# --- main ------------------------------------------------------------------

ensure_uv

if [ "$DEV" -eq 1 ]; then
    install_dev
    check_prereqs
    info "Done (dev mode)."
    exit 0
fi

install_tool
check_prereqs
check_path_and_smoke

cat <<EOF

$(printf '\033[1;32mSetup complete.\033[0m')

Per-repo usage — run inside any repository you want to evaluate:

  cd /path/to/your/repo
  agent-loop-ledger-init --ledger evidence-ledger.json \\
    --loop-run-id issue-123 --repo "owner/repo" --branch "feature/x" --base-ref main \\
    --required-check test
  agent-loop-ledger-run --ledger evidence-ledger.json --check-id CHECK-test --type test -- pytest
  agent-loop-evaluate --record --trigger local evidence-ledger.json

Add 'evidence-ledger.json' and '.agent-loop/' to that repo's .gitignore if you
do not want to commit run state.
EOF
