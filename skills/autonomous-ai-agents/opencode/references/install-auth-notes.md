# OpenCode CLI Installation & Auth Notes

## Project Status
- The original `opencode-ai/opencode` repository is **archived** and development moved to [Crush](https://github.com/charmbracelet/crush) by the Charm team.
- However, the install script and npm package (`opencode-ai`) remain functional as of 2025-06.

## Installation Paths

### Install Script (Preferred)
```bash
curl -fsSL https://raw.githubusercontent.com/opencode-ai/opencode/refs/heads/main/install | bash
```
- Installs binary to: `~/.opencode/bin/opencode`
- May not add to PATH automatically; add `export PATH="$PATH:$HOME/.opencode/bin"` to shell profile if needed.

### npm
```bash
npm i -g opencode-ai@latest
```
- Installs both a Node wrapper and platform-specific native binaries under the npm tree.
- The wrapper binary is typically at the npm global bin path.

## Auth in v0.0.55+

Older versions used `opencode auth login` and `opencode auth list`. These commands are **no longer present** in v0.0.55.

**Current auth mechanism:**
- Set provider environment variables (`OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY`, etc.).
- OpenCode reads these at runtime; there is no persistent credential store.
- The `~/.opencode.json` file is created automatically on first run and stores UI preferences, not API keys.

**Go Plan / TUI connection:**
- Some OpenCode plans (e.g., goプラン) require authentication via the TUI using `/connect`.
- `opencode login` and `opencode auth` return `unknown command` in v0.0.55.
- To connect: run `opencode` interactively (`pty=true`), then send `/connect` via `process(action="submit")`.
- The exact connection token or credentials for `/connect` are plan-specific and must be obtained from the provider.

**Error:** `agent coder not found`
- This means no valid provider credentials were found.
- Fix: export the relevant `*_API_KEY` env var and retry, or use the TUI `/connect` flow for plan-based auth.

## Smoke Test
```bash
opencode run 'Respond with exactly: OPENCODE_SMOKE_OK'
```
Expected: output contains `OPENCODE_SMOKE_OK` with no provider errors.
