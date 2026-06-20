# agent-loop

Evidence-backed autonomous development loop toolkit. This repo contains the files needed to run a deterministic agent-loop evaluator, capture machine evidence, optionally invoke a bounded LLM repair loop in CI, and stop with a human handoff instead of looping forever.

## What is included

- `hermes_cli/agent_loop_capture.py` — ledger init, command evidence, git snapshot, PR snapshot, repair status helpers.
- `hermes_cli/agent_loop_evaluator.py` — deterministic evaluator and hard gates.
- `hermes_cli/agent_loop_controller.py` — bounded repair controller with max attempts, repeated-failure stop, runtime limit, and handoff report.
- `hermes_cli/agent_loop_ledger_update.py` — deterministic semantic ledger updater for requirements/tasks/findings/claims.
- `hermes_cli/agent_loop_knowledge.py` — failure/pattern/decision/handoff knowledge capture so lessons accumulate as repo assets.
- `hermes_cli/agent_loop_pr_guard.py` — fail-closed guard that blocks AI PR merges when CI/checks are failing, pending, or missing.
- `scripts/*.py` — CLI wrappers for the above.
- `templates/evidence-ledger.json` — starter ledger.
- `templates/knowledge-entry.md` — reviewable knowledge entry template.
- `templates/pr-body-human-review-ja.md` — Japanese PR body focused on points humans must review.
- `docs/knowledge-asset-design.md` — design for converting failures and lessons into durable project knowledge.
- `docs/pr-human-review-ja.md` — Japanese PR review summary and CI merge-gate policy.
- `skills/software-development/agent-loop-evaluation/` — evidence ledger, deterministic evaluation, bounded repair, and handoff rules.
- `skills/software-development/subagent-driven-development/` — autonomous implementation loop: plan → subagent implementation → spec review → quality review → final verification.
- `skills/github/github-pr-workflow/` — branch → commit → draft PR → CI → AI review → merge/cleanup loop.
- `skills/github/github-issues/`, `github-code-review`, `github-auth`, `github-repo-management` — issue/PR/review/auth/repo operations used by the loop.
- `skills/autonomous-ai-agents/{codex,claude-code,opencode}/` — optional external coding-agent delegation backends.
- `.github/workflows/agent-loop.yml` — PR / workflow_dispatch / workflow_call CI gate.
- `tests/cli/` — core unit tests copied from Hermes Agent.

## Quick start

```bash
cd /path/to/your/repo
python -m pip install -e /home/yappa/dev/app/agent-loop

python /home/yappa/dev/app/agent-loop/scripts/ledger_init.py \
  --ledger evidence-ledger.json \
  --loop-run-id issue-123 \
  --repo "owner/repo" \
  --issue 123 \
  --branch "feature/issue-123" \
  --base-ref main \
  --required-check test \
  --required-check lint

python /home/yappa/dev/app/agent-loop/scripts/ledger_run.py \
  --ledger evidence-ledger.json \
  --check-id CHECK-test \
  --type test -- pytest

python /home/yappa/dev/app/agent-loop/scripts/ledger_git_snapshot.py --ledger evidence-ledger.json
python /home/yappa/dev/app/agent-loop/scripts/evaluate_agent_loop.py --record --trigger local evidence-ledger.json
```

## CI modes

### Evaluate-only gate

The workflow fails the PR if the deterministic evaluator returns `FAIL`. The LLM does not decide pass/fail.

### Bounded repair mode

Manual or reusable workflow runs can set `repair=true`. The controller:

1. evaluates the ledger,
2. builds a repair prompt from deterministic `repair_tasks`,
3. invokes one configured repair command,
4. re-evaluates,
5. stops on success or escalates to humans when any limit is reached.

Limits default to:

- `AGENT_LOOP_MAX_ATTEMPTS=3`
- `AGENT_LOOP_MAX_SAME_FAILURE_COUNT=2`
- `AGENT_LOOP_MAX_RUNTIME_MINUTES=30`

Set `AGENT_LOOP_REPAIR_COMMAND` to the command that should consume the generated prompt. The controller exposes:

- `HERMES_LEDGER_PATH`
- `HERMES_AGENT_LOOP_REPAIR_PROMPT_FILE`
- `HERMES_AGENT_LOOP_REPAIR_ATTEMPT`
- `HERMES_AGENT_LOOP_PHASE`

Example:

```bash
AGENT_LOOP_REPAIR_COMMAND='hermes chat -q "$(cat $HERMES_AGENT_LOOP_REPAIR_PROMPT_FILE)"' \
python scripts/agent_loop_controller.py evidence-ledger.json --comment-pr
```

If attempts are exhausted, the same failure repeats, runtime expires, permissions/secrets are missing, or the repair command is absent, the controller exits with escalation and writes `agent-loop-handoff.md`. In PR CI it can also comment the handoff on the PR when `gh` and `GH_TOKEN` are available.

## Japanese PR review summaries

AI-authored PRs should include a Japanese review summary that shows only the points humans must judge: problem/scope, architecture decisions, responsibility boundaries, test adequacy, high-risk diffs, and production/customer impact. Use:

```bash
cp templates/pr-body-human-review-ja.md /tmp/pr-body.md
gh pr create --draft --body-file /tmp/pr-body.md
```

Before any automated merge, run the fail-closed PR guard:

```bash
python scripts/pr_merge_guard.py <PR_NUMBER>
```

The guard blocks when the PR is Draft, checks are failing/pending/missing, GitHub reports `mergeable=false`, or optional review approval is required but missing. See `docs/pr-human-review-ja.md` for the full policy.

## Ledger updates

Apply structured annotations without trusting them as proof:

```bash
python scripts/ledger_update.py --ledger evidence-ledger.json --updates examples/semantic-updates.json
```

The updater marks semantic entries as annotation. Machine evidence still must come from wrappers/CI/tooling.

## Knowledge assets

Failures and durable lessons can be promoted into `.agent-loop/knowledge/` as Markdown files plus a small `index.json`. These knowledge assets are intentionally separate from evaluator evidence: they can guide future agents, but they cannot make the current run pass.

Record a human-authored lesson:

```bash
python scripts/knowledge_record.py \
  --repo-root . \
  --type pattern \
  --title "Authenticated Next.js pages require force-dynamic" \
  --summary "Pages that call getCurrentUser() must export dynamic = force-dynamic." \
  --prevention "Check new authenticated pages before pushing." \
  --tag nextjs --tag ci
```

Create a failure candidate from the latest ledger evaluation:

```bash
python scripts/knowledge_record.py --repo-root . --ledger evidence-ledger.json
```

See `docs/knowledge-asset-design.md` for promotion rules, storage layout, and the comment policy.

## Code comment policy

The orchestration code should be comment-rich where it matters. Add docstrings/comments that explain why a class or function exists, what authority it has, what failure mode it prevents, and what must not be trusted. Avoid comments that merely restate the next line of code.

## Hard rules

- AI self-report is not evidence.
- Required checks must be machine-captured with command, cwd, commit, exit code, stdout/stderr logs, and `source: machine`.
- Completion claims need evidence. Unsupported or contradicted completion claims fail.
- Fixed findings need recheck evidence.
- The repair controller is bounded and hands off to humans instead of infinite looping.
# agent-loop
# agent-loop
